import { auth, currentUser } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";

import { api, type Subscription } from "@/lib/api";
import { normalizeApiError } from "@/lib/apiErrors";
import { formatLongDate } from "@/lib/dates";
import { Alert } from "@/components/ui/Alert";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { CheckoutStatus } from "@/components/billing/CheckoutStatus";
import { PlanActions } from "@/components/billing/PlanActions";

/**
 * Settings — currently just billing.
 *
 * A Server Component like the rest of the dashboard, reading the plan
 * server-side so no Clerk token is ever exposed to the page's HTML. The two
 * interactive controls (upgrade, manage) are an isolated client component,
 * because both of them navigate away to Stripe.
 *
 * Everything shown here comes from `GET /api/me/subscription`, which is also
 * what the Coach page reads. One source means the two screens cannot end up
 * disagreeing about whether someone is premium.
 */

export default async function SettingsPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const user = await currentUser();
  if (!user) {
    redirect("/sign-in?redirect_url=/dashboard/settings");
  }

  const { checkout } = await searchParams;
  const { getToken } = await auth();
  const token = await getToken();

  let subscription: Subscription | null = null;
  let loadError: string | null = null;

  try {
    subscription = await api.me.subscription(token);
  } catch (error) {
    loadError = normalizeApiError(error).formError;
  }

  return (
    <div className="mx-auto w-full max-w-3xl">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-1 max-w-lg text-sm text-zinc-500">
          Your plan and billing. Payments are handled by Stripe — FitMind never
          sees your card.
        </p>
      </header>

      {checkout === "cancelled" && (
        <Alert className="mt-6" tone="warning" title="Checkout cancelled">
          Nothing was charged. You can upgrade whenever you like.
        </Alert>
      )}

      {loadError && (
        <Alert className="mt-6" title="Couldn't load your plan">
          {loadError}
        </Alert>
      )}

      {subscription && (
        <>
          {checkout === "success" && (
            <CheckoutStatus premium={subscription.premium} />
          )}
          <PlanCard subscription={subscription} />
        </>
      )}
    </div>
  );
}

/* ---------------------------------- plan ---------------------------------- */

function PlanCard({ subscription }: { subscription: Subscription }) {
  const {
    premium,
    status,
    current_period_end,
    cancel_at_period_end,
    billing_enabled,
  } = subscription;

  return (
    <section className="mt-6">
      <Card>
        <CardHeader
          title="Plan"
          description={
            premium
              ? "Unlimited AI coaching"
              : "Free — AI coaching is limited each day"
          }
          action={
            <span
              className={
                premium
                  ? "rounded-full bg-indigo-500/15 px-2.5 py-1 text-xs font-medium text-indigo-300"
                  : "rounded-full bg-zinc-800 px-2.5 py-1 text-xs font-medium text-zinc-400"
              }
            >
              {premium ? "Premium" : "Free"}
            </span>
          }
        />
        <CardBody className="space-y-5">
          <RenewalLine
            premium={premium}
            status={status}
            periodEnd={current_period_end}
            cancelAtPeriodEnd={cancel_at_period_end}
          />

          <AllowanceLine subscription={subscription} />

          {billing_enabled ? (
            <PlanActions
              premium={premium}
              hasBillingAccount={subscription.has_billing_account}
            />
          ) : (
            // No dead buttons: with Stripe unconfigured there is nothing to
            // click, so say why rather than offering an upgrade that 503s.
            <p className="text-sm text-zinc-500">
              Billing is not configured on this deployment.
            </p>
          )}
        </CardBody>
      </Card>
    </section>
  );
}

/**
 * When the plan next changes, in the user's terms.
 *
 * The renews/ends distinction is the point. Stripe keeps `status` at `active`
 * through a cancelled-but-paid-up period, so reading status alone would tell
 * someone who just cancelled that their plan renews — the one thing they know
 * to be false, on the screen they went to specifically to check.
 */
function RenewalLine({
  premium,
  status,
  periodEnd,
  cancelAtPeriodEnd,
}: {
  premium: boolean;
  status: string | null;
  periodEnd: string | null;
  cancelAtPeriodEnd: boolean;
}) {
  if (!premium) {
    return (
      <p className="text-sm text-zinc-400">
        Upgrade for unlimited AI coaching, and support the project.
      </p>
    );
  }

  const date = periodEnd ? formatLongDate(periodEnd.slice(0, 10)) : null;

  // `past_due` still counts as premium — Stripe is retrying the charge — but
  // saying nothing would leave the user to discover it when access stops.
  if (status === "past_due") {
    return (
      <Alert tone="warning" title="Your last payment failed">
        Stripe is retrying. Update your card in the billing portal to avoid
        losing access.
      </Alert>
    );
  }

  if (!date) {
    return <p className="text-sm text-zinc-400">Your subscription is active.</p>;
  }

  return (
    <p className="text-sm text-zinc-400">
      {cancelAtPeriodEnd ? (
        <>
          Your plan ends on{" "}
          <span className="text-zinc-200">{date}</span>. You keep premium until
          then.
        </>
      ) : (
        <>
          Renews on <span className="text-zinc-200">{date}</span>.
        </>
      )}
    </p>
  );
}

/** Today's AI coach allowance — the thing premium actually buys. */
function AllowanceLine({ subscription }: { subscription: Subscription }) {
  const { premium, ai_limit, ai_used, ai_remaining } = subscription;

  if (premium) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 px-4 py-3">
        <p className="text-sm text-zinc-300">AI coach — unlimited</p>
        <p className="mt-0.5 text-xs text-zinc-500">
          Run an analysis as often as you find it useful.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 px-4 py-3">
      <p className="text-sm text-zinc-300">
        AI coach — {ai_remaining} of {ai_limit} left today
      </p>
      <p className="mt-0.5 text-xs text-zinc-500">
        {ai_used === 0
          ? "Your allowance resets on a rolling 24-hour basis."
          : "Each run counts for 24 hours from when you made it."}
      </p>
    </div>
  );
}
