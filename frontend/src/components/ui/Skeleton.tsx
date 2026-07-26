import { cn } from "@/lib/cn";

/**
 * Shimmer placeholder for content that is still loading.
 *
 * Preferred over a centred spinner for lists and cards: it holds the layout at
 * roughly the right size, so the page does not jump when data lands.
 */
export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn("animate-pulse rounded-lg bg-zinc-800/70", className)}
    />
  );
}

/** A card-shaped skeleton — the repeating unit in workout and dashboard lists. */
export function SkeletonCard() {
  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900/60 p-5">
      <Skeleton className="h-4 w-1/3" />
      <Skeleton className="mt-3 h-3 w-1/2" />
      <Skeleton className="mt-5 h-3 w-2/3" />
    </div>
  );
}
