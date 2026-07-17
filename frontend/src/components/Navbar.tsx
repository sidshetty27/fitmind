"use client";

/**
 * Global navigation bar (Phase 2 — Authentication).
 *
 * This is a Client Component because it reads live auth state with Clerk's
 * React hooks/components:
 *  - <Show when="signed-out"> / <Show when="signed-in"> render their children
 *    only in that auth state. (Clerk v7 replaced the old <SignedIn>/<SignedOut>
 *    components with this single <Show> component.)
 *  - useUser() exposes the current user (name, avatar) once signed in.
 *  - <SignOutButton> wraps any element and ends the session on click.
 */

import Image from "next/image";
import Link from "next/link";
import { Show, SignOutButton, useUser } from "@clerk/nextjs";

export default function Navbar() {
  const { user } = useUser();

  const displayName =
    user?.fullName ?? user?.primaryEmailAddress?.emailAddress ?? "Athlete";

  return (
    <header className="flex items-center justify-between border-b border-zinc-800 bg-zinc-950/80 px-6 py-3 backdrop-blur">
      <Link href="/" className="flex items-center gap-2 text-zinc-100">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 text-sm font-bold">
          F
        </span>
        <span className="text-sm font-semibold tracking-tight">FitMind AI</span>
      </Link>

      <nav className="flex items-center gap-3 text-sm">
        <Show when="signed-out">
          <Link
            href="/sign-in"
            className="rounded-lg px-3 py-1.5 font-medium text-zinc-300 hover:text-white"
          >
            Sign in
          </Link>
          <Link
            href="/sign-up"
            className="rounded-lg bg-indigo-600 px-3 py-1.5 font-medium text-white hover:bg-indigo-500"
          >
            Sign up
          </Link>
        </Show>

        <Show when="signed-in">
          <Link
            href="/dashboard"
            className="hidden px-2 font-medium text-zinc-300 hover:text-white sm:block"
          >
            Dashboard
          </Link>

          <div className="flex items-center gap-2">
            {user?.imageUrl && (
              <Image
                src={user.imageUrl}
                alt={displayName}
                width={32}
                height={32}
                className="rounded-full border border-zinc-700"
              />
            )}
            <span className="hidden font-medium text-zinc-200 sm:inline">
              {displayName}
            </span>
          </div>

          <SignOutButton>
            <button
              type="button"
              className="rounded-lg border border-zinc-700 px-3 py-1.5 font-medium text-zinc-300 hover:border-zinc-500 hover:text-white"
            >
              Sign out
            </button>
          </SignOutButton>
        </Show>
      </nav>
    </header>
  );
}
