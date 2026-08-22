import type { NextConfig } from "next";

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

export default nextConfig;

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
