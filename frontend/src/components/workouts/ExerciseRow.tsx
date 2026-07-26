"use client";

import { Input } from "@/components/ui/Input";
import { exerciseFieldKey } from "@/lib/apiErrors";
import type { DraftExercise } from "@/lib/workoutDraft";

/** Prettify an enum value: `full_body` -> `Full body`. */
function humanize(value: string): string {
  const spaced = value.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

function IconButton({
  label,
  onClick,
  disabled,
  children,
  tone = "default",
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
  tone?: "default" | "danger";
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      className={
        "rounded-md p-1.5 transition-colors disabled:cursor-not-allowed disabled:opacity-30 " +
        (tone === "danger"
          ? "text-zinc-500 hover:bg-red-950/50 hover:text-red-400"
          : "text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200")
      }
    >
      {children}
    </button>
  );
}

/**
 * One movement in the editor: its performance fields, plus reorder and remove.
 *
 * Every edit here is local state. Nothing hits the network until the workout is
 * saved, which is what the `PUT /workouts/{id}/exercises` full-replace endpoint is
 * shaped for — the client owns the whole list and submits it as one atomic set.
 *
 * `index` drives both the displayed position and the error keys, so a server 422
 * on `exercises.2.sets` highlights the third row's Sets box specifically.
 */
export function ExerciseRow({
  row,
  index,
  total,
  errors,
  disabled,
  onChange,
  onRemove,
  onMove,
}: {
  row: DraftExercise;
  index: number;
  total: number;
  errors: Record<string, string>;
  disabled?: boolean;
  onChange: (key: string, patch: Partial<DraftExercise>) => void;
  onRemove: (key: string) => void;
  onMove: (key: string, direction: -1 | 1) => void;
}) {
  const err = (field: string) => errors[exerciseFieldKey(index, field)];

  return (
    <li className="rounded-xl border border-zinc-800 bg-zinc-950/40 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-zinc-800 text-xs font-semibold text-zinc-400">
            {index + 1}
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-zinc-100">
              {row.exercise.name}
            </p>
            <p className="mt-0.5 text-xs text-zinc-500">
              {humanize(row.exercise.primary_muscle_group)} ·{" "}
              {humanize(row.exercise.equipment)}
            </p>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-0.5">
          <IconButton
            label="Move up"
            disabled={disabled || index === 0}
            onClick={() => onMove(row.key, -1)}
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24" aria-hidden="true">
              <path d="m18 15-6-6-6 6" />
            </svg>
          </IconButton>
          <IconButton
            label="Move down"
            disabled={disabled || index === total - 1}
            onClick={() => onMove(row.key, 1)}
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24" aria-hidden="true">
              <path d="m6 9 6 6 6-6" />
            </svg>
          </IconButton>
          <IconButton
            label={`Remove ${row.exercise.name}`}
            tone="danger"
            disabled={disabled}
            onClick={() => onRemove(row.key)}
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" />
            </svg>
          </IconButton>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Input
          label="Sets"
          type="number"
          inputMode="numeric"
          min={1}
          step={1}
          required
          disabled={disabled}
          value={row.sets}
          error={err("sets")}
          onChange={(e) => onChange(row.key, { sets: e.target.value })}
        />
        <Input
          label="Reps"
          type="number"
          inputMode="numeric"
          min={1}
          step={1}
          required
          disabled={disabled}
          value={row.reps}
          error={err("reps")}
          onChange={(e) => onChange(row.key, { reps: e.target.value })}
        />
        <Input
          label="Weight (kg)"
          type="number"
          inputMode="decimal"
          min={0}
          // The server stores 2 decimal places; 0.5 matches how plates actually
          // come off the rack and keeps the spinner from producing 62.505.
          step={0.5}
          placeholder="Bodyweight"
          disabled={disabled}
          value={row.weight_kg}
          error={err("weight_kg")}
          onChange={(e) => onChange(row.key, { weight_kg: e.target.value })}
        />
        <Input
          label="RPE"
          type="number"
          inputMode="decimal"
          min={1}
          max={10}
          step={0.5}
          placeholder="1–10"
          disabled={disabled}
          value={row.rpe}
          error={err("rpe")}
          onChange={(e) => onChange(row.key, { rpe: e.target.value })}
        />
      </div>

      <div className="mt-3">
        <Input
          label="Notes"
          type="text"
          placeholder="Optional — form cues, how it felt"
          disabled={disabled}
          value={row.notes}
          error={err("notes")}
          onChange={(e) => onChange(row.key, { notes: e.target.value })}
        />
      </div>
    </li>
  );
}
