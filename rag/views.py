from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response

from core.models import CaseSession
from rag.models import KnowledgeDocument
from rag.serializers import (
    KnowledgeDocumentUploadSerializer,
    KnowledgeDocumentIngestResponseSerializer,
    RetrievalRequestSerializer,
    RetrievalResponseSerializer,
)
from rag.service import rag_service


@extend_schema(
    request=KnowledgeDocumentUploadSerializer,
    responses={201: KnowledgeDocumentIngestResponseSerializer},
)
@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def upload_knowledge_document(request):
    serializer = KnowledgeDocumentUploadSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    doc: KnowledgeDocument = serializer.save()

    try:
        stats = rag_service.ingest_document(doc)
        return Response(stats, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response(
            {
                "error": "Failed to ingest document",
                "detail": str(e),
                "document_id": str(doc.id),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


@extend_schema(
    request=RetrievalRequestSerializer,
    responses={200: RetrievalResponseSerializer},
)
@api_view(["POST"])
def retrieve_context(request):
    serializer = RetrievalRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    case_id = serializer.validated_data.get("case_id")
    query = serializer.validated_data["query"]
    top_k = serializer.validated_data["top_k"]

    case = get_object_or_404(CaseSession, id=case_id) if case_id else None
    out = rag_service.retrieve(query_text=query, case=case, top_k=top_k)

    return Response(
        {
            "query": query,
            "top_k": top_k,
            "retrieval_mode": out["retrieval_mode"],
            "latency_ms": out["latency_ms"],
            "context_text": out["context_text"],
            "citations": out["citations"],
        },
        status=status.HTTP_200_OK,
    )
