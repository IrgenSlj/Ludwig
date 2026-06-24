"use client";

import { useEffect, useState } from "react";
import { getHealth, type Health } from "./lib/api";

export default function HealthLine() {
  const [health, setHealth] = useState<Health | null>(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    let alive = true;
    getHealth()
      .then((h) => {
        if (alive) setHealth(h);
      })
      .catch(() => {
        if (alive) setOffline(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  if (offline) {
    return (
      <div className="health">
        <span className="dot off" />
        Daemon offline — start it from the repo root:{" "}
        <code>./.venv/bin/uvicorn daemon.app:app --port 8765</code>
      </div>
    );
  }

  if (!health) {
    return (
      <div className="health">
        <span className="dot off" />
        Checking daemon…
      </div>
    );
  }

  return (
    <div className="health">
      <span className="dot ok" />
      Daemon ok · Blender:{" "}
      {health.blender_found ? health.blender || "found" : "not found"} ·
      provider: {health.provider || "unknown"}
    </div>
  );
}
