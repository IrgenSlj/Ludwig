# Ludwig public demo image — the secure, $0-inference direct-manipulation demo (LUDWIG_DEMO=1).
# pip-on-slim is smaller + simpler than conda for getting cadquery/OCP importable (~1.4 GB image).
# OCP/vtk wheels pin CPython <=3.12, so we pin 3.12 here (the dev box runs 3.14 via .venv).
FROM python:3.12-slim-bookworm

# OCP + vtk dlopen GL/X11 libs even headless; missing them = "libGL.so.1: cannot open shared object".
# (bookworm dropped libgl1-mesa-glx — use the new names.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglx-mesa0 libglu1-mesa \
        libxrender1 libxext6 libsm6 libice6 libx11-6 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install the kernel + backends first (their own layer) so app edits don't bust the heavy cache.
RUN pip install --no-cache-dir \
        "cadquery>=2.8" \
        "ezdxf>=1.1" \
        "ifcopenshell>=0.8" \
        "matplotlib>=3.7" \
        "PyYAML>=6.0"
# matplotlib renders the conventioned shop-drawing + section PNG previews the studio shows (best-effort;
# the DXF/STEP/IFC deliverables generate without it). The sketch solver uses its pure-Python Gauss-Newton
# fallback here — scipy/numpy are intentionally NOT installed (the demo needs neither).

COPY . .

# Public-safe by default: demo mode (no RCE, no inference), bind all interfaces, honor the platform PORT.
ENV LUDWIG_DEMO=1 \
    LUDWIG_HOST=0.0.0.0 \
    PORT=8080
EXPOSE 8080

# Fail fast if the kernel didn't import (catches a missing .so before traffic hits).
RUN python -c "import cadquery; print('cadquery', cadquery.__version__, 'OK')"

CMD ["sh", "-c", "python cli.py --serve ${PORT}"]
