"use client";

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";

import { api } from "@/lib/api";
import { normalizeApiError } from "@/lib/apiErrors";
import { Button } from "@/components/ui/Button";

/**
 * Upgrade, or manage an existing subscription.
 *
 * Both buttons do the same thing structurally: ask the backend for a
 * Stripe-hosted URL and navigate to it. Neither changes the plan — that only
 * happens when Stripe's webhook confirms money moved.
 *
 * The pending state is never cleared on success, deliberately. A full-page
 * navigation to Stripe is about to replace this document, and flipping the
 * button back to idle first would show an interactive control for the moment
 * before the browser leaves — long enough on a slow connection to click twice
 * and open two checkout sessions. It clears only on failure, when there is
 * genuinely something to try again.
 */
export function PlanActions({
  premium,
  hasBillingAccount,
}: {
  premium: boolean;
  hasBillingAccount: boolean;
}) {
  const { getToken } = useAuth();
  const [pending, setPending] = useState<"checkout" | "portal" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function go(which: "checkout" | "portal") {
    setPending(which);
    setError(null);
    try {
      const token = await getToken();
      const { url } =
        which === "checkout"
          ? await api.billing.checkout(token)
          : await api.billing.portal(token);
      // `assign`, not `replace`: the browser Back button should return here
      // rather than skipping the settings page entirely.
      window.location.assign(url);
    } catch (err) {
      setError(normalizeApiError(err).formError);
      setPending(null);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2">
        {!premium && (
          <Button onClick={() => go("checkout")} pending={pending === "checkout"}>
            Upgrade to Premium
          </Button>
        )}
        {hasBillingAccount && (
          // Shown to lapsed and cancelled users too, not just current
          // subscribers: past invoices and a saved card are exactly what
          // someone who has stopped paying comes here to deal with.
          <Button
            variant={premium ? "primary" : "secondary"}
            onClick={() => go("portal")}
            pending={pending === "portal"}
          >
            Manage billing
          </Button>
        )}
      </div>
      {error && (
        <p role="alert" className="text-xs text-red-400">
          {error}
        </p>
      )}
    </div>
  );
}
