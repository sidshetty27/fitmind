"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@clerk/nextjs";

import { api, type Exercise, type WorkoutTemplate } from "@/lib/api";
import { normalizeApiError } from "@/lib/apiErrors";
import {
  draftFromExercise,
  draftFromSaved,
  toExercisePayload,
  totalVolume,
  validateTemplateDraft,
  type DraftExercise,
  type TemplateDraft,
} from "@/lib/workoutDraft";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input, Textarea } from "@/components/ui/Input";
import { ExerciseRow } from "@/components/workouts/ExerciseRow";
import { ExerciseSearch } from "@/components/workouts/ExerciseSearch";

/**
 * The template editor.
 *
 * Structurally the twin of `WorkoutForm`, and it reuses `ExerciseSearch` and
 * `ExerciseRow` unchanged — both take a `DraftExercise` and know nothing about
 * whether they sit inside a plan or a logged session. The parts that differ are
 * the header fields (name/description instead of date/duration) and the endpoints.
 *
 * A duplicate name comes back as **409**, not 422, so it is surfaced on the name
 * field specifically rather than as a generic banner.
 */
export function TemplateForm({
  mode,
  initial,
}: {
  mode: "create" | "edit";
  initial?: WorkoutTemplate;
}) {
  const router = useRouter();
  const { getToken } = useAuth();

  const [draft, setDraft] = useState<TemplateDraft>(() => ({
    name: initial?.name ?? "",
    description: initial?.description ?? "",
    exercises: initial?.exercises.map(draftFromSaved) ?? [],
  }));
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [showValidation, setShowValidation] = useState(false);
  const [dirty, setDirty] = useState(false);

  const localErrors = useMemo(() => validateTemplateDraft(draft), [draft]);
  const errors = { ...(showValidation ? localErrors : {}), ...serverErrors };

  useEffect(() => {
    if (!dirty || saving) return;
    const onBeforeUnload = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty, saving]);

  function patchDraft(patch: Partial<TemplateDraft>) {
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

    const problems = validateTemplateDraft(draft);
    if (Object.keys(problems).length > 0) {
      const count = Object.keys(problems).length;
      setFormError(`Please fix ${count} ${count === 1 ? "field" : "fields"} below.`);
      return;
    }

    setSaving(true);
    const fields = {
      name: draft.name.trim(),
      description: draft.description.trim() || null,
    };
    const exercises = toExercisePayload(draft.exercises);

    let fieldsSaved = false;

    try {
      const token = await getToken();

      if (mode === "create") {
        const created = await api.templates.create(token, { ...fields, exercises });
        setDirty(false);
        router.push(`/dashboard/templates/${created.id}`);
        return;
      }

      if (!initial) throw new Error("Missing template to edit.");

      await api.templates.update(token, initial.id, fields);
      fieldsSaved = true;
      await api.templates.replaceExercises(token, initial.id, exercises);

      setDirty(false);
      setSaved(true);
      setSaving(false);
      router.refresh();
    } catch (error) {
      const normalized = normalizeApiError(error);

      // 409 means the name collides with another of this user's templates. The
      // server sends it as a plain string detail, so pin it to the name field
      // where the user can actually act on it.
      if (normalized.status === 409) {
        setServerErrors({ name: normalized.formError });
        setFormError("That name is already taken.");
      } else {
        setServerErrors(normalized.fieldErrors);
        setFormError(
          fieldsSaved
            ? `Name and description were saved, but the exercise list failed: ${normalized.formError}`
            : normalized.formError,
        );
      }
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!initial) return;
    if (
      !window.confirm(
        `Delete the "${initial.name}" template? Workouts already logged from it are not affected.`,
      )
    ) {
      return;
    }

    setDeleting(true);
    setFormError(null);
    try {
      const token = await getToken();
      await api.templates.delete(token, initial.id);
      setDirty(false);
      router.refresh();
      router.push("/dashboard/templates");
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

  return (
    // noValidate: `required` stays for semantics, but the browser's native
    // validation would otherwise block submit before `submit` runs, so our own
    // messages (and the aria-invalid wiring) would never appear.
    <form
      onSubmit={submit}
      noValidate
      className="mx-auto w-full max-w-3xl space-y-6"
    >
      {formError && <Alert title="Couldn't save">{formError}</Alert>}
      {saved && !formError && (
        <Alert tone="success" title="Template saved">
          Your changes are live.
        </Alert>
      )}

      <Card>
        <CardHeader
          title="Template details"
          description="How you'll recognise this plan in the list"
        />
        <CardBody className="space-y-4">
          <Input
            label="Name"
            type="text"
            required
            maxLength={200}
            placeholder="e.g. Push Day A"
            disabled={busy}
            value={draft.name}
            error={errors["name"]}
            onChange={(e) => patchDraft({ name: e.target.value })}
          />
          <Textarea
            label="Description"
            placeholder="Optional — what this session is for"
            disabled={busy}
            value={draft.description}
            error={errors["description"]}
            onChange={(e) => patchDraft({ description: e.target.value })}
          />
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="Planned exercises"
          description={
            draft.exercises.length === 0
              ? "Search the catalog to add movements"
              : `${draft.exercises.length} ${draft.exercises.length === 1 ? "movement" : "movements"} · ${volume} target reps`
          }
        />
        <CardBody className="space-y-4">
          <ExerciseSearch onSelect={addExercise} disabled={busy} />

          {draft.exercises.length === 0 ? (
            <EmptyState
              title="No exercises planned"
              description="Add the movements this session should include. Weight and RPE are optional — leave them blank for 'work up to something hard'."
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

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" size="lg" pending={saving} disabled={deleting}>
            {saving ? "Saving…" : mode === "create" ? "Save template" : "Save changes"}
          </Button>
          <Link href="/dashboard/templates" onClick={confirmLeave}>
            <Button variant="secondary" size="lg" disabled={busy}>
              {mode === "edit" ? "Back to templates" : "Cancel"}
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
            {deleting ? "Deleting…" : "Delete template"}
          </Button>
        )}
      </div>
    </form>
  );
}
