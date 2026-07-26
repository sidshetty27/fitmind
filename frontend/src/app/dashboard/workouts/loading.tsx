import { Skeleton } from "@/components/ui/Skeleton";

export default function WorkoutsLoading() {
  return (
    <div className="mx-auto w-full max-w-4xl">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <Skeleton className="h-7 w-40" />
          <Skeleton className="mt-2 h-4 w-52" />
        </div>
        <Skeleton className="h-11 w-36" />
      </div>

      <Skeleton className="mt-8 h-3 w-28" />
      <div className="mt-3 rounded-2xl border border-zinc-800 bg-zinc-900/60 p-4">
        <div className="space-y-4">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-11 w-full" />
          ))}
        </div>
      </div>
    </div>
  );
}
