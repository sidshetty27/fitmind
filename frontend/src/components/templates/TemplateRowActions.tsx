"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@clerk/nextjs";

import { api } from "@/lib/api";
import { normalizeApiError } from "@/lib/apiErrors";
import { todayISO } from "@/lib/dates";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";

/**
 * "Log now" and delete, for a row in the template list.
 *
 * Log now calls `POST /api/templates/{id}/apply`, which creates the workout
 * server-side in a single request and returns it. We then land the user in that
 * workout's editor: the plan is recorded, and the numbers they actually hit are
 * what they came to fill in.
 *
 * The date is resolved client-side via `todayISO()` because "today" is a fact
 * about the user's timezone, not the server's — the same reason the backend
 * stores `performed_on` as a DATE and lets the client decide the day.
 */
export function TemplateRowActions({
  templateId,
  name,
  exerciseCount,
}: {
  templateId: string;
  name: string;
  exerciseCount: number;
}) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [applying, setApplying] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function logNow() {
    setApplying(true);
    setError(null);
    try {
      const token = await getToken();
      const workout = await api.templates.apply(token, templateId, {
        performed_on: todayISO(),
      });
      router.refresh();
      router.push(`/dashboard/workouts/${workout.id}`);
    } catch (err) {
      setError(normalizeApiError(err).formError);
      setApplying(false);
    }
  }

  async function handleDelete() {
    if (
      !window.confirm(
        `Delete the "${name}" template? Workouts already logged from it are not affected.`,
      )
    ) {
      return;
    }
    setDeleting(true);
    setError(null);
    try {
      const token = await getToken();
      await api.templates.delete(token, templateId);
      router.refresh();
    } catch (err) {
      setError(normalizeApiError(err).formError);
      setDeleting(false);
    }
  }

  const busy = applying || deleting;

  return (
    <div className="flex items-center gap-2">
      {error && (
        <span role="alert" className="text-xs text-red-400">
          {error}
        </span>
      )}

      <Button
        size="sm"
        pending={applying}
        // An empty template would produce an empty workout — technically valid,
        // but never what the user meant by "log this plan".
        disabled={busy || exerciseCount === 0}
        title={
          exerciseCount === 0 ? "Add exercises to this template first" : undefined
        }
        onClick={logNow}
      >
        {applying ? "Logging…" : "Log now"}
      </Button>

      <button
        type="button"
        onClick={handleDelete}
        disabled={busy}
        aria-label={`Delete ${name}`}
        title="Delete"
        className="rounded-md p-1.5 text-zinc-500 transition-colors hover:bg-red-950/50 hover:text-red-400 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {deleting ? (
          <Spinner size="sm" label="Deleting" />
        ) : (
          <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" />
          </svg>
        )}
      </button>
    </div>
  );
}
