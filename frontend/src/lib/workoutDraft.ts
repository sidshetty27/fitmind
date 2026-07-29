/**
 * The editor's in-memory model for a workout, and the validation that mirrors the
 * backend's constraints.
 *
 * Two decisions shape this file:
 *
 * **Numeric fields are held as strings.** A `number` state cannot represent "the
 * user has cleared the box and is mid-typing", so `""` becomes `0` or `NaN` and
 * the input fights back as you type. Strings hold exactly what was typed; the
 * conversion to numbers happens once, at submit.
 *
 * **Errors are keyed the way the server keys them** (`exercises.0.sets`), so a
 * locally-caught problem and a 422 from FastAPI render through the same code path
 * — see `normalizeApiError`. There is one error-display mechanism, not two.
 *
 * The rules below intentionally duplicate `app/schemas/common.py`. The server
 * remains the authority; this copy exists so the common mistakes are caught before
 * a round trip, and it is deliberately no stricter than the server, so nothing is
 * rejected here that the API would have accepted.
 */

import type {
  Exercise,
  TemplateExercise,
  WorkoutExercise,
  WorkoutExerciseInput,
} from "@/lib/api";

export interface DraftExercise {
  /** Stable local key for React lists. Not sent to the server. */
  key: string;
  exercise: Exercise;
  sets: string;
  reps: string;
  weight_kg: string;
  rpe: string;
  notes: string;
}

export interface WorkoutDraft {
  performed_on: string;
  title: string;
  notes: string;
  duration_min: string;
  exercises: DraftExercise[];
}

let keyCounter = 0;
/** Monotonic local id. Not `crypto.randomUUID()` — this must be SSR-stable. */
function nextKey(): string {
  keyCounter += 1;
  return `draft-${keyCounter}`;
}

/** A blank row for a movement just picked out of the catalog. */
export function draftFromExercise(exercise: Exercise): DraftExercise {
  return {
    key: nextKey(),
    exercise,
    // Sensible starting point; both are required so they cannot be left blank.
    sets: "3",
    reps: "10",
    weight_kg: "",
    rpe: "",
    notes: "",
  };
}

/**
 * Hydrate a saved entry back into an editable row.
 *
 * Accepts a workout entry or a template entry: the backend defines the two with
 * identical columns precisely so this conversion needs no branch.
 */
export function draftFromSaved(entry: WorkoutExercise | TemplateExercise): DraftExercise {
  return {
    key: nextKey(),
    exercise: entry.exercise,
    sets: String(entry.sets),
    reps: String(entry.reps),
    weight_kg: entry.weight_kg == null ? "" : String(entry.weight_kg),
    rpe: entry.rpe == null ? "" : String(entry.rpe),
    notes: entry.notes ?? "",
  };
}

/* ------------------------------- validation ------------------------------- */

/** Count digits after the decimal point in a numeric string. */
function decimalPlaces(value: string): number {
  const dot = value.indexOf(".");
  return dot === -1 ? 0 : value.length - dot - 1;
}

/**
 * A required whole number greater than zero — the server's `PositiveInt`.
 * Returns an error message, or null when valid.
 */
function checkPositiveInt(raw: string, label: string): string | null {
  const value = raw.trim();
  if (!value) return `${label} is required.`;
  if (!/^-?\d+$/.test(value)) return `${label} must be a whole number.`;
  const parsed = Number(value);
  if (parsed <= 0) return `${label} must be greater than 0.`;
  if (parsed > 1000) return `${label} looks too large.`;
  return null;
}

/**
 * Optional weight — the server's `NonNegativeWeight`
 * (`ge=0, max_digits=6, decimal_places=2`), i.e. 0 to 9999.99 with at most two
 * decimal places. Sending 62.505 is a 422, so we say so here instead.
 */
function checkWeight(raw: string): string | null {
  const value = raw.trim();
  if (!value) return null;
  if (!/^-?\d*\.?\d+$/.test(value)) return "Weight must be a number.";
  if (decimalPlaces(value) > 2) return "Weight can have at most 2 decimal places.";
  const parsed = Number(value);
  if (parsed < 0) return "Weight cannot be negative.";
  if (parsed > 9999.99) return "Weight must be 9999.99 or less.";
  return null;
}

/** Optional RPE — the server's `Rpe` (`ge=1, le=10, decimal_places=1`). */
function checkRpe(raw: string): string | null {
  const value = raw.trim();
  if (!value) return null;
  if (!/^-?\d*\.?\d+$/.test(value)) return "RPE must be a number.";
  if (decimalPlaces(value) > 1) return "RPE can have at most 1 decimal place.";
  const parsed = Number(value);
  if (parsed < 1 || parsed > 10) return "RPE must be between 1 and 10.";
  return null;
}

/**
 * Validate a whole draft. Keys match the server's 422 `loc` paths so both sources
 * of truth feed one `fieldErrors` map.
 */
export function validateDraft(draft: WorkoutDraft): Record<string, string> {
  const errors: Record<string, string> = {};

  if (!draft.performed_on.trim()) {
    errors["performed_on"] = "Pick the date you trained.";
  }

  if (draft.title.length > 200) {
    errors["title"] = "Title must be 200 characters or fewer.";
  }

  const duration = draft.duration_min.trim();
  if (duration) {
    const problem = checkPositiveInt(duration, "Duration");
    if (problem) errors["duration_min"] = problem;
  }

  draft.exercises.forEach((row, index) => {
    const prefix = `exercises.${index}`;
    const sets = checkPositiveInt(row.sets, "Sets");
    if (sets) errors[`${prefix}.sets`] = sets;
    const reps = checkPositiveInt(row.reps, "Reps");
    if (reps) errors[`${prefix}.reps`] = reps;
    const weight = checkWeight(row.weight_kg);
    if (weight) errors[`${prefix}.weight_kg`] = weight;
    const rpe = checkRpe(row.rpe);
    if (rpe) errors[`${prefix}.rpe`] = rpe;
  });

  return errors;
}

/* -------------------------------- templates -------------------------------- */

export interface TemplateDraft {
  name: string;
  description: string;
  exercises: DraftExercise[];
}

/**
 * Validate a template draft.
 *
 * The exercise rules are identical to a workout's — the two tables carry the same
 * constraints — so this reuses them rather than restating them. The differences
 * are at the top level: a template requires a name (it is chosen from a list) and
 * has no date (it never happened).
 */
export function validateTemplateDraft(draft: TemplateDraft): Record<string, string> {
  const errors: Record<string, string> = {};

  const name = draft.name.trim();
  if (!name) {
    errors["name"] = "Give this template a name.";
  } else if (name.length > 200) {
    errors["name"] = "Name must be 200 characters or fewer.";
  }

  draft.exercises.forEach((row, index) => {
    const prefix = `exercises.${index}`;
    const sets = checkPositiveInt(row.sets, "Sets");
    if (sets) errors[`${prefix}.sets`] = sets;
    const reps = checkPositiveInt(row.reps, "Reps");
    if (reps) errors[`${prefix}.reps`] = reps;
    const weight = checkWeight(row.weight_kg);
    if (weight) errors[`${prefix}.weight_kg`] = weight;
    const rpe = checkRpe(row.rpe);
    if (rpe) errors[`${prefix}.rpe`] = rpe;
  });

  return errors;
}

/* -------------------------------- payloads -------------------------------- */

/** Empty string -> null (the server's "no value"), otherwise a number. */
function optionalNumber(raw: string): number | null {
  const value = raw.trim();
  return value ? Number(value) : null;
}

/**
 * Draft rows -> API payload. Array order becomes `position` server-side, so this
 * must preserve order exactly.
 */
export function toExercisePayload(rows: DraftExercise[]): WorkoutExerciseInput[] {
  return rows.map((row) => ({
    exercise_id: row.exercise.id,
    sets: Number(row.sets),
    reps: Number(row.reps),
    weight_kg: optionalNumber(row.weight_kg),
    rpe: optionalNumber(row.rpe),
    notes: row.notes.trim() || null,
  }));
}

/** The workout's own fields, trimmed and nulled out where blank. */
export function toWorkoutFields(draft: WorkoutDraft) {
  return {
    performed_on: draft.performed_on,
    title: draft.title.trim() || null,
    notes: draft.notes.trim() || null,
    duration_min: optionalNumber(draft.duration_min),
  };
}

/** Total reps across the session — the headline number while editing. */
export function totalVolume(rows: DraftExercise[]): number {
  return rows.reduce((sum, row) => {
    const sets = Number(row.sets);
    const reps = Number(row.reps);
    if (!Number.isFinite(sets) || !Number.isFinite(reps)) return sum;
    return sum + sets * reps;
  }, 0);
}
