import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

const TONES = {
  error: "border-red-900/60 bg-red-950/40 text-red-300",
  warning: "border-amber-900/60 bg-amber-950/40 text-amber-300",
  success: "border-emerald-900/60 bg-emerald-950/40 text-emerald-300",
} as const;

/**
 * Banner for a whole-form or whole-page message — typically
 * `normalizeApiError().formError`.
 *
 * Errors get `role="alert"` so a screen reader announces a failed save without
 * the user having to go hunting for what changed.
 */
export function Alert({
  tone = "error",
  title,
  children,
  action,
  className,
}: {
  tone?: keyof typeof TONES;
  title?: string;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cn(
        "flex items-start justify-between gap-4 rounded-xl border px-4 py-3 text-sm",
        TONES[tone],
        className,
      )}
    >
      <div className="min-w-0">
        {title && <p className="font-medium">{title}</p>}
        {children && <div className={cn(title && "mt-1", "text-xs opacity-90")}>{children}</div>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}
