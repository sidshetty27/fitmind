import type { ReactNode } from "react";

/**
 * The "nothing here yet" panel. Empty is a first-class state, not an accident —
 * a blank region reads as a broken page, so every list renders this instead.
 */
export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-zinc-800 px-6 py-14 text-center">
      {icon && <div className="mb-3 text-zinc-600">{icon}</div>}
      <h3 className="text-sm font-semibold text-zinc-200">{title}</h3>
      {description && (
        <p className="mt-1.5 max-w-sm text-sm text-zinc-500">{description}</p>
      )}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
