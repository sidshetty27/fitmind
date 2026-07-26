import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";

import { api, type Workout } from "@/lib/api";
import { Alert } from "@/components/ui/Alert";
import { WorkoutForm } from "@/components/workouts/WorkoutForm";

/**
 * Log a new workout (Phase 5).
 *
 * `?duplicate=<id>` prefills the editor from an existing session — the "repeat
 * last week's push day" flow. The copy is loaded here on the server rather than
 * written straight to the database, so the user reviews and adjusts the numbers
 * before anything is saved.
 *
 * Next.js 16: `searchParams` is a Promise and must be awaited.
 */
export default async function NewWorkoutPage({
  searchParams,
}: {
  searchParams: Promise<{ duplicate?: string }>;
}) {
  const { userId, getToken } = await auth();
  if (!userId) {
    redirect("/sign-in?redirect_url=/dashboard/workouts/new");
  }

  const { duplicate } = await searchParams;

  let source: Workout | undefined;
  let duplicateError: string | null = null;

  if (duplicate) {
    try {
      const token = await getToken();
      source = await api.workouts.get(token, duplicate);
    } catch {
      // A bad or foreign id just means no prefill — the user can still log a
      // workout from scratch, so this must not take the page down.
      duplicateError =
        "We couldn't load that workout to copy, so this form is blank.";
    }
  }

  return (
    <div className="mx-auto w-full max-w-3xl">
      <header className="mb-6">
        <Link
          href="/dashboard/workouts"
          className="text-xs text-zinc-500 hover:text-zinc-300"
        >
          ← Workouts
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">
          {source ? "Duplicate workout" : "Log a workout"}
        </h1>
        <p className="mt-1 text-sm text-zinc-500">
          {source
            ? `Copied from "${source.title ?? "Untitled workout"}" — dated today, adjust anything you need.`
            : "Record what you did. Only the date is required."}
        </p>
      </header>

      {duplicateError && (
        <Alert tone="warning" className="mb-6">
          {duplicateError}
        </Alert>
      )}

      {/* Pointer to the one-click path, shown only when starting from scratch —
          someone already duplicating a session has their starting point. */}
      {!source && (
        <p className="mb-6 rounded-xl border border-zinc-800 bg-zinc-900/40 px-4 py-3 text-xs text-zinc-500">
          Repeat a session you run often?{" "}
          <Link
            href="/dashboard/templates"
            className="font-medium text-indigo-400 hover:text-indigo-300"
          >
            Log it from a template
          </Link>{" "}
          in one click instead.
        </p>
      )}

      <WorkoutForm mode="create" duplicateOf={source} />
    </div>
  );
}
