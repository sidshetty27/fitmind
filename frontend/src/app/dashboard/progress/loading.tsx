import { Skeleton } from "@/components/ui/Skeleton";

/**
 * Placeholders mirror the real layout's boxes — four tiles, two charts, a table —
 * so the page does not jump when the data lands.
 */
export default function ProgressLoading() {
  return (
    <div className="mx-auto w-full max-w-6xl">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <Skeleton className="h-7 w-32" />
          <Skeleton className="mt-2 h-4 w-44" />
        </div>
        <Skeleton className="h-8 w-40" />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-24 w-full" />
        ))}
      </div>

      <div className="mt-8 grid grid-cols-1 gap-4 xl:grid-cols-2">
        {Array.from({ length: 2 }, (_, i) => (
          <Skeleton key={i} className="h-72 w-full" />
        ))}
      </div>

      <Skeleton className="mt-8 h-64 w-full" />
    </div>
  );
}
