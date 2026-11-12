import { useEffect, useState } from "react";
import { api, assist, fetchBlob, pageUrl, PAGE_SCALE, type FindingDetail, type SourceRef } from "../api";
import { href } from "../route";
import { bySide, describeSource, formatValue, type Side } from "../sides";
import { useLoad } from "../useLoad";

export function FindingPage({ id }: { id: number }) {
  const finding = useLoad(() => api.finding(id), [id]);
  const siblings = useLoad(
    () => (finding.data ? api.findings(finding.data.run_id, "fail,not_checked") : Promise.resolve([])),
    [finding.data?.run_id],
  );
  const f = finding.data;
  if (finding.error) return <p className="error">{finding.error}</p>;
  if (!f) return <p className="muted">Loading…</p>;

  const sides = bySide(f);
  const list = siblings.data ?? [];
  const at = list.findIndex((x) => x.id === f.id);
  const next = list.slice(at + 1).find((x) => !x.review) ?? null;
  const pdfSources = f.evidence.filter((s) => s.kind === "pdf" && s.page && s.bbox);

  return (
    <section>
      <p className="crumbs">
        <a href={href.projects()}>Projects</a> / <a href={href.run(f.run_id)}>Run {f.run_id}</a> /
      </p>
      <h1 className={`sev-${f.severity}`}>
        <span className={`badge ${f.severity}`}>{f.severity}</span> {f.message || f.rule_id}
      </h1>
      <dl className="facts">
        <dt>Status</dt>
        <dd>{f.status.replace("_", " ")}</dd>
        <dt>Rule</dt>
        <dd>
          {f.rule_id} <span className="muted">({f.pack} {f.pack_version})</span>
        </dd>
        {f.mark && (
          <>
            <dt>Mark</dt>
            <dd>{f.mark}</dd>
          </>
        )}
        {f.expected && (
          <>
            <dt>Expected</dt>
            <dd>{f.expected}</dd>
          </>
        )}
        {f.reason && (
          <>
            <dt>Not checked because</dt>
            <dd>{f.reason}</dd>
          </>
        )}
      </dl>

      <Explain id={f.id} />

      <div className="columns">
        <SideCard title="Drawings" side="architect" value={sides.values.architect} sources={sides.sources.architect} />
        <SideCard title="Production" side="erp" value={sides.values.erp} sources={sides.sources.erp} />
      </div>

      {pdfSources.length > 0 && (
        <>
          <h2>In the PDF</h2>
          <div className="previews">
            {pdfSources.map((s, i) =>
              f.files[s.file] ? <PagePreview key={i} upload={f.files[s.file]} source={s} /> : null,
            )}
          </div>
        </>
      )}

      <ReviewForm finding={f} onDone={() => (next ? (window.location.hash = href.finding(next.id)) : finding.reload())} />
      {f.reviews.length > 0 && (
        <>
          <h2>History</h2>
          <ul className="list">
            {f.reviews.map((r, i) => (
              <li key={i}>
                <span className={`badge ${r.decision}`}>{r.decision}</span> {r.reason}{" "}
                <span className="muted">{new Date(r.created).toLocaleString()}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      {next && (
        <p>
          <a href={href.finding(next.id)}>Next open finding →</a>
        </p>
      )}
    </section>
  );
}

function SideCard(p: { title: string; side: Side; value: unknown; sources: SourceRef[] }) {
  return (
    <div className={`card side ${p.side}`}>
      <h2>{p.title}</h2>
      <div className="big">{p.value === undefined ? <span className="muted">—</span> : formatValue(p.value)}</div>
      <ul className="sources">
        {p.sources.map((s, i) => (
          <li key={i}>{describeSource(s)}</li>
        ))}
        {p.sources.length === 0 && <li className="muted">no source on this side</li>}
      </ul>
    </div>
  );
}

function PagePreview({ upload, source }: { upload: number; source: SourceRef }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    let href = "";
    fetchBlob(pageUrl(upload, source.page!))
      .then((b) => setUrl((href = URL.createObjectURL(b))))
      .catch(() => setUrl(null));
    return () => URL.revokeObjectURL(href);
  }, [upload, source.page]);
  const [x0, top, x1, bottom] = source.bbox!;
  const pad = 3;
  return (
    <figure className="preview">
      <div className="page">
        {url && <img src={url} alt={`${source.file} page ${source.page}`} />}
        <div
          className="box"
          style={{
            left: (x0 - pad) * PAGE_SCALE,
            top: (top - pad) * PAGE_SCALE,
            width: (x1 - x0 + 2 * pad) * PAGE_SCALE,
            height: (bottom - top + 2 * pad) * PAGE_SCALE,
          }}
        />
      </div>
      <figcaption>{describeSource(source)}</figcaption>
    </figure>
  );
}

function ReviewForm({ finding, onDone }: { finding: FindingDetail; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  if (finding.status !== "fail" && finding.status !== "not_checked") return null;
  async function decide(decision: "accept" | "dismiss") {
    try {
      await api.review(finding.id, decision, reason);
      setReason("");
      setError(null);
      onDone();
    } catch (e) {
      setError(String(e));
    }
  }
  return (
    <div className="card review">
      <h2>Review</h2>
      <p className="muted">
        Accept: the finding is right and needs action. Dismiss: it does not apply; say why.
      </p>
      <textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (needed to dismiss)" />
      <div className="row">
        <button onClick={() => decide("accept")}>Accept</button>
        <button className="secondary" onClick={() => decide("dismiss")} disabled={!reason.trim()}>
          Dismiss
        </button>
      </div>
      {error && <p className="error">{error}</p>}
    </div>
  );
}

function Explain({ id }: { id: number }) {
  const state = useLoad(assist.state, []);
  const [text, setText] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setText(null), [id]);
  if (!state.data?.enabled) return null;
  return (
    <div className="explain">
      {text ? (
        <p>
          {text} <span className="muted small">(written by a language model; the finding above is what counts)</span>
        </p>
      ) : (
        <button
          className="secondary"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              setText((await assist.explain(id)).explanation);
              setError(null);
            } catch (e) {
              setError(String(e));
            }
            setBusy(false);
          }}
        >
          {busy ? "Explaining…" : "Explain in plain words"}
        </button>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  );
}
