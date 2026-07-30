"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@clerk/nextjs";

import { api } from "@/lib/api";
import { normalizeApiError } from "@/lib/apiErrors";
import { Button } from "@/components/ui/Button";

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
export function RunAnalysisButton({ hasWorkouts }: { hasWorkouts: boolean }) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [submitting, setSubmitting] = useState(false);
  const [refreshing, startRefresh] = useTransition();
  const [error, setError] = useState<string | null>(null);

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
      setError(normalizeApiError(err).formError);
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
        disabled={!hasWorkouts}
        title={hasWorkouts ? undefined : "Log a workout first"}
      >
        Analyse my training
      </Button>
      {error && (
        <p role="alert" className="text-xs text-red-400">
          {error}
        </p>
      )}
    </div>
  );
}
