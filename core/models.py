import uuid
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


def max_vehicle_year():
    return timezone.now().year + 1


class VehicleProfile(models.Model):
    class TransmissionType(models.TextChoices):
        MANUAL = "manual", "Manual"
        AUTOMATIC = "automatic", "Automatic"
        CVT = "cvt", "CVT"
        DCT = "dct", "DCT"
        OTHER = "other", "Other"

    class FuelType(models.TextChoices):
        GASOLINE = "gasoline", "Gasoline"
        DIESEL = "diesel", "Diesel"
        HYBRID = "hybrid", "Hybrid"
        ELECTRIC = "electric", "Electric"
        LPG = "lpg", "LPG"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Since we currently allow anonymous/public API, owner_ref can be:
    # phone number, frontend device ID, email hash, etc.
    owner_ref = models.CharField(max_length=120, db_index=True)

    nickname = models.CharField(max_length=100, blank=True, default="")
    make = models.CharField(max_length=80)
    model = models.CharField(max_length=80)
    trim = models.CharField(max_length=80, blank=True, default="")

    year = models.PositiveIntegerField(
        validators=[MinValueValidator(1980), MaxValueValidator(max_vehicle_year)]
    )
    engine_cc = models.PositiveIntegerField(null=True, blank=True)
    transmission = models.CharField(
        max_length=20,
        choices=TransmissionType.choices,
        default=TransmissionType.AUTOMATIC,
    )
    fuel_type = models.CharField(
        max_length=20,
        choices=FuelType.choices,
        default=FuelType.GASOLINE,
    )
    mileage_km = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["owner_ref", "created_at"]),
            models.Index(fields=["make", "model", "year"]),
        ]

    def __str__(self):
        return f"{self.make} {self.model} ({self.year})"


class CaseSession(models.Model):
    class Channel(models.TextChoices):
        API = "api", "API"
        WHATSAPP = "whatsapp", "WhatsApp"
        WEB = "web", "Web"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        NEEDS_FOLLOWUP = "needs_followup", "Needs Follow-up"
        RESOLVED = "resolved", "Resolved"
        ESCALATED = "escalated", "Escalated"
        CLOSED = "closed", "Closed"

    class RiskLevel(models.TextChoices):
        UNKNOWN = "unknown", "Unknown"
        GREEN = "green", "Green"
        YELLOW = "yellow", "Yellow"
        RED = "red", "Red"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vehicle = models.ForeignKey(
        VehicleProfile,
        on_delete=models.CASCADE,
        related_name="cases",
    )

    channel = models.CharField(max_length=20, choices=Channel.choices, default=Channel.API)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    current_risk_level = models.CharField(
        max_length=20,
        choices=RiskLevel.choices,
        default=RiskLevel.UNKNOWN,
    )

    initial_problem_title = models.CharField(max_length=200, blank=True, default="")
    latest_user_message = models.TextField(blank=True, default="")
    final_summary = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)

    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "current_risk_level", "opened_at"]),
            models.Index(fields=["vehicle", "last_activity_at"]),
        ]

    def __str__(self):
        return f"Case {self.id} - {self.vehicle}"


class SymptomReport(models.Model):
    class Source(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"
        SYSTEM = "system", "System"
        TOOL = "tool", "Tool"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(
        CaseSession,
        on_delete=models.CASCADE,
        related_name="symptoms",
    )

    source = models.CharField(max_length=20, choices=Source.choices, default=Source.USER)
    raw_text = models.TextField()
    normalized_symptoms = models.JSONField(default=list, blank=True)
    observed_signals = models.JSONField(default=dict, blank=True)
    odometer_at_report = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["case", "created_at"]),
            models.Index(fields=["source", "created_at"]),
        ]

    def __str__(self):
        return f"SymptomReport({self.source}) - {self.case_id}"


class DiagnosisResult(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(
        CaseSession,
        on_delete=models.CASCADE,
        related_name="diagnoses",
    )

    version = models.PositiveIntegerField(default=1)
    triage_level = models.CharField(
        max_length=20,
        choices=CaseSession.RiskLevel.choices,
        default=CaseSession.RiskLevel.UNKNOWN,
    )

    # 0.000 -> 1.000
    confidence_score = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        default=0.500,
    )

    likely_causes = models.JSONField(default=list, blank=True)
    recommended_actions = models.JSONField(default=list, blank=True)
    stop_driving_reasons = models.JSONField(default=list, blank=True)

    disclaimer_shown = models.BooleanField(default=True)

    # Observability / performance tracking
    model_name = models.CharField(max_length=120, default="unknown")
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    tokens_input = models.PositiveIntegerField(null=True, blank=True)
    tokens_output = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["case", "version"], name="uniq_case_version")
        ]
        indexes = [
            models.Index(fields=["case", "created_at"]),
            models.Index(fields=["triage_level", "created_at"]),
        ]

    def __str__(self):
        return f"Diagnosis v{self.version} - Case {self.case_id}"

class CaseNote(models.Model):
    class Source(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"
        AGENT = "agent", "Agent"
        SYSTEM = "system", "System"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey("CaseSession", on_delete=models.CASCADE, related_name="notes")
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.AGENT)
    note_text = models.TextField()
    tags = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["case", "created_at"]),
            models.Index(fields=["source", "created_at"]),
        ]

    def __str__(self):
        return f"CaseNote({self.source}) - {self.case_id}"


class CaseAction(models.Model):
    class ActionType(models.TextChoices):
        SAVE_NOTE = "save_note", "Save Note"
        CREATE_CHECKLIST = "create_checklist", "Create Checklist"
        ESCALATE_CASE = "escalate_case", "Escalate Case"
        RESOLVE_CASE = "resolve_case", "Resolve Case"

    class Status(models.TextChoices):
        EXECUTED = "executed", "Executed"
        SKIPPED = "skipped", "Skipped"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey("CaseSession", on_delete=models.CASCADE, related_name="actions")
    action_type = models.CharField(max_length=40, choices=ActionType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.EXECUTED)
    reason = models.CharField(max_length=300, blank=True, default="")
    input_payload = models.JSONField(default=dict, blank=True)
    output_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["case", "created_at"]),
            models.Index(fields=["action_type", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return f"{self.action_type} ({self.status}) - {self.case_id}"
