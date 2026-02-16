import json
import os
import re
import time
from typing import Dict, Any, List, Optional

from openai import OpenAI

from core.models import CaseSession
from .schemas import DiagnosisPayload, TriageLevel
from .prompts import SYSTEM_PROMPT, build_user_prompt


class DiagnosisService:
    RED_FLAG_MAP = {
        "brake failed": "Possible brake failure reported.",
        "can't stop": "Vehicle may not stop safely.",
        "cannot stop": "Vehicle may not stop safely.",
        "burning smell": "Possible overheating or electrical/fire risk.",
        "smoke": "Smoke detected, possible fire/mechanical hazard.",
        "engine overheating": "Engine overheating can cause severe damage.",
        "temperature red": "Engine temperature in red zone.",
        "fuel leak": "Possible fuel leak and fire risk.",
        "steering locked": "Steering control issue may be dangerous.",
        "check engine blinking": "Flashing check-engine may indicate severe misfire.",
    }

    FORBIDDEN_ACTION_KEYWORDS = [
        "disassemble brakes",
        "open fuel line",
        "bypass",
        "disable airbag",
        "high-voltage battery",
        "remove brake caliper",
        "bleed brakes yourself",
    ]

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None

    def generate(self, case: CaseSession, user_message: str, rag_context: str = "") -> Dict[str, Any]:
        start = time.perf_counter()

        vehicle_text = self._vehicle_text(case)
        case_history_text = self._case_history_text(case)
        rag_context_for_prompt = self._prepare_rag_context_for_prompt(rag_context)

        if not self.client:
            fallback = self._fallback_payload("API key missing")
            return self._finalize_result(
                fallback,
                user_message,
                start,
                model_name="rule_based_fallback",
                tokens_in=None,
                tokens_out=None,
            )

        try:
            user_prompt = build_user_prompt(
                vehicle_text=vehicle_text,
                latest_user_message=user_message,
                case_history_text=case_history_text,
                rag_context=rag_context_for_prompt,
            )

            completion = self.client.chat.completions.create(
                model=self.model,
                temperature=0.2,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )

            raw = completion.choices[0].message.content or "{}"
            payload = self._parse_payload(raw)

            tokens_in = getattr(completion.usage, "prompt_tokens", None)
            tokens_out = getattr(completion.usage, "completion_tokens", None)

            return self._finalize_result(
                payload,
                user_message=user_message,
                start_time=start,
                model_name=self.model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            )
        except Exception:
            fallback = self._fallback_payload("LLM generation error")
            return self._finalize_result(
                fallback,
                user_message,
                start,
                model_name="rule_based_fallback",
                tokens_in=None,
                tokens_out=None,
            )

    def _prepare_rag_context_for_prompt(self, rag_context: str) -> str:
        """
        Ensures prompt always has a deterministic knowledge block:
        - If docs/snippets exist => include them (bounded size)
        - If none => explicitly say 'none' and continue normal diagnosis
        """
        clean = (rag_context or "").strip()
        if clean:
            return (
                "Retrieved knowledge context (use only if relevant and do not hallucinate):\n"
                f"{clean[:7000]}"
            )
        return (
            "Retrieved knowledge context: none.\n"
            "Proceed with normal safe troubleshooting based on vehicle profile and user symptoms."
        )

    def _parse_payload(self, raw: str) -> DiagnosisPayload:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
            if not match:
                raise
            data = json.loads(match.group(0))
        return DiagnosisPayload.model_validate(data)

    def _finalize_result(
        self,
        payload: DiagnosisPayload,
        user_message: str,
        start_time: float,
        model_name: str,
        tokens_in: Optional[int],
        tokens_out: Optional[int],
    ) -> Dict[str, Any]:
        # deterministic safety override
        override_reason = self._keyword_risk_override(user_message)
        if override_reason:
            payload.triage_level = TriageLevel.RED
            if override_reason not in payload.stop_driving_reasons:
                payload.stop_driving_reasons.insert(0, override_reason)
            payload.recommended_actions = [
                "Do not continue driving.",
                "Park in a safe place away from traffic.",
                "Contact roadside assistance or a certified mechanic immediately.",
            ]

        # sanitize potentially unsafe actions
        payload.recommended_actions = self._sanitize_actions(payload.recommended_actions)

        assistant_reply = self._render_reply(payload)
        latency_ms = int((time.perf_counter() - start_time) * 1000)

        return {
            "assistant_reply": assistant_reply,
            "triage_level": payload.triage_level.value,
            "confidence": float(payload.confidence),
            "likely_causes": payload.likely_causes,
            "recommended_actions": payload.recommended_actions,
            "stop_driving_reasons": payload.stop_driving_reasons,
            "follow_up_questions": payload.follow_up_questions,
            "model_name": model_name,
            "latency_ms": latency_ms,
            "tokens_input": tokens_in,
            "tokens_output": tokens_out,
        }

    def _keyword_risk_override(self, text: str) -> Optional[str]:
        msg = (text or "").lower()
        for kw, reason in self.RED_FLAG_MAP.items():
            if kw in msg:
                return reason
        return None

    def _sanitize_actions(self, actions: List[str]) -> List[str]:
        safe_actions = []
        for a in actions:
            low = a.lower()
            if any(bad in low for bad in self.FORBIDDEN_ACTION_KEYWORDS):
                safe_actions.append("Have a certified mechanic inspect this safely.")
            else:
                safe_actions.append(a)
        return safe_actions[:8]

    def _vehicle_text(self, case: CaseSession) -> str:
        v = case.vehicle
        return (
            f"Make: {v.make}, Model: {v.model}, Year: {v.year}, "
            f"Engine CC: {v.engine_cc or 'unknown'}, Transmission: {v.transmission}, "
            f"Fuel: {v.fuel_type}, Mileage KM: {v.mileage_km or 'unknown'}"
        )

    def _case_history_text(self, case: CaseSession, limit: int = 6) -> str:
        recent = list(case.symptoms.order_by("-created_at")[:limit])
        if not recent:
            return "No previous symptom reports."
        recent.reverse()
        lines = [f"- [{s.source}] {s.raw_text}" for s in recent]
        return "\n".join(lines)

    def _render_reply(self, p: DiagnosisPayload) -> str:
        lines = []
        lines.append(f"Assessment: {p.summary}")
        lines.append(f"Triage level: {p.triage_level.value.upper()} (confidence {p.confidence:.2f})")

        if p.likely_causes:
            lines.append("Likely causes:")
            lines.extend([f"- {x}" for x in p.likely_causes[:5]])

        if p.recommended_actions:
            lines.append("Recommended safe actions:")
            lines.extend([f"- {x}" for x in p.recommended_actions[:6]])

        if p.stop_driving_reasons:
            lines.append("Stop driving reasons:")
            lines.extend([f"- {x}" for x in p.stop_driving_reasons[:4]])

        if p.follow_up_questions:
            lines.append("Follow-up questions:")
            lines.extend([f"- {x}" for x in p.follow_up_questions[:5]])

        lines.append("Note: This is informational guidance, not a substitute for a certified mechanic.")
        return "\n".join(lines)

    def _fallback_payload(self, reason: str) -> DiagnosisPayload:
        return DiagnosisPayload(
            summary=f"Initial safe assessment generated by fallback mode ({reason}).",
            triage_level=TriageLevel.YELLOW,
            confidence=0.35,
            likely_causes=["Insufficient data for precise diagnosis yet."],
            recommended_actions=[
                "Avoid long/high-speed driving until inspected.",
                "Check dashboard warning lights and note exact behavior.",
                "Book a certified mechanic inspection soon.",
            ],
            stop_driving_reasons=[],
            follow_up_questions=[
                "When did the issue start?",
                "Any dashboard warning lights currently on?",
                "Does the problem get worse with speed, braking, or AC?",
            ],
        )


diagnosis_service = DiagnosisService()
