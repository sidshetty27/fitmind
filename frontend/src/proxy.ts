import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

/**
 * Route protection (Phase 2).
 *
 * Next.js 16 renamed the `middleware` file convention to `proxy` (runs on the
 * Node.js runtime). Clerk's `clerkMiddleware()` works unchanged here — only the
 * filename differs from older Next.js versions.
 *
 * We protect `/dashboard` (and anything under it) with an explicit check:
 * read the session and, if there's no `userId`, redirect to /sign-in. We do NOT
 * use `auth.protect()` because it currently mis-redirects to the current URL in
 * the Next.js 16 Node proxy runtime (clerk/javascript#8302).
 */
const isProtectedRoute = createRouteMatcher(["/dashboard(.*)"]);

export default clerkMiddleware(async (auth, req) => {
  if (isProtectedRoute(req)) {
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
  ],
};
