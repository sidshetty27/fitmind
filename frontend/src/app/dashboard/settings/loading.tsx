import { Skeleton } from "@/components/ui/Skeleton";

export default function SettingsLoading() {
  return (
    <div className="mx-auto w-full max-w-3xl">
      <div>
        <Skeleton className="h-7 w-28" />
        <Skeleton className="mt-2 h-4 w-80" />
      </div>

      <div className="mt-6 rounded-2xl border border-zinc-800 bg-zinc-900/60 p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <Skeleton className="h-4 w-16" />
            <Skeleton className="mt-2 h-3 w-56" />
          </div>
          <Skeleton className="h-6 w-16 rounded-full" />
        </div>
        <Skeleton className="mt-5 h-4 w-64" />
        <Skeleton className="mt-4 h-16 w-full rounded-xl" />
        <Skeleton className="mt-5 h-9 w-44" />
      </div>
    </div>
  );
}
