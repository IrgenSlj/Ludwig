import { useState } from "react";
import { setToken } from "./api";
import { FindingPage } from "./pages/FindingPage";
import { PackPage, Packs } from "./pages/Packs";
import { ProjectPage } from "./pages/ProjectPage";
import { Projects } from "./pages/Projects";
import { RunPage } from "./pages/RunPage";
import { href, useRoute } from "./route";

export function App() {
  const route = useRoute();
  return (
    <>
      <header className="top">
        <a href={href.projects()} className="brand">
          Ludwig
        </a>
        <span className="tagline">pre-production check</span>
        <a href={href.projects()}>Projects</a>
        <a href={href.packs()}>Packs</a>
        <TokenField />
      </header>
      <main>
        {route.page === "projects" && <Projects />}
        {route.page === "project" && <ProjectPage id={route.id} />}
        {route.page === "run" && <RunPage id={route.id} />}
        {route.page === "finding" && <FindingPage id={route.id} />}
        {route.page === "packs" && <Packs />}
        {route.page === "pack" && <PackPage name={route.name} />}
      </main>
    </>
  );
}

function TokenField() {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  if (!open)
    return (
      <button className="link token" onClick={() => setOpen(true)}>
        Access token
      </button>
    );
  return (
    <form
      className="token"
      onSubmit={(e) => {
        e.preventDefault();
        setToken(value);
        setOpen(false);
        window.location.reload();
      }}
    >
      <input type="password" value={value} onChange={(e) => setValue(e.target.value)} placeholder="token" />
      <button type="submit">Use</button>
    </form>
  );
}
