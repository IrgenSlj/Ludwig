import { useState } from "react";
import { api } from "../api";
import { href } from "../route";
import { useLoad } from "../useLoad";

export function Projects() {
  const { data, error, reload, setError } = useLoad(api.projects, []);
  const [name, setName] = useState("");
  return (
    <section>
      <h1>Projects</h1>
      {error && <p className="error">{error}</p>}
      <form
        className="row"
        onSubmit={async (e) => {
          e.preventDefault();
          if (!name.trim()) return;
          try {
            const project = await api.createProject(name.trim());
            window.location.hash = href.project(project.id);
          } catch (err) {
            setError(String(err));
          }
          reload();
        }}
      >
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="New project name" />
        <button type="submit" disabled={!name.trim()}>
          Create
        </button>
      </form>
      {data && data.length === 0 && <p className="muted">No projects yet.</p>}
      <ul className="list">
        {data?.map((p) => (
          <li key={p.id}>
            <a href={href.project(p.id)}>{p.name}</a>
            <span className="muted"> · created {new Date(p.created).toLocaleDateString()}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
