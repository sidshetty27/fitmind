import { Skeleton } from "@/components/ui/Skeleton";

export default function CoachLoading() {
  return (
    <div className="mx-auto w-full max-w-4xl">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Skeleton className="h-7 w-28" />
          <Skeleton className="mt-2 h-4 w-72" />
        </div>
        <Skeleton className="h-9 w-44" />
      </div>

      <div className="mt-6 rounded-2xl border border-zinc-800 bg-zinc-900/60 p-5">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="mt-4 h-16 w-full" />
        <div className="mt-5 space-y-2.5">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      </div>
    </div>
  );
}
