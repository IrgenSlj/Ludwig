"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import {
  artifactUrl,
  streamGenerate,
  type StreamEvent,
} from "./lib/api";

interface LogRow {
  cls: string;
  text: string;
}

interface DoneState {
  projectId: string;
  score: number | null;
  critique: string | null;
  imageId?: string;
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
    if (!brief.trim() || running) return;
    setRunning(true);
    setRows([]);
    setDone(null);
    setFatal(null);

    try {
      await streamGenerate({ brief, quick }, (ev) => {
        append(rowFor(ev));
        if (ev.type === "done") {
          setDone({
            projectId: ev.project_id,
            score: ev.score,
            critique: ev.critique,
            imageId: ev.artifacts.hero ?? ev.artifacts.render,
          });
        }
      });
    } catch (err) {
      setFatal(
        "Could not reach the daemon. Is it running on the configured API URL?",
      );
      append({ cls: "ev-error", text: String(err) });
    } finally {
      setRunning(false);
    }
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
        <div className="controls">
          <button onClick={onGenerate} disabled={running || !brief.trim()}>
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
