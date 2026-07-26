import { Skeleton, SkeletonCard } from "@/components/ui/Skeleton";

/**
 * Streamed fallback while the dashboard's server fetch is in flight.
 *
 * Mirrors the real layout — four stat cards over a list — so the page settles
 * into place instead of jumping when the data lands.
 */
export default function DashboardLoading() {
  return (
    <div className="mx-auto w-full max-w-6xl">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <Skeleton className="h-7 w-64" />
          <Skeleton className="mt-2 h-4 w-48" />
        </div>
        <Skeleton className="h-11 w-36" />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <SkeletonCard key={i} />
        ))}
      </div>

      <div className="mt-8 rounded-2xl border border-zinc-800 bg-zinc-900/60 p-5">
        <Skeleton className="h-4 w-40" />
        <div className="mt-5 space-y-4">
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      </div>
    </div>
  );
}
