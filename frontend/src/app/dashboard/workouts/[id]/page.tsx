import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { notFound, redirect } from "next/navigation";

import { api, ApiError, type Workout } from "@/lib/api";
import { formatLongDate } from "@/lib/dates";
import { WorkoutForm } from "@/components/workouts/WorkoutForm";

/**
 * View and edit one workout (Phase 5).
 *
 * Detail and edit are the same screen. A logged session is a working document —
 * you come back to it to fix a weight or add the movement you forgot — so a
 * read-only view with an "Edit" button would just be an extra click before every
 * real interaction.
 *
 * Next.js 16: `params` is a Promise and must be awaited. A 404 from the API means
 * the workout does not exist *or* belongs to someone else — the backend
 * deliberately does not distinguish, and neither do we.
 */
export default async function WorkoutDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  const { userId, getToken } = await auth();
  if (!userId) {
    redirect(`/sign-in?redirect_url=/dashboard/workouts/${id}`);
  }

  const token = await getToken();

  let workout: Workout;
  try {
    workout = await api.workouts.get(token, id);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 422)) {
      // 422 covers a malformed UUID in the URL, which is a bad link, not a bug.
      notFound();
    }
    // Anything else is a real failure — let error.tsx handle it.
    throw error;
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
          {workout.title ?? "Untitled workout"}
        </h1>
        <p className="mt-1 text-sm text-zinc-500">
          <time dateTime={workout.performed_on}>
            {formatLongDate(workout.performed_on)}
          </time>
          {workout.duration_min ? ` · ${workout.duration_min} min` : ""}
          {` · ${workout.exercises.length} ${workout.exercises.length === 1 ? "exercise" : "exercises"}`}
        </p>
      </header>

      <WorkoutForm mode="edit" initial={workout} />
    </div>
  );
}
