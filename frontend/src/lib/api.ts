/**
 * Typed client for the FitMind FastAPI backend.
 *
 * Every protected endpoint needs the caller's Clerk session JWT. Rather than
 * reach into Clerk from here (which differs between server and client
 * components), each helper takes a `token` the caller has already obtained:
 *
 *   // client component
 *   const { getToken } = useAuth();
 *   const me = await api.me.get(await getToken());
 *
 *   // server component / route handler
 *   const { getToken } = await auth();
 *   const me = await api.me.get(await getToken());
 *
 * Keeping token retrieval at the call site means this module has no dependency on
 * the Clerk runtime and stays trivially testable. All request plumbing — base
 * URL, auth header, JSON encoding, error shaping — lives in `request()` so no
 * component ever hand-builds a fetch.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Thrown for any non-2xx response, carrying the status and parsed detail. */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * A server-side `Decimal` as it actually arrives on the wire: a **string**.
 *
 * Pydantic serialises `Decimal` to a JSON string rather than a number, and that is
 * the right call — it preserves the exact stored scale, so `60.50` survives the trip
 * instead of becoming a float that renders as `60.5`. The cost is that these fields
 * are never safe to do arithmetic on directly; `toNumber()` below is the one way in.
 *
 * Typing them as `number` (as this module briefly did) compiles fine and then fails
 * at runtime the first time something calls `.toFixed()` on one.
 */
export type DecimalString = string;

/** Parse a wire `Decimal`. `null` in, `null` out — never a silent 0. */
export function toNumber(value: DecimalString | null): number | null {
  if (value === null) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

type Query = Record<string, string | number | boolean | null | undefined>;

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  token?: string | null;
  query?: Query;
  signal?: AbortSignal;
}

function buildUrl(path: string, query?: Query): string {
  const url = new URL(`${API_URL}${path}`);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null) {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.toString();
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, token, query, signal } = options;

  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(buildUrl(path, query), {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    // Auth'd, user-specific data must never be served from a cache.
    cache: "no-store",
    signal,
  });

  if (!res.ok) {
    // FastAPI puts the message under `detail`; fall back gracefully if the body
    // is empty or not JSON (e.g. a proxy 502).
    let detail: unknown;
    try {
      detail = (await res.json())?.detail;
    } catch {
      detail = undefined;
    }
    const message =
      typeof detail === "string"
        ? detail
        : `Request to ${path} failed with status ${res.status}`;
    throw new ApiError(res.status, message, detail);
  }

  // 204 No Content (deletes) has no body to parse.
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/* ----------------------------- Domain types ------------------------------ */

export type Goal =
  | "strength"
  | "hypertrophy"
  | "fat_loss"
  | "endurance"
  | "general_fitness";
export type ExperienceLevel = "beginner" | "intermediate" | "advanced";
export type MuscleGroup =
  | "chest"
  | "back"
  | "shoulders"
  | "quads"
  | "hamstrings"
  | "glutes"
  | "calves"
  | "biceps"
  | "triceps"
  | "forearms"
  | "core"
  | "full_body";
export type Equipment =
  | "barbell"
  | "dumbbell"
  | "machine"
  | "cable"
  | "bodyweight"
  | "kettlebell"
  | "band"
  | "other";

export interface User {
  id: string;
  email: string;
  name: string | null;
  height_cm: number | null;
  weight_kg: number | null;
  goal: Goal | null;
  experience_level: ExperienceLevel | null;
  created_at: string;
  updated_at: string;
}

export type UserUpdate = Partial<
  Pick<User, "name" | "height_cm" | "weight_kg" | "goal" | "experience_level">
>;

export interface Exercise {
  id: string;
  name: string;
  primary_muscle_group: MuscleGroup;
  equipment: Equipment;
  is_compound: boolean;
  instructions: string | null;
}

export interface WorkoutExerciseInput {
  exercise_id: string;
  sets: number;
  reps: number;
  weight_kg?: number | null;
  rpe?: number | null;
  notes?: string | null;
}

/**
 * Note the narrowing on the way *back*: the API accepts `weight_kg` / `rpe` as
 * numbers but returns them as `Decimal` strings, so a read model cannot reuse the
 * input's `number`. Existing callers only ever `String(...)` these, which is why the
 * old `number` typing never broke — it was still a lie waiting for the first
 * arithmetic.
 */
export interface WorkoutExercise extends Omit<WorkoutExerciseInput, "weight_kg" | "rpe"> {
  id: string;
  exercise: Exercise;
  position: number;
  weight_kg: DecimalString | null;
  rpe: DecimalString | null;
}

export interface Workout {
  id: string;
  performed_on: string;
  title: string | null;
  notes: string | null;
  duration_min: number | null;
  created_at: string;
  updated_at: string;
  exercises: WorkoutExercise[];
}

export interface WorkoutListItem {
  id: string;
  performed_on: string;
  title: string | null;
  duration_min: number | null;
  exercise_count: number;
  created_at: string;
  updated_at: string;
}

export interface WorkoutCreate {
  performed_on: string;
  title?: string | null;
  notes?: string | null;
  duration_min?: number | null;
  exercises?: WorkoutExerciseInput[];
}

export type WorkoutUpdate = Partial<
  Pick<Workout, "performed_on" | "title" | "notes" | "duration_min">
>;

/**
 * Templates mirror workouts on purpose — same exercise payload shape — so
 * applying one is a field-for-field copy with no translation layer.
 */
export interface TemplateExercise
  extends Omit<WorkoutExerciseInput, "weight_kg" | "rpe"> {
  id: string;
  exercise: Exercise;
  position: number;
  weight_kg: DecimalString | null;
  rpe: DecimalString | null;
}

export interface WorkoutTemplate {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  exercises: TemplateExercise[];
}

export interface TemplateListItem {
  id: string;
  name: string;
  description: string | null;
  exercise_count: number;
  created_at: string;
  updated_at: string;
}

export interface TemplateCreate {
  name: string;
  description?: string | null;
  exercises?: WorkoutExerciseInput[];
}

export type TemplateUpdate = Partial<Pick<WorkoutTemplate, "name" | "description">>;

/** The facts a plan cannot know: when it was actually performed, and for how long. */
export interface TemplateApply {
  performed_on: string;
  title?: string | null;
  notes?: string | null;
  duration_min?: number | null;
}

export interface ProgressEntry {
  id: string;
  recorded_on: string;
  bodyweight_kg: number | null;
  calories: number | null;
  protein_g: number | null;
  sleep_hours: number | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProgressUpsert {
  recorded_on: string;
  bodyweight_kg?: number | null;
  calories?: number | null;
  protein_g?: number | null;
  sleep_hours?: number | null;
  notes?: string | null;
}

/**
 * Derived training data (Phase 6). Nothing here is stored server-side — it is
 * computed per request from logged workouts.
 *
 * Numeric fields arrive as JSON numbers but are `Decimal` on the server, and a
 * `null` always means *not applicable* (bodyweight work has no load, one session
 * has no trend), never zero. Rendering `null` as `0` would flatten exactly the
 * signals these charts exist to show.
 */
export interface ExerciseSessionPoint {
  workout_id: string;
  performed_on: string;
  sets: number;
  reps: number;
  weight_kg: DecimalString | null;
  rpe: DecimalString | null;
  volume_kg: DecimalString | null;
  estimated_one_rm: DecimalString | null;
  total_reps: number;
}

export interface ExerciseHistory {
  exercise_id: string;
  exercise_name: string;
  points: ExerciseSessionPoint[];
  session_count: number;
  best_estimated_one_rm: DecimalString | null;
  /** Signed: a negative value is a real finding, not an error. */
  one_rm_change_pct: DecimalString | null;
}

export interface WeekVolume {
  week_start: string;
  volume_kg: DecimalString;
  total_reps: number;
  session_count: number;
}

export interface PersonalRecord {
  exercise_id: string;
  exercise_name: string;
  heaviest_weight_kg: DecimalString | null;
  heaviest_weight_on: string | null;
  best_estimated_one_rm: DecimalString | null;
  best_estimated_one_rm_on: string | null;
  best_session_volume_kg: DecimalString | null;
  best_session_volume_on: string | null;
  session_count: number;
  last_performed_on: string;
}

export interface TrainingSummary {
  window_start: string;
  window_end: string;
  workout_count: number;
  /** Weeks with no training are **absent**, not zero-filled — fill the axis client-side. */
  weekly_volume: WeekVolume[];
  exercises: ExerciseHistory[];
}

/**
 * AI coach (Phase 7).
 *
 * A finding is computed from the user's own logged sets, never generated — its
 * `statement` is already a complete, true sentence, which is why the UI can
 * render an analysis with no `narrative` and have it read as finished rather
 * than as raw data.
 */
export type FindingKind =
  | "plateau"
  | "volume_drop"
  | "stale_muscle_group"
  | "ready_to_progress";

export interface Finding {
  /** Widened beyond `FindingKind` on purpose: a detector added server-side must
   *  render as an unstyled finding, not crash the page. */
  kind: FindingKind | string;
  subject: string;
  statement: string;
  detail: Record<string, unknown>;
}

export interface AiAnalysis {
  id: string;
  window_start: string;
  window_end: string;
  workout_count: number;
  findings: Finding[];
  /** Null when no coaching voice was available. The findings still stand. */
  narrative: string | null;
  /** Which model wrote `narrative`. Null exactly when `narrative` is null. */
  model: string | null;
  created_at: string;
}

export interface AiAnalysisListItem {
  id: string;
  window_start: string;
  window_end: string;
  workout_count: number;
  finding_count: number;
  has_narrative: boolean;
  created_at: string;
}

export type PingResponse = { message: string };
export type HealthResponse = { status: string; service: string; environment: string };

type Token = string | null | undefined;

/**
 * Per-call options for read endpoints that a component may need to cancel.
 *
 * Type-ahead search fires a request per keystroke; without an abort the responses
 * can resolve out of order and a stale result overwrites a newer one. `request()`
 * has always forwarded `signal` to `fetch` — these helpers expose it.
 */
interface CallOptions {
  signal?: AbortSignal;
}

/* ------------------------------ API surface ------------------------------ */

export const api = {
  baseUrl: API_URL,

  // Phase 1 connectivity checks — unauthenticated.
  ping: () => request<PingResponse>("/api/ping"),
  health: () => request<HealthResponse>("/health"),

  me: {
    get: (token: Token) => request<User>("/api/me", { token }),
    update: (token: Token, data: UserUpdate) =>
      request<User>("/api/me", { method: "PATCH", body: data, token }),
  },

  exercises: {
    list: (
      token: Token,
      params?: {
        muscle_group?: MuscleGroup;
        equipment?: Equipment;
        search?: string;
        limit?: number;
        offset?: number;
      },
      opts?: CallOptions,
    ) => request<Exercise[]>("/api/exercises", { token, query: params, ...opts }),
    get: (token: Token, id: string) =>
      request<Exercise>(`/api/exercises/${id}`, { token }),
  },

  workouts: {
    list: (
      token: Token,
      params?: { date_from?: string; date_to?: string; limit?: number; offset?: number },
      opts?: CallOptions,
    ) => request<WorkoutListItem[]>("/api/workouts", { token, query: params, ...opts }),
    get: (token: Token, id: string) => request<Workout>(`/api/workouts/${id}`, { token }),
    create: (token: Token, data: WorkoutCreate) =>
      request<Workout>("/api/workouts", { method: "POST", body: data, token }),
    update: (token: Token, id: string, data: WorkoutUpdate) =>
      request<Workout>(`/api/workouts/${id}`, { method: "PATCH", body: data, token }),
    replaceExercises: (token: Token, id: string, exercises: WorkoutExerciseInput[]) =>
      request<Workout>(`/api/workouts/${id}/exercises`, {
        method: "PUT",
        body: { exercises },
        token,
      }),
    delete: (token: Token, id: string) =>
      request<void>(`/api/workouts/${id}`, { method: "DELETE", token }),
  },

  templates: {
    list: (token: Token, opts?: CallOptions) =>
      request<TemplateListItem[]>("/api/templates", { token, ...opts }),
    get: (token: Token, id: string) =>
      request<WorkoutTemplate>(`/api/templates/${id}`, { token }),
    create: (token: Token, data: TemplateCreate) =>
      request<WorkoutTemplate>("/api/templates", {
        method: "POST",
        body: data,
        token,
      }),
    update: (token: Token, id: string, data: TemplateUpdate) =>
      request<WorkoutTemplate>(`/api/templates/${id}`, {
        method: "PATCH",
        body: data,
        token,
      }),
    replaceExercises: (token: Token, id: string, exercises: WorkoutExerciseInput[]) =>
      request<WorkoutTemplate>(`/api/templates/${id}/exercises`, {
        method: "PUT",
        body: { exercises },
        token,
      }),
    /** Log a workout from this template. Returns the new **workout**. */
    apply: (token: Token, id: string, data: TemplateApply) =>
      request<Workout>(`/api/templates/${id}/apply`, {
        method: "POST",
        body: data,
        token,
      }),
    delete: (token: Token, id: string) =>
      request<void>(`/api/templates/${id}`, { method: "DELETE", token }),
  },

  coach: {
    /** Run a fresh analysis. POST because it costs a model call and writes a row. */
    run: (token: Token, params?: { weeks?: number }) =>
      request<AiAnalysis>("/api/coach/analyses", {
        method: "POST",
        query: params,
        token,
      }),
    history: (token: Token, params?: { limit?: number; offset?: number }) =>
      request<AiAnalysisListItem[]>("/api/coach/analyses", { token, query: params }),
    get: (token: Token, id: string) =>
      request<AiAnalysis>(`/api/coach/analyses/${id}`, { token }),
  },

  analytics: {
    /** One round trip for the whole Progress page — the charts share a window. */
    summary: (
      token: Token,
      params?: { weeks?: number; exercise_limit?: number },
      opts?: CallOptions,
    ) => request<TrainingSummary>("/api/analytics/summary", { token, query: params, ...opts }),
    volume: (token: Token, params?: { weeks?: number }) =>
      request<WeekVolume[]>("/api/analytics/volume", { token, query: params }),
    records: (token: Token) =>
      request<PersonalRecord[]>("/api/analytics/records", { token }),
    /** 404s when the caller has never logged this movement. */
    exercise: (token: Token, exerciseId: string, params?: { weeks?: number }) =>
      request<ExerciseHistory>(`/api/analytics/exercises/${exerciseId}`, {
        token,
        query: params,
      }),
  },

  progress: {
    list: (token: Token, params?: { date_from?: string; date_to?: string; limit?: number; offset?: number }) =>
      request<ProgressEntry[]>("/api/progress", { token, query: params }),
    get: (token: Token, recordedOn: string) =>
      request<ProgressEntry>(`/api/progress/${recordedOn}`, { token }),
    upsert: (token: Token, data: ProgressUpsert) =>
      request<ProgressEntry>("/api/progress", { method: "PUT", body: data, token }),
    delete: (token: Token, recordedOn: string) =>
      request<void>(`/api/progress/${recordedOn}`, { method: "DELETE", token }),
  },
};
