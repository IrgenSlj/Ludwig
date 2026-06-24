"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  artifactUrl,
  DiscoveryError,
  getDiscoverySchema,
  streamGenerate,
  type DiscoveryField,
  type DiscoveryValues,
  type StreamEvent,
} from "./lib/api";
import ModelViewer from "./ModelViewer";

interface LogRow {
  cls: string;
  text: string;
}

interface DoneState {
  projectId: string;
  score: number | null;
  critique: string | null;
  imageId?: string;
  previewId?: string;
}

function rowFor(ev: StreamEvent): LogRow | null {
  switch (ev.type) {
    case "start":
      return { cls: "ev-log", text: `start · ${ev.brief}` };
    case "round":
      return {
        cls: "ev-round",
        text: `round ${ev.round}/${ev.rounds} · ${ev.candidates} candidate(s)`,
      };
    case "candidate":
      return {
        cls: "ev-candidate",
        text: `candidate ${ev.label} → score ${ev.score}`,
      };
    case "best":
      return { cls: "ev-best", text: `best so far → score ${ev.score}` };
    case "hero_start":
      return { cls: "ev-hero", text: "rendering hero…" };
    case "hero":
      return { cls: "ev-hero", text: "hero render ready" };
    case "cleared":
      return { cls: "ev-log", text: "scene cleared" };
    case "log":
      return { cls: "ev-log", text: ev.message };
    case "error":
      return { cls: "ev-error", text: `error: ${ev.message}` };
    case "done":
      return {
        cls: "ev-best",
        text: `done → score ${ev.score ?? "n/a"}`,
      };
    default:
      return null;
  }
}

export default function Generator() {
  const [brief, setBrief] = useState("");
  const [quick, setQuick] = useState(false);
  const [running, setRunning] = useState(false);
  const [rows, setRows] = useState<LogRow[]>([]);
  const [done, setDone] = useState<DoneState | null>(null);
  const [fatal, setFatal] = useState<string | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  // Discovery — the mandatory brief-lock step. RULE 1: lock the brief before
  // the model draws. We fetch the schema, pre-fill defaults, and gate Generate
  // on every required field having a non-empty value.
  const [fields, setFields] = useState<DiscoveryField[]>([]);
  const [required, setRequired] = useState<string[]>([]);
  const [values, setValues] = useState<DiscoveryValues>({});
  const [showOptional, setShowOptional] = useState(false);
  const [problems, setProblems] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    getDiscoverySchema()
      .then((data) => {
        if (cancelled) return;
        setFields(data.schema);
        setRequired(data.required);
        setValues((prev) => {
          const next: DiscoveryValues = { ...prev };
          for (const f of data.schema) {
            if (next[f.name] === undefined) next[f.name] = f.default ?? "";
          }
          return next;
        });
      })
      .catch(() => {
        // Non-fatal: the brief textarea still renders. The generate gate below
        // keeps the button disabled until any required fields are satisfied.
        if (!cancelled) setFields([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const requiredFields = useMemo(
    () => fields.filter((f) => required.includes(f.name)),
    [fields, required],
  );
  const optionalFields = useMemo(
    () => fields.filter((f) => !required.includes(f.name)),
    [fields, required],
  );

  // The brief is "locked" once every required field has a non-empty value.
  const locked = useMemo(
    () => required.every((name) => (values[name] ?? "").trim() !== ""),
    [required, values],
  );
  const canGenerate = brief.trim() !== "" && locked && !running;

  function setField(name: string, value: string) {
    setValues((prev) => ({ ...prev, [name]: value }));
  }

  function append(row: LogRow | null) {
    if (!row) return;
    setRows((prev) => [...prev, row]);
    // scroll the log to the bottom on the next paint
    requestAnimationFrame(() => {
      const el = logRef.current;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }

  async function onGenerate() {
    if (!canGenerate) return;
    setRunning(true);
    setRows([]);
    setDone(null);
    setFatal(null);
    setProblems([]);

    // Only send fields the schema knows about, trimmed.
    const discovery: DiscoveryValues = {};
    for (const f of fields) {
      const v = (values[f.name] ?? "").trim();
      if (v !== "") discovery[f.name] = v;
    }

    try {
      await streamGenerate({ brief, quick, discovery }, (ev) => {
        append(rowFor(ev));
        if (ev.type === "done") {
          setDone({
            projectId: ev.project_id,
            score: ev.score,
            critique: ev.critique,
            imageId: ev.artifacts.hero ?? ev.artifacts.render,
            previewId: ev.artifacts.preview,
          });
        }
      });
    } catch (err) {
      if (err instanceof DiscoveryError) {
        setProblems(err.problems);
        append({ cls: "ev-error", text: `brief rejected: ${err.message}` });
      } else {
        setFatal(
          "Could not reach the daemon. Is it running on the configured API URL?",
        );
        append({ cls: "ev-error", text: String(err) });
      }
    } finally {
      setRunning(false);
    }
  }

  function renderField(f: DiscoveryField) {
    const value = values[f.name] ?? "";
    return (
      <div className="disco-field" key={f.name}>
        <label htmlFor={`disco-${f.name}`}>{f.label}</label>
        {f.type === "select" ? (
          <select
            id={`disco-${f.name}`}
            value={value}
            onChange={(e) => setField(f.name, e.target.value)}
            disabled={running}
          >
            {(f.options ?? []).map((opt) => (
              <option key={opt} value={opt}>
                {opt}
              </option>
            ))}
          </select>
        ) : (
          <input
            id={`disco-${f.name}`}
            type="text"
            value={value}
            onChange={(e) => setField(f.name, e.target.value)}
            disabled={running}
          />
        )}
        {f.help && <span className="disco-help">{f.help}</span>}
      </div>
    );
  }

  return (
    <>
      <section className="panel">
        <textarea
          placeholder="Describe what to model — e.g. 'a minimalist ceramic pour-over coffee dripper on a wooden table'"
          value={brief}
          onChange={(e) => setBrief(e.target.value)}
          disabled={running}
        />

        {fields.length > 0 && (
          <div className="discovery">
            <div className="disco-head">
              <strong>Lock the brief</strong>
              <span className="muted">
                Set the constraints before the model draws.
              </span>
            </div>
            <div className="disco-grid">{requiredFields.map(renderField)}</div>
            {optionalFields.length > 0 && (
              <>
                <button
                  type="button"
                  className="disco-toggle"
                  onClick={() => setShowOptional((v) => !v)}
                  disabled={running}
                >
                  {showOptional ? "− Fewer options" : "+ More options"}
                </button>
                {showOptional && (
                  <div className="disco-grid">
                    {optionalFields.map(renderField)}
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {problems.length > 0 && (
          <div className="disco-problems">
            <strong className="ev-error">Fix the brief lock:</strong>
            <ul>
              {problems.map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
          </div>
        )}

        <div className="controls">
          <button onClick={onGenerate} disabled={!canGenerate}>
            {running ? "Generating…" : "Generate"}
          </button>
          <label className="check">
            <input
              type="checkbox"
              checked={quick}
              onChange={(e) => setQuick(e.target.checked)}
              disabled={running}
            />
            Quick (1 candidate, 1 round)
          </label>
          {!canGenerate && !running && (
            <span className="muted disco-hint">
              {brief.trim() === ""
                ? "Describe what to model, then lock the brief to generate"
                : "Lock the brief to generate"}
            </span>
          )}
        </div>
      </section>

      {fatal && (
        <section className="panel">
          <strong className="ev-error">{fatal}</strong>
        </section>
      )}

      {(rows.length > 0 || running) && (
        <section className="panel">
          <div className="muted" style={{ marginBottom: 8 }}>
            Live progress
          </div>
          <div className="log" ref={logRef}>
            {rows.map((r, i) => (
              <div key={i} className={`row ${r.cls}`}>
                {r.text}
              </div>
            ))}
          </div>
        </section>
      )}

      {done && (
        <section className="panel result">
          <div className="muted" style={{ marginBottom: 8 }}>
            Result · score <span className="score">{done.score ?? "n/a"}</span>
          </div>
          {done.imageId ? (
            <img src={artifactUrl(done.imageId)} alt="hero render" />
          ) : (
            <div className="muted">No image artifact returned.</div>
          )}
          {done.previewId && (
            <>
              <div className="muted" style={{ margin: "12px 0 6px" }}>
                Rotate · interactive 3D
              </div>
              <ModelViewer
                src={artifactUrl(done.previewId)}
                alt="Interactive 3D preview of the generated object"
              />
            </>
          )}
          {done.critique && <div className="critique">{done.critique}</div>}
          <p style={{ marginBottom: 0 }}>
            <Link href={`/projects/${done.projectId}`}>
              Open project workspace →
            </Link>
          </p>
        </section>
      )}
    </>
  );
}
