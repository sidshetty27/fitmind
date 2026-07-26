"use client";

import { useId } from "react";
import type {
  InputHTMLAttributes,
  ReactNode,
  Ref,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";
import { FieldShell, controlClasses, describedBy } from "@/components/ui/Field";

interface Common {
  label?: ReactNode;
  hint?: ReactNode;
  /** Message from `normalizeApiError().fieldErrors`, or local validation. */
  error?: string;
  /** Class for the wrapper, not the control — use for grid spans. */
  fieldClassName?: string;
}

/* --------------------------------- Input --------------------------------- */

export interface InputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "id">,
    Common {
  ref?: Ref<HTMLInputElement>;
}

export function Input({
  label,
  hint,
  error,
  fieldClassName,
  className,
  required,
  ref,
  ...props
}: InputProps) {
  const id = useId();
  return (
    <FieldShell
      id={id}
      label={label}
      hint={hint}
      error={error}
      hintId={`${id}-hint`}
      errorId={`${id}-error`}
      required={required}
      className={fieldClassName}
    >
      <input
        ref={ref}
        id={id}
        required={required}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(hint, error, `${id}-hint`, `${id}-error`)}
        className={controlClasses(error, className)}
        {...props}
      />
    </FieldShell>
  );
}

/* -------------------------------- Textarea -------------------------------- */

export interface TextareaProps
  extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "id">,
    Common {
  ref?: Ref<HTMLTextAreaElement>;
}

export function Textarea({
  label,
  hint,
  error,
  fieldClassName,
  className,
  required,
  rows = 3,
  ref,
  ...props
}: TextareaProps) {
  const id = useId();
  return (
    <FieldShell
      id={id}
      label={label}
      hint={hint}
      error={error}
      hintId={`${id}-hint`}
      errorId={`${id}-error`}
      required={required}
      className={fieldClassName}
    >
      <textarea
        ref={ref}
        id={id}
        rows={rows}
        required={required}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(hint, error, `${id}-hint`, `${id}-error`)}
        className={controlClasses(error, `resize-y ${className ?? ""}`)}
        {...props}
      />
    </FieldShell>
  );
}

/* --------------------------------- Select --------------------------------- */

export interface SelectProps
  extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "id">,
    Common {
  ref?: Ref<HTMLSelectElement>;
}

export function Select({
  label,
  hint,
  error,
  fieldClassName,
  className,
  required,
  children,
  ref,
  ...props
}: SelectProps) {
  const id = useId();
  return (
    <FieldShell
      id={id}
      label={label}
      hint={hint}
      error={error}
      hintId={`${id}-hint`}
      errorId={`${id}-error`}
      required={required}
      className={fieldClassName}
    >
      <select
        ref={ref}
        id={id}
        required={required}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(hint, error, `${id}-hint`, `${id}-error`)}
        className={controlClasses(error, className)}
        {...props}
      >
        {children}
      </select>
    </FieldShell>
  );
}
