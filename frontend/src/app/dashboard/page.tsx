import { currentUser } from "@clerk/nextjs/server";

/**
 * Protected dashboard (Phase 2).
 *
 * `src/proxy.ts` guarantees only signed-in users reach this route, but we also
 * read the user server-side here: this is where real product data will hang off
 * the authenticated user in later phases. `currentUser()` runs on the server and
 * never exposes secrets to the client.
 */
export default async function DashboardPage() {
  const user = await currentUser();
  const name = user?.firstName ?? "Athlete";

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
