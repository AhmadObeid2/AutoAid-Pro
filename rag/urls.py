from django.urls import path
from rag.views import upload_knowledge_document, retrieve_context

urlpatterns = [
    path("documents/upload/", upload_knowledge_document, name="rag-upload-document"),
    path("retrieve/", retrieve_context, name="rag-retrieve"),
]
