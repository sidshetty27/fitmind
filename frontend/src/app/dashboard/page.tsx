import Link from "next/link";
import { auth, currentUser } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";

import { api, type WorkoutListItem } from "@/lib/api";
import { normalizeApiError } from "@/lib/apiErrors";
import { formatRelativeDay, formatShortDate, startOfWeekISO } from "@/lib/dates";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { StatCard } from "@/components/dashboard/StatCard";

/**
 * Dashboard overview (Phase 4).
 *
 * A Server Component: it holds the authoritative auth check (Clerk's recommended
 * resource-level guard, kept from Phase 2) and fetches on the server, so the
 * session token never reaches the browser.
 *
 * All four stats come from the single `GET /api/workouts` list call. That endpoint
 * already returns `exercise_count` as a SQL aggregate, so the whole overview costs
 * one request — no per-workout fetch, no N+1.
 */

// The backend caps `limit` at 200. That is plenty for the summary, but it means
// the totals are "of the most recent 200", which the UI states rather than
// silently rounding off.
const FETCH_LIMIT = 200;

export default async function DashboardPage() {
  const user = await currentUser();
  if (!user) {
    redirect("/sign-in?redirect_url=/dashboard");
  }

  const { getToken } = await auth();
  const token = await getToken();

  let workouts: WorkoutListItem[] = [];
  let loadError: string | null = null;

  try {
    workouts = await api.workouts.list(token, { limit: FETCH_LIMIT });
  } catch (error) {
    // A dead backend should degrade to a banner, not a crashed page — the rest of
    // the shell is still useful and the user can retry.
    loadError = normalizeApiError(error).formError;
  }

  const name = user.firstName ?? "Athlete";
  const weekStart = startOfWeekISO();
  const thisWeek = workouts.filter((w) => w.performed_on >= weekStart).length;
  const totalExercises = workouts.reduce((sum, w) => sum + w.exercise_count, 0);
  const atLimit = workouts.length === FETCH_LIMIT;
  // The list arrives ordered by performed_on desc, so the head is the latest.
  const latest = workouts[0];
  const recent = workouts.slice(0, 5);

  return (
    <div className="mx-auto w-full max-w-6xl">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Welcome back, {name}.
          </h1>
          <p className="mt-1 text-sm text-zinc-500">
            Here&apos;s where your training stands.
          </p>
        </div>
        <Link href="/dashboard/workouts/new">
          <Button size="lg">Add Workout</Button>
        </Link>
      </header>

      {loadError && (
        <Alert className="mt-6" title="Couldn't load your workouts">
          {loadError}
        </Alert>
      )}

      <section className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Total workouts"
          value={atLimit ? `${FETCH_LIMIT}+` : String(workouts.length)}
          sublabel={atLimit ? "Most recent 200" : "All time"}
          accent="indigo"
        />
        <StatCard
          label="This week"
          value={String(thisWeek)}
          sublabel="Since Monday"
          accent="emerald"
        />
        <StatCard
          label="Last session"
          value={latest ? formatRelativeDay(latest.performed_on) : "—"}
          sublabel={latest?.title ?? (latest ? "Untitled workout" : "Nothing logged yet")}
          accent="amber"
        />
        <StatCard
          label="Exercises logged"
          value={String(totalExercises)}
          sublabel="Across all sessions"
          accent="violet"
        />
      </section>

      <section className="mt-8">
        <Card>
          <CardHeader
            title="Recent workouts"
            description="Your five most recent sessions"
            action={
              <Link href="/dashboard/workouts">
                <Button variant="secondary" size="sm">
                  View all
                </Button>
              </Link>
            }
          />
          <CardBody className="p-0">
            {recent.length === 0 ? (
              <div className="p-5">
                <EmptyState
                  title={loadError ? "Nothing to show" : "No workouts yet"}
                  description={
                    loadError
                      ? "We couldn't reach the API, so this list is empty."
                      : "Log your first session and it'll show up here."
                  }
                  action={
                    !loadError && (
                      <Link href="/dashboard/workouts/new">
                        <Button>Add your first workout</Button>
                      </Link>
                    )
                  }
                />
              </div>
            ) : (
              <ul className="divide-y divide-zinc-800">
                {recent.map((workout) => (
                  <li key={workout.id}>
                    <Link
                      href={`/dashboard/workouts/${workout.id}`}
                      className="flex items-center justify-between gap-4 px-5 py-3.5 transition-colors hover:bg-zinc-800/40"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-zinc-100">
                          {workout.title ?? "Untitled workout"}
                        </p>
                        <p className="mt-0.5 text-xs text-zinc-500">
                          {formatRelativeDay(workout.performed_on)}
                          {workout.duration_min ? ` · ${workout.duration_min} min` : ""}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-3">
                        <span className="rounded-full border border-zinc-800 px-2.5 py-0.5 text-xs text-zinc-400">
                          {workout.exercise_count}{" "}
                          {workout.exercise_count === 1 ? "exercise" : "exercises"}
                        </span>
                        <span className="hidden text-xs text-zinc-600 sm:inline">
                          {formatShortDate(workout.performed_on)}
                        </span>
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      </section>
    </div>
  );
}
