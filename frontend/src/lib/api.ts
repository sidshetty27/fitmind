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

export interface WorkoutExercise extends WorkoutExerciseInput {
  id: string;
  exercise: Exercise;
  position: number;
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

export type PingResponse = { message: string };
export type HealthResponse = { status: string; service: string; environment: string };

type Token = string | null | undefined;

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
      params?: { muscle_group?: MuscleGroup; equipment?: Equipment; search?: string },
    ) => request<Exercise[]>("/api/exercises", { token, query: params }),
    get: (token: Token, id: string) =>
      request<Exercise>(`/api/exercises/${id}`, { token }),
  },

  workouts: {
    list: (token: Token, params?: { date_from?: string; date_to?: string; limit?: number; offset?: number }) =>
      request<WorkoutListItem[]>("/api/workouts", { token, query: params }),
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
