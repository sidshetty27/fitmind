import Link from "next/link";
import { auth, currentUser } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";

import {
  api,
  type AiAnalysis,
  type AiAnalysisListItem,
  type Subscription,
  type WorkoutListItem,
} from "@/lib/api";
import { normalizeApiError } from "@/lib/apiErrors";
import { formatRelativeDay, formatShortDate } from "@/lib/dates";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { FindingCard } from "@/components/coach/FindingCard";
import { RunAnalysisButton } from "@/components/coach/RunAnalysisButton";

/**
 * Coach — the Phase 7 view.
 *
 * A Server Component like the rest of the dashboard: it reads the user's stored
 * coaching history server-side, and the single interactive control (running a
 * new analysis) is an isolated client component.
 *
 * The page renders the *latest stored* analysis rather than computing one on
 * load. Running an analysis costs a model call and writes a row that Phase 8
 * will meter, so it has to be something the user chooses, never a side effect of
 * navigating here.
 */

export default async function CoachPage() {
  const user = await currentUser();
  if (!user) {
    redirect("/sign-in?redirect_url=/dashboard/coach");
  }

  const { getToken } = await auth();
  const token = await getToken();

  let history: AiAnalysisListItem[] = [];
  let latest: AiAnalysis | null = null;
  let workouts: WorkoutListItem[] = [];
  let subscription: Subscription | null = null;
  let loadError: string | null = null;

  try {
    // The history list carries counts but not findings, so the newest one is
    // fetched in full. Two calls rather than a fatter list endpoint: the history
    // is usually rendered without ever expanding a row.
    [history, workouts, subscription] = await Promise.all([
      api.coach.history(token, { limit: 10 }),
      api.workouts.list(token, { limit: 1 }),
      api.me.subscription(token),
    ]);
    if (history.length > 0) {
      latest = await api.coach.get(token, history[0].id);
    }
  } catch (error) {
    loadError = normalizeApiError(error).formError;
  }

  const hasWorkouts = workouts.length > 0;

  return (
    <div className="mx-auto w-full max-w-4xl">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Coach</h1>
          <p className="mt-1 max-w-lg text-sm text-zinc-500">
            Observations drawn from your logged sessions. Every number here is
            computed from what you actually lifted.
          </p>
        </div>
        {/* Defaults to unlimited when the plan could not be loaded. The server
            enforces the quota regardless, so an optimistic button costs at
            worst one refused request — while a pessimistic one would lock a
            paying subscriber out of a feature they bought because an unrelated
            call failed. */}
        <RunAnalysisButton
          hasWorkouts={hasWorkouts}
          remaining={subscription?.ai_remaining ?? -1}
        />
      </header>

      {loadError && (
        <Alert className="mt-6" title="Couldn't load your coaching">
          {loadError}
        </Alert>
      )}

      {!loadError && !hasWorkouts && (
        <Card className="mt-6">
          <CardBody>
            <EmptyState
              title="Nothing to analyse yet"
              description="Log a few sessions and the coach can start looking for plateaus, drops in volume, and muscle groups you've been skipping."
              action={
                <Link href="/dashboard/workouts/new">
                  <Button>Add a workout</Button>
                </Link>
              }
            />
          </CardBody>
        </Card>
      )}

      {!loadError && hasWorkouts && !latest && (
        <Card className="mt-6">
          <CardBody>
            <EmptyState
              title="No analysis yet"
              description="Run one and the coach will review your recent training for plateaus, volume drops, neglected muscle groups, and lifts with room to move."
            />
          </CardBody>
        </Card>
      )}

      {latest && <LatestAnalysis analysis={latest} />}

      {history.length > 1 && <History rows={history.slice(1)} />}
    </div>
  );
}

/* ------------------------------- latest run ------------------------------- */

function LatestAnalysis({ analysis }: { analysis: AiAnalysis }) {
  return (
    <section className="mt-6">
      <Card>
        <CardHeader
          title="Latest analysis"
          description={`${formatShortDate(analysis.window_start)} – ${formatShortDate(
            analysis.window_end,
          )} · ${analysis.workout_count} ${
            analysis.workout_count === 1 ? "session" : "sessions"
          }`}
          action={
            <span className="text-xs text-zinc-600">
              {formatRelativeDay(analysis.created_at.slice(0, 10))}
            </span>
          }
        />
        <CardBody className="space-y-5">
          {analysis.narrative ? (
            <Narrative text={analysis.narrative} model={analysis.model} />
          ) : (
            <NoNarrativeNote />
          )}

          {analysis.findings.length === 0 ? (
            <p className="text-sm text-zinc-500">
              Nothing stood out in this window — no stalls, no drops, nothing
              obviously neglected. Keep logging and check back.
            </p>
          ) : (
            <ul className="space-y-2.5">
              {analysis.findings.map((finding, index) => (
                <FindingCard key={`${finding.kind}-${index}`} finding={finding} />
              ))}
            </ul>
          )}
        </CardBody>
      </Card>
    </section>
  );
}

/** The model's prose, when there was one. Paragraphs come through as blank lines. */
function Narrative({ text, model }: { text: string; model: string | null }) {
  return (
    <div className="rounded-xl border border-indigo-500/20 bg-indigo-500/5 px-4 py-3.5">
      <div className="space-y-2">
        {text.split("\n\n").map((paragraph, index) => (
          <p
            key={index}
            className={
              index === 0
                ? "text-sm font-medium text-zinc-100"
                : "text-sm text-zinc-300"
            }
          >
            {paragraph}
          </p>
        ))}
      </div>
      {model && (
        <p className="mt-3 text-[11px] text-zinc-600">
          Written by {model} from the observations below.
        </p>
      )}
    </div>
  );
}

/**
 * Shown when an analysis has findings but no narrative.
 *
 * Deliberately not an error. The coaching voice is the optional half; the
 * observations below it were computed from the user's own sets and are the part
 * that has to be right. Framing a missing narrative as a failure would tell the
 * user their analysis is broken when it is complete.
 */
function NoNarrativeNote() {
  return (
    <p className="text-sm text-zinc-500">
      These observations were computed directly from your logged sets. Written
      coaching is off — add an{" "}
      <code className="rounded bg-zinc-800 px-1 py-0.5 text-xs text-zinc-400">
        ANTHROPIC_API_KEY
      </code>{" "}
      to have them written up as advice.
    </p>
  );
}

/* --------------------------------- history -------------------------------- */

function History({ rows }: { rows: AiAnalysisListItem[] }) {
  return (
    <section className="mt-8">
      <Card>
        <CardHeader
          title="Earlier analyses"
          description="A finding is true of the window it was computed for, so past runs are kept as they were"
        />
        <CardBody className="p-0">
          <ul className="divide-y divide-zinc-800">
            {rows.map((row) => (
              <li
                key={row.id}
                className="flex items-center justify-between gap-4 px-5 py-3.5"
              >
                <div className="min-w-0">
                  <p className="text-sm text-zinc-200">
                    {formatShortDate(row.window_start)} –{" "}
                    {formatShortDate(row.window_end)}
                  </p>
                  <p className="mt-0.5 text-xs text-zinc-500">
                    {row.finding_count}{" "}
                    {row.finding_count === 1 ? "observation" : "observations"}
                    {row.has_narrative ? " · written up" : ""}
                  </p>
                </div>
                <span className="shrink-0 text-xs text-zinc-600">
                  {formatRelativeDay(row.created_at.slice(0, 10))}
                </span>
              </li>
            ))}
          </ul>
        </CardBody>
      </Card>
    </section>
  );
}
