# Ludwig — Web Shell (M1)

A minimal Next.js (App Router + TypeScript) front end for the Ludwig local
daemon. It is the "file is a conversation" surface from `BRIEF.md` §7 (M1): type
a prompt, watch candidates and scores stream in, see the hero render, and browse
past projects and their runs.

This is a thin client. All work happens in the Python daemon — this app only
drives its HTTP/SSE API.

## Prerequisites: run the daemon first

The web shell needs the FastAPI daemon running. From the **repo root**:

```bash
./.venv/bin/uvicorn daemon.app:app --port 8765
```

The daemon owns Blender, the agent, the filesystem and SQLite. If it is not
running, the UI shows a friendly "daemon offline" message instead of crashing.

## Run the web shell

```bash
cd web
npm install
npm run dev      # http://localhost:3000
```

For a production build:

```bash
npm run build
npm run start
```

## Configuration

The API base URL comes from `NEXT_PUBLIC_LUDWIG_API` and defaults to
`http://localhost:8765`. To point at a different daemon:

```bash
NEXT_PUBLIC_LUDWIG_API=http://localhost:9000 npm run dev
```

(Because it is a `NEXT_PUBLIC_*` variable it is inlined at build time, so set it
before `npm run build` if you are building for a non-default daemon.)

## Pages

- `/` — prompt textarea + Quick checkbox + Generate. Streams live progress
  (rounds, candidates with scores, best-so-far, hero status, logs) via SSE
  (`fetch` + a stream reader, since `EventSource` cannot POST). On completion it
  shows the hero/render image, the numeric score, the critique, and a link to
  the project. A daemon status line reports Blender and provider state.
- `/projects` — lists all projects from the daemon.
- `/projects/[id]` — the file workspace: the brief, each run's status/score,
  render/hero images, the critique, and a link to the `code` artifact (the
  scene program — the source of truth).

## Notes / tradeoffs

- **No extra dependencies.** Plain CSS (`app/globals.css`), no Tailwind, no state
  or UI libraries — fewer build failures, easier to audit.
- **Client-side data fetching.** Project lists and details are fetched in the
  browser with `cache: "no-store"` so the build never reaches out to the daemon
  and pages always reflect live daemon state.
