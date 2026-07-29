import Link from "next/link";
import { auth, currentUser } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";

import {
  api,
  toNumber,
  type DecimalString,
  type PersonalRecord,
  type TrainingSummary,
} from "@/lib/api";
import { normalizeApiError } from "@/lib/apiErrors";
import { formatShortDate, weeksBetween } from "@/lib/dates";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { StatCard } from "@/components/dashboard/StatCard";
import { ChartTable, ColumnChart, type Column } from "@/components/charts/ColumnChart";
import { Sparkline } from "@/components/charts/Sparkline";

/**
 * Progress — the Phase 6 analytics view.
 *
 * A Server Component, like the rest of the dashboard: it fetches with the caller's
 * Clerk token so no session JWT reaches the browser, and the charts render to markup
 * rather than to a canvas, so the page needs no client JavaScript at all.
 *
 * Two requests, not five. `/analytics/summary` returns the window, the weekly
 * rollup, and the per-exercise series together so the charts cannot disagree about
 * where a week boundary falls; `/analytics/records` is separate because records are
 * all-time and deliberately do not move when the window control does.
 */

const WINDOW_CHOICES = [4, 12, 26, 52] as const;
const DEFAULT_WEEKS = 12;

export default async function ProgressPage({
  searchParams,
}: {
  searchParams: Promise<{ weeks?: string }>;
}) {
  const user = await currentUser();
  if (!user) {
    redirect("/sign-in?redirect_url=/dashboard/progress");
  }

  const { weeks: weeksParam } = await searchParams;
  const weeks = normaliseWeeks(weeksParam);

  const { getToken } = await auth();
  const token = await getToken();

  let summary: TrainingSummary | null = null;
  let records: PersonalRecord[] = [];
  let loadError: string | null = null;

  try {
    [summary, records] = await Promise.all([
      api.analytics.summary(token, { weeks }),
      api.analytics.records(token),
    ]);
  } catch (error) {
    // Same rule as the rest of the dashboard: a dead backend degrades to a banner
    // over a usable shell, never a blank screen.
    loadError = normalizeApiError(error).formError;
  }

  const hasData = !!summary && summary.workout_count > 0;

  return (
    <div className="mx-auto w-full max-w-6xl">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Progress</h1>
          <p className="mt-1 text-sm text-zinc-500">
            {summary
              ? `${formatShortDate(summary.window_start)} – ${formatShortDate(
                  summary.window_end,
                )}`
              : "What your logged sessions add up to."}
          </p>
        </div>
        {/* Filters in one row above the charts. Links, not a JS control — the window
            lives in the URL, so a range is shareable and survives a reload. */}
        <nav aria-label="Time range" className="flex gap-1">
          {WINDOW_CHOICES.map((choice) => (
            <Link
              key={choice}
              href={`/dashboard/progress?weeks=${choice}`}
              aria-current={choice === weeks ? "page" : undefined}
              className={
                choice === weeks
                  ? "rounded-lg bg-indigo-500/15 px-3 py-1.5 text-xs font-medium text-indigo-300"
                  : "rounded-lg px-3 py-1.5 text-xs text-zinc-500 transition-colors hover:bg-zinc-800/60 hover:text-zinc-300"
              }
            >
              {choice}w
            </Link>
          ))}
        </nav>
      </header>

      {loadError && (
        <Alert className="mt-6" title="Couldn't load your analytics">
          {loadError}
        </Alert>
      )}

      {!loadError && !hasData && (
        <Card className="mt-6">
          <CardBody>
            <EmptyState
              title="Nothing to chart yet"
              description="Log a few sessions and your volume, frequency, and personal records will appear here."
              action={
                <Link href="/dashboard/workouts/new">
                  <Button>Add a workout</Button>
                </Link>
              }
            />
          </CardBody>
        </Card>
      )}

      {summary && hasData && (
        <>
          <SummaryTiles summary={summary} weeks={weeks} />
          <VolumeAndFrequency summary={summary} />
          <ExerciseTrends summary={summary} />
          <Records records={records} />
        </>
      )}
    </div>
  );
}

/** Only the offered windows are honoured — an arbitrary `?weeks=` is not a query knob. */
function normaliseWeeks(raw: string | undefined): number {
  const parsed = Number(raw);
  return (WINDOW_CHOICES as readonly number[]).includes(parsed) ? parsed : DEFAULT_WEEKS;
}

const KG = (n: number) => Math.round(n).toLocaleString();

/** Wire `Decimal` to a number for arithmetic, treating "not applicable" as no load. */
const kg = (value: DecimalString | null) => toNumber(value) ?? 0;

/* ------------------------------- summary tiles ------------------------------ */

function SummaryTiles({ summary, weeks }: { summary: TrainingSummary; weeks: number }) {
  const totalVolume = summary.weekly_volume.reduce((sum, w) => sum + kg(w.volume_kg), 0);
  const totalReps = summary.weekly_volume.reduce((sum, w) => sum + w.total_reps, 0);
  // Per *window* week, not per week trained — averaging over only the weeks that
  // have rows would quietly exclude rest weeks and overstate consistency.
  const perWeek = summary.workout_count / weeks;

  return (
    <section className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <StatCard
        label="Sessions"
        value={String(summary.workout_count)}
        sublabel={`Last ${weeks} weeks`}
        accent="indigo"
      />
      <StatCard
        label="Sessions / week"
        value={perWeek.toFixed(1)}
        sublabel="Averaged over the window"
        accent="emerald"
      />
      <StatCard
        label="Volume"
        value={`${KG(totalVolume)} kg`}
        sublabel="Loaded work only"
        accent="violet"
      />
      <StatCard
        label="Reps"
        value={totalReps.toLocaleString()}
        sublabel="Loaded and bodyweight"
        accent="amber"
      />
    </section>
  );
}

/* --------------------------- volume and frequency --------------------------- */

/**
 * Two charts, never one. Volume (kg) and session count share an x-axis but not a
 * scale, and putting them on one plot would need a second y-axis — the single most
 * misread thing in a dashboard, because the crossing point is an artefact of the
 * scales rather than a fact about the training.
 */
function VolumeAndFrequency({ summary }: { summary: TrainingSummary }) {
  const byWeek = new Map(summary.weekly_volume.map((w) => [w.week_start, w]));
  const axis = weeksBetween(summary.window_start, summary.window_end);

  const volume: Column[] = axis.map((week) => ({
    label: formatShortDate(week),
    title: `Week of ${formatShortDate(week)}`,
    value: kg(byWeek.get(week)?.volume_kg ?? null),
  }));

  const frequency: Column[] = axis.map((week) => ({
    label: formatShortDate(week),
    title: `Week of ${formatShortDate(week)}`,
    value: byWeek.get(week)?.session_count ?? 0,
  }));

  return (
    <section className="mt-8 grid grid-cols-1 gap-4 xl:grid-cols-2">
      <Card>
        <CardHeader
          title="Volume over time"
          description="Sets x reps x load, per week. Bodyweight work is counted in reps, not here."
        />
        <CardBody>
          <ColumnChart columns={volume} accent="indigo" format={KG} unit=" kg" />
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="Workout frequency"
          description="Sessions logged per week"
        />
        <CardBody>
          <ColumnChart columns={frequency} accent="emerald" integer />
        </CardBody>
      </Card>
    </section>
  );
}

/* ------------------------------ exercise trends ----------------------------- */

/**
 * Small multiples rather than one multi-series chart.
 *
 * Past about four lines a shared plot needs a categorical palette whose adjacent
 * pairs stay separable under colour-vision deficiency, and it converges into an
 * unreadable knot at the right edge. One panel per movement keeps every series in
 * the same validated hue and scales to as many movements as the user trains.
 */
function ExerciseTrends({ summary }: { summary: TrainingSummary }) {
  // A movement needs two estimable points to have a direction. One is a reading.
  const trends = summary.exercises
    .map((exercise) => ({
      exercise,
      // Parse once, here, so nothing downstream can do maths on a wire string.
      points: exercise.points.flatMap((point) => {
        const oneRm = toNumber(point.estimated_one_rm);
        return oneRm === null ? [] : [{ point, oneRm }];
      }),
    }))
    .filter((t) => t.points.length > 0);

  return (
    <section className="mt-8">
      <Card>
        <CardHeader
          title="Exercise progress"
          description="Estimated one-rep max per session, most-trained movements first"
        />
        <CardBody>
          {trends.length === 0 ? (
            <p className="text-sm text-zinc-500">
              No movement in this window has a loaded set in the 1–12 rep range, so
              there is no max to estimate yet.
            </p>
          ) : (
            <ul className="grid grid-cols-1 gap-x-6 gap-y-8 md:grid-cols-2">
              {trends.map(({ exercise, points }) => {
                const values = points.map((p) => p.oneRm);
                const latest = values[values.length - 1];
                const change = toNumber(exercise.one_rm_change_pct);
                return (
                  <li key={exercise.exercise_id}>
                    <div className="flex items-baseline justify-between gap-3">
                      <h3 className="truncate text-sm font-medium text-zinc-200">
                        {exercise.exercise_name}
                      </h3>
                      {/* The one direct label: the latest reading, at the line's end. */}
                      <span className="shrink-0 text-sm tabular-nums text-zinc-300">
                        {latest.toFixed(1)} kg
                      </span>
                    </div>
                    <p className="mt-0.5 text-xs text-zinc-600">
                      {exercise.session_count}{" "}
                      {exercise.session_count === 1 ? "session" : "sessions"}
                      {change !== null && (
                        <>
                          {" · "}
                          {/* Signed, and stated in words as well as sign — a red
                              number alone would be colour-only meaning. */}
                          <span
                            className={
                              change < 0 ? "text-amber-400/90" : "text-emerald-400/90"
                            }
                          >
                            {change > 0 ? "up" : change < 0 ? "down" : "level"}{" "}
                            {Math.abs(change).toFixed(1)}%
                          </span>{" "}
                          over the window
                        </>
                      )}
                    </p>
                    <div className="mt-2">
                      <Sparkline
                        values={values}
                        labels={points.map(
                          ({ point, oneRm }) =>
                            `${formatShortDate(point.performed_on)} — ${oneRm.toFixed(
                              1,
                            )} kg estimated max (${point.sets}x${point.reps}${
                              point.weight_kg ? ` @ ${point.weight_kg} kg` : ""
                            })`,
                        )}
                      />
                    </div>
                    <ChartTable
                      caption={`Estimated one-rep max per session for ${exercise.exercise_name}.`}
                      headers={["Session", "Est. 1RM"]}
                      rows={points.map(({ point, oneRm }) => [
                        formatShortDate(point.performed_on),
                        `${oneRm.toFixed(1)} kg`,
                      ])}
                    />
                  </li>
                );
              })}
            </ul>
          )}
        </CardBody>
      </Card>
    </section>
  );
}

/* ----------------------------- personal records ----------------------------- */

/**
 * A table, not a chart. Records are a handful of exact values a reader looks up
 * one at a time — plotting them would make them harder to read, not easier.
 */
function Records({ records }: { records: PersonalRecord[] }) {
  return (
    <section className="mt-8">
      <Card>
        <CardHeader
          title="Personal records"
          description="All-time bests, unaffected by the range above"
        />
        <CardBody className="p-0">
          {records.length === 0 ? (
            <p className="p-5 text-sm text-zinc-500">Nothing logged yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[36rem] text-left text-sm">
                <thead className="border-b border-zinc-800 text-xs text-zinc-500">
                  <tr>
                    <th scope="col" className="px-5 py-3 font-medium">
                      Movement
                    </th>
                    <th scope="col" className="px-5 py-3 text-right font-medium">
                      Heaviest
                    </th>
                    <th scope="col" className="px-5 py-3 text-right font-medium">
                      Est. 1RM
                    </th>
                    <th scope="col" className="px-5 py-3 text-right font-medium">
                      Best session
                    </th>
                    <th scope="col" className="px-5 py-3 text-right font-medium">
                      Last done
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/70">
                  {records.map((record) => (
                    <tr key={record.exercise_id} className="hover:bg-zinc-800/30">
                      <td className="px-5 py-3">
                        <span className="text-zinc-200">{record.exercise_name}</span>
                        <span className="ml-2 text-xs text-zinc-600">
                          {record.session_count}x
                        </span>
                      </td>
                      <RecordCell
                        value={record.heaviest_weight_kg}
                        on={record.heaviest_weight_on}
                        unit="kg"
                      />
                      <RecordCell
                        value={record.best_estimated_one_rm}
                        on={record.best_estimated_one_rm_on}
                        unit="kg"
                      />
                      <RecordCell
                        value={record.best_session_volume_kg}
                        on={record.best_session_volume_on}
                        unit="kg"
                        decimals={0}
                      />
                      <td className="px-5 py-3 text-right text-xs text-zinc-500">
                        {formatShortDate(record.last_performed_on)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardBody>
      </Card>
    </section>
  );
}

/**
 * One record cell. A dash — never a zero — when the metric does not apply: a
 * bodyweight movement has no heaviest load, and printing `0 kg` would claim it was
 * lifted with none.
 */
function RecordCell({
  value: raw,
  on,
  unit,
  /**
   * Fixed per column, never per value. `91.83` beside `49` beside `111` is a column
   * that does not line up; one decimal everywhere does, which is the whole reason
   * these cells are tabular-nums.
   */
  decimals = 1,
}: {
  value: DecimalString | null;
  on: string | null;
  unit: string;
  decimals?: number;
}) {
  const value = toNumber(raw);
  if (value === null) {
    return (
      <td className="px-5 py-3 text-right text-zinc-700" title="Not applicable — bodyweight movement">
        —
      </td>
    );
  }
  return (
    <td className="px-5 py-3 text-right">
      <span className="tabular-nums text-zinc-200">
        {value.toLocaleString(undefined, {
          minimumFractionDigits: decimals,
          maximumFractionDigits: decimals,
        })}
        <span className="ml-1 text-xs text-zinc-500">{unit}</span>
      </span>
      {on && <span className="block text-xs text-zinc-600">{formatShortDate(on)}</span>}
    </td>
  );
}
