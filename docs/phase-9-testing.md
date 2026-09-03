# Phase 9 — Deployment: Testing Checklist

Verify in order. **Sections 0–2 gate the rest** — there is nothing to test until
the API is up and migrated.

Legend: ✅ expected result · ⚠️ known limitation, not a bug · 🔴 stop and fix

Throughout, `API` means your Render origin (e.g. `https://fitmind-api.onrender.com`)
and `APP` means your Vercel origin (e.g. `https://fitmind.vercel.app`).

---

## 0. Before deploying (local)

| # | Step | Expected result |
|---|---|---|
| 0.1 | `cd frontend && npx tsc --noEmit` | No output |
| 0.2 | `cd frontend && npm run lint` | No output |
| 0.3 | `cd frontend && npm run build` | ✓ Compiled successfully, 14 routes |
| 0.4 | `cd backend && .venv\Scripts\python -m pytest -q` | ✅ `232 passed, 6 skipped` |
| 0.5 | `.venv\Scripts\python -m alembic current` | Shows `0006_ai_analyses_created_at_idx` |
| 0.6 | `.venv\Scripts\python -m alembic revision --autogenerate -m "drift"` | ✅ Empty `upgrade()` — models and migrations agree. **Delete the generated file** |
| 0.7 | GitHub → Actions on `main` | ✅ All three jobs green, including **backend (docker build + boot)** |

> 0.7 is the one that matters most here: that job builds `backend/Dockerfile`
> and requires a 200 from `/health` inside the running container. If it is red,
> the deploy will fail in the same way, only slower and with worse logs.

**The build's own inputs.** `npm run build` now requires `NEXT_PUBLIC_API_URL`
— locally from `.env.local`, in CI from an explicit placeholder in `ci.yml`.
Prove the guard is live before you rely on it:

| # | Step | Expected result |
|---|---|---|
| 0.8 | Rename `frontend/.env.local` aside and `npm run build` | ✅ Build **fails** naming `NEXT_PUBLIC_API_URL`, rather than producing a bundle that calls `http://localhost:8000`. Restore the file |
| 0.9 | `npm run dev` with it still renamed aside | ✅ Starts normally — the fallback is development-only by design, and dev is where it is correct |

---

## 1. The container itself

Skip if you have no local Docker — CI job `backend (docker build + boot)` covers
all of it. Run it if you have Docker and want the faster loop.

| # | Step | Expected result |
|---|---|---|
| 1.1 | `docker build -t fitmind-api ./backend` | Builds, no compiler needed (every dep is a wheel) |
| 1.2 | `docker run --rm -e DATABASE_URL='postgresql://u:p@127.0.0.1:5432/db' -e RUN_MIGRATIONS=false -e PORT=9137 -p 9137:9137 fitmind-api` | Logs `==> uvicorn on 0.0.0.0:9137` |
| 1.3 | `curl localhost:9137/health` | ✅ `{"status":"ok",...}` — proves it read `$PORT` rather than hardcoding 8000 |
| 1.4 | `docker run ... ` **without** `DATABASE_URL` | ✅ Exits immediately with a pydantic validation error. Fails loudly at boot, not on the first query |
| 1.5 | Inspect the image: `docker run --rm fitmind-api ls -la /app/.env` | ✅ No such file — `.dockerignore` kept secrets out of the layers |
| 1.6 | `docker run --rm --entrypoint whoami fitmind-api` | ✅ `fitmind`, not `root` |

---

## 2. First API deploy and migration

| # | Step | Expected result |
|---|---|---|
| 2.1 | Render → New → Blueprint, connect repo | ✅ Detects `render.yaml`, shows service **fitmind-api**, prompts for 13 secret vars |
| 2.2 | Watch the deploy log | ✅ `==> alembic upgrade head`, then `==> uvicorn on 0.0.0.0:10000` |
| 2.3 | `curl $API/health` | ✅ `{"status":"ok","service":"fitmind-api","environment":"production"}` |
| 2.4 | Check `environment` in that response | ✅ Reads `production`, **not** `development` — proves `ENVIRONMENT` reached the container |
| 2.5 | `curl $API/health/db` | ✅ `"database":"reachable"` and `"migration_revision":"0006_ai_analyses_created_at_idx"` |
| 2.6 | 🔴 If `migration_revision` is older than `0006_ai_analyses_created_at_idx` | The API is serving against a schema it does not expect. Stop — check `MIGRATION_DATABASE_URL` |
| 2.7 | `curl $API/docs` | ✅ Swagger UI loads, `templates`/`billing`/`coach` sections present |
| 2.8 | Supabase → Table editor | ✅ All tables present, `alembic_version` holds `0006_ai_analyses_created_at_idx` |
| 2.9 | Redeploy from the Render dashboard, watch the log | ✅ `alembic upgrade head` runs again and is a **no-op** — it does not re-apply anything |

**Migration failure drill.** Temporarily set `MIGRATION_DATABASE_URL` to a bad
password and redeploy:

| # | Step | Expected result |
|---|---|---|
| 2.10 | Redeploy with the bad URL | ✅ Deploy **fails**. uvicorn never starts — the container does not come up serving against an unmigrated database |
| 2.11 | The previously deployed version | ✅ Still serving. Restore the correct URL and redeploy |

---

## 3. Frontend deploy

| # | Step | Expected result |
|---|---|---|
| 3.1 | Vercel import with **Root Directory = `frontend`** | ✅ Build succeeds |
| 3.2 | Omit the root directory setting on purpose, once | ⚠️ Fails with a missing-`package.json` error — worth seeing so you recognise it |
| 3.3 | Visit `APP` | ✅ Landing page renders |
| 3.4 | DevTools → Network → the document request → Response Headers | ✅ `x-frame-options: DENY`, `x-content-type-options: nosniff`, `referrer-policy: strict-origin-when-cross-origin`, `permissions-policy`, `strict-transport-security` |
| 3.5 | Same headers | ✅ **No** `x-powered-by` |
| 3.6 | View source on the landing page | ✅ No `sk_` or `whsec_` anywhere |

**The silent-misconfiguration check.** `lib/api.ts` falls back to
`http://localhost:8000` when `NEXT_PUBLIC_API_URL` is unset. That is right for
local dev and dangerous in production: the build would succeed and the deployed
app would quietly call the visitor's own machine. `next.config.ts` now fails a
production build without the variable, so this is a guard to confirm rather than
a risk to watch — but confirm it, because the whole point is that a broken
version of this looks healthy.

| # | Step | Expected result |
|---|---|---|
| 3.7 | Sign in, open the dashboard, watch the Network tab | ✅ Requests go to `$API`. 🔴 Any request to `localhost:8000` means `NEXT_PUBLIC_API_URL` did not reach the build |
| 3.8 | Change `NEXT_PUBLIC_API_URL` in Vercel and **do not** redeploy | ⚠️ Nothing changes — it is inlined at build time. Redeploy to apply. Not a bug; the thing to know |
| 3.9 | Remove `NEXT_PUBLIC_API_URL` in Vercel and redeploy | ✅ The deploy **fails** with an error naming the variable. Restore it and redeploy. 🔴 A green deploy here means the guard is not running |

---

## 4. CORS and auth end to end

| # | Step | Expected result |
|---|---|---|
| 4.1 | With `CORS_ORIGINS` still on localhost, load the dashboard | ⚠️ Requests fail with a CORS error in the console — confirms the allow-list is actually enforced |
| 4.2 | Set `CORS_ORIGINS` to `APP`, wait for the redeploy, reload | ✅ Data loads |
| 4.3 | Sign up as a brand-new user | ✅ Lands on `/dashboard` |
| 4.4 | Supabase → `users` table | ✅ A row for that user exists — the Clerk webhook fired |
| 4.5 | 🔴 If no row appears | `CLERK_WEBHOOK_SECRET` is missing or wrong. Clerk Dashboard → Webhooks → the endpoint's delivery log will show 503 |
| 4.6 | Sign out, visit `APP/dashboard/workouts` | ✅ Redirected to sign-in with `redirect_url` set |
| 4.7 | Sign back in | ✅ Returns to the page you asked for |
| 4.8 | `curl $API/api/workouts` (no token) | ✅ 401 |
| 4.9 | `curl -H "Origin: https://evil.example" $API/api/workouts` | ✅ No `access-control-allow-origin` for that origin. ⚠️ `access-control-allow-credentials: true` *is* present and grants nothing — without the origin header the browser will not expose the response (pinned in `tests/test_cors.py`) |
| 4.10 | Sign in as user B, open a URL for user A's workout | ✅ 404 page — not the data, and not a 403 that would confirm it exists |

**Preview deployments.** Vercel builds one per branch whether or not you wanted
it. Skip this block only if you have decided previews stay blocked — and if so,
run 4.11 anyway, so "previews do not work" is something you know rather than
something you discover mid-review.

| # | Step | Expected result |
|---|---|---|
| 4.11 | Push a branch, open its preview URL, sign in, load the dashboard | With `CORS_ORIGIN_REGEX` unset: ⚠️ CORS errors in the console, no data. The page shell still renders |
| 4.12 | Set `CORS_ORIGIN_REGEX` on Render to `^https://fitmind-git-[a-z0-9-]+-<team>\.vercel\.app$`, wait for the redeploy, reload the preview | ✅ Data loads. Take the team slug from the preview URL itself — it is not always your username |
| 4.13 | `curl -H "Origin: https://evil.example" $API/health` and `-H "Origin: https://someone-elses-app.vercel.app"` | ✅ Neither gets `access-control-allow-origin`. The pattern allows *your* previews, not Vercel |
| 4.14 | Set `CORS_ORIGIN_REGEX` to `.*\.vercel\.app` and redeploy | ✅ The container **refuses to start** — a pattern that wide hands every Vercel deployment a credentialed origin. Restore the narrow one. 🔴 A successful boot means the validator is gone |
| 4.15 | Production `APP` after all of the above | ✅ Still works — the pattern adds preview origins, it does not replace `CORS_ORIGINS` |

---

## 5. Core app on production data

The Phase 5–7 checklists cover the behaviour. This is the subset that can break
*because* the pieces are now on different hosts.

| # | Step | Expected result |
|---|---|---|
| 5.1 | Create a workout with two exercises, save | ✅ Persists; reload confirms |
| 5.2 | Exercise search — type `bench` | ✅ Results appear. Confirms the seeded catalog survived the production migration |
| 5.3 | Create a template, use **Log now** | ✅ Creates today's workout with the exercises copied |
| 5.4 | Progress page | ✅ Charts render from real data |
| 5.5 | Coach → Run analysis | ✅ Returns findings. With `ANTHROPIC_API_KEY` set, a written narrative too |
| 5.6 | Unset `ANTHROPIC_API_KEY`, redeploy, run again | ✅ Findings still returned, narrative absent — degrades, does not error |
| 5.7 | Dates around midnight in your timezone | ✅ "Today" is still today — the server is UTC, the formatting is local |
| 5.8 | Start a coach analysis, and while it is still running `curl $API/health` from another terminal | ✅ Answers immediately. 🔴 A hang that clears when the analysis finishes means the model call is back on the event loop |

> 5.8 is cheap and worth doing once. The API runs a single uvicorn worker, so a
> synchronous model call does not occupy a thread — it occupies the *event
> loop*, and everything else in the process waits behind it. Render's health
> check is one of those things, and its timeout decides whether the container
> gets restarted: a slow model call would take down a healthy API. The coach
> uses `AsyncAnthropic` and awaits it for this reason, and
> `tests/test_coach.py` fails if that ever regresses.

---

## 6. Billing end to end

Use Stripe **test mode** and card `4242 4242 4242 4242`.

| # | Step | Expected result |
|---|---|---|
| 6.1 | Settings page with Stripe configured | ✅ Upgrade button visible |
| 6.2 | Unset `STRIPE_SECRET_KEY`, redeploy | ✅ Button **hidden**, not broken. Restore afterwards |
| 6.3 | Click Upgrade | ✅ Redirects to Stripe Checkout |
| 6.4 | Complete the payment | ✅ Returns to `APP`, **not** localhost. 🔴 Landing on localhost means `FRONTEND_URL` is wrong |
| 6.5 | Settings after checkout | ✅ Shows Premium, with the renewal date |
| 6.6 | Supabase → `subscriptions` | ✅ Row with `status = active` and the right `price_id` |
| 6.7 | Stripe → Webhooks → delivery log | ✅ All deliveries 2xx |
| 6.8 | 🔴 Any 400 in that log | `STRIPE_WEBHOOK_SECRET` is the `stripe listen` one, not the endpoint's. They differ |
| 6.9 | Stripe → cancel the subscription | ✅ App reflects it within seconds |
| 6.10 | Manage billing → portal | ✅ Opens, returns to `APP` |
| 6.11 | Free account, run the coach 4× in a day | ✅ Fourth is refused with the quota message (`FREE_DAILY_AI_ANALYSES=3`) |
| 6.12 | Premium account, same | ✅ Unlimited — by the *quota*. The rate limits below still apply |

---

## 6a. AI rate limits — the spending ceiling

The coach is the only endpoint that bills per call, so it is the only one where
a refused request saves real money. The quota above cannot bound that spend:
accounts are free, so an attacker never needs to exceed anyone's allowance —
they need more accounts, each arriving with a fresh one.

Two limits, and they refuse with **429 and a `Retry-After`**, not 402. Nothing
the user can buy changes the answer, so an upgrade prompt here would be selling
something that does not fix it.

Set the limits low to test them, then put them back.

| # | Step | Expected result |
|---|---|---|
| 6a.1 | `AI_RATE_LIMIT_PER_USER_HOURLY=2`, redeploy, run the coach 3× as a **premium** account | ✅ Third is refused, 429. Premium is exempt from the quota and **not** from this. 🔴 A third analysis means the rate limit is not applied to premium |
| 6a.2 | Read that response's headers | ✅ `retry-after` present, a positive number of seconds |
| 6a.3 | The JSON body | ✅ `detail.code` is `rate_limited`, and the message does not mention upgrading |
| 6a.4 | The Coach page after that refusal | ✅ Shows the wait message. **No** "Upgrade for unlimited" prompt — that is the 402's copy and this is not a billing problem |
| 6a.5 | Wait out the `Retry-After`, run again | ✅ Succeeds. The window is rolling, so a slot frees as the oldest run ages out |
| 6a.6 | `AI_RATE_LIMIT_GLOBAL_DAILY=1`, redeploy, run the coach once, then again from a **different account with a full allowance** | ✅ The second is refused, 429, `detail.code` is `ai_capacity_reached` — the ceiling is global, which is the only framing more accounts cannot widen |
| 6a.7 | Render logs during 6a.6 | ✅ A `WARNING` naming `AI_RATE_LIMIT_GLOBAL_DAILY`. It is the only signal this ceiling is being hit — `/health/db` stays green throughout |
| 6a.8 | While the ceiling is full, open the Coach page and read an existing analysis | ✅ Loads. Only running a *new* analysis is limited; history already paid for is never withheld |
| 6a.9 | Restore both limits, redeploy | ✅ Runs succeed again |

> The counts read rows from completed runs, and this run's row is written after
> the model call returns — so two overlapping requests can both pass the same
> check. The overshoot is bounded by how many coach requests are in flight at
> once, which on one worker at 0.1 CPU is very small. Deliberate: these are a
> budget guard, not an invariant. `app/core/entitlements.py` says what the exact
> version would cost.

---

## 7. Webhook hardening

| # | Step | Expected result |
|---|---|---|
| 7.1 | `curl -X POST $API/api/webhooks/stripe -d '{"type":"customer.subscription.updated"}'` | ✅ 400 Invalid signature — a forged "make me premium" is rejected |
| 7.2 | `curl -X POST $API/api/webhooks/clerk -d '{}'` | ✅ 400 |
| 7.3 | Stripe → Webhooks → **Resend** a past event | ✅ 2xx, and the subscription row is unchanged — the handler is idempotent |
| 7.4 | Both endpoints over plain `http://` | ✅ Redirected to HTTPS by the platform |

---

## 8. Resilience

| # | Step | Expected result |
|---|---|---|
| 8.1 | Leave the app idle 20 min, then load the dashboard | ⚠️ ~1 min cold start. Skeletons show; it does not error |
| 8.2 | Pause the Supabase project, load the dashboard | ✅ Red "Couldn't load your workouts" banner. **Sidebar and page still render** |
| 8.3 | While paused, `curl $API/health` | ✅ Still 200 — liveness does no database I/O, so Render does not restart the container |
| 8.4 | While paused, `curl $API/health/db` | ✅ 503, `"database":"unreachable"`, and the detail is a class name only — no DSN, no password |
| 8.5 | Resume Supabase, reload | ✅ Recovers with no redeploy |
| 8.6 | `APP/dashboard/workouts/not-a-uuid` | ✅ 404 page, not a server error |
| 8.7 | 375px viewport on the deployed app | ✅ No horizontal scroll |

---

## 9. Rollback drill

Do this once, deliberately, before you need it.

| # | Step | Expected result |
|---|---|---|
| 9.1 | Change some visible text, merge to `main` | ✅ CI runs, then Vercel and Render deploy |
| 9.2 | Push a commit that breaks the build | ✅ Render does **not** deploy it — `autoDeployTrigger: checksPass` holds it behind the red suite |
| 9.3 | Vercel → previous deployment → Promote to Production | ✅ Old version live within seconds |
| 9.4 | Render → Events → previous deploy → Rollback | ✅ Old image redeploys |
| 9.5 | Read the "Rolling back" section of `docs/deployment.md` | ✅ You understand why a rollback does **not** revert a migration |

---

## 10. Automated checks

```bash
cd frontend && npx tsc --noEmit     # expect: no output
cd frontend && npm run lint         # expect: no output
cd frontend && npm run build        # expect: ✓ Compiled successfully
cd backend  && .venv\Scripts\python -m pytest -q   # expect: 232 passed, 6 skipped
```

Plus, on every pull request, `backend (docker build + boot)` in CI.

⚠️ The 6 skips need a live database and opt in via `TEST_DATABASE_URL`.

Two of the sections above are covered by the suite rather than only by hand:

- `tests/test_cors.py` — the allow-list in both directions, and the preview
  pattern. §4.13 and §4.14 have automated equivalents, so a too-wide
  `CORS_ORIGIN_REGEX` fails at boot and in CI rather than serving quietly.
- `tests/test_coach.py` — that the model call is awaited and the client closed.
  §5.8's failure mode is caught before it reaches a container.
- `tests/test_entitlements.py` — the rate limits, including the two properties
  §6a exists to check by hand: that premium is not exempt, and that the global
  ceiling refuses a user who is well within their own allowance.
- `tests/test_migrations.py` — revision-id length, a single head, and a
  `downgrade()` on every migration. §0.5 is the step that catches a migration
  that cannot apply; this makes the cheap half of it automatic.

⚠️ **Migrations are still not executed by CI.** The Docker job sets
`RUN_MIGRATIONS=false` because it has no database, and the suite builds its
schema from the models rather than by upgrading. `test_migrations.py` reads the
revision files statically — it does not run them. §0.5 and §0.6 remain the only
place a migration is actually executed before production, which is why they are
listed as gates and not as nice-to-haves.

---

## Open items (not done, tracked)

- **Content-Security-Policy.** Not shipped. It needs the production Clerk domain
  to be verified against, and a wrong one blanks the sign-in page with nothing
  in the server logs. Add it **report-only** first, once `APP` exists, then
  enforce. Reasoning in `frontend/next.config.ts`.
- **Preview environments.** `main` goes straight to production. CI gates it, but
  there is no staging deploy to click through first. Vercel's per-branch
  previews can now reach the API (`CORS_ORIGIN_REGEX`, §4.11–4.15), which makes
  them clickable — not a staging environment. They run against the *production*
  API and the production database.
- **Uptime monitoring.** Nothing watches `/health/db`. A paused Supabase project
  is discovered by a visitor.
- **Log aggregation.** Render's log tail only; nothing is retained or searchable.

## Known limitations (deliberate, not defects)

- **Cold starts** — ~1 min on Render free. Fixed by `plan: starter`.
- **Single instance** — migrations run at container start, safe only because
  there is one. Scaling out means moving to `preDeployCommand` and setting
  `RUN_MIGRATIONS=false`.
- **Supabase free pauses** after 7 days idle and needs a manual resume.
- **Anthropic has no free tier** — the coach is the one thing that bills per use.
