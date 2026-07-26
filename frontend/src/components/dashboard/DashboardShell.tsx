"use client";

import { useEffect, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { SidebarNav } from "@/components/dashboard/Sidebar";

/**
 * The dashboard chrome: a fixed sidebar on large screens, an off-canvas drawer
 * below that, and the content region.
 *
 * This is a Client Component because the drawer needs open/closed state, but
 * `children` is still rendered on the server — it arrives as an already-rendered
 * RSC payload, so pages inside the shell stay Server Components and none of their
 * code ships to the browser.
 */
export function DashboardShell({ children }: { children: ReactNode }) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const pathname = usePathname();
  const [lastPathname, setLastPathname] = useState(pathname);

  // Close the drawer whenever the route changes, so it never sits open over the
  // page the user just navigated to.
  //
  // Adjusted during render rather than in an effect: React's documented pattern
  // for "reset state when a value changes". An effect would re-render a second
  // time after painting the stale open drawer, which is both a visible flash and
  // what the react-hooks/set-state-in-effect rule exists to prevent. The link
  // handler also closes it — this covers browser back/forward, where no link is
  // clicked at all.
  if (pathname !== lastPathname) {
    setLastPathname(pathname);
    setDrawerOpen(false);
  }

  // Escape closes the drawer — expected of anything modal.
  useEffect(() => {
    if (!drawerOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDrawerOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [drawerOpen]);

  return (
    <div className="flex flex-1 bg-zinc-950 text-zinc-100">
      {/* Desktop rail. `sticky` under the global navbar, which is 57px tall. */}
      <aside className="sticky top-0 hidden h-[calc(100vh-57px)] w-60 shrink-0 border-r border-zinc-800 bg-zinc-950 p-4 lg:block">
        <SidebarNav />
      </aside>

      {/* Mobile drawer + scrim. Rendered only when open so it cannot trap focus
          or intercept clicks while hidden. */}
      {drawerOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            onClick={() => setDrawerOpen(false)}
            className="absolute inset-0 h-full w-full bg-black/60 backdrop-blur-sm"
          />
          <aside
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
            className="absolute inset-y-0 left-0 w-64 border-r border-zinc-800 bg-zinc-950 p-4 shadow-2xl"
          >
            <SidebarNav onNavigate={() => setDrawerOpen(false)} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Drawer trigger. Only exists below `lg`, where the rail is hidden. */}
        <div className="flex items-center gap-3 border-b border-zinc-800 px-4 py-2.5 lg:hidden">
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            aria-label="Open navigation"
            aria-expanded={drawerOpen}
            className="rounded-lg p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
          >
            <svg
              className="h-5 w-5"
              fill="none"
              stroke="currentColor"
              strokeWidth={1.75}
              strokeLinecap="round"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <span className="text-sm font-medium text-zinc-400">Menu</span>
        </div>

        <main className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}
