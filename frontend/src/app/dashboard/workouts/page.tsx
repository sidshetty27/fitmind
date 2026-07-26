import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";

import { api, type WorkoutListItem } from "@/lib/api";
import { normalizeApiError } from "@/lib/apiErrors";
import { formatLongDate, formatRelativeDay } from "@/lib/dates";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { WorkoutRowActions } from "@/components/workouts/WorkoutRowActions";

/**
 * Workout history (Phase 5).
 *
 * Server Component: fetches with the session token server-side, then hands each
 * row's interactive bits to a small Client Component. The page itself ships no
 * JavaScript.
 *
 * Rows are grouped by month. `GET /api/workouts` already returns them ordered by
 * `performed_on` desc, so grouping is a single pass with no re-sorting.
 */

const PAGE_SIZE = 100;

function monthKey(iso: string): string {
  // Slice rather than parse: `YYYY-MM` is already the grouping key, and building
  // a Date here would reintroduce the UTC-vs-local off-by-one.
  return iso.slice(0, 7);
}

function monthLabel(key: string): string {
  const [year, month] = key.split("-").map(Number);
  return new Date(year, month - 1, 1).toLocaleDateString(undefined, {
    month: "long",
    year: "numeric",
  });
}

function groupByMonth(workouts: WorkoutListItem[]) {
  const groups: Array<{ key: string; items: WorkoutListItem[] }> = [];
  for (const workout of workouts) {
    const key = monthKey(workout.performed_on);
    const last = groups[groups.length - 1];
    if (last?.key === key) last.items.push(workout);
    else groups.push({ key, items: [workout] });
  }
  return groups;
}

export default async function WorkoutsPage() {
  const { userId, getToken } = await auth();
  if (!userId) {
    redirect("/sign-in?redirect_url=/dashboard/workouts");
  }

  const token = await getToken();

  let workouts: WorkoutListItem[] = [];
  let loadError: string | null = null;

  try {
    workouts = await api.workouts.list(token, { limit: PAGE_SIZE });
  } catch (error) {
    loadError = normalizeApiError(error).formError;
  }

  const groups = groupByMonth(workouts);

  return (
    <div className="mx-auto w-full max-w-4xl">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Workouts</h1>
          <p className="mt-1 text-sm text-zinc-500">
            {workouts.length === 0
              ? "Every session you log will appear here."
              : `${workouts.length} ${workouts.length === 1 ? "session" : "sessions"} logged`}
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

      {!loadError && workouts.length === 0 && (
        <div className="mt-6">
          <EmptyState
            title="No workouts yet"
            description="Log your first session to start building a training history. It takes about a minute."
            action={
              <Link href="/dashboard/workouts/new">
                <Button>Add your first workout</Button>
              </Link>
            }
          />
        </div>
      )}

      <div className="mt-6 space-y-8">
        {groups.map((group) => (
          <section key={group.key}>
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              {monthLabel(group.key)}
            </h2>
            <Card>
              <ul className="divide-y divide-zinc-800">
                {group.items.map((workout) => {
                  const title = workout.title ?? "Untitled workout";
                  return (
                    <li
                      key={workout.id}
                      className="flex items-center gap-3 px-4 py-3.5 transition-colors hover:bg-zinc-800/30"
                    >
                      <Link
                        href={`/dashboard/workouts/${workout.id}`}
                        className="min-w-0 flex-1"
                      >
                        <p className="truncate text-sm font-medium text-zinc-100">
                          {title}
                        </p>
                        <p className="mt-0.5 text-xs text-zinc-500">
                          <time dateTime={workout.performed_on}>
                            {formatRelativeDay(workout.performed_on)}
                          </time>
                          <span className="hidden sm:inline">
                            {" · "}
                            {formatLongDate(workout.performed_on)}
                          </span>
                          {workout.duration_min ? ` · ${workout.duration_min} min` : ""}
                        </p>
                      </Link>

                      <span className="shrink-0 rounded-full border border-zinc-800 px-2.5 py-0.5 text-xs text-zinc-400">
                        {workout.exercise_count}
                        <span className="hidden sm:inline">
                          {" "}
                          {workout.exercise_count === 1 ? "exercise" : "exercises"}
                        </span>
                      </span>

                      <WorkoutRowActions workoutId={workout.id} title={title} />
                    </li>
                  );
                })}
              </ul>
            </Card>
          </section>
        ))}
      </div>

      {workouts.length === PAGE_SIZE && (
        <p className="mt-6 text-center text-xs text-zinc-600">
          Showing your {PAGE_SIZE} most recent sessions.
        </p>
      )}
    </div>
  );
}
