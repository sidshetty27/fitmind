"use client";

import { useState } from "react";
import Link from "next/link";
import { useAuth } from "@clerk/nextjs";

import { api, type WorkoutExerciseInput } from "@/lib/api";
import { normalizeApiError } from "@/lib/apiErrors";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

/**
 * Turn the workout currently in the editor into a reusable template.
 *
 * This is the most natural way templates get created — you build a session, it
 * works, you want it again — so it lives next to the save controls rather than
 * behind a separate "create template" flow.
 *
 * The name is collected inline instead of via `window.prompt()`: a prompt cannot
 * show a validation error, cannot show a pending state, and is blocked outright
 * by some browsers. A 409 (name already taken) needs all three.
 *
 * Only the exercises are copied. Date, duration and session notes are facts about
 * the session that happened, not about the plan.
 */
export function SaveAsTemplateButton({
  exercises,
  defaultName,
  disabled,
}: {
  exercises: WorkoutExerciseInput[];
  defaultName: string;
  disabled?: boolean;
}) {
  const { getToken } = useAuth();

  const [open, setOpen] = useState(false);
  const [name, setName] = useState(defaultName);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedId, setSavedId] = useState<string | null>(null);

  async function save() {
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Give this template a name.");
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const token = await getToken();
      const created = await api.templates.create(token, {
        name: trimmed,
        exercises,
      });
      setSavedId(created.id);
      setOpen(false);
    } catch (err) {
      const normalized = normalizeApiError(err);
      setError(
        normalized.status === 409
          ? `You already have a template named "${trimmed}". Pick another name.`
          : normalized.formError,
      );
    } finally {
      setSaving(false);
    }
  }

  if (savedId) {
    return (
      <Alert tone="success" title="Saved as a template">
        <Link href={`/dashboard/templates/${savedId}`} className="underline">
          Open the template
        </Link>{" "}
        or keep editing this workout.
      </Alert>
    );
  }

  if (!open) {
    return (
      <Button
        variant="secondary"
        // An empty template is never what someone means by "save this as a plan".
        disabled={disabled || exercises.length === 0}
        title={
          exercises.length === 0 ? "Add exercises before saving a template" : undefined
        }
        onClick={() => {
          setName(defaultName);
          setError(null);
          setOpen(true);
        }}
      >
        Save as template
      </Button>
    );
  }

  return (
    <div className="w-full rounded-xl border border-zinc-800 bg-zinc-950/40 p-4">
      <Input
        label="Template name"
        type="text"
        maxLength={200}
        autoFocus
        value={name}
        error={error ?? undefined}
        disabled={saving}
        placeholder="e.g. Push Day A"
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => {
          // Enter must not bubble up and submit the workout form behind this.
          if (e.key === "Enter") {
            e.preventDefault();
            void save();
          }
          if (e.key === "Escape") setOpen(false);
        }}
      />
      <p className="mt-2 text-xs text-zinc-600">
        Copies the {exercises.length}{" "}
        {exercises.length === 1 ? "exercise" : "exercises"} above — not the date or
        duration.
      </p>
      <div className="mt-3 flex items-center gap-2">
        <Button size="sm" pending={saving} onClick={save}>
          {saving ? "Saving…" : "Save template"}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={saving}
          onClick={() => setOpen(false)}
        >
          Cancel
        </Button>
      </div>
    </div>
  );
}
