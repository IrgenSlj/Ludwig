"use client";

import { useEffect } from "react";

// CDN module script for Google's <model-viewer> web component. Loaded once on the
// client (no npm dependency) — keeps the dep tree minimal and the build clean.
const MODEL_VIEWER_SRC =
  "https://unpkg.com/@google/model-viewer/dist/model-viewer.min.js";

let injected = false;

function ensureModelViewerScript() {
  if (injected || typeof document === "undefined") return;
  if (document.querySelector(`script[src="${MODEL_VIEWER_SRC}"]`)) {
    injected = true;
    return;
  }
  const script = document.createElement("script");
  script.type = "module";
  script.src = MODEL_VIEWER_SRC;
  document.head.appendChild(script);
  injected = true;
}

interface ModelViewerProps {
  /** URL to a .glb / glTF binary model. */
  src?: string | null;
  alt?: string;
  height?: number;
}

export default function ModelViewer({
  src,
  alt = "Interactive 3D model",
  height = 360,
}: ModelViewerProps) {
  useEffect(() => {
    ensureModelViewerScript();
  }, []);

  if (!src) {
    return (
      <div
        className="muted"
        style={{
          height,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          borderRadius: 8,
          background: "var(--panel-2)",
        }}
      >
        No interactive 3D preview available.
      </div>
    );
  }

  return (
    <model-viewer
      src={src}
      alt={alt}
      camera-controls
      auto-rotate
      shadow-intensity="1"
      exposure="1"
      interaction-prompt="none"
      style={{
        width: "100%",
        height,
        borderRadius: 8,
        background:
          "radial-gradient(circle at 50% 30%, #23262d 0%, #16181d 100%)",
        "--poster-color": "transparent",
      } as React.CSSProperties}
    />
  );
}
