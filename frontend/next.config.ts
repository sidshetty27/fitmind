import type { NextConfig } from "next";
import { PHASE_PRODUCTION_BUILD } from "next/constants";

/**
 * Fail a production build that has no API origin (Phase 9).
 *
 * `NEXT_PUBLIC_API_URL` is inlined into the client bundle at build time, and
 * `lib/api.ts` falls back to `http://localhost:8000` without it. That fallback
 * is correct for `next dev` and catastrophic in a deployment: the build
 * succeeds, the deploy log is clean, the pages render — and every visitor's
 * browser calls port 8000 on their own machine. There is no error anywhere to
 * find; you discover it from the Network tab, if you think to look.
 *
 * A missing build input should stop the build, so it does. This runs on every
 * `next build` regardless of which modules the page graph happens to import,
 * which is why the check lives here rather than only in `lib/api.ts`.
 *
 * Deliberately gated on the build phase, not on `NODE_ENV`: `next start` and
 * `next dev` both load this file, and neither is the moment the value gets
 * baked in. Only the build is.
 *
 * Consequence worth knowing: `npm run build` now requires the variable. Locally
 * it comes from `.env.local`; in CI, `.github/workflows/ci.yml` passes an
 * explicit placeholder. A production build is a thing with inputs, and this is
 * one of them.
 */
function requireApiUrl(phase: string): void {
  if (phase !== PHASE_PRODUCTION_BUILD) return;
  if (process.env.NEXT_PUBLIC_API_URL) return;

  throw new Error(
    "NEXT_PUBLIC_API_URL is not set.\n\n" +
      "It is inlined into the client bundle at build time, so a build without " +
      "it produces an app that calls http://localhost:8000 in the visitor's " +
      "browser — succeeding at build time and failing for every user.\n\n" +
      "  Vercel:  Settings → Environment Variables → NEXT_PUBLIC_API_URL\n" +
      "           e.g. https://fitmind-api.onrender.com (no trailing slash)\n" +
      "  Local:   set it in frontend/.env.local\n\n" +
      "Setting it in the Vercel dashboard is not enough on its own: the value " +
      "is baked in at build time, so an existing deployment must be rebuilt.",
  );
}

/**
 * Response headers applied to every route (Phase 9).
 *
 * These are the ones that are correct without knowing anything about a
 * particular page, which is why they belong here rather than in a route. Set at
 * the framework rather than at Vercel so they survive `next start` anywhere —
 * a header that only exists in one host's dashboard is a header you lose the
 * day you move, and cannot test locally.
 *
 * Content-Security-Policy is deliberately NOT here; see the note below.
 */
const securityHeaders = [
  // Clickjacking. The app has no legitimate reason to be framed, and it has
  // buttons that spend money — an invisible overlay over "Upgrade" is the
  // attack this closes. Note this governs others framing us, not us framing
  // Clerk, so it does not affect sign-in.
  { key: "X-Frame-Options", value: "DENY" },

  // Stop the browser second-guessing our Content-Type. Without it a response
  // we serve as text can be re-interpreted as a script.
  { key: "X-Content-Type-Options", value: "nosniff" },

  // Send the full URL within our own origin, bare origin cross-origin. The
  // default is already this in modern browsers; stating it means the app does
  // not silently become more leaky under an older or differently-configured
  // one. It matters here because dashboard URLs contain workout and template
  // UUIDs, which have no business appearing in a third party's referer log.
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },

  // Nothing in FitMind uses these. Premium "form analysis from uploaded video"
  // is an upload, not a capture, so it needs no camera grant — revisit this
  // line, rather than deleting it, if that ever becomes live recording.
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), browsing-topics=()",
  },

  // Two years, subdomains included. Vercel already sends HSTS for its own
  // domains, so on the default deployment this is redundant — it is here for
  // the custom-domain and non-Vercel cases, where it is not.
  //
  // Worth understanding before changing: a browser that has seen this refuses
  // to talk to the origin over plain HTTP for the stated duration, and there is
  // no way to call that back early. That is the point, and it is also why the
  // max-age is not something to raise casually on a domain you might reuse.
  {
    key: "Strict-Transport-Security",
    value: "max-age=63072000; includeSubDomains",
  },
];

const nextConfig: NextConfig = {
  images: {
    // Clerk serves user avatars from this host. Next.js 16 requires external
    // image hosts to be allow-listed via `remotePatterns` (`domains` is deprecated).
    remotePatterns: [{ protocol: "https", hostname: "img.clerk.com" }],
  },

  // Drop `X-Powered-By: Next.js`. Version disclosure is not a vulnerability by
  // itself; it is free reconnaissance, and the header buys nothing back.
  poweredByHeader: false,

  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

/**
 * The function form of the config, so Next.js hands us the build phase. The
 * object itself is unchanged — `requireApiUrl` is the only reason this is not
 * still a plain `export default nextConfig`.
 */
const withBuildTimeChecks = (phase: string): NextConfig => {
  requireApiUrl(phase);
  return nextConfig;
};

export default withBuildTimeChecks;

/**
 * On the Content-Security-Policy that is not here.
 *
 * A real CSP for this app has to account for everything Clerk injects — its
 * Frontend API script, the worker it spawns, and the hosted account portal —
 * and Next.js needs a per-request nonce threaded through `proxy.ts` for its own
 * inline bootstrap. Both are documented and doable.
 *
 * The reason it is not in this commit is that a CSP is only ever proven correct
 * against a deployed instance: the directives depend on the production Clerk
 * domain, which does not exist yet, and the failure mode of getting it wrong is
 * a blank sign-in page for every user with nothing in the server logs. Shipping
 * one written from documentation and never loaded in a browser would be
 * asserting a security control this project has not actually tested.
 *
 * The honest state is therefore "not yet", tracked as an open item in
 * docs/phase-9-testing.md, to be added report-only first once there is a
 * production URL to point it at. The headers above are the subset that is
 * correct without that knowledge.
 */
