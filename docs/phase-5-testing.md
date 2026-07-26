# Phase 5 — Workout Logging: Testing Checklist

Verify in order. **Section 0 is a prerequisite** — the rest will fail without it.

Legend: ✅ expected result · ⚠️ known limitation, not a bug

---

## 0. Setup (required first)

| # | Step | Expected result |
|---|---|---|
| 0.1 | `cd backend && .venv\Scripts\python -m alembic current` | Shows `0002_seed_exercise_catalog` |
| 0.2 | `.venv\Scripts\python -m alembic upgrade head` | ✅ Applies `0003_workout_templates`. **This writes to your Supabase database** — it is purely additive (two new tables), no existing table is touched |
| 0.3 | `.venv\Scripts\python -m alembic current` | Shows `0003_workout_templates` |
| 0.4 | `.venv\Scripts\python -m alembic revision --autogenerate -m "drift check"` | ✅ Generated file has an **empty** `upgrade()`. This proves models and migration agree. **Delete the generated file afterwards** |
| 0.5 | Start backend: `.venv\Scripts\python run.py` | Boots, no errors |
| 0.6 | Open `http://localhost:8000/docs` | ✅ A **`templates`** section with 7 routes: POST/GET `/api/templates`, GET/PATCH/DELETE `/api/templates/{id}`, PUT `/api/templates/{id}/exercises`, POST `/api/templates/{id}/apply` |
| 0.7 | `cd frontend && npm run dev`, sign in | Lands on `/dashboard` |

---

## 1. Dashboard shell (the Phase 4 gap this closes)

| # | Step | Expected result |
|---|---|---|
| 1.1 | Load `/dashboard` on a wide screen | ✅ Sidebar rail on the left with **Dashboard, Workouts, Templates**, plus **Progress** and **Settings** greyed out with a "Soon" chip |
| 1.2 | Click a "Soon" item | ✅ Nothing happens — no navigation, no 404 |
| 1.3 | Observe the active item | ✅ Only the current page is highlighted indigo. On `/dashboard/workouts`, "Dashboard" is **not** also highlighted |
| 1.4 | Narrow the window below ~1024px | ✅ Rail disappears, a hamburger + "Menu" bar appears |
| 1.5 | Open the drawer, click "Workouts" | ✅ Drawer closes and navigates in one action |
| 1.6 | Open the drawer, press `Escape` | ✅ Closes |
| 1.7 | Open the drawer, click the dark scrim | ✅ Closes |
| 1.8 | Open the drawer, then browser **Back** | ✅ Drawer closes (does not sit open over the previous page) |
| 1.9 | Four stat cards | ✅ Total workouts, This week, Last session, Exercises logged — real numbers, not placeholders |
| 1.10 | With zero workouts | ✅ Stats read `0`, Last session reads `—`, "Recent workouts" shows an empty state with a CTA |
| 1.11 | Stop the backend, reload `/dashboard` | ✅ Red banner "Couldn't load your workouts". **The sidebar and page still render** — no crash, no blank screen |
| 1.12 | Restart backend, hard-reload | ✅ Banner gone, data returns |

---

## 2. Workout list — `/dashboard/workouts`

| # | Step | Expected result |
|---|---|---|
| 2.1 | Visit with no workouts | ✅ Empty state: "No workouts yet" + "Add your first workout" |
| 2.2 | With workouts | ✅ Grouped under month headings ("July 2026"), newest first |
| 2.3 | Date labels | ✅ Today's session reads **"Today"**, yesterday's **"Yesterday"**, 3 days ago **"3 days ago"**, older shows a full date |
| 2.4 | Exercise count badge | ✅ Matches the number of exercises in that workout; reads "1 exercise" (singular) when it is one |
| 2.5 | Untitled workout | ✅ Renders "Untitled workout", not a blank row |
| 2.6 | Click a row | ✅ Opens that workout's editor |
| 2.7 | Throttle to Slow 3G, navigate to the list | ✅ Skeleton placeholders appear first — layout does **not** jump when data lands |

---

## 3. Create a workout — `/dashboard/workouts/new`

| # | Step | Expected result |
|---|---|---|
| 3.1 | Click "Add Workout" from dashboard or list | ✅ Opens the form |
| 3.2 | Date field default | ✅ **Today's date in your local timezone.** Test after 9pm — it must still say today, not tomorrow |
| 3.3 | Save with only a date | ✅ Succeeds. Redirects to the new workout's page |
| 3.4 | Save with title, duration, notes, and 2 exercises | ✅ All values persist; reload the page and confirm |
| 3.5 | A note about templates | ✅ Visible hint linking to `/dashboard/templates` (only when not duplicating) |

---

## 4. Exercise search

| # | Step | Expected result |
|---|---|---|
| 4.1 | Type `bench` | ✅ Dropdown lists matching movements with muscle group · equipment, and a "Compound" chip where applicable |
| 4.2 | Watch the Network tab while typing `bench` quickly | ✅ **One** request, not five — 250ms debounce |
| 4.3 | Type `be`, then quickly `bench` | ✅ Earlier request shows as **cancelled**; results never flash the wrong term's matches |
| 4.4 | Type `zzzzz` | ✅ `No movements match "zzzzz".` |
| 4.5 | Arrow Down / Up | ✅ Highlight moves and wraps around |
| 4.6 | Press `Enter` on a highlighted item | ✅ Adds that exercise. **The workout form does not submit** |
| 4.7 | Press `Escape` | ✅ Dropdown closes, typed text remains |
| 4.8 | Click outside the dropdown | ✅ Closes |
| 4.9 | After selecting | ✅ Search box clears, ready for the next movement |
| 4.10 | Add the same exercise twice | ✅ Allowed — two separate rows (legitimate training, e.g. a second bench slot) |
| 4.11 | Stop the backend, type in search | ✅ Inline red error in the dropdown. Page does not crash |

---

## 5. Edit / delete / reorder exercises

| # | Step | Expected result |
|---|---|---|
| 5.1 | New exercise row defaults | ✅ Sets `3`, Reps `10`, weight/RPE/notes blank |
| 5.2 | Weight placeholder | ✅ Reads "Bodyweight" (blank means no external load, stored as NULL — not 0) |
| 5.3 | Edit sets/reps/weight/RPE/notes | ✅ Accepts input; clearing a field leaves it empty rather than snapping to `0` |
| 5.4 | Header count | ✅ Updates live: "3 movements · 96 total reps" |
| 5.5 | Move up / down arrows | ✅ Row reorders; the numbered badges renumber |
| 5.6 | First row's "up" and last row's "down" | ✅ Disabled |
| 5.7 | Delete a row | ✅ Removed; remaining rows renumber contiguously |
| 5.8 | Delete all rows | ✅ Returns to the "No exercises yet" empty state |
| 5.9 | Save, then reload | ✅ **Order is preserved exactly as arranged** |

---

## 6. Validation

Errors appear only **after** the first save attempt — an untouched form must not be pre-marked red.

| # | Input | Expected result |
|---|---|---|
| 6.1 | Clear the date, Save | ✅ "Pick the date you trained." Banner: "Please fix 1 field below." No network request is sent |
| 6.2 | Sets = `0` | ✅ "Sets must be greater than 0." |
| 6.3 | Reps = `0` | ✅ "Reps must be greater than 0." |
| 6.4 | Sets = `2.5` | ✅ "Sets must be a whole number." |
| 6.5 | Weight = `-5` | ✅ "Weight cannot be negative." |
| 6.6 | Weight = `62.505` | ✅ "Weight can have at most 2 decimal places." (would otherwise be a server 422 — mirrors `NonNegativeWeight`) |
| 6.7 | Weight = `10000` | ✅ "Weight must be 9999.99 or less." |
| 6.8 | RPE = `11` | ✅ "RPE must be between 1 and 10." |
| 6.9 | RPE = `7.25` | ✅ "RPE can have at most 1 decimal place." |
| 6.10 | Duration = `0` | ✅ "Duration must be greater than 0." |
| 6.11 | Weight/RPE spinner arrows | ✅ Step by `0.5` — cannot produce an invalid decimal |
| 6.12 | Fix an error and re-save | ✅ Message clears; save proceeds |
| 6.13 | Multiple errors | ✅ Banner counts them: "Please fix 3 fields below." |
| 6.14 | Valid weight `60.5`, RPE `7.5` | ✅ Saves; reload shows `60.50` / `7.5` |

---

## 7. Edit an existing workout

| # | Step | Expected result |
|---|---|---|
| 7.1 | Open a workout | ✅ All fields and exercises prefilled from the server |
| 7.2 | Change the title, Save | ✅ Green "Workout saved" banner; **stays on the page** |
| 7.3 | Return to the list | ✅ New title shown (page was refreshed, not stale) |
| 7.4 | Change something, then click "Back to workouts" | ✅ Browser confirm: "Discard unsaved changes?" |
| 7.5 | Change something, then close the tab | ✅ Browser's leave-site warning |
| 7.6 | Save with no changes pending, then navigate away | ✅ **No** confirm prompt |
| 7.7 | Add an exercise to a saved workout, Save, reload | ✅ Persisted at the correct position |
| 7.8 | During save | ✅ Button reads "Saving…" with a spinner; all inputs disabled |
| 7.9 | Stop the backend, then Save | ✅ Red "Couldn't save" banner. Your edits stay in the form — nothing is lost |

⚠️ **Partial-save case (by design).** Editing sends two requests: `PATCH` for the fields, then `PUT` for the exercises — the API separates them so a title edit can never wipe your sets. If the second fails, you get the explicit message *"Workout details were saved, but the exercise list failed… Your exercises below are unsaved."* This is correct behaviour, not a bug.

---

## 8. Delete and duplicate

| # | Step | Expected result |
|---|---|---|
| 8.1 | Delete from a workout's page | ✅ Confirm dialog; on OK redirects to the list and the row is gone |
| 8.2 | Cancel the confirm | ✅ Nothing deleted |
| 8.3 | Delete via the list row's trash icon | ✅ Confirm names the workout; row disappears without a full page reload |
| 8.4 | Click the duplicate icon on a list row | ✅ Opens `/new?duplicate=<id>`, heading "Duplicate workout" |
| 8.5 | Inspect the duplicate | ✅ Same exercises/sets/reps/weights; title has " (copy)" appended; **date is today**, not the original's |
| 8.6 | Save the duplicate | ✅ Creates a *new* workout — the original is untouched |
| 8.7 | Visit `/new?duplicate=00000000-0000-0000-0000-000000000000` | ✅ Amber warning "We couldn't load that workout to copy" and a **usable blank form** — not a crash |

---

## 9. Templates

| # | Step | Expected result |
|---|---|---|
| 9.1 | `/dashboard/templates` with none saved | ✅ Empty state + "Create your first template" |
| 9.2 | Create one with a name and 3 exercises | ✅ Saves, redirects to its page |
| 9.3 | Save a second template with the **same name** | ✅ Error pinned to the **name field**: "You already have a template named…" (HTTP 409, not a generic banner) |
| 9.4 | Save with a blank name | ✅ "Give this template a name." |
| 9.5 | Template list ordering | ✅ Alphabetical (plans are chosen by name, not by date) |
| 9.6 | Click **"Log now"** | ✅ Creates a workout dated **today** titled with the template's name, and lands you in its editor with all exercises copied |
| 9.7 | Verify the copy is independent | ✅ Change a weight in that workout and save → reopen the template → **template is unchanged** |
| 9.8 | And the reverse | ✅ Edit the template → the previously logged workout is **unchanged** |
| 9.9 | "Log now" on a template with 0 exercises | ✅ Button disabled, tooltip "Add exercises to this template first" |
| 9.10 | Edit a template's exercises, Save, reload | ✅ Persisted, order preserved |
| 9.11 | Delete a template | ✅ Confirm says workouts already logged from it are unaffected; verify one still exists afterwards |
| 9.12 | In a workout editor, click **"Save as template"** | ✅ Inline name box (not a `window.prompt`), prefilled with the workout's title |
| 9.13 | Confirm the save | ✅ Green "Saved as a template" with a link to open it |
| 9.14 | Use a name that already exists | ✅ Inline error, name box stays open so you can change it |
| 9.15 | "Save as template" with 0 exercises | ✅ Button disabled |
| 9.16 | Check the created template | ✅ Contains the exercises **only** — no date, no duration, no session notes |

---

## 10. Security and isolation

| # | Step | Expected result |
|---|---|---|
| 10.1 | Sign out, visit `/dashboard/workouts` | ✅ Redirected to sign-in with `redirect_url` set |
| 10.2 | Same for `/dashboard/workouts/new`, `/dashboard/templates` | ✅ All redirect |
| 10.3 | Sign in as user B, open a URL for user A's workout | ✅ **404 page** (not the data, and not a 403 that would confirm it exists) |
| 10.4 | Same for a template id | ✅ 404 |
| 10.5 | Visit `/dashboard/workouts/not-a-uuid` | ✅ 404 page, not a server error |
| 10.6 | View page source on the workout list | ✅ No Clerk JWT in the HTML — fetching happens server-side |

---

## 11. Responsive and accessibility

| # | Step | Expected result |
|---|---|---|
| 11.1 | 375px (iPhone SE) | ✅ No horizontal scroll anywhere; exercise fields stack 2-up |
| 11.2 | 768px (tablet) | ✅ Fields 4-up; still drawer navigation |
| 11.3 | 1440px | ✅ Sidebar rail, content max-width constrained (not stretched edge to edge) |
| 11.4 | Tab through the workout form | ✅ Visible focus ring on every control |
| 11.5 | Trigger a validation error, inspect the input | ✅ `aria-invalid="true"` and `aria-describedby` pointing at the error text |
| 11.6 | Screen reader on a failed save | ✅ Banner is announced (`role="alert"`) |
| 11.7 | Icon-only buttons (delete, move, duplicate) | ✅ All have `aria-label` — verify via the accessibility tree |

---

## 12. Automated checks

Run before committing:

```bash
cd frontend && npx tsc --noEmit     # expect: no output
cd frontend && npm run lint         # expect: no output
cd frontend && npm run build        # expect: ✓ Compiled successfully
cd backend  && .venv\Scripts\python -m pytest -q   # expect: 50 passed, 6 skipped
```

⚠️ The 6 skips are the tests that need a live database; they opt in via `TEST_DATABASE_URL` (see `tests/conftest.py`). To run them against a scratch database:
`$env:TEST_DATABASE_URL="postgresql+psycopg://…"; .venv\Scripts\python -m pytest -q`

---

## Known limitations (deliberate, not defects)

- **Pagination.** The list shows the 100 most recent sessions and says so; the dashboard totals cover the most recent 200 and display "200+". Infinite scroll is not in Phase 5 scope.
- **One row per movement.** A workout entry aggregates all sets (`3×8 @ 60kg`); it cannot express `1×5 @ 100 + 2×8 @ 80` or a dropset. Documented as a Phase 3 decision in `docs/database.md`; the fix is an additive `exercise_sets` table.
- **Reordering is by arrow button**, not drag-and-drop — keyboard-accessible and dependency-free.
- **Unsaved-changes guard** covers tab close/reload and the Cancel link. Next.js exposes no stable API for intercepting client-side route changes, so the sidebar links do not prompt.
- **Progress and Settings** are "Soon" placeholders — later phases.
