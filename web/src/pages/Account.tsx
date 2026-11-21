import { useState } from "react";
import { account, ApiError, type ActivityEvent, api, setToken, type User } from "../api";
import { href } from "../route";
import { useLoad } from "../useLoad";

const message = (e: unknown) => (e instanceof ApiError ? e.message : String(e));

export function Login({ onDone }: { onDone: () => void }) {
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [token, setTokenValue] = useState<string | null>(null);
  return (
    <section className="login card">
      <h1>Sign in</h1>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(null);
          try {
            await account.login(name.trim(), password);
            onDone();
          } catch (err) {
            setError(message(err));
          }
          setBusy(false);
        }}
      >
        <label>
          Name
          <input autoFocus autoComplete="username" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label>
          Password
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={busy || !name.trim() || !password}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
      <p className="muted small">Forgot your password? Ask your Ludwig admin to set a new one.</p>
      {token === null ? (
        <button className="link small" onClick={() => setTokenValue("")}>
          Use an access token instead
        </button>
      ) : (
        <form
          className="row"
          onSubmit={(e) => {
            e.preventDefault();
            setToken(token);
            onDone();
          }}
        >
          <input type="password" value={token} onChange={(e) => setTokenValue(e.target.value)} placeholder="token" />
          <button type="submit">Use</button>
        </form>
      )}
    </section>
  );
}

export function Users({ me }: { me: User | null }) {
  const users = useLoad(account.users, []);
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [admin, setAdmin] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resetFor, setResetFor] = useState<number | null>(null);
  const [newPassword, setNewPassword] = useState("");

  async function change(id: number, c: Parameters<typeof account.changeUser>[1]) {
    setError(null);
    try {
      await account.changeUser(id, c);
      users.reload();
      return true;
    } catch (e) {
      setError(message(e));
      return false;
    }
  }

  return (
    <section>
      <h1>Users</h1>
      <p className="muted">
        Admins add people and set their passwords. Ludwig sends no email: give each person their password yourself.
        Deactivating someone signs them out everywhere; their reviews keep their name.
      </p>
      {users.data?.length === 0 && (
        <p className="notice">
          Nobody can sign in yet, so this instance is open to anyone who reaches it. The first person you add becomes
          an admin, and from then on everyone must sign in.
        </p>
      )}
      {(error || users.error) && <p className="error">{error || users.error}</p>}
      <table className="grid">
        <thead>
          <tr>
            <th>Name</th>
            <th>Role</th>
            <th>Status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {users.data?.map((u) => (
            <tr key={u.id}>
              <td>{u.name}</td>
              <td>{u.admin ? "admin" : "member"}</td>
              <td>{u.active ? "active" : <span className="muted">deactivated</span>}</td>
              <td className="actions-cell">
                {resetFor === u.id ? (
                  <form
                    className="row"
                    onSubmit={async (e) => {
                      e.preventDefault();
                      if (await change(u.id, { password: newPassword })) {
                        setResetFor(null);
                        setNewPassword("");
                      }
                    }}
                  >
                    <input
                      type="password"
                      autoComplete="new-password"
                      placeholder="new password (10+ characters)"
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                    />
                    <button type="submit" disabled={newPassword.length < 10}>
                      Set
                    </button>
                    <button type="button" className="secondary" onClick={() => setResetFor(null)}>
                      Cancel
                    </button>
                  </form>
                ) : (
                  <>
                    <button className="link" onClick={() => setResetFor(u.id)}>
                      set password
                    </button>
                    {me?.id !== u.id && (
                      <>
                        <button className="link" onClick={() => change(u.id, { active: !u.active })}>
                          {u.active ? "deactivate" : "activate"}
                        </button>
                        <button className="link" onClick={() => change(u.id, { admin: !u.admin })}>
                          {u.admin ? "make member" : "make admin"}
                        </button>
                      </>
                    )}
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Add a person</h2>
      <form
        className="row"
        onSubmit={async (e) => {
          e.preventDefault();
          setError(null);
          try {
            await account.addUser(name.trim(), password, admin);
            setName("");
            setPassword("");
            setAdmin(false);
            users.reload();
          } catch (err) {
            setError(message(err));
          }
        }}
      >
        <input placeholder="name" autoComplete="off" value={name} onChange={(e) => setName(e.target.value)} />
        <input
          type="password"
          autoComplete="new-password"
          placeholder="password (10+ characters)"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <label>
          <input type="checkbox" checked={admin} onChange={(e) => setAdmin(e.target.checked)} /> admin
        </label>
        <button type="submit" disabled={!name.trim() || password.length < 10}>
          Add
        </button>
      </form>
    </section>
  );
}

export function describe(e: ActivityEvent): string {
  const d = e.detail as Record<string, unknown>;
  const parts: string[] = [];
  if (d.filename) parts.push(String(d.filename));
  if (d.role) parts.push(`(${d.role})`);
  if (d.run) parts.push(`run ${d.run}`);
  if (d.pack) parts.push(String(d.pack));
  if (d.rule) parts.push(`${d.rule}${d.mark ? ` ${d.mark}` : ""}`);
  if (d.user) parts.push(String(d.user));
  if (Array.isArray(d.changes)) parts.push(d.changes.join(", "));
  if (d.values && typeof d.values === "object")
    parts.push(
      Object.entries(d.values as Record<string, unknown>)
        .map(([k, v]) => `${k} = ${v}`)
        .join(", "),
    );
  if (d.project) parts.push(`project ${d.project}`);
  if (Array.isArray(d.projects)) parts.push(`projects ${d.projects.join(", ")} after ${d.days} days`);
  if (d.name) parts.push(String(d.name));
  return parts.join(" · ");
}

export function ActivityList({ project }: { project?: number }) {
  const events = useLoad(() => api.activity(project), [project]);
  if (events.error) return <p className="error">{events.error}</p>;
  if (!events.data) return <p className="muted">Loading…</p>;
  if (!events.data.length) return <p className="muted">Nothing yet.</p>;
  return (
    <table className="grid compact">
      <thead>
        <tr>
          <th>When</th>
          <th>Who</th>
          <th>What</th>
          {!project && <th>Project</th>}
          <th>Detail</th>
        </tr>
      </thead>
      <tbody>
        {events.data.map((e) => (
          <tr key={e.id}>
            <td className="nowrap">{new Date(e.created).toLocaleString()}</td>
            <td>{e.user ?? <span className="muted">—</span>}</td>
            <td>{e.action}</td>
            {!project && <td>{e.project_id ? <a href={href.project(e.project_id)}>{e.project_id}</a> : ""}</td>}
            <td className="muted">{describe(e)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function Activity() {
  return (
    <section>
      <h1>Activity</h1>
      <p className="muted">Newest first: who uploaded, ran checks, reviewed findings, changed limits or managed data.</p>
      <ActivityList />
    </section>
  );
}
