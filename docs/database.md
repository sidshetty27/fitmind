# FitMind AI — Database Design

PostgreSQL, accessed from FastAPI via SQLAlchemy, with Alembic migrations. Full schema and migrations land in **Phase 3**; this document is the design we will implement.

## Design principles
- **Third normal form** where it aids integrity; denormalize only with a measured reason.
- Every user-owned row carries a `user_id` FK — authorization is enforced in the API by scoping to the authenticated user.
- UUID primary keys (avoids leaking row counts, safe in URLs).
- `created_at` / `updated_at` timestamps on every table.
- Money/subscription state is derived from Stripe but cached locally for fast gating.

## Entity-relationship overview

```
users ──1:N──► workouts ──1:N──► exercises
  │
  ├──1:N──► progress_entries         (bodyweight, calories, protein, sleep)
  ├──1:N──► ai_insights              (generated analyses / summaries)
  ├──1:1──► subscriptions            (Stripe plan + status)
  └──1:N──► ai_usage                 (free-tier usage metering)
```

## Tables

### `users`
| column           | type        | notes                                   |
| ---------------- | ----------- | --------------------------------------- |
| id               | uuid PK     |                                         |
| clerk_id         | text UNIQUE | maps Clerk identity → internal user     |
| name             | text        |                                         |
| email            | text UNIQUE |                                         |
| height_cm        | numeric     | nullable                                |
| weight_kg        | numeric     | nullable (see `progress_entries` for history) |
| goal             | text        | e.g. strength, hypertrophy, fat_loss    |
| experience_level | text        | beginner / intermediate / advanced      |
| created_at       | timestamptz |                                         |
| updated_at       | timestamptz |                                         |

### `workouts`
| column     | type        | notes                        |
| ---------- | ----------- | ---------------------------- |
| id         | uuid PK     |                              |
| user_id    | uuid FK     | → users.id, ON DELETE CASCADE |
| date       | date        |                              |
| duration_min | integer   | nullable                     |
| notes      | text        | nullable                     |
| created_at | timestamptz |                              |

### `exercises`
| column        | type        | notes                          |
| ------------- | ----------- | ------------------------------ |
| id            | uuid PK     |                                |
| workout_id    | uuid FK     | → workouts.id, ON DELETE CASCADE |
| exercise_name | text        | (later: FK to an exercise catalog) |
| sets          | integer     |                                |
| reps          | integer     |                                |
| weight_kg     | numeric     |                                |
| rpe           | numeric     | rate of perceived exertion, nullable |

> **Normalization note:** `sets/reps/weight` at the exercise row is the pragmatic v1. A fully normalized model would split into an `exercise_sets` table (one row per set) to support per-set weights. We'll note this as a future refinement and start simple.

### `progress_entries`
| column     | type        | notes                    |
| ---------- | ----------- | ------------------------ |
| id         | uuid PK     |                          |
| user_id    | uuid FK     | → users.id               |
| date       | date        |                          |
| bodyweight_kg | numeric  | nullable                 |
| calories   | integer     | nullable                 |
| protein_g  | integer     | nullable                 |
| sleep_hours| numeric     | nullable                 |

### `subscriptions`
| column                | type        | notes                             |
| --------------------- | ----------- | --------------------------------- |
| id                    | uuid PK     |                                   |
| user_id               | uuid FK UNIQUE | → users.id                     |
| stripe_customer_id    | text        |                                   |
| stripe_subscription_id| text        |                                   |
| plan                  | text        | free / premium                    |
| status                | text        | active / canceled / past_due …    |
| current_period_end    | timestamptz | for gating                        |

### `ai_usage`
| column     | type        | notes                              |
| ---------- | ----------- | ---------------------------------- |
| id         | uuid PK     |                                    |
| user_id    | uuid FK     | → users.id                         |
| feature    | text        | e.g. summary, plan                 |
| used_at    | timestamptz | used to enforce free-tier limits   |

### `ai_insights`
| column     | type        | notes                              |
| ---------- | ----------- | ---------------------------------- |
| id         | uuid PK     |                                    |
| user_id    | uuid FK     | → users.id                         |
| type       | text        | plateau / summary / plan / …       |
| content    | jsonb       | structured AI output               |
| created_at | timestamptz |                                    |

## Indexing plan (initial)
- `workouts (user_id, date)` — dashboard queries by user over time.
- `exercises (workout_id)` — join workouts→exercises.
- `progress_entries (user_id, date)`.
- `ai_usage (user_id, used_at)` — usage-limit windows.
