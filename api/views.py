import django
from django.shortcuts import get_object_or_404

from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from drf_spectacular.utils import extend_schema, OpenApiParameter

from core.models import VehicleProfile, CaseSession, SymptomReport, DiagnosisResult
from llm.service import diagnosis_service
from llm.agent_service import case_agent_service
from rag.service import rag_service

from .serializers import (
    HealthResponseSerializer,
    VehicleCreateSerializer,
    VehicleSerializer,
    CaseCreateSerializer,
    CaseSnapshotSerializer,
    SymptomCreateSerializer,
    SymptomReportSerializer,
    ChatRequestSerializer,
    ChatResponseSerializer,
    AgentRunRequestSerializer,
    AgentRunResponseSerializer,
    CaseActionSerializer,
    CaseNoteSerializer,
)


@extend_schema(responses={200: HealthResponseSerializer})
@api_view(["GET"])
def health_check(request):
    return Response({
        "status": "ok",
        "service": "autoaid-pro",
        "django_version": django.get_version(),
    })


@extend_schema(
    request=VehicleCreateSerializer,
    responses={201: VehicleSerializer},
)
@api_view(["POST"])
def create_vehicle(request):
    serializer = VehicleCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    vehicle = serializer.save()
    return Response(VehicleSerializer(vehicle).data, status=status.HTTP_201_CREATED)


@extend_schema(
    responses={200: VehicleSerializer},
)
@api_view(["GET"])
def get_vehicle(request, vehicle_id):
    vehicle = get_object_or_404(VehicleProfile, id=vehicle_id)
    return Response(VehicleSerializer(vehicle).data)


@extend_schema(
    request=CaseCreateSerializer,
    responses={201: CaseSnapshotSerializer},
)
@api_view(["POST"])
def create_case(request):
    serializer = CaseCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    case = serializer.save()
    return Response(CaseSnapshotSerializer(case).data, status=status.HTTP_201_CREATED)


@extend_schema(
    parameters=[
        OpenApiParameter(
            name="case_id",
            type=str,
            location=OpenApiParameter.PATH,
            required=True,
        )
    ],
    request=SymptomCreateSerializer,
    responses={201: SymptomReportSerializer},
)
@api_view(["POST"])
def add_symptom(request, case_id):
    case = get_object_or_404(CaseSession, id=case_id)
    serializer = SymptomCreateSerializer(data=request.data, context={"case": case})
    serializer.is_valid(raise_exception=True)
    symptom = serializer.save()

    # update case latest message if user input
    if symptom.source == "user":
        case.latest_user_message = symptom.raw_text
        case.save(update_fields=["latest_user_message", "last_activity_at"])

    return Response(SymptomReportSerializer(symptom).data, status=status.HTTP_201_CREATED)


@extend_schema(
    parameters=[
        OpenApiParameter(
            name="case_id",
            type=str,
            location=OpenApiParameter.PATH,
            required=True,
        )
    ],
    responses={200: CaseSnapshotSerializer},
)
@api_view(["GET"])
def get_case_snapshot(request, case_id):
    case = get_object_or_404(CaseSession, id=case_id)
    return Response(CaseSnapshotSerializer(case).data)


@extend_schema(
    request=ChatRequestSerializer,
    responses={200: ChatResponseSerializer},
)
@api_view(["POST"])
def chat_case(request):
    serializer = ChatRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    case_id = serializer.validated_data["case_id"]
    user_message = serializer.validated_data["message"].strip()
    case = get_object_or_404(CaseSession, id=case_id)

    # Save user turn
    SymptomReport.objects.create(
        case=case,
        source=SymptomReport.Source.USER,
        raw_text=user_message,
    )

    # Retrieve knowledge context (Mini-RAG) with graceful fallback:
    # if no docs / retrieval issue => continue normal LLM flow.
    rag_context = ""
    citations = []
    retrieval_mode = "keyword"
    try:
        retrieval_out = rag_service.retrieve(query_text=user_message, case=case, top_k=5)
        rag_context = (retrieval_out.get("context_text") or "").strip()
        citations = retrieval_out.get("citations") or []
        retrieval_mode = retrieval_out.get("retrieval_mode") or "keyword"
    except Exception:
        rag_context = ""
        citations = []
        retrieval_mode = "keyword"

    # LLM + safety orchestration with optional retrieved context
    result = diagnosis_service.generate(
        case=case,
        user_message=user_message,
        rag_context=rag_context,
    )

    # Controlled follow-up policy:
    # - max 2 rounds per case
    # - at most 1 follow-up question per turn (keeps chat concise)
    meta = case.metadata or {}
    asked_followup_rounds = int(meta.get("asked_followup_rounds", 0) or 0)
    max_followup_rounds = 2

    followups = result.get("follow_up_questions") or []
    if asked_followup_rounds >= max_followup_rounds:
        followups = []
    else:
        followups = followups[:1]
        if followups:
            asked_followup_rounds += 1

    result["follow_up_questions"] = followups
    meta["asked_followup_rounds"] = asked_followup_rounds
    meta["max_followup_rounds"] = max_followup_rounds
    meta["last_retrieval_mode"] = retrieval_mode
    meta["last_citations_count"] = len(citations)
    case.metadata = meta

    assistant_reply = result["assistant_reply"]
    if citations:
        src_lines = ["Sources used:"]
        for c in citations[:5]:
            src_lines.append(f"[{c['rank']}] {c['title']} (chunk {c['chunk_index']})")
        assistant_reply = f"{assistant_reply}\n\n" + "\n".join(src_lines)

    latest = case.diagnoses.order_by("-version").first()
    next_version = 1 if not latest else latest.version + 1

    # IMPORTANT: keep reference for agent
    diagnosis_obj = DiagnosisResult.objects.create(
        case=case,
        version=next_version,
        triage_level=result["triage_level"],
        confidence_score=result["confidence"],
        likely_causes=result["likely_causes"],
        recommended_actions=result["recommended_actions"],
        stop_driving_reasons=result["stop_driving_reasons"],
        model_name=result["model_name"],
        latency_ms=result["latency_ms"],
        tokens_input=result["tokens_input"],
        tokens_output=result["tokens_output"],
        disclaimer_shown=True,
    )

    # Save assistant turn
    SymptomReport.objects.create(
        case=case,
        source=SymptomReport.Source.ASSISTANT,
        raw_text=assistant_reply,
        normalized_symptoms=result["follow_up_questions"],
        observed_signals={
            "triage_level": result["triage_level"],
            "citations_count": len(citations),
            "retrieval_mode": retrieval_mode,
        },
    )

    # Baseline case status update first
    case.latest_user_message = user_message
    case.current_risk_level = result["triage_level"]

    if result["triage_level"] == CaseSession.RiskLevel.RED:
        case.status = CaseSession.Status.ESCALATED
    elif result["follow_up_questions"]:
        case.status = CaseSession.Status.NEEDS_FOLLOWUP
    else:
        case.status = CaseSession.Status.RESOLVED

    case.save(
        update_fields=[
            "latest_user_message",
            "current_risk_level",
            "status",
            "last_activity_at",
            "metadata",
        ]
    )

    # Run agent AFTER baseline save so agent can override status if needed
    agent_out = case_agent_service.run(
        case=case,
        latest_diagnosis=diagnosis_obj,
        user_message=user_message,
        assistant_reply=assistant_reply,
        force_action="auto",
    )

    return Response(
        {
            "case_id": case.id,
            "diagnosis_version": next_version,
            "triage_level": result["triage_level"],
            "confidence": result["confidence"],
            "assistant_reply": assistant_reply,
            "likely_causes": result["likely_causes"],
            "recommended_actions": result["recommended_actions"],
            "stop_driving_reasons": result["stop_driving_reasons"],
            "follow_up_questions": result["follow_up_questions"],
            "model_name": result["model_name"],
            "latency_ms": result["latency_ms"],
            "citations": citations,
            "retrieval_mode": retrieval_mode,
            "agent_actions": agent_out.get("executed_actions", []),
            "agent_reason_trace": agent_out.get("reason_trace", []),
        },
        status=status.HTTP_200_OK,
    )


@extend_schema(
    request=AgentRunRequestSerializer,
    responses={200: AgentRunResponseSerializer},
)
@api_view(["POST"])
def run_case_agent(request, case_id):
    case = get_object_or_404(CaseSession, id=case_id)
    serializer = AgentRunRequestSerializer(data=request.data or {})
    serializer.is_valid(raise_exception=True)

    latest = case.diagnoses.order_by("-version", "-created_at").first()

    out = case_agent_service.run(
        case=case,
        latest_diagnosis=latest,
        user_message=serializer.validated_data.get("message", ""),
        assistant_reply="",
        force_action=serializer.validated_data.get("force_action", "auto"),
        resolution_summary=serializer.validated_data.get("resolution_summary", ""),
    )
    return Response(out, status=status.HTTP_200_OK)


@extend_schema(responses={200: CaseActionSerializer(many=True)})
@api_view(["GET"])
def list_case_actions(request, case_id):
    case = get_object_or_404(CaseSession, id=case_id)
    actions = case.actions.order_by("-created_at")[:100]
    data = [
        {
            "id": a.id,
            "action_type": a.action_type,
            "status": a.status,
            "reason": a.reason,
            "input_payload": a.input_payload,
            "output_payload": a.output_payload,
            "created_at": a.created_at,
        }
        for a in actions
    ]
    return Response(data)


@extend_schema(responses={200: CaseNoteSerializer(many=True)})
@api_view(["GET"])
def list_case_notes(request, case_id):
    case = get_object_or_404(CaseSession, id=case_id)
    notes = case.notes.order_by("-created_at")[:100]
    data = [
        {
            "id": n.id,
            "source": n.source,
            "note_text": n.note_text,
            "tags": n.tags,
            "created_at": n.created_at,
        }
        for n in notes
    ]
    return Response(data)
