import uuid
from django.db import models


class KnowledgeDocument(models.Model):
    class SourceType(models.TextChoices):
        OWNER_MANUAL = "owner_manual", "Owner Manual"
        SERVICE_GUIDE = "service_guide", "Service Guide"
        TROUBLE_CODE = "trouble_code", "Trouble Code Notes"
        INTERNAL_NOTE = "internal_note", "Internal Note"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    title = models.CharField(max_length=200)
    source_type = models.CharField(
        max_length=30,
        choices=SourceType.choices,
        default=SourceType.OTHER,
    )

    vehicle_make = models.CharField(max_length=80, blank=True, default="")
    vehicle_model = models.CharField(max_length=80, blank=True, default="")
    year_from = models.PositiveIntegerField(null=True, blank=True)
    year_to = models.PositiveIntegerField(null=True, blank=True)

    file = models.FileField(upload_to="knowledge_docs/", null=True, blank=True)
    raw_text = models.TextField(blank=True, default="")

    is_active = models.BooleanField(default=True)
    checksum = models.CharField(max_length=64, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["source_type", "is_active"]),
            models.Index(fields=["vehicle_make", "vehicle_model"]),
        ]

    def __str__(self):
        return self.title


class DocumentChunk(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        KnowledgeDocument,
        on_delete=models.CASCADE,
        related_name="chunks",
    )

    chunk_index = models.PositiveIntegerField()
    content = models.TextField()
    token_count = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)

    # maps to vector DB record id (e.g., Chroma id)
    vector_id = models.CharField(max_length=128, unique=True, null=True, blank=True)
    embedding_model = models.CharField(max_length=120, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["document", "chunk_index"], name="uniq_doc_chunk_index")
        ]
        indexes = [
            models.Index(fields=["document", "chunk_index"]),
            models.Index(fields=["vector_id"]),
        ]

    def __str__(self):
        return f"{self.document.title} - chunk {self.chunk_index}"


class RetrievalLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(
        "core.CaseSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="retrieval_logs",
    )

    query_text = models.TextField()
    top_k = models.PositiveIntegerField(default=5)
    retrieved_chunks = models.JSONField(default=list, blank=True)
    reranked = models.BooleanField(default=False)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["top_k"]),
        ]

    def __str__(self):
        return f"RetrievalLog {self.id}"

