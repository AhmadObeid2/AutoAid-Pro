from django.shortcuts import get_object_or_404
from rest_framework import serializers
from core.models import VehicleProfile, CaseSession, SymptomReport, DiagnosisResult
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field


class VehicleSerializer(serializers.ModelSerializer):
    year = serializers.IntegerField(
        min_value=1980,
        max_value=timezone.now().year + 1
    )

    class Meta:
        model = VehicleProfile
        fields = "__all__"


class VehicleCreateSerializer(serializers.ModelSerializer):
    year = serializers.IntegerField(
        min_value=1980,
        max_value=timezone.now().year + 1
    )

    class Meta:
        model = VehicleProfile
        fields = [
            "owner_ref",
            "nickname",
            "make",
            "model",
            "trim",
            "year",
            "engine_cc",
            "transmission",
            "fuel_type",
            "mileage_km",
        ]


class CaseCreateSerializer(serializers.Serializer):
    vehicle_id = serializers.UUIDField()
    channel = serializers.ChoiceField(choices=CaseSession.Channel.choices, default=CaseSession.Channel.API)
    initial_problem_title = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    latest_user_message = serializers.CharField(required=False, allow_blank=True, default="")
    metadata = serializers.JSONField(required=False, default=dict)

    def create(self, validated_data):
        vehicle_id = validated_data.pop("vehicle_id")
        vehicle = get_object_or_404(VehicleProfile, id=vehicle_id)
        return CaseSession.objects.create(vehicle=vehicle, **validated_data)


class SymptomCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SymptomReport
        fields = [
            "source",
            "raw_text",
            "normalized_symptoms",
            "observed_signals",
            "odometer_at_report",
        ]

    def create(self, validated_data):
        case = self.context["case"]
        return SymptomReport.objects.create(case=case, **validated_data)


class SymptomReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = SymptomReport
        fields = "__all__"


class DiagnosisResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiagnosisResult
        fields = "__all__"


class CaseSnapshotSerializer(serializers.ModelSerializer):
    vehicle = VehicleSerializer(read_only=True)
    recent_symptoms = serializers.SerializerMethodField()
    latest_diagnosis = serializers.SerializerMethodField()

    class Meta:
        model = CaseSession
        fields = [
            "id",
            "vehicle",
            "channel",
            "status",
            "current_risk_level",
            "initial_problem_title",
            "latest_user_message",
            "final_summary",
            "metadata",
            "opened_at",
            "closed_at",
            "last_activity_at",
            "recent_symptoms",
            "latest_diagnosis",
        ]

    @extend_schema_field(SymptomReportSerializer(many=True))
    def get_recent_symptoms(self, obj):
        qs = obj.symptoms.order_by("-created_at")[:10]
        return SymptomReportSerializer(qs, many=True).data

    @extend_schema_field(DiagnosisResultSerializer(allow_null=True))
    def get_latest_diagnosis(self, obj):
        diagnosis = obj.diagnoses.order_by("-version", "-created_at").first()
        if not diagnosis:
            return None
        return DiagnosisResultSerializer(diagnosis).data

class ChatRequestSerializer(serializers.Serializer):
    case_id = serializers.UUIDField()
    message = serializers.CharField(max_length=2000)


class ChatResponseSerializer(serializers.Serializer):
    case_id = serializers.UUIDField()
    diagnosis_version = serializers.IntegerField()
    triage_level = serializers.ChoiceField(choices=CaseSession.RiskLevel.choices)
    confidence = serializers.FloatField()
    assistant_reply = serializers.CharField()
    likely_causes = serializers.ListField(child=serializers.CharField())
    recommended_actions = serializers.ListField(child=serializers.CharField())
    stop_driving_reasons = serializers.ListField(child=serializers.CharField())
    follow_up_questions = serializers.ListField(child=serializers.CharField())
    model_name = serializers.CharField()
    latency_ms = serializers.IntegerField(allow_null=True, required=False)
    citations = serializers.ListField(child=serializers.DictField(), required=False)
    retrieval_mode = serializers.CharField(required=False)
    agent_actions = serializers.ListField(child=serializers.DictField(), required=False)
    agent_reason_trace = serializers.ListField(child=serializers.CharField(), required=False)

class HealthResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    service = serializers.CharField()
    django_version = serializers.CharField()

class CaseNoteSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    source = serializers.CharField()
    note_text = serializers.CharField()
    tags = serializers.ListField(child=serializers.CharField(), required=False)
    created_at = serializers.DateTimeField()


class CaseActionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    action_type = serializers.CharField()
    status = serializers.CharField()
    reason = serializers.CharField()
    input_payload = serializers.DictField()
    output_payload = serializers.DictField()
    created_at = serializers.DateTimeField()


class AgentRunRequestSerializer(serializers.Serializer):
    force_action = serializers.ChoiceField(
        choices=["auto", "escalate", "resolve", "checklist"],
        default="auto",
        required=False
    )
    message = serializers.CharField(required=False, allow_blank=True, default="")
    resolution_summary = serializers.CharField(required=False, allow_blank=True, default="")


class AgentRunResponseSerializer(serializers.Serializer):
    case_id = serializers.UUIDField()
    case_status = serializers.CharField()
    risk_level = serializers.CharField()
    executed_actions = serializers.ListField(child=serializers.DictField())
    reason_trace = serializers.ListField(child=serializers.CharField())

