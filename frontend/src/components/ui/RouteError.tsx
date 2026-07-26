"use client";

import { useEffect } from "react";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";

/**
 * Shared body for every `error.tsx` in the app.
 *
 * Next.js 16 note: the retry prop is `unstable_retry`, not the old `reset`. Both
 * exist, but they do different things — `reset()` only clears the boundary and
 * re-renders children, while `unstable_retry()` re-fetches the segment on the
 * server. Every error we expect here is a failed fetch, so re-rendering the same
 * stale tree would just fail again; retry is the one that can actually recover.
 */
export function RouteError({
  error,
  retry,
  title = "Something went wrong",
}: {
  error: Error & { digest?: string };
  retry: () => void;
  title?: string;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="mx-auto w-full max-w-2xl py-10">
      <Alert title={title}>
        <p>{error.message || "An unexpected error occurred."}</p>
        {error.digest && (
          <p className="mt-2 font-mono text-[11px] opacity-70">
            Reference: {error.digest}
          </p>
        )}
      </Alert>
      <div className="mt-4 flex gap-3">
        <Button onClick={retry}>Try again</Button>
      </div>
    </div>
  );
}
