from typing import Any, Dict, List, Optional
from django.utils import timezone

from core.models import CaseSession, CaseNote, CaseAction, DiagnosisResult


def _record_action(
    case: CaseSession,
    action_type: str,
    status: str = CaseAction.Status.EXECUTED,
    reason: str = "",
    input_payload: Optional[Dict[str, Any]] = None,
    output_payload: Optional[Dict[str, Any]] = None,
) -> CaseAction:
    return CaseAction.objects.create(
        case=case,
        action_type=action_type,
        status=status,
        reason=reason[:300],
        input_payload=input_payload or {},
        output_payload=output_payload or {},
    )


def save_case_note(case: CaseSession, note_text: str, tags: Optional[List[str]] = None, source: str = CaseNote.Source.AGENT):
    note = CaseNote.objects.create(
        case=case,
        source=source,
        note_text=(note_text or "").strip(),
        tags=tags or [],
    )
    action = _record_action(
        case=case,
        action_type=CaseAction.ActionType.SAVE_NOTE,
        reason="Agent saved a case note.",
        input_payload={"tags": tags or [], "source": source},
        output_payload={"note_id": str(note.id)},
    )
    return {"note_id": str(note.id), "action_id": str(action.id)}


def create_action_checklist(case: CaseSession, diagnosis: Optional[DiagnosisResult]):
    checklist = {
        "immediate": [],
        "soon": [],
        "monitor": [],
    }

    if diagnosis:
        # RED => immediate escalation checklist
        if diagnosis.triage_level == CaseSession.RiskLevel.RED:
            checklist["immediate"].extend([
                "Do not continue driving.",
                "Park in a safe location.",
                "Contact roadside assistance or certified mechanic.",
            ])
            for reason in (diagnosis.stop_driving_reasons or [])[:4]:
                checklist["immediate"].append(f"Reason: {reason}")

        # Recommended actions from diagnosis
        for item in (diagnosis.recommended_actions or [])[:8]:
            text = str(item).strip()
            if not text:
                continue
            if diagnosis.triage_level == CaseSession.RiskLevel.YELLOW:
                checklist["soon"].append(text)
            elif diagnosis.triage_level == CaseSession.RiskLevel.GREEN:
                checklist["monitor"].append(text)
            else:
                checklist["soon"].append(text)

    # Deduplicate, keep short
    for k in checklist:
        seen = set()
        deduped = []
        for x in checklist[k]:
            if x not in seen:
                seen.add(x)
                deduped.append(x)
        checklist[k] = deduped[:10]

    # Store in case metadata
    meta = case.metadata or {}
    meta["latest_checklist"] = checklist
    meta["latest_checklist_at"] = timezone.now().isoformat()
    case.metadata = meta
    case.save(update_fields=["metadata", "last_activity_at"])

    action = _record_action(
        case=case,
        action_type=CaseAction.ActionType.CREATE_CHECKLIST,
        reason="Agent generated action checklist.",
        input_payload={"diagnosis_id": str(diagnosis.id) if diagnosis else None},
        output_payload={"checklist": checklist},
    )
    return {"checklist": checklist, "action_id": str(action.id)}


def escalate_case(case: CaseSession, reasons: Optional[List[str]] = None):
    reasons = reasons or ["High risk triage from diagnostic workflow."]
    case.status = CaseSession.Status.ESCALATED
    case.current_risk_level = CaseSession.RiskLevel.RED
    case.save(update_fields=["status", "current_risk_level", "last_activity_at"])

    action = _record_action(
        case=case,
        action_type=CaseAction.ActionType.ESCALATE_CASE,
        reason="Case escalated by agent.",
        input_payload={"reasons": reasons},
        output_payload={"status": case.status, "risk": case.current_risk_level},
    )
    return {"escalated": True, "reasons": reasons, "action_id": str(action.id)}


def resolve_case(case: CaseSession, resolution_summary: str):
    case.status = CaseSession.Status.RESOLVED
    case.final_summary = (resolution_summary or "").strip()[:2000]
    case.closed_at = timezone.now()
    case.save(update_fields=["status", "final_summary", "closed_at", "last_activity_at"])

    action = _record_action(
        case=case,
        action_type=CaseAction.ActionType.RESOLVE_CASE,
        reason="Case resolved by agent.",
        input_payload={"resolution_summary": resolution_summary},
        output_payload={"status": case.status, "closed_at": case.closed_at.isoformat()},
    )
    return {"resolved": True, "action_id": str(action.id)}
