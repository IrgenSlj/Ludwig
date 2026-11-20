import { useEffect, useState } from "react";
import { api, ApiError, type Upload } from "../api";
import {
  blockers,
  ELEMENT_TYPES,
  FIELDS,
  hints,
  type Mapping,
  type Preview,
  PROPS,
  type Proposal,
  setColumn,
  setProp,
  setTypeColumn,
  setTypeValue,
  setValueTranslation,
  TYPE_LABELS,
  updateProp,
} from "../mapping";

const message = (e: unknown) => (e instanceof ApiError ? e.message : String(e));

// Which column holds what: proposed by the service from the headers, confirmed here.
export function MappingEditor({ file, onDone }: { file: Upload; onDone: (saved: boolean) => void }) {
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [mapping, setMapping] = useState<Mapping | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [extra, setExtra] = useState(false);

  function load(headerRow?: number, sheet?: string) {
    api
      .columns(file.id, headerRow, sheet)
      .then((p) => {
        setProposal(p);
        setMapping(p.mapping);
        setError(null);
      })
      .catch((e) => setError(message(e)));
  }
  useEffect(() => load(), [file.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Read the file with the current mapping after each change, so problems show before saving.
  useEffect(() => {
    if (!mapping || blockers(mapping).length) {
      setPreview(null);
      return;
    }
    const timer = setTimeout(() => {
      api
        .mapping(file.id, mapping, false)
        .then((p) => {
          setPreview(p);
          setError(null);
        })
        .catch((e) => setError(message(e)));
    }, 300);
    return () => clearTimeout(timer);
  }, [file.id, mapping]);

  async function save() {
    if (!mapping) return;
    setSaving(true);
    try {
      await api.mapping(file.id, mapping, true);
      onDone(true);
    } catch (e) {
      setError(message(e));
      setSaving(false);
    }
  }

  if (!proposal || !mapping) {
    return <div className="mapping card">{error ? <p className="error">{error}</p> : <p className="muted">Reading columns…</p>}</div>;
  }

  const headers = proposal.headers.filter(Boolean);
  const examples = (h: string | undefined) => (h ? (proposal.values[h] ?? []).slice(0, 3).join(" · ") : "");
  const typeColumn = typeof mapping.type === "string" ? "" : mapping.type.column;
  const stop = blockers(mapping);
  const shownProps = PROPS.filter((p, i) => extra || i < 3 || mapping.props?.[p.key]);

  const columnSelect = (value: string | undefined, onChange: (h: string) => void) => (
    <select value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
      <option value="">— not in this file</option>
      {headers.map((h) => (
        <option key={h} value={h}>
          {h}
        </option>
      ))}
    </select>
  );

  return (
    <div className="mapping card">
      <h2>Columns of {file.filename}</h2>
      <p className="muted small">
        Ludwig guessed which column holds what from the headers. Check each line against the example values, then
        save. The mapping is kept and offered again for files with the same columns.
      </p>

      {proposal.previous.length > 0 && (
        <p className="notice">
          Same columns as <strong>{proposal.previous[0].filename}</strong> (project {proposal.previous[0].project}).{" "}
          <button className="link" onClick={() => setMapping(proposal.previous[0].mapping)}>
            Use that mapping
          </button>
        </p>
      )}

      <div className="row">
        {proposal.sheets.length > 1 && (
          <label>
            Sheet{" "}
            <select value={mapping.sheet ?? proposal.sheets[0]} onChange={(e) => load(undefined, e.target.value)}>
              {proposal.sheets.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
        )}
        <label>
          Header row{" "}
          <input
            className="number"
            type="number"
            min={1}
            value={mapping.header_row}
            onChange={(e) => {
              const row = Number(e.target.value);
              if (row >= 1) load(row, mapping.sheet);
            }}
          />
        </label>
        <label>
          Sizes in{" "}
          <select value={mapping.units} onChange={(e) => setMapping({ ...mapping, units: e.target.value as Mapping["units"] })}>
            <option value="mm">mm</option>
            <option value="cm">cm</option>
            <option value="m">m</option>
          </select>
        </label>
      </div>

      <table className="grid compact">
        <thead>
          <tr>
            <th>Ludwig field</th>
            <th>Column in the file</th>
            <th>Example values</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Element type</td>
            <td>
              <select value={typeColumn} onChange={(e) => setMapping(setTypeColumn(mapping, e.target.value))}>
                <option value="">— every row is one kind</option>
                {headers.map((h) => (
                  <option key={h} value={h}>
                    {h}
                  </option>
                ))}
              </select>{" "}
              {typeof mapping.type === "string" && (
                <select value={mapping.type} onChange={(e) => setMapping({ ...mapping, type: e.target.value as Mapping["type"] })}>
                  {ELEMENT_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {TYPE_LABELS[t]}
                    </option>
                  ))}
                </select>
              )}
            </td>
            <td className="muted">{examples(typeColumn)}</td>
          </tr>
          {typeof mapping.type !== "string" &&
            (proposal.values[typeColumn] ?? []).map((raw) => (
              <tr key={`type-${raw}`} className="sub">
                <td />
                <td colSpan={2}>
                  “{raw}” is{" "}
                  <select
                    value={(mapping.type as { values: Record<string, string> }).values[raw] ?? ""}
                    onChange={(e) => setMapping(setTypeValue(mapping, raw, e.target.value as never))}
                  >
                    <option value="">not an element (skip the row)</option>
                    {ELEMENT_TYPES.map((t) => (
                      <option key={t} value={t}>
                        {TYPE_LABELS[t]}
                      </option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
          {FIELDS.map((f) => (
            <tr key={f.key}>
              <td>{f.label}</td>
              <td>{columnSelect(mapping.columns[f.key], (h) => setMapping(setColumn(mapping, f.key, h)))}</td>
              <td className="muted">{examples(mapping.columns[f.key])}</td>
            </tr>
          ))}
          {shownProps.map((p) => {
            const spec = mapping.props?.[p.key];
            return [
              <tr key={p.key}>
                <td>{p.label}</td>
                <td>
                  {columnSelect(spec?.column, (h) => setMapping(setProp(mapping, p.key, h)))}
                  {spec && p.key === "fire_rating_min" && (
                    <label className="small">
                      {" "}
                      <input
                        type="checkbox"
                        checked={spec.default === 0}
                        onChange={(e) => setMapping(updateProp(mapping, p.key, { default: e.target.checked ? 0 : undefined }))}
                      />{" "}
                      empty cell means no fire rating
                    </label>
                  )}
                </td>
                <td className="muted">{examples(spec?.column)}</td>
              </tr>,
              ...(spec && p.key === "opening_direction"
                ? (proposal.values[spec.column] ?? []).map((raw) => (
                    <tr key={`dir-${raw}`} className="sub">
                      <td />
                      <td colSpan={2}>
                        “{raw}” means{" "}
                        <select
                          value={spec.values?.[raw] ?? ""}
                          onChange={(e) => setMapping(setValueTranslation(mapping, p.key, raw, e.target.value))}
                        >
                          <option value="">“{raw}” as written</option>
                          <option value="left">left</option>
                          <option value="right">right</option>
                        </select>
                      </td>
                    </tr>
                  ))
                : []),
            ];
          })}
        </tbody>
      </table>
      {!extra && (
        <button className="link small" onClick={() => setExtra(true)}>
          More properties (burglary class, U-value, sound, threshold, grille, material, finish)
        </button>
      )}

      {proposal.sample.length > 0 && (
        <details className="small">
          <summary>First rows of the file</summary>
          <div className="scroll">
            <table className="grid compact">
              <thead>
                <tr>
                  {proposal.headers.map((h, i) => (
                    <th key={i}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {proposal.sample.map((r, i) => (
                  <tr key={i}>
                    {r.map((c, j) => (
                      <td key={j}>{c}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}

      {error && <p className="error">{error}</p>}
      {stop.map((s) => (
        <p key={s} className="warn">
          {s}
        </p>
      ))}
      {hints(mapping).map((s) => (
        <p key={s} className="muted small">
          {s}
        </p>
      ))}
      {preview && (
        <div className="small">
          <p>
            Reads <strong>{preview.elements}</strong> positions ({preview.quantity} pieces).
          </p>
          {preview.warnings.length > 0 && (
            <ul className="list warn">
              {preview.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
              {preview.more_warnings > 0 && <li>and {preview.more_warnings} more</li>}
            </ul>
          )}
        </div>
      )}
      <div className="row">
        <button onClick={save} disabled={saving || stop.length > 0 || !preview}>
          {saving ? "Saving…" : "Save mapping"}
        </button>
        <button className="secondary" onClick={() => onDone(false)}>
          Cancel
        </button>
      </div>
    </div>
  );
}
