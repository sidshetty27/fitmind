"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@clerk/nextjs";

import { api, type Exercise, type Workout } from "@/lib/api";
import { normalizeApiError } from "@/lib/apiErrors";
import { todayISO } from "@/lib/dates";
import {
  draftFromExercise,
  draftFromSaved,
  toExercisePayload,
  toWorkoutFields,
  totalVolume,
  validateDraft,
  type DraftExercise,
  type WorkoutDraft,
} from "@/lib/workoutDraft";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input, Textarea } from "@/components/ui/Input";
import { ExerciseRow } from "@/components/workouts/ExerciseRow";
import { ExerciseSearch } from "@/components/workouts/ExerciseSearch";
import { SaveAsTemplateButton } from "@/components/workouts/SaveAsTemplateButton";

/**
 * The workout editor — one component for both creating and editing.
 *
 * Sharing it is what keeps "add an exercise" behaving identically on a new
 * session and an existing one. The two modes differ only in how they save:
 *
 *   create — one `POST /api/workouts` carrying fields *and* exercises.
 *   edit   — `PATCH /api/workouts/{id}` for the fields, then
 *            `PUT /api/workouts/{id}/exercises` for the list.
 *
 * The edit path is two requests because the API deliberately separates them, so a
 * title change can never silently wipe a session's logged sets. That means a
 * partial failure is possible, and `submit()` reports exactly which half landed
 * rather than a generic "save failed" that leaves the user unsure what to redo.
 */

interface Props {
  mode: "create" | "edit";
  /** Present in edit mode; also used to seed a duplicate in create mode. */
  initial?: Workout;
  /** Create mode only: prefill from another workout, dated today. */
  duplicateOf?: Workout;
}

function buildInitialDraft(initial?: Workout, duplicateOf?: Workout): WorkoutDraft {
  const source = initial ?? duplicateOf;
  if (!source) {
    return {
      performed_on: todayISO(),
      title: "",
      notes: "",
      duration_min: "",
      exercises: [],
    };
  }
  return {
    // A duplicate is a *new* session happening now, so it takes today's date
    // rather than the original's.
    performed_on: initial ? initial.performed_on : todayISO(),
    title: initial ? (source.title ?? "") : source.title ? `${source.title} (copy)` : "",
    notes: source.notes ?? "",
    duration_min: source.duration_min == null ? "" : String(source.duration_min),
    exercises: source.exercises.map(draftFromSaved),
  };
}

export function WorkoutForm({ mode, initial, duplicateOf }: Props) {
  const router = useRouter();
  const { getToken } = useAuth();

  const [draft, setDraft] = useState<WorkoutDraft>(() =>
    buildInitialDraft(initial, duplicateOf),
  );
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  // Local validation stays hidden until the first submit attempt — flagging
  // "Sets is required" on a row the user has not reached yet is just noise.
  const [showValidation, setShowValidation] = useState(false);
  const [dirty, setDirty] = useState(mode === "create" && Boolean(duplicateOf));
  const [saved, setSaved] = useState(false);

  const localErrors = useMemo(() => validateDraft(draft), [draft]);

  // Server errors win: they are the authoritative rejection, and they are cleared
  // on the next submit so a fixed field stops showing a stale message.
  const errors = { ...(showValidation ? localErrors : {}), ...serverErrors };

  // Warn before losing unsaved work to a tab close or reload. Client-side
  // navigation is not covered — Next.js has no stable API for intercepting it —
  // so the Cancel link asks for confirmation itself.
  useEffect(() => {
    if (!dirty || saving) return;
    const onBeforeUnload = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty, saving]);

  function patchDraft(patch: Partial<WorkoutDraft>) {
    setDraft((current) => ({ ...current, ...patch }));
    setDirty(true);
  }

  function addExercise(exercise: Exercise) {
    setDraft((current) => ({
      ...current,
      exercises: [...current.exercises, draftFromExercise(exercise)],
    }));
    setDirty(true);
  }

  function updateExercise(key: string, patch: Partial<DraftExercise>) {
    setDraft((current) => ({
      ...current,
      exercises: current.exercises.map((row) =>
        row.key === key ? { ...row, ...patch } : row,
      ),
    }));
    setDirty(true);
  }

  function removeExercise(key: string) {
    setDraft((current) => ({
      ...current,
      exercises: current.exercises.filter((row) => row.key !== key),
    }));
    // Indices shift when a row is removed, so any server errors keyed by the old
    // positions now point at the wrong rows. Drop them.
    setServerErrors({});
    setDirty(true);
  }

  function moveExercise(key: string, direction: -1 | 1) {
    setDraft((current) => {
      const rows = [...current.exercises];
      const from = rows.findIndex((row) => row.key === key);
      const to = from + direction;
      if (from === -1 || to < 0 || to >= rows.length) return current;
      [rows[from], rows[to]] = [rows[to], rows[from]];
      return { ...current, exercises: rows };
    });
    setServerErrors({});
    setDirty(true);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setShowValidation(true);
    setServerErrors({});
    setFormError(null);
    setSaved(false);

    const problems = validateDraft(draft);
    if (Object.keys(problems).length > 0) {
      const count = Object.keys(problems).length;
      setFormError(`Please fix ${count} ${count === 1 ? "field" : "fields"} below.`);
      return;
    }

    setSaving(true);
    const fields = toWorkoutFields(draft);
    const exercises = toExercisePayload(draft.exercises);

    // Tracks how far the two-request edit path got, so a failure can say which
    // half was written.
    let fieldsSaved = false;

    try {
      const token = await getToken();

      if (mode === "create") {
        const created = await api.workouts.create(token, { ...fields, exercises });
        setDirty(false);
        router.push(`/dashboard/workouts/${created.id}`);
        return;
      }

      if (!initial) throw new Error("Missing workout to edit.");

      await api.workouts.update(token, initial.id, fields);
      fieldsSaved = true;
      await api.workouts.replaceExercises(token, initial.id, exercises);

      setDirty(false);
      setSaved(true);
      setSaving(false);
      // Re-run the server component so the page (and the list behind it) reflect
      // what was just written. We stay on the page rather than navigating: the
      // user is often mid-session, adding movements as they go.
      router.refresh();
    } catch (error) {
      const normalized = normalizeApiError(error);
      setServerErrors(normalized.fieldErrors);
      setFormError(
        fieldsSaved
          ? `Workout details were saved, but the exercise list failed: ${normalized.formError} Your exercises below are unsaved — fix and save again.`
          : normalized.formError,
      );
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!initial) return;
    const confirmed = window.confirm(
      "Delete this workout? Its exercises go with it. This cannot be undone.",
    );
    if (!confirmed) return;

    setDeleting(true);
    setFormError(null);
    try {
      const token = await getToken();
      await api.workouts.delete(token, initial.id);
      setDirty(false);
      router.refresh();
      router.push("/dashboard/workouts");
    } catch (error) {
      setFormError(normalizeApiError(error).formError);
      setDeleting(false);
    }
  }

  function confirmLeave(event: React.MouseEvent) {
    if (!dirty) return;
    if (!window.confirm("Discard unsaved changes?")) event.preventDefault();
  }

  const busy = saving || deleting;
  const volume = totalVolume(draft.exercises);
  // Only meaningful once the rows are valid — `toExercisePayload` would otherwise
  // produce NaN for a half-typed sets field.
  const exercisesAreValid = draft.exercises.every(
    (_, index) =>
      !localErrors[`exercises.${index}.sets`] &&
      !localErrors[`exercises.${index}.reps`] &&
      !localErrors[`exercises.${index}.weight_kg`] &&
      !localErrors[`exercises.${index}.rpe`],
  );

  return (
    <form onSubmit={submit} className="mx-auto w-full max-w-3xl space-y-6">
      {formError && <Alert title="Couldn't save">{formError}</Alert>}
      {saved && !formError && (
        <Alert tone="success" title="Workout saved">
          Your changes are live.
        </Alert>
      )}

      <Card>
        <CardHeader
          title="Session details"
          description="When you trained, and how it went overall"
        />
        <CardBody className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Input
            label="Date"
            type="date"
            required
            disabled={busy}
            value={draft.performed_on}
            error={errors["performed_on"]}
            onChange={(e) => patchDraft({ performed_on: e.target.value })}
          />
          <Input
            label="Duration (minutes)"
            type="number"
            inputMode="numeric"
            min={1}
            step={1}
            placeholder="Optional"
            disabled={busy}
            value={draft.duration_min}
            error={errors["duration_min"]}
            onChange={(e) => patchDraft({ duration_min: e.target.value })}
          />
          <Input
            fieldClassName="sm:col-span-2"
            label="Title"
            type="text"
            maxLength={200}
            placeholder="Optional — e.g. Push Day A"
            disabled={busy}
            value={draft.title}
            error={errors["title"]}
            onChange={(e) => patchDraft({ title: e.target.value })}
          />
          <Textarea
            fieldClassName="sm:col-span-2"
            label="Notes"
            placeholder="Optional — how the session felt, anything to remember"
            disabled={busy}
            value={draft.notes}
            error={errors["notes"]}
            onChange={(e) => patchDraft({ notes: e.target.value })}
          />
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="Exercises"
          description={
            draft.exercises.length === 0
              ? "Search the catalog to add movements"
              : `${draft.exercises.length} ${draft.exercises.length === 1 ? "movement" : "movements"} · ${volume} total reps`
          }
        />
        <CardBody className="space-y-4">
          <ExerciseSearch onSelect={addExercise} disabled={busy} />

          {draft.exercises.length === 0 ? (
            <EmptyState
              title="No exercises yet"
              description="Use the search above to add your first movement. You can also save the session now and add them later."
            />
          ) : (
            <ul className="space-y-3">
              {draft.exercises.map((row, index) => (
                <ExerciseRow
                  key={row.key}
                  row={row}
                  index={index}
                  total={draft.exercises.length}
                  errors={errors}
                  disabled={busy}
                  onChange={updateExercise}
                  onRemove={removeExercise}
                  onMove={moveExercise}
                />
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      <SaveAsTemplateButton
        exercises={exercisesAreValid ? toExercisePayload(draft.exercises) : []}
        defaultName={draft.title.trim() || "My template"}
        disabled={busy}
      />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" size="lg" pending={saving} disabled={deleting}>
            {saving
              ? "Saving…"
              : mode === "create"
                ? "Save workout"
                : "Save changes"}
          </Button>
          <Link href="/dashboard/workouts" onClick={confirmLeave}>
            <Button variant="secondary" size="lg" disabled={busy}>
              {mode === "edit" ? "Back to workouts" : "Cancel"}
            </Button>
          </Link>
        </div>

        {mode === "edit" && (
          <Button
            variant="danger"
            size="lg"
            pending={deleting}
            disabled={saving}
            onClick={handleDelete}
          >
            {deleting ? "Deleting…" : "Delete workout"}
          </Button>
        )}
      </div>
    </form>
  );
}
