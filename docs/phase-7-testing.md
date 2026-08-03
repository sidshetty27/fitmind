# Phase 7 — AI Coach: Testing Checklist

Verify in order. **Section 0 is a prerequisite** — the rest will fail without it.

Legend: ✅ expected result · ⚠️ known limitation, not a bug

The coach has two halves, and the split is the thing to keep in mind while testing:

- **Findings** are computed by `app/analysis/findings.py` from the user's own logged
  sets. They are deterministic and unit-tested. They must always be right.
- **The narrative** is written by a model from those findings. It is optional. Its
  absence is a normal state, not an error.

Most of the interesting test cases live at that seam.

---

## 0. Setup (required first)

| # | Step | Expected result |
|---|---|---|
| 0.1 | `cd backend && .venv\Scripts\python -m alembic current` | Shows `0003_workout_templates` |
| 0.2 | `.venv\Scripts\python -m alembic upgrade head` | ✅ Applies `0004_ai_analyses`. **This writes to your Supabase database** — purely additive (one new table + one index), nothing existing is altered |
| 0.3 | `.venv\Scripts\python -m alembic current` | Shows `0004_ai_analyses` |
| 0.4 | `.venv\Scripts\python -m alembic revision --autogenerate -m "drift check"` | ✅ Generated `upgrade()` contains **only** the pre-existing `exercises.is_compound` server-default drift documented in the `0004` docstring — no `ai_analyses` operations. **Delete the generated file afterwards** |
| 0.5 | Confirm `ANTHROPIC_API_KEY` is **unset** in `backend/.env` | Section 3 tests the no-key path first — that is the default and it must work |
| 0.6 | Start backend: `.venv\Scripts\python run.py` | Boots, no errors |
| 0.7 | Open `http://localhost:8000/docs` | ✅ A **`coach`** section with 3 routes: POST `/api/coach/analyses`, GET `/api/coach/analyses`, GET `/api/coach/analyses/{analysis_id}` |
| 0.8 | `cd frontend && npm run dev`, sign in | Lands on `/dashboard`, sidebar shows **Coach** as a live link (not "Soon") |

---

## 1. Findings — the deterministic half

These are the observations the whole feature rests on. Thresholds live in
`app/analysis/findings.py`; each is named there so the number is arguable in one
place. The window is `COACH_WINDOW_WEEKS` (default **12 weeks**).

Seed data by logging workouts through the UI, or via `/docs`.

| # | Setup | Expected result |
|---|---|---|
| 1.1 | Log **3** sessions of Bench Press with a rising estimated 1RM | ✅ **No** plateau finding — under `MIN_SESSIONS_FOR_TREND` (4). Two or three points drift for reasons unrelated to adaptation |
| 1.2 | Log a **4th** Bench session so the estimated 1RM change is ≤ 2% | ✅ Plateau finding: *"Bench Press has stalled — your estimated max moved X% across 4 sessions."* |
| 1.3 | Make the 4-session change **negative** | ✅ Reads *"has gone backwards: your estimated max is down X%"* — named as a decline, not softened |
| 1.4 | Make the 4-session gain **> 2%** | ✅ **No** plateau finding — that is progress |
| 1.5 | Log Squat volume in the previous 3-week block, then ~20% less in the recent 3-week block | ✅ Volume-drop finding with both figures: *"down X% over the past 3 weeks (N kg to M kg)"* |
| 1.6 | Same, but only a ~10% drop | ✅ **No** finding — under `VOLUME_DROP_PCT` (15) |
| 1.7 | Log a movement **only** in the recent block (new exercise) | ✅ **No** volume-drop finding — a new movement is not "down 100%" |
| 1.8 | Log a movement **only** in the prior block | ✅ **No** volume-drop finding — covered by staleness instead, which says something more useful |
| 1.9 | Train a muscle group, then let **10+ days** pass without it | ✅ Staleness finding: *"You haven't trained hamstrings in 12 days."* |
| 1.10 | A muscle group last trained **9 days** ago | ✅ **No** finding — under `STALE_DAYS` |
| 1.11 | A muscle group you have **never** trained in the window | ✅ **No** finding — the detector only covers groups already present. It reports on your training, not on your programme |
| 1.12 | Log the same exercise **twice** at the same weight, both at RPE ≤ 7.5 | ✅ Ready-to-progress finding suggesting **weight + 2.5 kg** |
| 1.13 | Same two sessions, but one at RPE 8 | ✅ **No** finding — no evidence the load is easy |
| 1.14 | Same two sessions with **no RPE logged** | ✅ **No** finding — skipped rather than guessed at |
| 1.15 | Two sessions at *different* weights | ✅ **No** finding — it has not "stayed at" a load |
| 1.16 | An analysis with several kinds of finding | ✅ Order is: stale muscle groups → volume drops → plateaus → ready-to-progress. Things going wrong before things going well; whole muscle groups before single lifts |
| 1.17 | A brand-new account with 1 logged workout | ✅ Zero findings. The detectors stay quiet rather than firing on thin data |

---

## 2. Backend API

| # | Step | Expected result |
|---|---|---|
| 2.1 | `POST /api/coach/analyses` | ✅ **201**, returns the full analysis with `findings`, `narrative`, `model`, `window_start`, `window_end`, `workout_count` |
| 2.2 | Run it twice | ✅ Two separate rows. POST is deliberately not idempotent — each run costs a model call and writes a row Phase 8 will meter |
| 2.3 | `GET /api/coach/analyses` | ✅ Summary rows, **newest first**, with `finding_count` and `has_narrative` — no `findings` payload |
| 2.4 | `GET /api/coach/analyses?limit=1` | ✅ One row. `limit` accepts 1–100, `offset` ≥ 0 |
| 2.5 | `GET /api/coach/analyses/{id}` with a valid id | ✅ Full analysis including findings |
| 2.6 | `POST /api/coach/analyses?weeks=4` | ✅ `window_start` is 4 weeks back, not 12 |
| 2.7 | `?weeks=0` and `?weeks=53` | ✅ 422 both — the range is 1–52 |
| 2.8 | Stop the database, then POST | ✅ 500 with no partial row written |
| 2.9 | Check the stored row's `narrative`/`model` columns | ✅ Both NULL or both set — the `ck_ai_analyses_narrative_model_together` constraint makes "narrative with no model" unrepresentable |

---

## 3. The narrative — with and without a key

**This is the section most worth being careful about.** The design goal is that a
missing, failing, or refusing model costs the user their coaching *voice*, never
their analysis.

### 3a. No API key (the default)

| # | Step | Expected result |
|---|---|---|
| 3.1 | With `ANTHROPIC_API_KEY` unset, POST an analysis | ✅ **201**. `findings` populated, `narrative: null`, `model: null`. **No error anywhere** |
| 3.2 | Open `/dashboard/coach` | ✅ Findings render normally, with a quiet note that written coaching is off and how to enable it. It reads as finished work, **not** as a broken page |
| 3.3 | Check the backend log | ✅ No traceback, no warning — an unset key is a configuration choice, not a failure |

### 3b. With an API key

Set `ANTHROPIC_API_KEY` in `backend/.env` and restart. **This bills real API calls.**

| # | Step | Expected result |
|---|---|---|
| 3.4 | POST an analysis with findings present | ✅ `narrative` is a headline plus up to 3 short paragraphs; `model` records which model wrote it |
| 3.5 | Read the narrative against the findings | ✅ **Every number describing your training appears in a finding** — weights, percentages, session counts, days since. Nothing computed, estimated, or inferred. This is the property that matters most: a figure about your training that the findings don't contain is a bug, not a style issue |
| 3.5a | Note the numbers in the *advice* | ✅ Sets, reps, "twice a week", "back off for a week" are the model's to choose and are **not** expected in the findings. Rule 1 of the system prompt draws that line explicitly — an earlier wording forbade every number, which each real narrative broke as soon as it recommended a frequency |
| 3.6 | Check it never contradicts or softens a finding | ✅ A decline is described as a decline |
| 3.7 | POST with **zero** findings | ✅ Narrative says plainly there is nothing notable in this window, rather than inventing something |
| 3.8 | Set `ANTHROPIC_API_KEY` to an invalid value, POST | ✅ **201** with `narrative: null`. A warning is logged. The user still gets their findings |
| 3.9 | Disconnect from the network, POST | ✅ Same — findings returned, narrative null, warning logged |
| 3.10 | Confirm `ANTHROPIC_MODEL` in config matches the `model` column | ✅ They agree — the model is pinned in config so an upgrade leaves an audit trail |

| 3.11 | Confirm thinking is off in `app/ai/coach.py` | ✅ The `messages.parse()` call passes `thinking={"type": "disabled"}` explicitly. See "The thinking budget" below for why this matters |

---

## 4. Coach page — `/dashboard/coach`

| # | Step | Expected result |
|---|---|---|
| 4.1 | Visit with **zero** workouts logged | ✅ "Nothing to analyse yet" + a link to add a workout. The **Analyse my training** button is disabled with the tooltip "Log a workout first" |
| 4.2 | Visit with workouts but no analysis run | ✅ "No analysis yet" empty state, button **enabled** |
| 4.3 | Confirm nothing runs on page load | ✅ No new row appears in the history just from navigating here. Running costs a model call — it must always be a choice |
| 4.4 | Click **Analyse my training** | ✅ Button shows a pending state and stays busy until the refreshed page is on screen — never idle over stale output |
| 4.5 | Click it a **second** time after the first completes | ✅ Works. (The first version of this component span forever on the second click — `router.refresh()` re-renders the server tree without remounting the client component, so a manual `setRunning(false)` never ran) |
| 4.6 | Latest analysis header | ✅ Window dates and session count, e.g. "12 Jun – 3 Sep · 14 sessions" |
| 4.7 | A finding of each kind | ✅ Each has its own icon, label, and tint — and the **statement carries the meaning**, so nothing depends on colour alone |
| 4.8 | Findings render verbatim | ✅ The UI never rewrites, truncates, or summarises a statement. Any edit this layer made would be an unverified claim about someone's training |
| 4.9 | Analysis with findings but no narrative | ✅ The quiet note from 3.2 — not a red banner |
| 4.10 | Analysis with **zero** findings | ✅ "Nothing stood out in this window…" — a real result, stated plainly |
| 4.11 | Stop the backend, reload the page | ✅ Red banner "Couldn't load your coaching". **Sidebar and page still render** — no crash, no blank screen |
| 4.12 | Throttle to Slow 3G and navigate here | ✅ Skeleton placeholders first; layout does not jump when data lands |
| 4.13 | Force an error in the route (e.g. bad token) | ✅ `error.tsx` catches it — a recoverable error card, not a Next.js crash overlay |

---

## 5. History

| # | Step | Expected result |
|---|---|---|
| 5.1 | Run 3 analyses | ✅ Newest renders in full; the other two appear under "Earlier analyses" |
| 5.2 | Check an earlier row | ✅ Shows its own window, observation count, and whether it was written up |
| 5.3 | Log a new workout, then re-open the page | ✅ **Past analyses are unchanged.** A finding is true of the window it was computed for — history is a record, not a live view |
| 5.4 | Run more than 10 analyses | ✅ Page requests the 10 most recent |
| 5.5 | With exactly 1 analysis | ✅ No "Earlier analyses" card at all |

---

## 6. Security and isolation

| # | Step | Expected result |
|---|---|---|
| 6.1 | Sign out, visit `/dashboard/coach` | ✅ Redirected to sign-in with `redirect_url` set |
| 6.2 | Sign in as user B, `GET /api/coach/analyses/{user A's id}` | ✅ **404** — not the data, and not a 403 that would confirm it exists |
| 6.3 | `GET /api/coach/analyses/not-a-uuid` | ✅ 422, not a server error |
| 6.4 | Call any coach route with no `Authorization` header | ✅ 401 |
| 6.5 | User B runs an analysis | ✅ Covers only B's workouts — verify `workout_count` matches B's own sessions |
| 6.6 | View page source on `/dashboard/coach` | ✅ No Clerk JWT in the HTML — fetching happens server-side |
| 6.7 | Delete a user (cascade check) | ✅ Their `ai_analyses` rows go with them (`ondelete="CASCADE"`) |

---

## 7. Responsive and accessibility

| # | Step | Expected result |
|---|---|---|
| 7.1 | 375px (iPhone SE) | ✅ No horizontal scroll; header and button stack cleanly |
| 7.2 | 768px / 1440px | ✅ Content max-width constrained, not stretched edge to edge |
| 7.3 | Tab to the Analyse button | ✅ Visible focus ring |
| 7.4 | Trigger a run failure | ✅ The inline error is announced (`role="alert"`) |
| 7.5 | While running, inspect the button | ✅ `aria-busy` set; label does not change, so the control does not resize mid-request |
| 7.6 | Finding icons | ✅ `aria-hidden` — the statement text is what a screen reader gets |

---

## 8. Automated checks

Run before committing:

```bash
cd frontend && npx tsc --noEmit     # expect: no output
cd frontend && npm run lint         # expect: no output
cd frontend && npm run build        # expect: ✓ Compiled successfully
cd backend  && .venv\Scripts\python -m pytest -q   # expect: 128 passed, 6 skipped
```

⚠️ The 6 skips need a live database; they opt in via `TEST_DATABASE_URL` (see
`tests/conftest.py`). To run them against a scratch database:
`$env:TEST_DATABASE_URL="postgresql+psycopg://…"; .venv\Scripts\python -m pytest -q`

---

## The thinking budget — why `MAX_TOKENS = 2000` is safe

Worth understanding before anyone touches this call, because getting it wrong
produces a failure that looks like something else entirely.

`max_tokens` caps thinking **and** response text together, and on current models
thinking is **on by default** when the `thinking` argument is omitted. A 2000-token
budget sized for the response alone would then be shared rather than reserved, and
a run that spent it reasoning would fail to parse — `parsed_output` comes back
`None`, `generate_narrative` returns `(None, None)`, and the user gets findings
with no narrative.

That is the intended degradation path, so nothing raises and nothing appears in the
UI as an error. It is indistinguishable from having no API key configured. The
symptom would be reported as "my key isn't working."

`app/ai/coach.py` therefore passes `thinking={"type": "disabled"}` explicitly. That
matches the call's intent — the findings arrive already computed and already
ordered, so there is nothing to reason about; the model is phrasing, not deciding.
`disabled` is accepted at effort `high` or below, and `EFFORT` here is `low`.

**If you ever turn thinking back on, raise `MAX_TOKENS` in the same change.**

One thing to confirm the first time a narrative is generated: the call passes both
`output_config={"effort": …}` and `output_format=CoachNarrative`. The SDK folds
`output_format` into `output_config.format`, so if structured parsing ever stops
working silently, check that the explicit `output_config` is not displacing it.

---

## Known limitations (deliberate, not defects)

- **The narrative is not verified line by line.** `_verify` rejects a narrative that
  cites a finding kind it was not given, which catches the failure that matters —
  advice invented about a pattern that never appeared. It cannot catch every
  fabricated number. That is why the prompt hands the model finished sentences
  rather than raw figures: the lowest-risk thing it can do is reuse them.
- **No pagination on history.** The page shows the 10 most recent analyses.
- **Analyses are immutable.** There is no edit or delete. A finding is true of its
  window; rewriting history would make the record useless.
- **`created_at` is rendered as a UTC date.** An analysis run late in the evening
  local time can display as the following day.
- **No usage metering yet.** Every run costs a model call with nothing counting
  them — that is Phase 8's job, and the stored rows are what it will count.
- **Detectors are conservative by design.** They stay quiet unless there is enough
  data to be sure. A coach that fires on one session is noise, and users switch
  noise off.
