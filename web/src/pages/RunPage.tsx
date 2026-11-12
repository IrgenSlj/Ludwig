import { useEffect, useMemo, useState } from "react";
import { api, csvUrl, download, reportUrl, type Finding } from "../api";
import { href } from "../route";
import { bySide, formatValue } from "../sides";
import { useLoad } from "../useLoad";

type Show = "open" | "unreviewed" | "all";

export function RunPage({ id }: { id: number }) {
  const run = useLoad(() => api.run(id), [id]);
  const findings = useLoad(() => api.findings(id), [id]);
  const [show, setShow] = useState<Show>("open");
  const [severity, setSeverity] = useState("");

  useEffect(() => {
    if (run.data && (run.data.status === "queued" || run.data.status === "running")) {
      const timer = setTimeout(() => {
        run.reload();
        findings.reload();
      }, 1500);
      return () => clearTimeout(timer);
    }
  }, [run.data, run.reload, findings.reload]);

  const rows = useMemo(
    () =>
      (findings.data ?? []).filter((f) => {
        if (severity && f.severity !== severity) return false;
        const open = f.status === "fail" || f.status === "not_checked";
        if (show === "open") return open;
        if (show === "unreviewed") return open && !f.review;
        return f.status !== "not_applicable";
      }),
    [findings.data, show, severity],
  );

  const r = run.data;
  const s = r?.summary;
  const pdfs = Object.keys(r?.files ?? {}).filter((n) => n.toLowerCase().endsWith(".pdf"));
  return (
    <section>
      <p className="crumbs">
        <a href={href.projects()}>Projects</a> / {r && <a href={href.project(r.project_id)}>Project</a>} /
      </p>
      <h1>Run {id}</h1>
      {(run.error || findings.error) && <p className="error">{run.error || findings.error}</p>}
      {r && (
        <p className="muted">
          {r.pack.name} {r.pack.version} · {new Date(r.created).toLocaleString()} ·{" "}
          <span className={`state ${r.status}`}>{r.status}</span>
          {r.error && <span className="error"> {r.error}</span>}
        </p>
      )}
      {s && (
        <div className="tiles">
          <Tile label="Blockers" value={s.fails_by_severity.blocker ?? 0} tone="blocker" />
          <Tile label="Warnings" value={s.fails_by_severity.warning ?? 0} tone="warning" />
          <Tile label="Not checked" value={s.not_checked} tone="muted" />
          <Tile label="Passed" value={s.by_status.pass ?? 0} tone="ok" />
          <Tile label="Elements" value={`${s.elements_covered} / ${s.elements_total}`} />
          <Tile label="Rules" value={s.rules_run} />
          <Tile label="Parse warnings" value={s.parse_warnings} />
        </div>
      )}
      {r?.status === "done" && (
        <div className="row exports">
          <span className="muted">Export:</span>
          <button className="link" onClick={() => download(reportUrl(id, "report.xlsx"), `run-${id}.xlsx`)}>
            Excel
          </button>
          <button className="link" onClick={() => download(csvUrl(id), `run-${id}-findings.csv`)}>
            CSV with reviews
          </button>
          <button className="link" onClick={() => download(reportUrl(id, "report.bcf"), `run-${id}.bcf`)}>
            BCF
          </button>
          <button className="link" onClick={() => download(reportUrl(id, "report.json"), `run-${id}.json`)}>
            JSON
          </button>
          {pdfs.map((name) => {
            const marked = `${name.replace(/\.pdf$/i, "")}.marked.pdf`;
            return (
              <button key={name} className="link" onClick={() => download(reportUrl(id, marked), marked)}>
                {marked}
              </button>
            );
          })}
        </div>
      )}
      <div className="row filters">
        {(["open", "unreviewed", "all"] as Show[]).map((v) => (
          <button key={v} className={show === v ? "chip on" : "chip"} onClick={() => setShow(v)}>
            {v === "open" ? "Open" : v === "unreviewed" ? "Not reviewed" : "All"}
          </button>
        ))}
        <select value={severity} onChange={(e) => setSeverity(e.target.value)}>
          <option value="">Every severity</option>
          <option value="blocker">Blockers</option>
          <option value="warning">Warnings</option>
          <option value="info">Info</option>
        </select>
        <span className="muted">{rows.length} findings</span>
      </div>
      <table className="grid findings">
        <thead>
          <tr>
            <th>Severity</th>
            <th>Status</th>
            <th>Mark</th>
            <th>Message</th>
            <th>Drawings</th>
            <th>Production</th>
            <th>Review</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((f) => (
            <FindingRow key={f.id} f={f} />
          ))}
        </tbody>
      </table>
    </section>
  );
}

function FindingRow({ f }: { f: Finding }) {
  const sides = bySide(f);
  return (
    <tr className={`sev-${f.severity} st-${f.status}`} onClick={() => (window.location.hash = href.finding(f.id))}>
      <td>
        <span className={`badge ${f.severity}`}>{f.severity}</span>
      </td>
      <td>{f.status.replace("_", " ")}</td>
      <td>{f.mark ?? ""}</td>
      <td>
        <a href={href.finding(f.id)}>{f.message || f.rule_id}</a>
        {f.reason && <div className="muted small">{f.reason}</div>}
      </td>
      <td>{formatValue(sides.values.architect)}</td>
      <td>{formatValue(sides.values.erp)}</td>
      <td>{f.review ? <span className={`badge ${f.review.decision}`}>{f.review.decision}</span> : ""}</td>
    </tr>
  );
}

function Tile({ label, value, tone }: { label: string; value: number | string; tone?: string }) {
  return (
    <div className={`tile ${tone ?? ""}`}>
      <div className="value">{value}</div>
      <div className="label">{label}</div>
    </div>
  );
}
