/**
 * Turns anything thrown by the API client into something a form can render.
 *
 * FastAPI returns `detail` in two different shapes and a component should not
 * have to know which one it got:
 *
 *   HTTPException  ->  { "detail": "Workout not found" }
 *   422 validation ->  { "detail": [{ "loc": ["body","exercises",0,"sets"],
 *                                     "msg": "Input should be greater than 0" }] }
 *
 * `normalizeApiError` collapses both (plus network failures and non-Error
 * throwables) into one shape: a banner message, and a map of field path -> message
 * that inputs can look themselves up in.
 *
 * Field paths are dotted and have the leading `body`/`query` segment stripped, so
 * a nested exercise error keys as `exercises.0.sets` — see `exerciseFieldKey()`
 * for building that key from the UI side.
 */

import { ApiError } from "@/lib/api";

export interface NormalizedApiError {
  /** Banner-level message. Always present, even when fieldErrors is populated. */
  formError: string;
  /** Dotted field path -> first message for that field. */
  fieldErrors: Record<string, string>;
  /** HTTP status, when the failure reached the server at all. */
  status?: number;
  /**
   * Machine-readable reason, when the server sent a structured `detail`.
   *
   * Branch on this rather than on the message — copy gets reworded, and a UI
   * that decides whether to show an upgrade prompt by matching prose breaks the
   * first time someone improves the wording.
   *
   * The values, all from the coach's gate in `app/core/entitlements.py`:
   *
   *   free_tier_limit_reached  402 — this plan does not include another run.
   *                            The remedy is to upgrade.
   *   rate_limited             429 — too fast. Applies to premium as well, so
   *                            an upgrade prompt here would sell something
   *                            that does not fix it. The remedy is to wait.
   *   ai_capacity_reached      429 — the deployment is at its daily ceiling on
   *                            model calls. Everyone is refused; nothing the
   *                            user can do changes it.
   *
   * Only the first should ever produce an upgrade prompt. The two 429s carry a
   * `retry_after_seconds` in the detail, and the response a `Retry-After`.
   */
  code?: string;
}

/** A structured `detail` body: `{ code, message, ... }` rather than a string. */
interface StructuredDetail {
  code?: unknown;
  message?: unknown;
}

function isStructuredDetail(value: unknown): value is StructuredDetail {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** One entry of FastAPI's 422 `detail` array. */
interface ValidationItem {
  loc?: unknown;
  msg?: unknown;
}

function isValidationItem(value: unknown): value is ValidationItem {
  return typeof value === "object" && value !== null && "msg" in value;
}

/**
 * `["body", "exercises", 0, "sets"]` -> `"exercises.0.sets"`.
 *
 * The first segment is where the value came from (`body`, `query`, `path`), which
 * is noise to a form — every field it could highlight is in the body.
 */
function locToPath(loc: unknown): string {
  if (!Array.isArray(loc)) return "";
  const parts = loc.map(String);
  if (parts.length > 1 && ["body", "query", "path", "header"].includes(parts[0])) {
    parts.shift();
  }
  return parts.join(".");
}

/** True when the throwable is just a cancelled request, not a real failure. */
export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

export function normalizeApiError(error: unknown): NormalizedApiError {
  if (error instanceof ApiError) {
    const fieldErrors: Record<string, string> = {};

    // A third `detail` shape, alongside the string and the 422 array: an object
    // carrying a `code` and a human message. `api.ts` cannot turn that into
    // `error.message` — it only unwraps strings — so without this branch a
    // structured refusal surfaces as "Request to /api/... failed with status
    // 402", which tells the user nothing about what happened or what to do.
    if (isStructuredDetail(error.detail)) {
      const { code, message } = error.detail;
      return {
        formError:
          typeof message === "string" && message ? message : error.message,
        fieldErrors,
        status: error.status,
        code: typeof code === "string" ? code : undefined,
      };
    }

    if (Array.isArray(error.detail)) {
      for (const item of error.detail) {
        if (!isValidationItem(item)) continue;
        const path = locToPath(item.loc);
        const msg = typeof item.msg === "string" ? item.msg : "Invalid value";
        // First message wins: Pydantic can emit several per field and the first
        // is the one that actually failed.
        if (path && !(path in fieldErrors)) fieldErrors[path] = msg;
      }
    }

    const count = Object.keys(fieldErrors).length;
    const formError =
      count > 0
        ? `Please fix ${count} ${count === 1 ? "field" : "fields"} below.`
        : error.message;

    return { formError, fieldErrors, status: error.status };
  }

  // fetch() rejects with a TypeError when the server is unreachable or CORS
  // blocks the response — there is no status to report.
  if (error instanceof TypeError) {
    return {
      formError: "Could not reach the server. Check your connection and try again.",
      fieldErrors: {},
    };
  }

  return {
    formError: error instanceof Error ? error.message : "Something went wrong.",
    fieldErrors: {},
  };
}

/** Field key for the nth exercise's `field`, matching the server's `loc` path. */
export function exerciseFieldKey(index: number, field: string): string {
  return `exercises.${index}.${field}`;
}
