import type { ButtonHTMLAttributes, Ref } from "react";
import { cn } from "@/lib/cn";
import { Spinner } from "@/components/ui/Spinner";

const VARIANTS = {
  primary: "bg-indigo-600 text-white hover:bg-indigo-500 focus-visible:outline-indigo-400",
  secondary:
    "border border-zinc-700 bg-transparent text-zinc-300 hover:border-zinc-500 hover:text-white focus-visible:outline-zinc-400",
  ghost: "bg-transparent text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 focus-visible:outline-zinc-500",
  danger: "bg-red-600 text-white hover:bg-red-500 focus-visible:outline-red-400",
} as const;

const SIZES = {
  sm: "px-3 py-1.5 text-sm",
  md: "px-4 py-2 text-sm",
  lg: "px-5 py-2.5 text-base",
} as const;

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: keyof typeof VARIANTS;
  size?: keyof typeof SIZES;
  /** Shows a spinner and blocks interaction. Use for in-flight requests. */
  pending?: boolean;
  ref?: Ref<HTMLButtonElement>;
}

/**
 * The one button in the app.
 *
 * `pending` is separate from `disabled` on purpose: a pending button keeps its
 * label (so the control does not resize mid-request) and announces itself via
 * `aria-busy`, while `disabled` is for "you may not do this at all".
 *
 * `type` defaults to "button". The HTML default is "submit", which turns every
 * unlabelled button inside a form into an accidental submit.
 */
export function Button({
  variant = "primary",
  size = "md",
  pending = false,
  disabled,
  type = "button",
  className,
  children,
  ref,
  ...props
}: ButtonProps) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || pending}
      aria-busy={pending || undefined}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors",
        "focus-visible:outline-2 focus-visible:outline-offset-2",
        "disabled:cursor-not-allowed disabled:opacity-50",
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...props}
    >
      {pending && <Spinner size="sm" />}
      {children}
    </button>
  );
}
