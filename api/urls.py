from django.urls import path, include
from .views import (
    health_check,
    create_vehicle,
    get_vehicle,
    create_case,
    add_symptom,
    get_case_snapshot,
    chat_case,
    run_case_agent,
    list_case_actions,
    list_case_notes,
)

urlpatterns = [
    path("health/", health_check, name="health-check"),

    path("vehicles/", create_vehicle, name="create-vehicle"),
    path("vehicles/<uuid:vehicle_id>/", get_vehicle, name="get-vehicle"),

    path("cases/", create_case, name="create-case"),
    path("cases/<uuid:case_id>/", get_case_snapshot, name="get-case-snapshot"),
    path("cases/<uuid:case_id>/symptoms/", add_symptom, name="add-symptom"),
    path("chat/", chat_case, name="chat-case"),
    path("rag/", include("rag.urls")),
    path("cases/<uuid:case_id>/agent/run/", run_case_agent, name="run-case-agent"),
    path("cases/<uuid:case_id>/actions/", list_case_actions, name="list-case-actions"),
    path("cases/<uuid:case_id>/notes/", list_case_notes, name="list-case-notes"),
]
