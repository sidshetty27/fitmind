"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@clerk/nextjs";

import { api } from "@/lib/api";
import { normalizeApiError } from "@/lib/apiErrors";
import { Spinner } from "@/components/ui/Spinner";

/**
 * Per-row Duplicate and Delete for the workout list.
 *
 * Duplicate is a plain link to `/new?duplicate=<id>` rather than an immediate
 * write: the new-workout page loads the original server-side and prefills the
 * editor, so the user reviews and adjusts before anything is saved. Copying a
 * session usually means "same plan, different numbers".
 *
 * Delete calls the API here, then `router.refresh()` re-runs the parent Server
 * Component so the row disappears without a full page load.
 */
export function WorkoutRowActions({
  workoutId,
  title,
}: {
  workoutId: string;
  title: string;
}) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDelete() {
    if (!window.confirm(`Delete "${title}"? This cannot be undone.`)) return;

    setDeleting(true);
    setError(null);
    try {
      const token = await getToken();
      await api.workouts.delete(token, workoutId);
      router.refresh();
    } catch (err) {
      setError(normalizeApiError(err).formError);
      setDeleting(false);
    }
  }

  return (
    <div className="flex items-center gap-1">
      {error && (
        <span role="alert" className="mr-1 text-xs text-red-400">
          {error}
        </span>
      )}

      <Link
        href={`/dashboard/workouts/new?duplicate=${workoutId}`}
        aria-label={`Duplicate ${title}`}
        title="Duplicate"
        className="rounded-md p-1.5 text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-zinc-200"
      >
        <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24" aria-hidden="true">
          <rect x="9" y="9" width="12" height="12" rx="2" />
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
        </svg>
      </Link>

      <button
        type="button"
        onClick={handleDelete}
        disabled={deleting}
        aria-label={`Delete ${title}`}
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
