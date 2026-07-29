"use client";

import { RouteError } from "@/components/ui/RouteError";

export default function ProgressError({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  return (
    <RouteError error={error} retry={unstable_retry} title="Couldn't load progress" />
  );
}
