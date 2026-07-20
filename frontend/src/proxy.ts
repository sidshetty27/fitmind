import { clerkMiddleware } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

/**
 * Route protection (Phase 2) — the UX layer of a defense-in-depth setup.
 *
 * Next.js 16 renamed the `middleware` file convention to `proxy` (runs on the
 * Node.js runtime). Clerk's `clerkMiddleware()` works unchanged here — only the
 * filename differs from older Next.js versions.
 *
 * We bounce unauthenticated visitors off `/dashboard` before it renders. Two
 * deliberate choices:
 *  - A plain `pathname.startsWith` check instead of Clerk's `createRouteMatcher`,
 *    which is deprecated (Clerk now steers auth checks toward the resource).
 *  - A manual `auth()` + redirect instead of `auth.protect()`, which currently
 *    mis-redirects to the current URL in the Next.js 16 Node proxy runtime
 *    (clerk/javascript#8302).
 *
 * The authoritative check lives in the page itself (see app/dashboard/page.tsx):
 * this proxy is convenience/UX, not the sole guard.
 */
export default clerkMiddleware(async (auth, req) => {
  if (req.nextUrl.pathname.startsWith("/dashboard")) {
    const { userId } = await auth();
    if (!userId) {
      const signInUrl = new URL("/sign-in", req.url);
      // Remember where the user was headed so we can send them back after login.
      signInUrl.searchParams.set("redirect_url", req.url);
      return NextResponse.redirect(signInUrl);
    }
  }
});

export const config = {
  matcher: [
    // Run on everything except Next.js internals and static asset file types...
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    // ...and always run on API/tRPC routes.
    "/(api|trpc)(.*)",
    // Clerk routes its Frontend API through this path — proxy must cover it.
    "/__clerk/:path*",
  ],
};
