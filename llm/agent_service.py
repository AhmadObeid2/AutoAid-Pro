from typing import Any, Dict, List, Optional

from core.models import CaseSession, DiagnosisResult
from .agent_tools import save_case_note, create_action_checklist, escalate_case, resolve_case


class CaseAgentService:
    RESOLVED_KEYWORDS = [
        "resolved", "fixed", "problem solved", "issue solved", "works now", "it is fine now"
    ]

    def run(
        self,
        case: CaseSession,
        latest_diagnosis: Optional[DiagnosisResult],
        user_message: str = "",
        assistant_reply: str = "",
        force_action: str = "auto",
        resolution_summary: str = "",
    ) -> Dict[str, Any]:
        executed_actions: List[Dict[str, Any]] = []
        reason_trace: List[str] = []

        msg = (user_message or "").lower().strip()
        force_action = (force_action or "auto").strip().lower()

        # Always save an agent note from assistant reply (if provided)
        if assistant_reply.strip():
            out = save_case_note(
                case=case,
                note_text=assistant_reply[:3000],
                tags=["assistant_reply", "auto_log"],
            )
            executed_actions.append({"tool": "save_case_note", **out})
            reason_trace.append("Saved assistant reply as agent note.")

        # Forced actions (manual override from frontend/admin)
        if force_action == "escalate":
            reasons = []
            if latest_diagnosis:
                reasons = (latest_diagnosis.stop_driving_reasons or [])[:5]
            out = escalate_case(case=case, reasons=reasons or ["Manual escalation requested."])
            executed_actions.append({"tool": "escalate_case", **out})
            reason_trace.append("Force action: escalate.")
            return self._result(case, executed_actions, reason_trace)

        if force_action == "resolve":
            summary = resolution_summary or "Manually resolved by operator."
            out = resolve_case(case=case, resolution_summary=summary)
            executed_actions.append({"tool": "resolve_case", **out})
            reason_trace.append("Force action: resolve.")
            return self._result(case, executed_actions, reason_trace)

        if force_action == "checklist":
            out = create_action_checklist(case=case, diagnosis=latest_diagnosis)
            executed_actions.append({"tool": "create_action_checklist", **out})
            reason_trace.append("Force action: checklist.")
            return self._result(case, executed_actions, reason_trace)

        # AUTO mode policy
        is_red = bool(latest_diagnosis and latest_diagnosis.triage_level == CaseSession.RiskLevel.RED)
        has_stop_reasons = bool(latest_diagnosis and (latest_diagnosis.stop_driving_reasons or []))
        user_reports_resolved = any(k in msg for k in self.RESOLVED_KEYWORDS)

        if is_red or has_stop_reasons:
            reasons = (latest_diagnosis.stop_driving_reasons or [])[:5] if latest_diagnosis else []
            out = escalate_case(case=case, reasons=reasons or ["RED triage auto-escalation"])
            executed_actions.append({"tool": "escalate_case", **out})
            reason_trace.append("Auto policy escalated due to RED/high-risk signal.")
            return self._result(case, executed_actions, reason_trace)

        if user_reports_resolved and case.status != CaseSession.Status.ESCALATED:
            summary = resolution_summary or "User indicated issue is resolved."
            out = resolve_case(case=case, resolution_summary=summary)
            executed_actions.append({"tool": "resolve_case", **out})
            reason_trace.append("Auto policy resolved case based on user message.")
            return self._result(case, executed_actions, reason_trace)

        out = create_action_checklist(case=case, diagnosis=latest_diagnosis)
        executed_actions.append({"tool": "create_action_checklist", **out})
        reason_trace.append("Auto policy generated checklist for next steps.")

        return self._result(case, executed_actions, reason_trace)

    def _result(self, case: CaseSession, actions: List[Dict[str, Any]], trace: List[str]) -> Dict[str, Any]:
        return {
            "case_id": str(case.id),
            "case_status": case.status,
            "risk_level": case.current_risk_level,
            "executed_actions": actions,
            "reason_trace": trace,
        }


case_agent_service = CaseAgentService()
