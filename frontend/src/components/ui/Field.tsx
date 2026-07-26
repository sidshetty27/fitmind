import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/**
 * Shared chrome for a labelled form control: label, hint, error text, and the
 * aria wiring between them.
 *
 * The inputs below own this rather than the caller because getting it right means
 * generating an id, pointing `htmlFor` at it, pointing `aria-describedby` at
 * *both* the hint and the error, and flipping `aria-invalid` — five things that
 * are easy to half-do at every call site.
 */
export function FieldShell({
  id,
  label,
  hint,
  error,
  hintId,
  errorId,
  required,
  className,
  children,
}: {
  id: string;
  label?: ReactNode;
  hint?: ReactNode;
  error?: string;
  hintId: string;
  errorId: string;
  required?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      {label && (
        <label htmlFor={id} className="text-xs font-medium text-zinc-400">
          {label}
          {required && (
            <span className="ml-0.5 text-red-400" aria-hidden="true">
              *
            </span>
          )}
        </label>
      )}

      {children}

      {hint && !error && (
        <p id={hintId} className="text-xs text-zinc-600">
          {hint}
        </p>
      )}

      {error && (
        <p id={errorId} role="alert" className="text-xs text-red-400">
          {error}
        </p>
      )}
    </div>
  );
}

/** Border/ring treatment shared by every control, including the invalid state. */
export function controlClasses(error?: string, extra?: string): string {
  return cn(
    "w-full rounded-lg border bg-zinc-950/50 px-3 py-2 text-sm text-zinc-100 transition-colors",
    "placeholder:text-zinc-600",
    "focus:outline-2 focus:outline-offset-0",
    "disabled:cursor-not-allowed disabled:opacity-50",
    error
      ? "border-red-500/70 focus:outline-red-400"
      : "border-zinc-800 hover:border-zinc-700 focus:outline-indigo-400",
    extra,
  );
}

/** Builds the `aria-describedby` value from whichever of hint/error is showing. */
export function describedBy(
  hint: ReactNode | undefined,
  error: string | undefined,
  hintId: string,
  errorId: string,
): string | undefined {
  const ids = [error ? errorId : undefined, hint && !error ? hintId : undefined].filter(
    Boolean,
  );
  return ids.length ? ids.join(" ") : undefined;
}
