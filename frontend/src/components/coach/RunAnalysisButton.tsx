"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@clerk/nextjs";

import { api } from "@/lib/api";
import { normalizeApiError } from "@/lib/apiErrors";
import { Button } from "@/components/ui/Button";

/**
 * The backend's machine-readable marker for a spent free allowance.
 *
 * Only this one flips the button into its upgrade state. The coach's other two
 * refusals (`rate_limited`, `ai_capacity_reached`) arrive as 429s and mean
 * "wait", not "pay" — they apply to premium accounts too, so prompting for an
 * upgrade would be offering to sell something that does not lift the refusal.
 * They fall through to the error line below, which shows the server's message
 * and leaves the button usable for the retry that will eventually work.
 */
const QUOTA_CODE = "free_tier_limit_reached";

/**
 * Runs a fresh analysis, then refreshes the page to show it.
 *
 * A POST rather than a page load because it is not idempotent: each run costs a
 * model call and writes a row that Phase 8's usage gate will count. That is also
 * why this is an explicit button and not something the page does on mount — a
 * user should never spend a call by navigating.
 *
 * `router.refresh()` re-runs the Server Component, so the new analysis arrives
 * through the same server-side fetch as everything else rather than being pushed
 * into client state where the two could disagree.
 *
 * The refresh is wrapped in a transition rather than tracked with local state.
 * `router.refresh()` re-renders the server tree but does **not** remount this
 * client component, so a `setRunning(false)` after it never runs and a hand-held
 * flag stays `true` forever — the button spins permanently and a second analysis
 * is impossible without a hard reload. `isPending` is tied to the refresh itself
 * and clears when the new markup lands.
 */
export function RunAnalysisButton({
  hasWorkouts,
  remaining,
}: {
  hasWorkouts: boolean;
  /** Free runs left today. `-1` means unlimited (premium). */
  remaining: number;
}) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [submitting, setSubmitting] = useState(false);
  const [refreshing, startRefresh] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [outOfRuns, setOutOfRuns] = useState(false);

  const unlimited = remaining < 0;
  // Known-empty from the server render, or learned from a 402 after the fact.
  // Both matter: the first stops a request that cannot succeed, the second
  // catches a page that was rendered before the allowance ran out in another
  // tab.
  const spent = outOfRuns || (!unlimited && remaining <= 0);

  // Busy from the moment the request goes out until the refreshed page is on
  // screen, so the button is never idle over stale output.
  const busy = submitting || refreshing;

  async function handleRun() {
    setSubmitting(true);
    setError(null);
    try {
      const token = await getToken();
      await api.coach.run(token);
      startRefresh(() => router.refresh());
    } catch (err) {
      const normalized = normalizeApiError(err);
      // Branch on the code, not the message: the copy will be reworded and a
      // check against prose would silently stop recognising this.
      if (normalized.code === QUOTA_CODE) {
        setOutOfRuns(true);
      }
      setError(normalized.formError);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-2">
      {/* `pending` rather than a swapped label: the house Button keeps its text
          while busy so the control does not resize mid-request, and announces
          itself with aria-busy. */}
      <Button
        onClick={handleRun}
        pending={busy}
        disabled={!hasWorkouts || spent}
        title={
          !hasWorkouts
            ? "Log a workout first"
            : spent
              ? "You've used today's free analyses"
              : undefined
        }
      >
        Analyse my training
      </Button>

      {/* The count is only worth showing when it is nearly gone. "3 of 3 left"
          is noise on a page nobody came here to read a quota on; "1 left" is
          the thing that changes what someone does next. */}
      {!unlimited && !spent && remaining <= 1 && (
        <p className="text-xs text-zinc-500">
          {remaining} free {remaining === 1 ? "analysis" : "analyses"} left today
        </p>
      )}

      {spent && (
        <p className="text-xs text-zinc-500">
          No free analyses left today.{" "}
          <Link
            href="/dashboard/settings"
            className="text-indigo-400 underline underline-offset-2 hover:text-indigo-300"
          >
            Upgrade for unlimited
          </Link>
        </p>
      )}

      {error && !spent && (
        <p role="alert" className="text-xs text-red-400">
          {error}
        </p>
      )}
    </div>
  );
}
