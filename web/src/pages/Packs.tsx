import { useEffect, useState } from "react";
import { api } from "../api";
import { href } from "../route";
import { useLoad } from "../useLoad";

export function Packs() {
  const { data, error } = useLoad(api.packs, []);
  return (
    <section>
      <h1>Rule packs</h1>
      {error && <p className="error">{error}</p>}
      <ul className="list">
        {data?.map((p) => (
          <li key={p.name}>
            <a href={href.pack(p.name)}>
              {p.name} {p.version}
            </a>
            <span className="muted"> · {p.rules} rules · {p.description}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function PackPage({ name }: { name: string }) {
  const pack = useLoad(() => api.pack(name), [name]);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const p = pack.data;

  useEffect(() => {
    if (p) setDraft(Object.fromEntries(p.limits.map((l) => [l.path, String(l.value)])));
  }, [p]);

  if (pack.error) return <p className="error">{pack.error}</p>;
  if (!p) return <p className="muted">Loading…</p>;

  const changed = p.limits.filter((l) => draft[l.path] !== undefined && Number(draft[l.path]) !== l.value);
  const invalid = p.limits.filter((l) => draft[l.path] === "" || Number.isNaN(Number(draft[l.path])));

  async function save() {
    try {
      const values = Object.fromEntries(changed.map((l) => [l.path, Number(draft[l.path])]));
      await api.setLimits(name, values, reason);
      setReason("");
      setError(null);
      setMessage(`Saved ${changed.length} limit${changed.length === 1 ? "" : "s"}. New checks use them.`);
      pack.reload();
    } catch (e) {
      setError(String(e));
      setMessage(null);
    }
  }

  return (
    <section>
      <p className="crumbs">
        <a href={href.packs()}>Packs</a> /
      </p>
      <h1>
        {p.name} {p.version}
      </h1>
      <p className="muted">{p.description}</p>
      <p className="muted small">Content hash {p.hash}</p>

      <h2>Factory limits</h2>
      {p.limits.length === 0 && <p className="muted">This pack has no limits.</p>}
      {!p.writable && p.limits.length > 0 && (
        <p className="warn">Read-only here: limits.yaml can only be changed on the server.</p>
      )}
      {p.limits.length > 0 && (
        <table className="grid">
          <thead>
            <tr>
              <th>Limit</th>
              <th>Value</th>
              <th>Meaning</th>
              <th>Used by</th>
            </tr>
          </thead>
          <tbody>
            {p.limits.map((l) => (
              <tr key={l.path}>
                <td>
                  <code>{l.path}</code>
                </td>
                <td>
                  <input
                    className="number"
                    inputMode="decimal"
                    value={draft[l.path] ?? ""}
                    disabled={!p.writable}
                    onChange={(e) => setDraft({ ...draft, [l.path]: e.target.value })}
                  />
                </td>
                <td className="muted">{l.note}</td>
                <td className="small">{l.used_by.join(", ") || <span className="muted">no rule</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {p.writable && p.limits.length > 0 && (
        <div className="card review">
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Why the change (optional, kept in the history)"
            style={{ width: "100%" }}
          />
          <div className="row">
            <button onClick={save} disabled={changed.length === 0 || invalid.length > 0}>
              Save {changed.length > 0 ? `${changed.length} change${changed.length === 1 ? "" : "s"}` : ""}
            </button>
            {invalid.length > 0 && <span className="error">Numbers only.</span>}
          </div>
          {message && <p>{message}</p>}
          {error && <p className="error">{error}</p>}
        </div>
      )}

      {p.changes.length > 0 && (
        <>
          <h2>History</h2>
          <ul className="list">
            {p.changes.map((c, i) => (
              <li key={i}>
                {Object.entries(c.values)
                  .map(([k, v]) => `${k} = ${v}`)
                  .join(", ")}{" "}
                {c.reason && <span>— {c.reason}</span>}{" "}
                <span className="muted">{new Date(c.created).toLocaleString()}</span>
              </li>
            ))}
          </ul>
        </>
      )}

      <h2>Rules</h2>
      <table className="grid">
        <tbody>
          {p.rules.map((r) => (
            <tr key={r.id}>
              <td>
                <span className={`badge ${r.severity}`}>{r.severity}</span>
              </td>
              <td>
                <code>{r.id}</code>
              </td>
              <td className="muted">{r.kind}</td>
              <td>{r.description || r.message}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
