# Phase 8 — Billing: Testing Checklist

Verify in order. **Section 0 is a prerequisite** — everything else fails without it.

Legend: ✅ expected result · ⚠️ known limitation, not a bug

Billing has one property that everything else here is arranged around:

> **Only the Stripe webhook grants premium.** No request path writes plan state.
> Completing a checkout does not make you premium; the webhook does, when Stripe
> confirms money moved.

That is what makes the success URL safe — it is an address anyone can type. It is
also why there is a visible gap between paying and the page saying "Premium", and
why several tests below are about that gap rather than about payments.

Use **test mode** throughout. Test card `4242 4242 4242 4242`, any future expiry,
any CVC. Cards that behave differently are listed in section 6.

---

## 0. Setup (required first)

### 0a. Database

| # | Step | Expected result |
|---|---|---|
| 0.1 | `cd backend && .venv\Scripts\python -m alembic current` | Shows `0004_ai_analyses` |
| 0.2 | `.venv\Scripts\python -m alembic upgrade head` | ✅ Applies `0005_subscriptions`. **This writes to your Supabase database** — purely additive (one new table, no index of its own), nothing existing is altered |
| 0.3 | `.venv\Scripts\python -m alembic current` | Shows `0005_subscriptions` |
| 0.4 | `.venv\Scripts\python -m alembic revision --autogenerate -m "drift check"` | ✅ Generated `upgrade()` contains **only** the pre-existing `exercises.is_compound` server-default drift documented in `0004` and `0005` — no `subscriptions` operations. **Delete the generated file afterwards** |

### 0b. Stripe dashboard

All in **test mode** — check the toggle before starting.

| # | Step | Expected result |
|---|---|---|
| 0.5 | Create a Stripe account (or use an existing one) at dashboard.stripe.com | Test mode available |
| 0.6 | Product catalog → **Add a product**. Name it "FitMind Premium", add a **recurring** monthly price | Product created |
| 0.7 | Copy the **price** id — `price_...`, from the pricing section of the product | ⚠️ Not the `prod_...` id, which is the easier one to grab by mistake. A `prod_` here fails at checkout, not at boot, with "No such price" |
| 0.8 | Developers → API keys → **Create restricted key**. Grant only: **Customers** Write, **Checkout Sessions** Write, **Billing Portal Sessions** Write, **Subscriptions** Write. Everything else None. Copy the `rk_test_...` | ✅ A restricted key, not the account secret key. The app makes exactly five calls (all in `app/core/stripe_client.py`) and those four permissions cover them. A leaked `sk_` can refund charges and read every customer; a leaked key scoped like this cannot |
| 0.9 | Set `STRIPE_SECRET_KEY` (to the `rk_`) and `STRIPE_PRICE_ID` in `backend/.env` | Saved. ⚠️ The variable is named for the slot, not the key type — an `rk_` belongs here |
| 0.9a | Work through sections 2 and 3 and watch for **403**s | ✅ None. A 403 means a permission is missing rather than that the key is wrong — add it in the Dashboard and retry. Stripe's own migration guidance is to watch `stripe logs tail` while exercising the integration |

### 0c. Local webhook forwarding

The webhook is the only thing that grants premium, so nothing works end to end
until Stripe can reach it.

| # | Step | Expected result |
|---|---|---|
| 0.10 | Install the Stripe CLI, then `stripe login` | Authenticated |
| 0.11 | `stripe listen --forward-to localhost:8000/api/webhooks/stripe` | Prints a `whsec_...` secret. **Leave this running** in its own terminal for the whole session |
| 0.12 | Put that `whsec_` in `backend/.env` as `STRIPE_WEBHOOK_SECRET` | ⚠️ This secret belongs to the `listen` session and is **different** from the one a dashboard-created endpoint shows. Using the dashboard's here is the most common reason every delivery 400s |
| 0.13 | Restart the backend | Boots with no errors |

### 0d. Confirm it is wired up

| # | Step | Expected result |
|---|---|---|
| 0.14 | Open `http://localhost:8000/docs` | ✅ A **`billing`** section with `POST /api/billing/checkout` and `POST /api/billing/portal`; `GET /api/me/subscription` under **`me`**; `POST /api/webhooks/stripe` under **`webhooks`** |
| 0.15 | `cd frontend && npm run dev`, sign in | Sidebar shows **Settings** as a live link (no "Soon" chip) |
| 0.16 | Open `/dashboard/settings` | ✅ Plan card renders, badge reads **Free** |

---

## 1. Free tier, before any payment

| # | Step | Expected result |
|---|---|---|
| 1.1 | `GET /api/me/subscription` as a new user | ✅ `premium: false`, `status: null`, `has_billing_account: false`, `ai_limit: 3`, `ai_used: 0`, `ai_remaining: 3` |
| 1.2 | Settings page | ✅ "Free" badge, "AI coach — 3 of 3 left today", **Upgrade to Premium** button, no "Manage billing" |
| 1.3 | Coach page with 0 runs used | ✅ Button enabled, **no** remaining-count text — the count only appears at 1 or fewer |
| 1.4 | Run 2 analyses, reload Coach | ✅ "1 free analysis left today" appears below the button |
| 1.5 | Run a 3rd, reload | ✅ Button **disabled**, tooltip "You've used today's free analyses", and "No free analyses left today · Upgrade for unlimited" linking to Settings |
| 1.6 | `POST /api/coach/analyses` via `/docs` while over quota | ✅ **402**, body `{"code": "free_tier_limit_reached", "message": ..., "limit": 3, "used": 3, "resets_at": ...}` |
| 1.7 | Check `resets_at` | ✅ 24h after your **oldest** run in the window, not 24h from now — that is the run whose expiry frees the next slot |
| 1.8 | `GET /api/coach/analyses` and `GET /api/coach/analyses/{id}` while over quota | ✅ Both **200**. Reading past coaching is never metered — it was already paid for |
| 1.9 | Open the Coach page while over quota | ✅ Full history renders normally. The paywall declines to give more; it does not take away what exists |
| 1.10 | Wait for the oldest run to age past 24h, retry | ✅ One run becomes available. The window is rolling, not a calendar day — you cannot spend the allowance at 23:59 and again at 00:01 |

---

## 2. Checkout

| # | Step | Expected result |
|---|---|---|
| 2.1 | Settings → **Upgrade to Premium** | ✅ Button shows a pending state and stays busy until the browser leaves — it never returns to idle first (two clicks would open two checkout sessions) |
| 2.2 | Land on Stripe checkout | ✅ Hosted Stripe page, your product and price, your email prefilled |
| 2.3 | Check the page source of `/dashboard/settings` | ✅ No Stripe publishable key, no Stripe.js. Checkout is hosted; the browser only ever gets a URL |
| 2.4 | Pay with `4242 4242 4242 4242` | ✅ Redirected back to `/dashboard/settings?checkout=success` |
| 2.5 | **Watch the moment you land** | ✅ "Payment received — confirming your subscription with Stripe", then the page updates itself to "You're on Premium" within a few seconds. See section 5 for why this exists |
| 2.6 | Check the `stripe listen` terminal | ✅ `checkout.session.completed` and `customer.subscription.created` both forwarded, both `[200]` |
| 2.7 | Reload Settings | ✅ "Premium" badge, "AI coach — unlimited", "Renews on <date>", **Manage billing** button, no Upgrade button |
| 2.8 | Coach page | ✅ Button enabled, no quota text at all |
| 2.9 | Run 5+ analyses in a row | ✅ All succeed. Premium short-circuits before the count is even queried |
| 2.10 | Cancel at the Stripe page instead of paying (press Back) | ✅ Returns to `/dashboard/settings?checkout=cancelled` with "Checkout cancelled — nothing was charged" |
| 2.11 | `POST /api/billing/checkout` while already premium | ✅ **409**. A second subscription against the same customer would bill twice |

---

## 3. The billing portal

| # | Step | Expected result |
|---|---|---|
| 3.1 | Settings → **Manage billing** | ✅ Stripe's hosted portal opens |
| 3.2 | Cancel the subscription there, return to FitMind | ✅ Settings reads **"Your plan ends on `<date>`. You keep premium until then."** — not "Renews on" |
| 3.3 | Confirm the badge still says Premium after cancelling | ✅ Correct, and important: they paid through the period. `status` is still `active`, which is exactly why `cancel_at_period_end` is stored separately |
| 3.4 | Coach page after cancelling-but-paid-up | ✅ Still unlimited |
| 3.5 | Renew/resubscribe in the portal | ✅ Settings returns to "Renews on `<date>`" |
| 3.6 | `POST /api/billing/portal` as a user who has never opened checkout | ✅ **404**. There is nothing to manage, and creating a customer just to open an empty portal answers no question they had |
| 3.7 | After a subscription has fully lapsed, check Settings | ✅ Badge "Free", **and** the Manage billing button is still there — past invoices are exactly what a lapsed user comes here for |

---

## 4. Webhook behaviour

The tests that matter most, because these are the paths that go wrong silently in
production. `stripe trigger` sends synthetic events without needing a real card.

| # | Step | Expected result |
|---|---|---|
| 4.1 | `stripe trigger customer.subscription.updated` | ✅ Forwarded, `[200]`, no traceback |
| 4.2 | Send the same event twice (`stripe events resend <evt_id>`) | ✅ Both succeed and the row is identical afterwards. Handlers re-fetch canonical state rather than applying a delta, so a duplicate writes the same thing twice |
| 4.3 | Resend an **older** event after a newer one | ✅ State still reflects reality, not the older event. Stripe promises no ordering; re-fetching is what makes that harmless |
| 4.4 | POST to `/api/webhooks/stripe` with no `Stripe-Signature` | ✅ **400** "Invalid signature" |
| 4.5 | POST with a signature computed from a *different* body | ✅ **400** — one opaque message for every verification failure, so nothing hints at how to shape a forgery |
| 4.6 | Replay a delivery captured more than 5 minutes ago | ✅ **400**. The replay tolerance is set explicitly; without it a captured-and-replayed delivery would be accepted forever |
| 4.7 | Unset `STRIPE_WEBHOOK_SECRET`, restart, send an event | ✅ **503**, and nothing is written. An unconfigured secret fails closed, never open |
| 4.8 | Stop the network (or set an invalid `STRIPE_SECRET_KEY`), then trigger a subscription event | ✅ **5xx**, and `stripe listen` shows the delivery failed so Stripe will retry. ⚠️ A 2xx here would tell Stripe the event is handled and **permanently lose** that state change |
| 4.9 | `stripe trigger invoice.payment_succeeded` | ✅ **204**, and no Stripe API call is made. Events we do not subscribe to are acknowledged and ignored, not 500'd |
| 4.10 | Check the row after a `customer.subscription.deleted` | ✅ `status: "canceled"`, and `stripe_subscription_id` is **retained** — Stripe keeps the object, and dropping our reference would make a past subscription unauditable from this side |

---

## 5. The confirmation gap

Worth understanding before reporting 2.5 as a bug.

Stripe redirects the browser back **before** it delivers the webhook. So for a
second or two after a successful payment, the database still says Free — and the
page a user lands on immediately after paying would say "Free plan" if nothing
covered it.

The tempting fix is to have the success URL mark the user premium. That URL is
just an address anyone can type, so it would put the entire paywall one
address-bar edit deep. The paywall stays where it is; the UI covers the gap.

| # | Step | Expected result |
|---|---|---|
| 5.1 | Pay, and watch `/dashboard/settings?checkout=success` | ✅ "Payment received — confirming…", then it becomes "You're on Premium" on its own. No manual reload |
| 5.2 | Stop `stripe listen`, then pay | ✅ The confirming message retries 4 times, then becomes "Still confirming your payment" pointing at the billing portal — rather than spinning forever |
| 5.3 | Restart `stripe listen` and let the queued events flush, reload | ✅ Premium appears. Nothing was lost, it was only late |
| 5.4 | Visit `/dashboard/settings?checkout=success` directly, having paid nothing | ✅ You are **not** premium. The message appears, retries, gives up. **This is the security property** — if this ever shows Premium, stop and treat it as a paywall bypass |

---

## 6. Failed and unusual payments

Stripe's test cards, at checkout.

| # | Card | Expected result |
|---|---|---|
| 6.1 | `4000 0000 0000 0002` (declined) | ✅ Stripe rejects it on its own page; no subscription created, you stay Free |
| 6.2 | `4000 0000 0000 9995` (insufficient funds) | ✅ Same |
| 6.3 | `4000 0025 0000 3155` (requires 3DS) | ✅ Authentication prompt, then premium as normal |
| 6.4 | Get a real subscription to `past_due`: subscribe with `4000 0000 0000 0341` (attaches, then fails on the renewal charge), or edit the subscription's status from the Stripe dashboard. ⚠️ `stripe trigger invoice.payment_failed` builds a *synthetic* object and will not move your existing subscription | ✅ Status becomes `past_due`. **Still premium** — Stripe retries for days, and revoking on the first failed charge would lock a paying customer out over an expired card |
| 6.5 | Settings while `past_due` | ✅ Amber "Your last payment failed — Stripe is retrying. Update your card…" — the user finds out while it is still fixable |
| 6.6 | Let Stripe exhaust its retries (or cancel in the dashboard) | ✅ Status becomes `canceled` or `unpaid`, premium ends, quota returns to 3/day |

---

## 7. Account deletion

The path with real money attached, and the one whose ordering is load-bearing.

| # | Step | Expected result |
|---|---|---|
| 7.1 | As a **premium** user, delete the account in Clerk's dashboard | ✅ Clerk sends `user.deleted` |
| 7.2 | Check Stripe | ✅ The subscription is **cancelled**. Deleting your account stops the charges |
| 7.3 | Check the database | ✅ User row gone, and its `subscriptions` row with it by CASCADE |
| 7.4 | Confirm the order in the log | ✅ Cancel happens **before** the delete. `subscriptions.user_id` is ON DELETE CASCADE, so reading it afterwards finds nothing and the card keeps being charged with nothing left pointing at it |
| 7.5 | Break the Stripe key, then delete a premium user | ✅ The webhook **5xx**s and the user is **not** deleted, so Clerk retries. ⚠️ Deleting anyway would destroy the last local record of a subscription that is still charging someone |
| 7.6 | Delete a **free** user | ✅ Deletes cleanly, no Stripe call |
| 7.7 | Delete a user who opened checkout but never paid | ✅ Deletes cleanly. There is a customer but no subscription, so there is nothing to cancel |

---

## 8. Security and isolation

| # | Step | Expected result |
|---|---|---|
| 8.1 | `POST /api/billing/checkout` with no `Authorization` header | ✅ **401** |
| 8.2 | `POST /api/billing/portal` with no header | ✅ **401** |
| 8.3 | `GET /api/me/subscription` with no header | ✅ **401** |
| 8.4 | Sign in as user B while user A is premium; check B's plan | ✅ B is Free. Entitlement is per-user, read by `user_id` |
| 8.5 | View source on `/dashboard/settings` | ✅ No Clerk JWT and no Stripe key in the HTML — the plan is fetched server-side |
| 8.6 | Search the codebase for a request path writing `status` | ✅ None. Only `crud/subscription.apply_stripe_state` writes it, and only the webhook calls it |
| 8.7 | Change `ai_remaining` in the browser devtools, then click Analyse | ✅ Still **402**. The button state is a convenience; the server is the gate |
| 8.8 | `grep STRIPE_SECRET_KEY backend/.env` | ✅ Starts `rk_`, not `sk_`. An account secret key here works and is the easy thing to paste, which is exactly why it is worth checking rather than assuming |
| 8.9 | Confirm no key is in source control:<br>`git grep -nE "[sr]k_(test\|live)_[A-Za-z0-9]{12,}" -- ':!*.env.example'` | ✅ No matches. Keys live in `.env`, which is git-ignored. A committed key is the leading cause of Stripe account takeover, and an `rk_test_` in a repo is a warning that an `rk_live_` will eventually follow the same path.<br><br>The length bound and the exclusion are both deliberate: without them the `xxxx` placeholders in `.env.example` match every time, and a check that always fails is a check you learn to ignore |

---

## 9. Degradation with billing unconfigured

The whole feature must be optional — CI has no Stripe account, and neither does a
fresh clone.

| # | Step | Expected result |
|---|---|---|
| 9.1 | Unset `STRIPE_SECRET_KEY` and `STRIPE_PRICE_ID`, restart | ✅ Backend boots with no errors or warnings |
| 9.2 | `GET /api/me/subscription` | ✅ **200**, `billing_enabled: false`, everyone free tier |
| 9.3 | Settings page | ✅ Renders, and says "Billing is not configured on this deployment" instead of showing an Upgrade button that would 503 |
| 9.4 | `POST /api/billing/checkout` anyway | ✅ **503** — a configuration problem, not a client error |
| 9.5 | Coach with billing off | ✅ Free-tier limit still applies. Metering does not depend on Stripe |
| 9.6 | Set only `STRIPE_SECRET_KEY`, leaving the price unset | ✅ `billing_enabled` still false. A key with nothing to charge for cannot sell anything |

---

## 10. Responsive and accessibility

| # | Step | Expected result |
|---|---|---|
| 10.1 | Settings at 375px (iPhone SE) | ✅ No horizontal scroll; plan header and badge stack cleanly |
| 10.2 | 768px / 1440px | ✅ Content max-width constrained, not stretched edge to edge |
| 10.3 | Tab to Upgrade / Manage billing | ✅ Visible focus ring on both |
| 10.4 | Trigger a checkout failure | ✅ Inline error announced (`role="alert"`) |
| 10.5 | While a billing button is pending | ✅ `aria-busy` set; the label does not change, so the control does not resize mid-request |
| 10.6 | Confirming message after checkout | ✅ `aria-live="polite"` — a screen reader hears the plan confirm without the page being re-read |
| 10.7 | Premium / Free badge | ✅ The text says which; nothing depends on the colour alone |

---

## 11. Automated checks

Run before committing:

```bash
cd frontend && npx tsc --noEmit     # expect: no output
cd frontend && npm run lint         # expect: no output
cd frontend && npm run build        # expect: ✓ Compiled successfully, /dashboard/settings listed
cd backend  && .venv\Scripts\python -m pytest -q   # expect: 194 passed, 6 skipped
```

⚠️ The 6 skips need a live database; they opt in via `TEST_DATABASE_URL` (see
`tests/conftest.py`).

None of the 194 tests touch Stripe's API or a database. That is deliberate — they
cover the decisions (what counts as premium, what a refusal returns, how an event
maps to a row) rather than the integration. **Sections 0–7 above are the only
thing that tests the integration**, and they cannot be automated away.

---

## Where the money logic lives

Four files, if you need to change a rule rather than find a bug:

| Question | File |
|---|---|
| What counts as premium? What does the free tier get? | `app/core/entitlements.py` |
| What does Stripe's object look like? | `app/core/stripe_client.py` |
| Who may write plan state? | `app/crud/subscription.py` |
| When does plan state change? | `app/api/routes/stripe_webhooks.py` |

---

## Known limitations (deliberate, not defects)

- **The confirmation gap is visible.** Section 5. Closing it properly needs the
  success page to poll, which is what it does; closing it *cheaply* would mean
  trusting the redirect, which would be a paywall bypass.
- **One plan, one price.** No annual option, no tiers, no proration handling —
  `STRIPE_PRICE_ID` is a single value. Multiple prices would need the price id
  stored per checkout rather than read from config.
- **No proration or plan switching in-app.** Stripe's portal handles it if the
  product is configured for it; FitMind neither offers nor blocks it.
- **No dunning emails from FitMind.** Stripe sends its own. A `past_due` user
  sees the warning only when they visit Settings.
- **No invoice history in-app.** The portal has it, and it is always correct
  there. Rebuilding it here would mean a second thing to keep in sync.
- **Quota is per rolling 24h, not per calendar month.** It meters the AI cost,
  which is a daily-rate problem, not a monthly-bill problem.
- **`FREE_DAILY_AI_ANALYSES` changes apply immediately to in-flight windows.**
  Lowering it can put a user instantly over quota. `remaining` floors at 0
  rather than going negative, but they will be refused until their oldest run
  ages out.
- **A user with no `subscriptions` row cannot open the portal.** Correct, but it
  means "Manage billing" is genuinely absent rather than disabled — there is no
  Stripe customer to show.
- **Unrecognised Stripe statuses are not premium.** If Stripe ships a new status
  that should grant access, users on it lose premium until `PREMIUM_STATUSES` is
  updated. The warning log names the constant to edit; that log is the only
  thing that makes this a five-minute fix instead of an investigation.
