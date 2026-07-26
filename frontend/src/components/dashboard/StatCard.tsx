import type { ReactNode } from "react";
import { Card } from "@/components/ui/Card";

/**
 * A single headline number on the dashboard.
 *
 * `value` is a string, not a number, so callers can render "200+", "—", or a
 * date without this component needing to know about any of those cases.
 */
export function StatCard({
  label,
  value,
  sublabel,
  accent = "indigo",
}: {
  label: string;
  value: string;
  sublabel?: ReactNode;
  accent?: "indigo" | "emerald" | "amber" | "violet";
}) {
  const dot = {
    indigo: "bg-indigo-400",
    emerald: "bg-emerald-400",
    amber: "bg-amber-400",
    violet: "bg-violet-400",
  }[accent];

  return (
    <Card className="p-5">
      <div className="flex items-center gap-2">
        <span className={`h-1.5 w-1.5 rounded-full ${dot}`} aria-hidden="true" />
        <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
          {label}
        </p>
      </div>
      <p className="mt-3 text-2xl font-semibold tracking-tight text-zinc-100">
        {value}
      </p>
      {sublabel && <p className="mt-1 text-xs text-zinc-500">{sublabel}</p>}
    </Card>
  );
}
