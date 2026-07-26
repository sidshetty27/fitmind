/**
 * Joins class names, dropping falsy entries.
 *
 * Deliberately not `clsx`/`tailwind-merge`: the only thing this codebase needs is
 * conditional concatenation, and the variant maps in `components/ui` are written
 * so no two entries set the same Tailwind property — there is nothing to merge.
 */
export function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}
