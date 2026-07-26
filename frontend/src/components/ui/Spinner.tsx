import { cn } from "@/lib/cn";

const SIZES = {
  sm: "h-4 w-4 border-2",
  md: "h-6 w-6 border-2",
  lg: "h-10 w-10 border-[3px]",
} as const;

/**
 * Indeterminate loading indicator.
 *
 * `border-current` means it inherits the text colour of whatever contains it, so
 * the same component works inside a filled button and on a dark page background.
 */
export function Spinner({
  size = "md",
  className,
  label = "Loading",
}: {
  size?: keyof typeof SIZES;
  className?: string;
  label?: string;
}) {
  return (
    <span
      role="status"
      aria-label={label}
      className={cn(
        "inline-block animate-spin rounded-full border-current border-r-transparent align-[-0.125em]",
        SIZES[size],
        className,
      )}
    />
  );
}
