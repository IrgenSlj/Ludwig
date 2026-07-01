# Deploying the Ludwig public demo

The demo is the **direct-manipulation core** — load a gallery part; drag its dimensions or **grab a 3D
face and pull it**; take a **live section cut**; on a sketch part, toggle **2D** and drag a sketch
dimension to re-solve the constraints live; then **download the verified STEP / IFC / shop DXF / section
DXF** (and see the conventioned shop drawing inline) — all running with **no inference** (the R3–R34
no-LLM evaluator + constraint solver). So it costs ~nothing per visitor. It runs in **demo mode**
(`LUDWIG_DEMO=1`): no remote code execution, no generation, only numeric edits to trusted seeds (see
`webapp/safety.py`). Generation ("describe a part") is the local / BYO-key experience, never exposed on
the public box.

## What ships
- `Dockerfile` — `python:3.12-slim` + the headless GL/X11 libs OCP/vtk need + `pip install cadquery
  ezdxf ifcopenshell matplotlib PyYAML`. ~1.5 GB image. Builds with a smoke test (`import cadquery`) so a
  missing `.so` fails the build, not production. (OCP wheels pin CPython ≤3.12 — the image pins 3.12; the
  dev box runs 3.14 via `.venv`. `matplotlib` renders the shop-drawing/section PNG previews; scipy/numpy
  are intentionally omitted — the sketch solver's pure-Python fallback covers the demo.)
- Binds `0.0.0.0` and honors `$PORT` (both set in the image). Defaults to demo mode.

## Option A — Google Cloud Run (recommended; ~$0/month)
Scale-to-zero, 2M req/mo free tier, image size irrelevant to cold start, ~10 s cold start (the OCP
import). Best when "free" matters more than instant first paint.
```sh
gcloud run deploy ludwig-demo \
  --source . \
  --region europe-west1 \
  --memory 2Gi --cpu 1 \
  --allow-unauthenticated \
  --set-env-vars LUDWIG_DEMO=1
# (Cloud Run injects $PORT=8080 and builds the Dockerfile for you.)
```
Set `--min-instances 0` (default) for $0; a warm `--min-instances 1` is ~$65/mo — avoid unless cold
starts hurt a live pitch.

## Option B — Hetzner CX22 (always-on, no cold start; ~$4.59/month)
Cheapest reliable always-on. You manage the box.
```sh
# on a fresh CX22 (2 vCPU / 4 GB, Docker installed):
git clone <repo> ludwig && cd ludwig
docker build -t ludwig-demo .
docker run -d --restart unless-stopped -p 80:8080 -e LUDWIG_DEMO=1 ludwig-demo
```
Put Caddy/Traefik in front for TLS + a domain.

## Not recommended
Render/Railway free tiers cap at 0.5 GB RAM — too tight for the OCP import + tessellation (OOM risk).
Fly.io `shared-cpu-1x@1GB` (~$5.78/mo always-on, or scale-to-zero) is a fine middle option.

## Notes / follow-ups
- **Artifacts (`out/`)** are written per edit and served from `/out/`. Concurrent visitors editing the
  same seed share a filename (e.g. `bracket.step`) — last-write-wins, fine for a demo; namespace by
  session before heavy traffic.
- **Generation stays off in public.** The wow ("I dragged it → got a fab-ready STEP") needs no AI; the
  generative "describe a part" is the reason to run locally / sign up — keep it that way (BYO inference).
- **WASM path (later):** OCP.wasm + Pyodide can move the kernel into the browser (→ truly $0 server),
  but it's a real porting project (50–70 MB download, vtk stripped), not a config flag.
