"use client";

/**
 * Phase 1 environment check.
 *
 * This is a Client Component (it uses state + useEffect) that calls the FastAPI
 * backend on mount and reports whether the frontend↔backend wire is connected.
 * It proves CORS is configured and the API URL env var resolves. Real product
 * pages replace this in later phases.
 */

import { useEffect, useState } from "react";
import { api, type PingResponse } from "@/lib/api";

type Status = "loading" | "connected" | "error";

const STATUS_META: Record<Status, { label: string; dot: string; text: string }> = {
  loading: { label: "Checking…", dot: "bg-amber-400", text: "text-amber-400" },
  connected: { label: "Connected", dot: "bg-emerald-400", text: "text-emerald-400" },
  error: { label: "Not reachable", dot: "bg-red-400", text: "text-red-400" },
};

export default function Home() {
  const [status, setStatus] = useState<Status>("loading");
  const [message, setMessage] = useState<string>("");

  useEffect(() => {
    api
      .ping()
      .then((data: PingResponse) => {
        setMessage(data.message);
        setStatus("connected");
      })
      .catch((err: unknown) => {
        setMessage(err instanceof Error ? err.message : "Unknown error");
        setStatus("error");
      });
  }, []);

  const meta = STATUS_META[status];

  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-zinc-950 px-6 text-zinc-100">
      <div className="w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-900/60 p-8 shadow-xl backdrop-blur">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-lg font-bold">
            F
          </div>
          <div>
            <h1 className="text-lg font-semibold tracking-tight">FitMind AI</h1>
            <p className="text-xs text-zinc-500">Phase 1 · Environment check</p>
          </div>
        </div>

        <div className="rounded-xl border border-zinc-800 bg-zinc-950/50 p-4">
          <div className="flex items-center justify-between">
            <span className="text-sm text-zinc-400">Backend status</span>
            <span className={`flex items-center gap-2 text-sm font-medium ${meta.text}`}>
              <span className={`h-2 w-2 rounded-full ${meta.dot} ${status === "loading" ? "animate-pulse" : ""}`} />
              {meta.label}
            </span>
          </div>

          <div className="mt-4 space-y-2 border-t border-zinc-800 pt-4 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-zinc-500">API URL</span>
              <code className="text-zinc-300">{api.baseUrl}</code>
            </div>
            <div className="flex items-center justify-between gap-4">
              <span className="text-zinc-500">Response</span>
              <code className={`truncate ${status === "error" ? "text-red-400" : "text-zinc-300"}`}>
                {message || "—"}
              </code>
            </div>
          </div>
        </div>

        <p className="mt-6 text-center text-xs text-zinc-600">
          Green means the Next.js frontend reached the FastAPI backend.
        </p>
      </div>
    </main>
  );
}
