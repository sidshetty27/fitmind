"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Alert } from "@/components/ui/Alert";

/** How many times to re-check, and how long to wait before each. */
const RETRY_DELAYS_MS = [1500, 2500, 4000, 6000];

/**
 * Closes the gap between Stripe redirecting the user back and the webhook
 * arriving.
 *
 * Checkout finishing does not make anyone premium — only
 * `customer.subscription.created` does, and Stripe sends the browser back a beat
 * before it sends us that. So a user who has just paid can land on this page and
 * be told they are on the Free plan, which reads as "my payment failed" at the
 * worst possible moment.
 *
 * Making the success URL grant premium would fix the display and open a hole:
 * that URL is just an address anyone can type. So the paywall stays where it is
 * and this component covers the seconds in between — it says a payment is
 * confirming, and re-runs the server component a few times until the webhook
 * lands and the page renders Premium on its own.
 *
 * If it never lands, the message stops apologising and points at the billing
 * portal, where Stripe's own record is authoritative. That is a better answer
 * than a spinner that never stops.
 */
export function CheckoutStatus({ premium }: { premium: boolean }) {
  const router = useRouter();
  const [attempt, setAttempt] = useState(0);

  const exhausted = attempt >= RETRY_DELAYS_MS.length;

  useEffect(() => {
    // Nothing to wait for: the webhook already landed, or we have stopped
    // asking. Both are terminal, so no timer is scheduled.
    if (premium || exhausted) return;

    const timer = setTimeout(() => {
      router.refresh();
      setAttempt((n) => n + 1);
    }, RETRY_DELAYS_MS[attempt]);

    return () => clearTimeout(timer);
  }, [premium, exhausted, attempt, router]);

  if (premium) {
    return (
      <Alert className="mt-6" tone="success" title="You're on Premium">
        Thanks for subscribing — AI coaching is now unlimited.
      </Alert>
    );
  }

  if (exhausted) {
    return (
      <Alert className="mt-6" tone="warning" title="Still confirming your payment">
        Stripe has not confirmed the subscription yet. This usually resolves on
        its own within a minute — reload the page, or open the billing portal
        below to see the status Stripe has.
      </Alert>
    );
  }

  return (
    <Alert className="mt-6" tone="success" title="Payment received">
      <span aria-live="polite">
        Confirming your subscription with Stripe. This page will update itself in
        a moment.
      </span>
    </Alert>
  );
}
