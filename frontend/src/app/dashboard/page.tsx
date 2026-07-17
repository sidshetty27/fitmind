import { currentUser } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";

/**
 * Protected dashboard (Phase 2).
 *
 * This page is the authoritative auth guard (Clerk's recommended resource-level
 * check): if there's no signed-in user we redirect, so the route is safe even if
 * the proxy matcher ever diverges. `currentUser()` runs on the server and never
 * exposes secrets to the client. Real product data will hang off this user in
 * later phases.
 */
export default async function DashboardPage() {
  const user = await currentUser();
  if (!user) {
    redirect("/sign-in?redirect_url=/dashboard");
  }

  const name = user.firstName ?? "Athlete";

  return (
    <main className="flex flex-1 flex-col items-center justify-center bg-zinc-950 px-6 py-16 text-zinc-100">
      <div className="w-full max-w-lg rounded-2xl border border-zinc-800 bg-zinc-900/60 p-8 shadow-xl backdrop-blur">
        <p className="text-xs uppercase tracking-wide text-indigo-400">
          Protected route
        </p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">
          Welcome back, {name}.
        </h1>
        <p className="mt-3 text-sm text-zinc-400">
          You&apos;re signed in. This page is only reachable with a valid session —
          try opening it in a private window to see the redirect to sign-in.
        </p>
      </div>
    </main>
  );
}
