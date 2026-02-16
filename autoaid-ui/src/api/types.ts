export type UUID = string;

export interface VehicleCreatePayload {
  owner_ref: string;
  nickname?: string;
  make: string;
  model: string;
  trim?: string;
  year: number;
  engine_cc?: number;
  transmission: "manual" | "automatic" | "cvt" | "dct" | "other";
  fuel_type: "gasoline" | "diesel" | "hybrid" | "electric" | "lpg" | "other";
  mileage_km?: number;
}

export interface Vehicle {
  id: UUID;
  owner_ref: string;
  nickname?: string;
  make: string;
  model: string;
  trim?: string;
  year: number;
  engine_cc?: number;
  transmission: string;
  fuel_type: string;
  mileage_km?: number;
  created_at?: string;
  updated_at?: string;
}

export interface CaseCreatePayload {
  vehicle_id: UUID;
  channel: "api" | "web" | "whatsapp" | "other";
  initial_problem_title: string;
  latest_user_message: string;
  metadata?: Record<string, unknown>;
}

export interface ChatResponse {
  case_id: UUID;
  diagnosis_version: number;
  triage_level: "green" | "yellow" | "red" | "unknown";
  confidence: number;
  assistant_reply: string;
  likely_causes: string[];
  recommended_actions: string[];
  stop_driving_reasons: string[];
  follow_up_questions: string[];
  model_name: string;
  latency_ms?: number;
  citations?: Array<{
    rank: number;
    title: string;
    chunk_index: number;
    snippet?: string;
    distance?: number | null;
  }>;
  retrieval_mode?: "vector" | "keyword";
  agent_actions?: Array<Record<string, unknown>>;
  agent_reason_trace?: string[];
}

export interface AgentRunPayload {
  force_action?: "auto" | "escalate" | "resolve" | "checklist";
  message?: string;
  resolution_summary?: string;
}
