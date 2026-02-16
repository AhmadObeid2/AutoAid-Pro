from django.contrib import admin
from .models import VehicleProfile, CaseSession, SymptomReport, DiagnosisResult, CaseNote, CaseAction


@admin.register(VehicleProfile)
class VehicleProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "owner_ref", "make", "model", "year", "transmission", "fuel_type", "created_at")
    search_fields = ("owner_ref", "make", "model", "nickname")
    list_filter = ("transmission", "fuel_type", "year")


@admin.register(CaseSession)
class CaseSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "vehicle", "channel", "status", "current_risk_level", "opened_at", "last_activity_at")
    search_fields = ("id", "vehicle__make", "vehicle__model", "initial_problem_title")
    list_filter = ("channel", "status", "current_risk_level")


@admin.register(SymptomReport)
class SymptomReportAdmin(admin.ModelAdmin):
    list_display = ("id", "case", "source", "created_at")
    search_fields = ("raw_text", "case__id")
    list_filter = ("source",)


@admin.register(DiagnosisResult)
class DiagnosisResultAdmin(admin.ModelAdmin):
    list_display = ("id", "case", "version", "triage_level", "confidence_score", "model_name", "created_at")
    search_fields = ("case__id", "model_name")
    list_filter = ("triage_level", "model_name")

@admin.register(CaseNote)
class CaseNoteAdmin(admin.ModelAdmin):
    list_display = ("id", "case", "source", "created_at")
    search_fields = ("case__id", "note_text")
    list_filter = ("source",)


@admin.register(CaseAction)
class CaseActionAdmin(admin.ModelAdmin):
    list_display = ("id", "case", "action_type", "status", "created_at")
    search_fields = ("case__id", "reason")
    list_filter = ("action_type", "status")


