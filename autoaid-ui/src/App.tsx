import { useMemo, useState } from "react";
import {
  createVehicle,
  createCase,
  chatCase,
  runAgent,
  getActions,
  getNotes,
  uploadKnowledgeFile,
} from "./api/autoaid";
import type {
  VehicleCreatePayload,
  CaseCreatePayload,
  AgentRunPayload,
} from "./api/types";

type Transmission = VehicleCreatePayload["transmission"];
type FuelType = VehicleCreatePayload["fuel_type"];
type CaseChannel = CaseCreatePayload["channel"];
type AgentForceAction = NonNullable<AgentRunPayload["force_action"]>;

type VehicleFormState = {
  owner_ref: string;
  nickname: string;
  make: string;
  model: string;
  trim: string;
  year: number;
  engine_cc: number;
  transmission: Transmission;
  fuel_type: FuelType;
  mileage_km: number;
};

type CaseFormState = {
  channel: CaseChannel;
  initial_problem_title: string;
  latest_user_message: string;
};

type Msg = {
  role: "user" | "assistant";
  text: string;
  triage?: string;
  citations?: Array<{ rank: number; title: string; chunk_index: number }>;
  followUps?: string[];
};

function getErrorMessage(err: unknown, fallback: string): string {
  const e = err as any;
  if (e?.response?.data) {
    if (typeof e.response.data === "string") return e.response.data;
    return JSON.stringify(e.response.data);
  }
  if (e instanceof Error && e.message) return e.message;
  return fallback;
}

export default function App() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const [vehicleId, setVehicleId] = useState("");
  const [caseId, setCaseId] = useState("");

  const [vehicleForm, setVehicleForm] = useState<VehicleFormState>({
    owner_ref: "demo_user_01",
    nickname: "",
    make: "",
    model: "",
    trim: "",
    year: 2016,
    engine_cc: 1600,
    transmission: "automatic",
    fuel_type: "gasoline",
    mileage_km: 120000,
  });

  const [caseForm, setCaseForm] = useState<CaseFormState>({
    channel: "web",
    initial_problem_title: "",
    latest_user_message: "",
  });

  const [docForm, setDocForm] = useState({
    title: "",
    vehicle_make: "",
    vehicle_model: "",
    year_from: 2012,
    year_to: 2020,
  });
  const [docFile, setDocFile] = useState<File | null>(null);
  const [uploadedDocsCount, setUploadedDocsCount] = useState(0);

  const [chatInput, setChatInput] = useState("");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [lastFollowUp, setLastFollowUp] = useState<string>("");

  const [actions, setActions] = useState<unknown[]>([]);
  const [notes, setNotes] = useState<unknown[]>([]);

  const canCreateCase = !!vehicleId;
  const canChat = !!caseId && !busy;

  const statusText = useMemo(() => {
    return `Vehicle: ${vehicleId || "not created"} | Case: ${caseId || "not created"} | Docs uploaded: ${uploadedDocsCount}`;
  }, [vehicleId, caseId, uploadedDocsCount]);

  async function handleCreateVehicle(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      setBusy(true);

      // Because vehicleForm is strongly typed to VehicleCreatePayload-compatible fields,
      // this is now fully type-safe.
      const payload: VehicleCreatePayload = {
        ...vehicleForm,
        year: Number(vehicleForm.year),
        engine_cc: Number(vehicleForm.engine_cc),
        mileage_km: Number(vehicleForm.mileage_km),
      };

      const v = await createVehicle(payload);
      setVehicleId(v.id);
    } catch (err: unknown) {
      setError(getErrorMessage(err, "Failed to create vehicle"));
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateCase(e: React.FormEvent) {
    e.preventDefault();
    if (!vehicleId) return setError("Create vehicle first.");
    setError("");
    try {
      setBusy(true);
      const c = await createCase({
        vehicle_id: vehicleId,
        channel: caseForm.channel,
        initial_problem_title: caseForm.initial_problem_title,
        latest_user_message: caseForm.latest_user_message,
        metadata: { source: "frontend_manual_form" },
      });
      setCaseId(c.id);
      setMessages([]);
      setLastFollowUp("");
    } catch (err: unknown) {
      setError(getErrorMessage(err, "Failed to create case"));
    } finally {
      setBusy(false);
    }
  }

  async function handleUploadDoc(e: React.FormEvent) {
    e.preventDefault();
    if (!docFile) return setError("Choose a document file first.");
    if (!docForm.title.trim()) return setError("Document title is required.");

    setError("");
    try {
      setBusy(true);
      await uploadKnowledgeFile({
        title: docForm.title.trim(),
        file: docFile,
        source_type: "internal_note", // instead of "manual"
        vehicle_make: docForm.vehicle_make || undefined,
        vehicle_model: docForm.vehicle_model || undefined,
        year_from: Number(docForm.year_from),
        year_to: Number(docForm.year_to),
      });
      setUploadedDocsCount((x) => x + 1);
      setDocFile(null);
      const fileInput = document.getElementById("doc-file-input") as HTMLInputElement | null;
      if (fileInput) fileInput.value = "";
    } catch (err: unknown) {
      setError(getErrorMessage(err, "Failed to upload document"));
    } finally {
      setBusy(false);
    }
  }

  async function handleChatSend(e: React.FormEvent) {
    e.preventDefault();
    if (!caseId) return setError("Create case first.");
    const text = chatInput.trim();
    if (!text) return;

    setError("");
    setMessages((m) => [...m, { role: "user", text }]);
    setChatInput("");

    try {
      setBusy(true);
      const out = await chatCase(caseId, text);

      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          text: out.assistant_reply,
          triage: out.triage_level,
          citations: (out.citations || []).map((c: any) => ({
            rank: c.rank,
            title: c.title,
            chunk_index: c.chunk_index,
          })),
          followUps: out.follow_up_questions || [],
        },
      ]);

      setLastFollowUp((out.follow_up_questions || [])[0] || "");
      await refreshLogs();
    } catch (err: unknown) {
      setError(getErrorMessage(err, "Chat failed"));
    } finally {
      setBusy(false);
    }
  }

  async function runManualAgent(force_action: AgentForceAction) {
    if (!caseId) return setError("Create case first.");
    setError("");
    try {
      setBusy(true);
      await runAgent(caseId, {
        force_action,
        message: chatInput || "manual action from UI",
        resolution_summary: force_action === "resolve" ? "Resolved via frontend manual control." : "",
      });
      await refreshLogs();
    } catch (err: unknown) {
      setError(getErrorMessage(err, "Agent action failed"));
    } finally {
      setBusy(false);
    }
  }

  async function refreshLogs() {
    if (!caseId) return;
    const [a, n] = await Promise.all([getActions(caseId), getNotes(caseId)]);
    setActions(a || []);
    setNotes(n || []);
  }

  return (
    <div className="page">
      <header className="hero">
        <h1>AutoAid Pro</h1>
        <p>AI Car Troubleshooter — Manual workflow + RAG + Agent tools</p>
        <div className="status">{statusText}</div>
      </header>

      {error && <div className="error">{error}</div>}

      <section className="grid-2">
        <form className="card" onSubmit={handleCreateVehicle}>
          <h2>1) Create Vehicle (Manual)</h2>
          <div className="form-grid">
            <input
              placeholder="Owner Ref"
              value={vehicleForm.owner_ref}
              onChange={(e) => setVehicleForm({ ...vehicleForm, owner_ref: e.target.value })}
            />
            <input
              placeholder="Nickname (optional)"
              value={vehicleForm.nickname}
              onChange={(e) => setVehicleForm({ ...vehicleForm, nickname: e.target.value })}
            />
            <input
              placeholder="Make (e.g. Honda)"
              value={vehicleForm.make}
              onChange={(e) => setVehicleForm({ ...vehicleForm, make: e.target.value })}
              required
            />
            <input
              placeholder="Model (e.g. Civic)"
              value={vehicleForm.model}
              onChange={(e) => setVehicleForm({ ...vehicleForm, model: e.target.value })}
              required
            />
            <input
              placeholder="Trim (optional)"
              value={vehicleForm.trim}
              onChange={(e) => setVehicleForm({ ...vehicleForm, trim: e.target.value })}
            />
            <input
              type="number"
              placeholder="Year"
              value={vehicleForm.year}
              onChange={(e) => setVehicleForm({ ...vehicleForm, year: Number(e.target.value) })}
              required
            />
            <input
              type="number"
              placeholder="Engine CC"
              value={vehicleForm.engine_cc}
              onChange={(e) => setVehicleForm({ ...vehicleForm, engine_cc: Number(e.target.value) })}
            />
            <input
              type="number"
              placeholder="Mileage KM"
              value={vehicleForm.mileage_km}
              onChange={(e) => setVehicleForm({ ...vehicleForm, mileage_km: Number(e.target.value) })}
            />
            <select
              value={vehicleForm.transmission}
              onChange={(e) =>
                setVehicleForm({ ...vehicleForm, transmission: e.target.value as Transmission })
              }
            >
              <option value="automatic">Automatic</option>
              <option value="manual">Manual</option>
              <option value="cvt">CVT</option>
              <option value="dct">DCT</option>
              <option value="other">Other</option>
            </select>
            <select
              value={vehicleForm.fuel_type}
              onChange={(e) =>
                setVehicleForm({ ...vehicleForm, fuel_type: e.target.value as FuelType })
              }
            >
              <option value="gasoline">Gasoline</option>
              <option value="diesel">Diesel</option>
              <option value="hybrid">Hybrid</option>
              <option value="electric">Electric</option>
              <option value="lpg">LPG</option>
              <option value="other">Other</option>
            </select>
          </div>
          <button disabled={busy}>Create Vehicle</button>
        </form>

        <form className="card" onSubmit={handleCreateCase}>
          <h2>2) Create Case (Manual)</h2>
          <div className="form-grid">
            <input value={vehicleId} placeholder="Vehicle ID (auto from step 1)" readOnly />
            <select
              value={caseForm.channel}
              onChange={(e) => setCaseForm({ ...caseForm, channel: e.target.value as CaseChannel })}
            >
              <option value="web">Web</option>
              <option value="api">API</option>
              <option value="other">Other</option>
            </select>
            <input
              placeholder="Initial problem title"
              value={caseForm.initial_problem_title}
              onChange={(e) => setCaseForm({ ...caseForm, initial_problem_title: e.target.value })}
              required
            />
            <textarea
              placeholder="Initial user message"
              value={caseForm.latest_user_message}
              onChange={(e) => setCaseForm({ ...caseForm, latest_user_message: e.target.value })}
              required
            />
          </div>
          <button disabled={busy || !canCreateCase}>Create Case</button>
        </form>
      </section>

      <section className="card">
        <h2>3) Upload Knowledge Document (Local File)</h2>
        <form onSubmit={handleUploadDoc} className="form-grid">
          <input
            placeholder="Document title"
            value={docForm.title}
            onChange={(e) => setDocForm({ ...docForm, title: e.target.value })}
            required
          />
          <input
            placeholder="Vehicle Make (optional)"
            value={docForm.vehicle_make}
            onChange={(e) => setDocForm({ ...docForm, vehicle_make: e.target.value })}
          />
          <input
            placeholder="Vehicle Model (optional)"
            value={docForm.vehicle_model}
            onChange={(e) => setDocForm({ ...docForm, vehicle_model: e.target.value })}
          />
          <input
            type="number"
            placeholder="Year From"
            value={docForm.year_from}
            onChange={(e) => setDocForm({ ...docForm, year_from: Number(e.target.value) })}
          />
          <input
            type="number"
            placeholder="Year To"
            value={docForm.year_to}
            onChange={(e) => setDocForm({ ...docForm, year_to: Number(e.target.value) })}
          />
          <input
            id="doc-file-input"
            type="file"
            accept=".pdf,.txt,.md,.doc,.docx"
            onChange={(e) => setDocFile(e.target.files?.[0] || null)}
            required
          />
          <button disabled={busy}>Upload Document</button>
        </form>
        <p className="hint">Now upload is fully manual from your local storage — nothing auto-inserted.</p>
      </section>

      <section className="card chat-card">
        <h2>4) Chat</h2>
        <div className="chat-box">
          {messages.map((m, i) => (
            <div key={i} className={`bubble ${m.role}`}>
              <div className="bubble-role">{m.role.toUpperCase()}</div>
              <div style={{ whiteSpace: "pre-wrap" }}>{m.text}</div>

              {m.triage && <div className={`badge ${m.triage}`}>Triage: {m.triage.toUpperCase()}</div>}

              {m.citations && m.citations.length > 0 && (
                <div className="citations">
                  <strong>Sources:</strong>
                  <ul>
                    {m.citations.map((c, idx) => (
                      <li key={idx}>
                        [{c.rank}] {c.title} (chunk {c.chunk_index})
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {m.followUps && m.followUps.length > 0 && (
                <div className="followup">
                  <strong>Follow-up:</strong> {m.followUps[0]}
                </div>
              )}
            </div>
          ))}
        </div>

        {lastFollowUp && <div className="hint">Suggested next answer: {lastFollowUp}</div>}

        <form onSubmit={handleChatSend} className="chat-input-row">
          <textarea
            placeholder="Describe symptom or answer follow-up question..."
            value={chatInput}
            onChange={(e) => setChatInput(e.target.value)}
            rows={3}
          />
          <button disabled={!canChat || !chatInput.trim()}>Send</button>
        </form>
      </section>

      <section className="card">
        <h2>5) Agent Manual Controls</h2>
        <div className="btn-row">
          <button disabled={!caseId || busy} onClick={() => runManualAgent("auto")}>Auto</button>
          <button disabled={!caseId || busy} onClick={() => runManualAgent("checklist")}>Checklist</button>
          <button disabled={!caseId || busy} onClick={() => runManualAgent("escalate")}>Escalate</button>
          <button disabled={!caseId || busy} onClick={() => runManualAgent("resolve")}>Resolve</button>
          <button disabled={!caseId || busy} onClick={refreshLogs}>Refresh Logs</button>
        </div>
      </section>

      <section className="grid-2">
        <div className="card">
          <h3>Case Actions</h3>
          <pre>{JSON.stringify(actions, null, 2)}</pre>
        </div>
        <div className="card">
          <h3>Case Notes</h3>
          <pre>{JSON.stringify(notes, null, 2)}</pre>
        </div>
      </section>
    </div>
  );
}
