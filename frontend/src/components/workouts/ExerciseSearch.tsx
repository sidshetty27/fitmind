"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useAuth } from "@clerk/nextjs";

import { api, type Exercise } from "@/lib/api";
import { isAbortError, normalizeApiError } from "@/lib/apiErrors";
import { cn } from "@/lib/cn";
import { Spinner } from "@/components/ui/Spinner";

const DEBOUNCE_MS = 250;
const MAX_RESULTS = 8;

/** Prettify an enum value: `full_body` -> `Full body`. */
function humanize(value: string): string {
  const spaced = value.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/**
 * Type-ahead over the shared exercise catalog.
 *
 * Two things make this safe to fire on every keystroke:
 *
 *  - **Debounce.** A 250ms idle window collapses a burst of typing into one
 *    request instead of one per character.
 *  - **Abort.** Each new search cancels the one before it. Without this, responses
 *    can resolve out of order and a slow request for "be" lands after the fast one
 *    for "bench", leaving the dropdown showing results for text the user has
 *    already moved past.
 *
 * The listbox is wired for keyboard use (arrows, Enter, Escape) because picking an
 * exercise sits in the middle of a form — forcing a reach for the mouse there is
 * the difference between logging a session in 30 seconds and 3 minutes.
 */
export function ExerciseSearch({
  onSelect,
  disabled,
}: {
  onSelect: (exercise: Exercise) => void;
  disabled?: boolean;
}) {
  const { getToken } = useAuth();
  const listboxId = useId();

  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(0);

  /**
   * Results are stored together with the query that produced them.
   *
   * Keeping them in one object makes staleness impossible to render: the
   * dropdown compares `outcome.query` against what is currently typed and shows
   * a searching state unless they match. A separate `results` array would still
   * be holding the previous term's matches during the debounce window, and would
   * briefly display them under the new text.
   */
  const [outcome, setOutcome] = useState<{
    query: string;
    items: Exercise[];
    error: string | null;
  }>({ query: "", items: [], error: null });

  const containerRef = useRef<HTMLDivElement>(null);
  const trimmed = query.trim();

  useEffect(() => {
    const search = query.trim();
    // Nothing to search for. No state to reset either — the dropdown is hidden
    // when the box is empty, and setting state synchronously here would force a
    // second render pass on every keystroke that empties the field.
    if (!search) return;

    const controller = new AbortController();

    const timer = setTimeout(async () => {
      try {
        const token = await getToken();
        const items = await api.exercises.list(
          token,
          { search, limit: MAX_RESULTS },
          { signal: controller.signal },
        );
        setOutcome({ query: search, items, error: null });
        setHighlighted(0);
      } catch (err) {
        // An abort is this component cancelling itself — not a failure to report.
        if (isAbortError(err)) return;
        setOutcome({ query: search, items: [], error: normalizeApiError(err).formError });
      }
    }, DEBOUNCE_MS);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query, getToken]);

  // Derived, not stored: we are loading whenever the latest result on hand was
  // for a different search term than the one in the box.
  const loading = trimmed.length > 0 && outcome.query !== trimmed;
  const results = loading ? [] : outcome.items;
  const error = loading ? null : outcome.error;

  // Clicking anywhere else dismisses the dropdown.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  function choose(exercise: Exercise) {
    onSelect(exercise);
    // Clear after picking: the common flow is adding several movements in a row,
    // and leaving the last name in the box means retyping over it every time.
    setQuery("");
    setOpen(false);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      setOpen(false);
      return;
    }
    if (!open || results.length === 0) return;

    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlighted((i) => (i + 1) % results.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlighted((i) => (i - 1 + results.length) % results.length);
    } else if (event.key === "Enter") {
      // Stop the form submitting — Enter here means "pick this exercise".
      event.preventDefault();
      const picked = results[highlighted];
      if (picked) choose(picked);
    }
  }

  const showDropdown = open && trimmed.length > 0;

  return (
    <div ref={containerRef} className="relative">
      <label htmlFor={`${listboxId}-input`} className="text-xs font-medium text-zinc-400">
        Add an exercise
      </label>

      <div className="relative mt-1.5">
        <input
          id={`${listboxId}-input`}
          type="text"
          role="combobox"
          autoComplete="off"
          aria-expanded={showDropdown}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-activedescendant={
            showDropdown && results[highlighted]
              ? `${listboxId}-opt-${results[highlighted].id}`
              : undefined
          }
          disabled={disabled}
          placeholder="Search movements — e.g. bench, squat, row"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          className={cn(
            "w-full rounded-lg border border-zinc-800 bg-zinc-950/50 px-3 py-2 pr-9 text-sm text-zinc-100",
            "placeholder:text-zinc-600 hover:border-zinc-700",
            "focus:outline-2 focus:outline-offset-0 focus:outline-indigo-400",
            "disabled:cursor-not-allowed disabled:opacity-50",
          )}
        />
        {loading && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500">
            <Spinner size="sm" label="Searching" />
          </span>
        )}
      </div>

      {showDropdown && (
        <div className="absolute z-20 mt-1.5 w-full overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900 shadow-2xl">
          {error ? (
            <p className="px-3 py-3 text-xs text-red-400">{error}</p>
          ) : results.length === 0 ? (
            <p className="px-3 py-3 text-xs text-zinc-500">
              {loading ? "Searching…" : `No movements match "${trimmed}".`}
            </p>
          ) : (
            <ul id={listboxId} role="listbox" className="max-h-72 overflow-y-auto py-1">
              {results.map((exercise, index) => (
                <li
                  key={exercise.id}
                  id={`${listboxId}-opt-${exercise.id}`}
                  role="option"
                  aria-selected={index === highlighted}
                >
                  <button
                    type="button"
                    // mousedown, not click: the input's blur would otherwise tear
                    // the dropdown down before the click ever lands.
                    onMouseDown={(e) => {
                      e.preventDefault();
                      choose(exercise);
                    }}
                    onMouseEnter={() => setHighlighted(index)}
                    className={cn(
                      "flex w-full items-center justify-between gap-3 px-3 py-2 text-left transition-colors",
                      index === highlighted ? "bg-indigo-600/20" : "hover:bg-zinc-800/60",
                    )}
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm text-zinc-100">
                        {exercise.name}
                      </span>
                      <span className="block text-xs text-zinc-500">
                        {humanize(exercise.primary_muscle_group)} ·{" "}
                        {humanize(exercise.equipment)}
                      </span>
                    </span>
                    {exercise.is_compound && (
                      <span className="shrink-0 rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-zinc-400">
                        Compound
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
