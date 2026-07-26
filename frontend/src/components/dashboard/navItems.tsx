import type { ReactNode } from "react";

/**
 * The dashboard navigation model, shared by the desktop rail and the mobile
 * drawer so the two can never drift apart.
 *
 * Items for routes that do not exist yet are marked `soon` and render as inert
 * labels rather than links — a nav that 404s is worse than one that says "later".
 */
export interface NavItem {
  href: string;
  label: string;
  icon: ReactNode;
  soon?: boolean;
}

const iconProps = {
  className: "h-4.5 w-4.5",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.75,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  viewBox: "0 0 24 24",
  "aria-hidden": true,
};

export const NAV_ITEMS: NavItem[] = [
  {
    href: "/dashboard",
    label: "Dashboard",
    icon: (
      <svg {...iconProps}>
        <rect x="3" y="3" width="7" height="9" rx="1.5" />
        <rect x="14" y="3" width="7" height="5" rx="1.5" />
        <rect x="14" y="12" width="7" height="9" rx="1.5" />
        <rect x="3" y="16" width="7" height="5" rx="1.5" />
      </svg>
    ),
  },
  {
    href: "/dashboard/workouts",
    label: "Workouts",
    icon: (
      <svg {...iconProps}>
        <path d="M6.5 6.5v11M17.5 6.5v11M3 9.5v5M21 9.5v5M6.5 12h11" />
      </svg>
    ),
  },
  {
    href: "/dashboard/templates",
    label: "Templates",
    icon: (
      <svg {...iconProps}>
        <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4h13A1.5 1.5 0 0 1 20 5.5v13a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 18.5z" />
        <path d="M8 9h8M8 13h8M8 17h4" />
      </svg>
    ),
  },
  {
    href: "/dashboard/progress",
    label: "Progress",
    soon: true,
    icon: (
      <svg {...iconProps}>
        <path d="M3 20h18M6 16l4-5 3.5 3L18 8" />
      </svg>
    ),
  },
  {
    href: "/dashboard/settings",
    label: "Settings",
    soon: true,
    icon: (
      <svg {...iconProps}>
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-2.9 1.2v.2a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-3-1.2l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0-1.2-2.9H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.2-3l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 2.9-1.2V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 3 1.2l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0 1.2 2.9h.2a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.6 1z" />
      </svg>
    ),
  },
];
