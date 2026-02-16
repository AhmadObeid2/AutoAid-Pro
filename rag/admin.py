from django.contrib import admin
from .models import KnowledgeDocument, DocumentChunk, RetrievalLog


@admin.register(KnowledgeDocument)
class KnowledgeDocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "source_type", "vehicle_make", "vehicle_model", "is_active", "created_at")
    search_fields = ("title", "vehicle_make", "vehicle_model")
    list_filter = ("source_type", "is_active")


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "chunk_index", "token_count", "embedding_model", "created_at")
    search_fields = ("document__title", "content", "vector_id")


@admin.register(RetrievalLog)
class RetrievalLogAdmin(admin.ModelAdmin):
    list_display = ("id", "case", "top_k", "reranked", "latency_ms", "created_at")
    search_fields = ("query_text", "case__id")
