import { useEffect, useState } from "react";
import { account, type Me } from "./api";
import { Activity, Login, Users } from "./pages/Account";
import { FindingPage } from "./pages/FindingPage";
import { PackPage, Packs } from "./pages/Packs";
import { ProjectPage } from "./pages/ProjectPage";
import { Projects } from "./pages/Projects";
import { RunPage } from "./pages/RunPage";
import { href, useRoute } from "./route";

export function App() {
  const route = useRoute();
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);
  const check = () =>
    account
      .me()
      .then((m) => {
        setMe(m);
        setError(null);
      })
      .catch((e) => setError(String(e)));
  useEffect(() => {
    check();
    const onOut = () => check();
    window.addEventListener("ludwig-signed-out", onOut);
    return () => window.removeEventListener("ludwig-signed-out", onOut);
  }, []);

  if (!me) return <main>{error ? <p className="error">{error}</p> : <p className="muted">Loading…</p>}</main>;
  if (!me.signed_in)
    return (
      <main>
        <Login onDone={check} noUsers={me.no_users} />
      </main>
    );

  const admin = !me.login_required || me.user?.admin;
  return (
    <>
      <header className="top">
        <a href={href.projects()} className="brand">
          Ludwig
        </a>
        <span className="tagline">pre-production check</span>
        <a href={href.projects()}>Projects</a>
        <a href={href.packs()}>Packs</a>
        <a href={href.activity()}>Activity</a>
        {admin && <a href={href.users()}>Users</a>}
        <span className="who">
          {me.name && <span className="muted">{me.name}</span>}
          {me.user && (
            <button
              className="link"
              onClick={async () => {
                await account.logout();
                check();
              }}
            >
              Sign out
            </button>
          )}
        </span>
      </header>
      <main>
        {route.page === "projects" && <Projects />}
        {route.page === "project" && <ProjectPage id={route.id} />}
        {route.page === "run" && <RunPage id={route.id} />}
        {route.page === "finding" && <FindingPage id={route.id} />}
        {route.page === "packs" && <Packs />}
        {route.page === "pack" && <PackPage name={route.name} />}
        {route.page === "activity" && <Activity />}
        {route.page === "users" && (admin ? <Users me={me.user} /> : <p>Only an admin can manage users.</p>)}
      </main>
    </>
  );
}
