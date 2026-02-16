from rest_framework import serializers
from rag.models import KnowledgeDocument


class KnowledgeDocumentUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = KnowledgeDocument
        fields = [
            "title",
            "source_type",
            "vehicle_make",
            "vehicle_model",
            "year_from",
            "year_to",
            "file",
            "raw_text",
            "is_active",
        ]

    def validate(self, attrs):
        raw_text = (attrs.get("raw_text") or "").strip()
        file_obj = attrs.get("file")
        if not raw_text and not file_obj:
            raise serializers.ValidationError("Provide either 'raw_text' or 'file' (or both).")
        return attrs


class KnowledgeDocumentIngestResponseSerializer(serializers.Serializer):
    document_id = serializers.UUIDField()
    title = serializers.CharField()
    chunks_created = serializers.IntegerField()
    vectors_indexed = serializers.IntegerField()
    embedding_mode = serializers.CharField()


class RetrievalRequestSerializer(serializers.Serializer):
    case_id = serializers.UUIDField(required=False, allow_null=True)
    query = serializers.CharField(max_length=2000)
    top_k = serializers.IntegerField(default=5, min_value=1, max_value=10)


class CitationSerializer(serializers.Serializer):
    rank = serializers.IntegerField()
    vector_id = serializers.CharField(allow_null=True, required=False)
    document_id = serializers.CharField()
    title = serializers.CharField()
    source_type = serializers.CharField()
    chunk_index = serializers.IntegerField()
    distance = serializers.FloatField(allow_null=True, required=False)
    score = serializers.IntegerField(required=False)
    snippet = serializers.CharField()


class RetrievalResponseSerializer(serializers.Serializer):
    query = serializers.CharField()
    top_k = serializers.IntegerField()
    retrieval_mode = serializers.CharField()
    latency_ms = serializers.IntegerField()
    context_text = serializers.CharField()
    citations = CitationSerializer(many=True)
