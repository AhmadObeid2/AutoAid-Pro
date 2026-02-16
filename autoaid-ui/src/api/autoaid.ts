import { api } from "./client";
import type {
  Vehicle,
  VehicleCreatePayload,
  CaseCreatePayload,
  ChatResponse,
  AgentRunPayload,
  UUID,
} from "./types";

export async function health() {
  const { data } = await api.get("/health/");
  return data;
}

export async function createVehicle(payload: VehicleCreatePayload): Promise<Vehicle> {
  const { data } = await api.post("/vehicles/", payload);
  return data;
}

export async function createCase(payload: CaseCreatePayload) {
  const { data } = await api.post("/cases/", payload);
  return data;
}

export async function chatCase(caseId: UUID, message: string): Promise<ChatResponse> {
  const { data } = await api.post("/chat/", { case_id: caseId, message });
  return data;
}

export async function runAgent(caseId: UUID, payload: AgentRunPayload) {
  const { data } = await api.post(`/cases/${caseId}/agent/run/`, payload);
  return data;
}

export async function getActions(caseId: UUID) {
  const { data } = await api.get(`/cases/${caseId}/actions/`);
  return data;
}

export async function getNotes(caseId: UUID) {
  const { data } = await api.get(`/cases/${caseId}/notes/`);
  return data;
}

export async function uploadKnowledgeRaw(input: {
  title: string;
  source_type?: string;
  vehicle_make?: string;
  vehicle_model?: string;
  year_from?: number;
  year_to?: number;
  raw_text: string;
  is_active?: boolean;
}) {
  const { data } = await api.post("/rag/documents/upload/", {
    source_type: "internal_note",
    is_active: true,
    ...input,
  });
  return data;
}

export async function uploadKnowledgeFile(input: {
  title: string;
  file: File;
  source_type?: string;
  vehicle_make?: string;
  vehicle_model?: string;
  year_from?: number;
  year_to?: number;
  is_active?: boolean;
}) {
  const form = new FormData();

  form.append("title", input.title.trim());
  form.append("file", input.file, input.file.name);

  // Your backend rejected "manual". Map it to a known valid value.
  // If your backend enum is different, change this single line.
  const safeSourceType = (input.source_type ?? "internal_note").trim();
  form.append("source_type", safeSourceType === "manual" ? "internal_note" : safeSourceType);

  form.append("is_active", String(input.is_active ?? true));

  if (input.vehicle_make) form.append("vehicle_make", input.vehicle_make);
  if (input.vehicle_model) form.append("vehicle_model", input.vehicle_model);
  if (typeof input.year_from === "number") form.append("year_from", String(input.year_from));
  if (typeof input.year_to === "number") form.append("year_to", String(input.year_to));

  const { data } = await api.post("/rag/documents/upload/", form);
  return data;
}
