import { DashboardShell } from "@/components/dashboard/DashboardShell";

/**
 * Chrome for every `/dashboard/*` route (Phase 4).
 *
 * Presentation only — the auth guard stays in each page. Layouts do not re-run on
 * client-side navigation between sibling routes, so treating one as the security
 * boundary would let a stale layout vouch for a page it never checked. Each page
 * needs the session token to fetch its own data anyway, so the check is free
 * where it belongs.
 */
export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <DashboardShell>{children}</DashboardShell>;
}
