import { useEffect, useMemo, useState } from "react";
import { api, type Upload } from "../api";
import { href } from "../route";
import { useLoad } from "../useLoad";

const NEEDS_MAPPING = /\.(xlsx|xlsm|csv|pdf)$/i;

export function ProjectPage({ id }: { id: number }) {
  const project = useLoad(() => api.project(id), [id]);
  const uploads = useLoad(() => api.uploads(id), [id]);
  const runs = useLoad(() => api.runs(id), [id]);
  const packs = useLoad(api.packs, []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [pack, setPack] = useState("");

  const files = useMemo(() => (uploads.data ?? []).filter((u) => u.role !== "mapping"), [uploads.data]);
  const mappingOf = useMemo(() => {
    const m = new Map<number, Upload>();
    for (const u of uploads.data ?? []) if (u.role === "mapping" && u.for_upload) m.set(u.for_upload, u);
    return m;
  }, [uploads.data]);

  useEffect(() => setSelected(new Set(files.map((f) => f.id))), [files]);
  useEffect(() => {
    if (!pack && packs.data?.length) setPack(packs.data[0].name);
  }, [packs.data, pack]);
  useEffect(() => {
    const active = runs.data?.some((r) => r.status === "queued" || r.status === "running");
    if (!active) return;
    const timer = setTimeout(runs.reload, 1500);
    return () => clearTimeout(timer);
  }, [runs.data, runs.reload]);

  async function send(list: FileList | null, role: Upload["role"], forUpload?: number) {
    if (!list?.length) return;
    setBusy(true);
    setError(null);
    try {
      for (const file of Array.from(list)) await api.upload(id, file, role, forUpload);
    } catch (e) {
      setError(String(e));
    }
    setBusy(false);
    uploads.reload();
  }

  async function start() {
    const chosen = files.filter((f) => selected.has(f.id));
    const ids = chosen.flatMap((f) => [f.id, ...(mappingOf.has(f.id) ? [mappingOf.get(f.id)!.id] : [])]);
    try {
      await api.startRun(id, pack, ids);
      runs.reload();
    } catch (e) {
      setError(String(e));
    }
  }

  const architect = files.filter((f) => f.role === "architect");
  const erp = files.filter((f) => f.role === "erp");
  const missing = files.filter(
    (f) => selected.has(f.id) && (f.role === "erp" || NEEDS_MAPPING.test(f.filename)) && !mappingOf.has(f.id),
  );
  const chosenErp = erp.filter((f) => selected.has(f.id)).length;
  const canRun =
    pack && architect.some((f) => selected.has(f.id)) && missing.length === 0 && chosenErp <= 1 && !busy;

  return (
    <section>
      <p className="crumbs">
        <a href={href.projects()}>Projects</a> /
      </p>
      <h1>{project.data?.name ?? "Project"}</h1>
      {(error || uploads.error || project.error) && (
        <p className="error">{error || uploads.error || project.error}</p>
      )}

      <div className="columns">
        <FileGroup
          title="Architect documents"
          hint="IFC, DXF, schedules (.xlsx, .csv) and vector PDF schedules"
          accept=".ifc,.dxf,.xlsx,.xlsm,.csv,.pdf"
          multiple
          files={architect}
          mappingOf={mappingOf}
          selected={selected}
          setSelected={setSelected}
          onFiles={(l) => send(l, "architect")}
          onMapping={(l, f) => send(l, "mapping", f)}
          busy={busy}
        />
        <FileGroup
          title="Production export"
          hint="The export from the production software, with its column mapping"
          accept=".xlsx,.xlsm,.csv"
          files={erp}
          mappingOf={mappingOf}
          selected={selected}
          setSelected={setSelected}
          onFiles={(l) => send(l, "erp")}
          onMapping={(l, f) => send(l, "mapping", f)}
          busy={busy}
        />
      </div>

      <h2>Check</h2>
      <div className="row">
        <select value={pack} onChange={(e) => setPack(e.target.value)}>
          {packs.data?.map((p) => (
            <option key={p.name} value={p.name}>
              {p.name} {p.version} · {p.rules} rules
            </option>
          ))}
        </select>
        <button onClick={start} disabled={!canRun}>
          Run check
        </button>
      </div>
      {missing.length > 0 && (
        <p className="warn">Needs a column mapping: {missing.map((f) => f.filename).join(", ")}</p>
      )}
      {chosenErp > 1 && <p className="warn">Choose one production export per check.</p>}

      <h2>Runs</h2>
      {runs.data?.length === 0 && <p className="muted">No checks run yet.</p>}
      <table className="grid">
        <tbody>
          {runs.data
            ?.slice()
            .reverse()
            .map((r) => (
              <tr key={r.id}>
                <td>
                  <a href={href.run(r.id)}>Run {r.id}</a>
                </td>
                <td>{new Date(r.created).toLocaleString()}</td>
                <td>
                  {r.pack.name} {r.pack.version}
                </td>
                <td className={`state ${r.status}`}>{r.status}</td>
                <td>
                  {r.summary
                    ? `${r.summary.fails_by_severity.blocker ?? 0} blockers · ${
                        r.summary.fails_by_severity.warning ?? 0
                      } warnings · ${r.summary.not_checked} not checked`
                    : r.error}
                </td>
              </tr>
            ))}
        </tbody>
      </table>
    </section>
  );
}

interface GroupProps {
  title: string;
  hint: string;
  accept: string;
  multiple?: boolean;
  files: Upload[];
  mappingOf: Map<number, Upload>;
  selected: Set<number>;
  setSelected: (s: Set<number>) => void;
  onFiles: (l: FileList | null) => void;
  onMapping: (l: FileList | null, forUpload: number) => void;
  busy: boolean;
}

function FileGroup(p: GroupProps) {
  return (
    <div className="card">
      <h2>{p.title}</h2>
      <p className="muted">{p.hint}</p>
      <label className="button">
        {p.busy ? "Uploading…" : "Add files"}
        <input
          type="file"
          hidden
          accept={p.accept}
          multiple={p.multiple}
          disabled={p.busy}
          onChange={(e) => {
            p.onFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </label>
      <ul className="files">
        {p.files.map((f) => {
          const mapping = p.mappingOf.get(f.id);
          return (
            <li key={f.id}>
              <label>
                <input
                  type="checkbox"
                  checked={p.selected.has(f.id)}
                  onChange={(e) => {
                    const next = new Set(p.selected);
                    if (e.target.checked) next.add(f.id);
                    else next.delete(f.id);
                    p.setSelected(next);
                  }}
                />{" "}
                {f.filename}
              </label>
              <span className="muted"> {(f.size / 1024).toFixed(0)} kB</span>
              <label className="link small">
                {mapping ? `mapping: ${mapping.filename}` : "add mapping"}
                <input
                  type="file"
                  hidden
                  accept=".yaml,.yml"
                  onChange={(e) => {
                    p.onMapping(e.target.files, f.id);
                    e.target.value = "";
                  }}
                />
              </label>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
