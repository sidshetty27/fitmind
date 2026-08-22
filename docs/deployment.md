# Deployment

How FitMind goes to production, and why in this order.

- **Frontend** → Vercel (Next.js 16, App Router)
- **API** → Render, from `backend/Dockerfile`, declared in `render.yaml`
- **Database** → Supabase Postgres (already live since Phase 3)
- **Auth** → Clerk · **Payments** → Stripe · **AI** → Anthropic

---

## The ordering problem

The two services need each other's URLs:

- the API needs `CORS_ORIGINS` and `FRONTEND_URL` — the Vercel origin
- the frontend needs `NEXT_PUBLIC_API_URL` — the Render origin

Neither exists before the first deploy, so something has to go first and be
corrected afterwards. **Deploy the API first**: its hostname is predictable
from the service name in `render.yaml` (`fitmind-api` → `https://fitmind-api.onrender.com`),
while Vercel's depends on the project name and your account. That makes the
frontend's config knowable in advance and the API's the one you come back to.

Expect to touch the API's env vars twice. That is the shape of the problem, not
a missed step.

One consequence worth internalising before you start: `NEXT_PUBLIC_API_URL` is
inlined into the client bundle at **build** time. Changing it in Vercel's
dashboard has no effect until you redeploy.

---

## 0. Before you start

| | |
|---|---|
| `main` is green | `image`, `backend (pytest)`, and `frontend` jobs all passing |
| Migrations are current | `alembic current` locally shows `0005_subscriptions` |
| Decide the Clerk instance | development (`pk_test_`) or production (`pk_live_`) — see below |

**The Clerk decision gates everything else**, so make it now. A Clerk
*production* instance is a separate instance: separate users, separate JWT
template, separate webhook endpoint and signing secret — and it requires DNS
records on a domain you own. Clerk will not issue live keys for a `*.vercel.app`
URL.

For a portfolio deployment, staying on the development instance is a legitimate
choice: it works on any origin, at the cost of a banner and rate limits. What
you must not do is start on one and switch later without redoing the webhook
endpoints and secrets in both Clerk and this app's config.

---

## 1. Supabase — production database

You already have one from Phase 3. The decision is whether the deployed app
shares it with your local development.

**Use a separate Supabase project for production if you can.** Sharing means
a local `alembic downgrade` or a bad seed script reaches real users' data, and
there is no undo. Free-tier accounts allow two projects.

Whichever you choose, collect **two** connection strings from
Project Settings → Database:

| Variable | Which string | Port | Why |
|---|---|---|---|
| `DATABASE_URL` | Transaction pooler | 6543 | Per-request connections — what pgbouncer's transaction mode is built for |
| `MIGRATION_DATABASE_URL` | **Session pooler** | 5432 | DDL needs session state the transaction pooler cannot hold |

> Prefer the **session pooler** over the "Direct connection" for the migration
> URL. Both are port 5432 and both work for DDL, but Supabase's direct host is
> IPv6-only, and a cloud host that has no IPv6 route fails with a connection
> timeout that looks nothing like the networking problem it is.

URL-encode special characters in the password (`@` → `%40`, `#` → `%23`). Paste
the scheme exactly as given — `app/core/config.py` normalises it to
`postgresql+psycopg://` for you.

---

## 2. API on Render

### Create it from the Blueprint

1. Render Dashboard → **New** → **Blueprint**
2. Connect the GitHub repo and pick `main`. Render reads `render.yaml`.
3. It will prompt for every `sync: false` variable. Fill in what you have; the
   Clerk webhook and Stripe values come later — leave them blank for now.
4. **Apply**.

For the first deploy, put a placeholder in `CORS_ORIGINS` and `FRONTEND_URL`
(`http://localhost:3000` is fine). You return to these in step 4.

### What happens on deploy

`backend/docker-entrypoint.sh` runs `alembic upgrade head` and then starts
uvicorn. A failed migration exits non-zero before uvicorn starts, so the deploy
fails rather than serving against a schema the code does not expect.

**This is the first time migrations run against the production database.** If
you created a fresh Supabase project, it applies all five from empty. Watch the
deploy log for `==> alembic upgrade head`.

### Verify

```bash
curl https://fitmind-api.onrender.com/health
# {"status":"ok","service":"fitmind-api","environment":"production"}

curl https://fitmind-api.onrender.com/health/db
# {"status":"ok","database":"reachable","latency_ms":..,"migration_revision":"0005_subscriptions"}
```

`migration_revision` is the one to read. It answers "did the migration actually
run?" without shelling into anything, and a revision older than
`0005_subscriptions` means the API is serving against a schema it does not
expect.

> **Free tier:** the service spins down after 15 minutes idle and takes about a
> minute to wake. The first request after a quiet period will feel broken and
> is not. `plan: starter` in `render.yaml` removes this.

---

## 3. Frontend on Vercel

1. Vercel → **Add New** → **Project** → import the repo
2. **Root Directory: `frontend`** — this is the one setting that is not
   inferred, and getting it wrong produces a build error about a missing
   `package.json` that reads like a corrupt repo.
3. Framework preset: Next.js. Leave the build and output settings alone.
4. Environment variables:

```
NEXT_PUBLIC_API_URL=https://fitmind-api.onrender.com
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_...
CLERK_SECRET_KEY=sk_...
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
NEXT_PUBLIC_CLERK_SIGN_IN_FALLBACK_REDIRECT_URL=/dashboard
NEXT_PUBLIC_CLERK_SIGN_UP_FALLBACK_REDIRECT_URL=/dashboard
```

No trailing slash on `NEXT_PUBLIC_API_URL`; `lib/api.ts` joins paths onto it.

5. Deploy, and note the resulting origin (`https://<project>.vercel.app`).

---

## 4. Close the loop

Now both URLs exist. Four things still point at nothing.

### 4a. CORS and the return URL — on Render

```
CORS_ORIGINS=https://<project>.vercel.app
FRONTEND_URL=https://<project>.vercel.app
```

Both, and they are not the same thing: `CORS_ORIGINS` is a browser allow-list
that may hold several entries, `FRONTEND_URL` is the single place Stripe returns
someone to after checkout. Leave the latter on localhost and paying customers
land on a machine that is not running.

Add the Vercel origin to `CLERK_AUTHORIZED_PARTIES` too, if you set it.

Saving these triggers a redeploy. Wait for it.

### 4b. Clerk webhook

Clerk Dashboard → **Webhooks** → add endpoint:

- URL: `https://fitmind-api.onrender.com/api/webhooks/clerk`
- Events: `user.created`, `user.updated`, `user.deleted`

Copy the **Signing Secret** into `CLERK_WEBHOOK_SECRET` on Render.

Until it is set the endpoint returns 503 to every delivery — by design; an
unverified webhook is an open door to forged user data.

### 4c. Stripe webhook

Stripe Dashboard → **Developers** → **Webhooks** → add endpoint:

- URL: `https://fitmind-api.onrender.com/api/webhooks/stripe`
- Events: `checkout.session.completed`, `customer.subscription.created`,
  `customer.subscription.updated`, `customer.subscription.deleted`

Copy its signing secret into `STRIPE_WEBHOOK_SECRET`.

> This secret is **not** the one `stripe listen` printed locally. That one is
> specific to the CLI session. Using it here means every real delivery fails
> signature verification.

Set `STRIPE_SECRET_KEY` (a restricted key — the four permissions are listed in
`backend/.env.example`) and `STRIPE_PRICE_ID`.

### 4d. Clerk allowed origins

If you moved to a Clerk production instance, add the Vercel domain there.
On a development instance there is nothing to do.

---

## 5. Verify end to end

Run `docs/phase-9-testing.md`. It exists for this and covers the failure modes
that only appear once the pieces are on different hosts.

---

## Rolling back

| Situation | Action |
|---|---|
| Bad frontend deploy | Vercel → Deployments → previous → **Promote to Production**. Instant. |
| Bad API deploy | Render → Events → previous deploy → **Rollback** |
| Bad **migration** | Neither of the above helps — see below |

A rollback reverts code, not schema. If a migration is the problem, the old
image starts and runs `alembic upgrade head` against a database that is already
past it, which is a no-op — so you are still on the new schema with the old
code. Recovering means writing the `downgrade()` path and applying it
deliberately:

```bash
cd backend
MIGRATION_DATABASE_URL='<production session pooler URL>' \
  .venv/Scripts/python -m alembic downgrade -1
```

This is why migrations in this project are additive wherever possible: an
additive change is compatible with the code that came before it, so a code
rollback alone is enough.

---

## What this costs

| | |
|---|---|
| Vercel Hobby | Free |
| Render free web service | Free, spins down after 15 min idle |
| Supabase free | Free, pauses after 7 days of inactivity |
| Clerk | Free to 10k MAU |
| Stripe | Per transaction |
| Anthropic | Per call — the only one that bills with no free floor |

Both free tiers sleep. A Supabase project that pauses needs a manual resume in
the dashboard; the API's `/health/db` will report `unreachable` until you do.

---

## Known limitations

- **Cold starts.** ~1 minute on Render free. The frontend's `loading.tsx` and
  error boundaries make it degrade rather than break, but it will feel slow.
- **No CSP.** Deliberate and explained in `frontend/next.config.ts`; it needs a
  live Clerk domain to be verified against. Tracked in the Phase 9 checklist.
- **Single API instance.** Migrations run at container start, which is only
  safe because there is exactly one. Before scaling out, switch to
  `preDeployCommand` (written and commented in `render.yaml`) and set
  `RUN_MIGRATIONS=false`.
- **No staging environment.** `main` deploys straight to production once CI is
  green. `autoDeployTrigger: checksPass` means a red suite blocks the deploy,
  which is the cheap half of the protection; a preview environment is the other
  half and is not set up.
