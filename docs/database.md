# FitMind AI — Database Design

PostgreSQL (Supabase), accessed from FastAPI via SQLAlchemy 2.0, with Alembic migrations.

**Status:** implemented in Phase 3 — `users`, `exercises`, `workouts`, `workout_exercises`, `progress_entries`. The billing and AI tables sketched at the bottom land with the phases that need them.

## Design principles
- **Third normal form** where it aids integrity; denormalize only with a measured reason (there is exactly one such case, noted below).
- Every user-owned row carries a `user_id` FK — authorization is enforced in the API by scoping to the authenticated user (see `architecture.md`: we use Clerk, not Supabase RLS).
- UUID primary keys (avoids leaking row counts, safe in URLs).
- `created_at` / `updated_at` on every table, `timestamptz`, defaulted by the **database** clock.
- Invariants live in the schema (FK / UNIQUE / CHECK), not only in application code — the API is not the only thing that will ever write to this database.

## Entity-relationship overview

```
users ──1:N──► workouts ──1:N──► workout_exercises ──N:1──► exercises
  │                                                          (shared catalog)
  └──1:N──► progress_entries      (bodyweight, calories, protein, sleep)

later phases:
  users ──1:N──► ai_insights · ai_usage      ──1:1──► subscriptions
```

## The central modelling decision: a shared exercise catalog

The obvious v1 stores `exercise_name` as free text on each logged row. It works right up until the product tries to do its job:

- *"Is my bench pressing plateauing?"* needs every bench row to group together. Free text yields `Bench Press`, `bench press`, `BB Bench`, `Benchpress` — they never group.
- *"How much chest volume this week?"* needs a muscle group per movement, which text does not carry.
- Renaming a movement means an UPDATE across every historical row.

So `exercises` is a **shared catalog** (one row per movement, with attributes that belong to the movement), and `workout_exercises` is an **association object** joining a workout to a catalog entry while carrying the performance data (sets, reps, weight, RPE) that exists only because *this* movement was done in *this* session.

This supersedes the flat `exercises` table sketched in the Phase 0 draft, which flagged exactly this refinement as future work. We took it in Phase 3, while there is no production data to migrate.

## Tables

### `users`
Mirrors Clerk. Clerk owns *identity*; this table owns *the application's user*. `clerk_id` is the single join point between the two systems — so this table deliberately stores no credentials, sessions, or verification state.

| column           | type        | notes                                     |
| ---------------- | ----------- | ----------------------------------------- |
| id               | uuid PK     | `gen_random_uuid()`                       |
| clerk_id         | text UNIQUE | Clerk's `user_...` id; the auth hot path   |
| email            | text UNIQUE | cached from Clerk                          |
| name             | text        | nullable                                   |
| height_cm        | numeric(5,2)| nullable                                   |
| weight_kg        | numeric(5,2)| nullable — *latest* only; history lives in `progress_entries` |
| goal             | enum `goal` | strength / hypertrophy / fat_loss / endurance / general_fitness |
| experience_level | enum        | beginner / intermediate / advanced         |
| created_at, updated_at | timestamptz |                                      |

> **The one deliberate denormalization.** `users.weight_kg` duplicates the newest `progress_entries.bodyweight_kg`. It saves a correlated subquery on every profile render; `progress_entries` remains the system of record.

### `exercises` (catalog)
| column               | type          | notes                                |
| -------------------- | ------------- | ------------------------------------ |
| id                   | uuid PK       |                                      |
| name                 | text UNIQUE   | duplicate rows would split a lift's history |
| primary_muscle_group | enum, indexed | volume-per-muscle analytics          |
| equipment            | enum          | lets us substitute by availability   |
| is_compound          | boolean       | compounds drive strength progression |
| instructions         | text          | nullable                             |

Seeded with ~32 common movements by migration `0002`, because the app is unusable with an empty catalog and every environment must get the identical one.

### `workouts`
| column       | type        | notes                                    |
| ------------ | ----------- | ---------------------------------------- |
| id           | uuid PK     |                                          |
| user_id      | uuid FK     | → users.id, **ON DELETE CASCADE**        |
| performed_on | date        | the calendar day trained                 |
| duration_min | integer     | nullable, CHECK > 0                      |
| title, notes | text        | nullable                                 |

- `performed_on`, not `date`: `date` is a reserved word, and it must not be confused with `created_at` — they differ whenever someone logs yesterday's session, and conflating them corrupts every streak calculation.
- `DATE`, not `TIMESTAMPTZ`: a workout belongs to a calendar day *in the user's timezone*. Storing an instant makes "did I train today?" depend on the server's timezone.
- Index `(user_id, performed_on)` — serves the dashboard's filter **and** its sort from one structure. No `DESC` needed: Postgres scans a btree in either direction.

### `workout_exercises`
| column      | type          | notes                                       |
| ----------- | ------------- | ------------------------------------------- |
| id          | uuid PK       |                                             |
| workout_id  | uuid FK       | → workouts.id, **ON DELETE CASCADE**        |
| exercise_id | uuid FK       | → exercises.id, **ON DELETE RESTRICT**      |
| position    | integer       | execution order; UNIQUE with workout_id     |
| sets, reps  | integer       | CHECK > 0                                   |
| weight_kg   | numeric(6,2)  | nullable — bodyweight movements have no load; 0 would skew averages |
| rpe         | numeric(3,1)  | nullable, CHECK 1–10                        |

- **CASCADE vs RESTRICT is not symmetric, on purpose.** These rows are parts of a workout, so they die with it. But `exercises` is shared reference data — deleting "Barbell Squat" must not erase two years of squat history for every user, so that delete is refused instead.
- `UNIQUE (workout_id, position)`, deliberately **not** `(workout_id, exercise_id)`: benching twice in one session is legitimate training, not a data error.
- Postgres does not index foreign keys automatically; `exercise_id` gets an explicit index so the RESTRICT check doesn't sequential-scan the log table.

> **Known simplification.** One row aggregates all sets of a movement (`3x8 @ 60kg`); it cannot express `1x5 @ 100 + 2x8 @ 80` or a dropset. The fully normalized form is a further `exercise_sets` table, one row per set. The aggregate covers the overwhelming majority of logging, and the split is purely additive later. Recorded so it reads as a decision, not an oversight.

### `progress_entries`
| column        | type         | notes                              |
| ------------- | ------------ | ---------------------------------- |
| id            | uuid PK      |                                    |
| user_id       | uuid FK      | → users.id, ON DELETE CASCADE      |
| recorded_on   | date         | UNIQUE with user_id — one per day  |
| bodyweight_kg | numeric(5,2) | nullable                           |
| calories      | integer      | nullable                           |
| protein_g     | integer      | nullable                           |
| sleep_hours   | numeric(3,1) | nullable, CHECK 0–24               |

Separate from `users` because progress is a *time series* — overwriting a column destroys the data the product exists to analyze. Separate from `workouts` because these are recorded on rest days too. `UNIQUE (user_id, recorded_on)` lets "log today's weight" be a clean idempotent UPSERT instead of a read-then-write race.

## Types
- **`numeric`, never `float`**, for every weight and measurement. 72.4 has no exact binary representation, and accumulated drift in a strength-progression chart is indefensible when the fix is free.
- **Native Postgres ENUMs** for closed vocabularies (`goal`, `experience_level`, `muscle_group`, `equipment`) — the database rejects typos regardless of which client wrote the row. Tradeoff: adding a value needs a migration (`ALTER TYPE ... ADD VALUE`, cheap); removing one needs a type rewrite. Open-ended vocabularies (exercise names) are a table, not an enum.

## Indexing plan (implemented)
| index | serves |
| ----- | ------ |
| `uq_users_clerk_id` (constraint-backed) | resolving Clerk's `sub` on every authenticated request |
| `ix_workouts_user_id_performed_on` | dashboard: one user's workouts over a date range |
| `ix_workout_exercises_workout_id` | loading a workout's exercises; cascade deletes |
| `ix_workout_exercises_exercise_id` | the RESTRICT check; per-exercise history |
| `ix_exercises_primary_muscle_group` | volume-by-muscle aggregation |
| `uq_progress_entries_user_id_recorded_on` (constraint-backed) | progress charts by date range |

No index is created where a UNIQUE constraint's backing btree already covers the access pattern — a redundant index costs write throughput and buys nothing.

## Planned for later phases
`subscriptions` (Stripe plan/status, 1:1 with users), `ai_usage` (free-tier metering), `ai_insights` (jsonb AI output). Designed in Phase 0; they arrive with Phases 6–7 rather than being built speculatively.
