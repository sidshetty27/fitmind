import type { ReactNode } from "react";

import type { Finding } from "@/lib/api";
import { cn } from "@/lib/cn";

/**
 * One finding, rendered as a finished observation.
 *
 * The `statement` is printed verbatim — it was computed from the user's own sets
 * and is already a true, complete sentence. Nothing here rewrites or summarises
 * it, because any edit this component made would be an unverified claim about
 * someone's training.
 *
 * Kind drives an icon and a tint, never the meaning: the sentence says what
 * happened, and colour only groups findings at a glance. That keeps the card
 * readable for anyone who can't distinguish the tints.
 */

interface KindStyle {
  label: string;
  /** Ring rather than a fill — a solid block of colour behind body text hurts
   *  legibility, and these cards are read, not scanned. */
  accent: string;
  icon: ReactNode;
}

const iconProps = {
  className: "h-4 w-4",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.75,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  viewBox: "0 0 24 24",
  "aria-hidden": true,
};

const KINDS: Record<string, KindStyle> = {
  plateau: {
    label: "Plateau",
    accent: "text-amber-300 ring-amber-500/25 bg-amber-500/5",
    icon: (
      <svg {...iconProps}>
        <path d="M3 17l5-5 4 3 4-6 5 4" />
        <path d="M3 21h18" />
      </svg>
    ),
  },
  volume_drop: {
    label: "Volume drop",
    accent: "text-amber-300 ring-amber-500/25 bg-amber-500/5",
    icon: (
      <svg {...iconProps}>
        <path d="M3 7l6 6 4-4 8 8" />
        <path d="M21 17v-4h-4" />
      </svg>
    ),
  },
  stale_muscle_group: {
    label: "Neglected",
    accent: "text-sky-300 ring-sky-500/25 bg-sky-500/5",
    icon: (
      <svg {...iconProps}>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
      </svg>
    ),
  },
  ready_to_progress: {
    label: "Ready to progress",
    accent: "text-emerald-300 ring-emerald-500/25 bg-emerald-500/5",
    icon: (
      <svg {...iconProps}>
        <path d="M12 19V5M5 12l7-7 7 7" />
      </svg>
    ),
  },
};

/** A detector added server-side renders plainly rather than breaking the page. */
const FALLBACK: KindStyle = {
  label: "Observation",
  accent: "text-zinc-300 ring-zinc-700 bg-zinc-800/30",
  icon: (
    <svg {...iconProps}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8h.01M11 12h1v4h1" />
    </svg>
  ),
};

export function FindingCard({ finding }: { finding: Finding }) {
  const style = KINDS[finding.kind] ?? FALLBACK;

  return (
    <li
      className={cn(
        "flex gap-3 rounded-xl px-4 py-3.5 ring-1 ring-inset",
        style.accent,
      )}
    >
      <span className="mt-0.5 shrink-0">{style.icon}</span>
      <div className="min-w-0">
        {/* The label repeats what the icon and tint convey, so identity never
            depends on colour alone. */}
        <p className="text-[11px] font-medium uppercase tracking-wide opacity-80">
          {style.label}
        </p>
        <p className="mt-1 text-sm text-zinc-200">{finding.statement}</p>
      </div>
    </li>
  );
}
