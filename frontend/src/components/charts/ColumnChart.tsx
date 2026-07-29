import { cn } from "@/lib/cn";

/**
 * A weekly column chart, rendered without a charting library and without client
 * JavaScript — it is plain layout, so it works inside a Server Component and adds
 * nothing to the bundle.
 *
 * Columns are elements rather than SVG on purpose: a `viewBox` scales its own text
 * with the drawing, so a responsive SVG chart either distorts labels or needs JS to
 * measure. Boxes reflow natively at every width, which is the whole requirement.
 *
 * Marks follow the house spec: columns capped at 24px with a 4px rounded cap and a
 * square baseline, a 2px surface gap doing the separating (never a stroke), hairline
 * solid gridlines a step off the surface, and exactly one direct label — on the peak.
 * Every other value is reachable from the axis, the per-column tooltip, and the table
 * view, so nothing is gated behind a hover.
 */

export interface Column {
  /** Axis label. Kept short — this is the only text under the mark. */
  label: string;
  /** The period spelled out, e.g. "Week of Jul 6". Names the row and the tooltip. */
  title: string;
  value: number;
}

const ACCENTS = {
  // Both validated against the dark chart surface: in the lightness band, above
  // the chroma floor, >= 3:1 contrast, and separated for every CVD type.
  indigo: { fill: "bg-indigo-500", text: "text-indigo-300" },
  emerald: { fill: "bg-emerald-600", text: "text-emerald-300" },
} as const;

export type ChartAccent = keyof typeof ACCENTS;

/** Round a maximum up to a clean 1 / 2 / 5 x 10^n so axis ticks read as round numbers. */
export function niceMax(value: number): number {
  if (value <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const normalised = value / magnitude;
  const step = normalised <= 1 ? 1 : normalised <= 2 ? 2 : normalised <= 5 ? 5 : 10;
  return step * magnitude;
}

export function ColumnChart({
  columns,
  accent = "indigo",
  format = (n) => n.toLocaleString(),
  unit,
  height = 200,
  integer = false,
}: {
  columns: Column[];
  accent?: ChartAccent;
  format?: (value: number) => string;
  /** Appended to the peak label and the axis, e.g. "kg". */
  unit?: string;
  height?: number;
  /**
   * For counts. Forces the scale to an even number so the midpoint tick is a whole
   * one — an axis reading "2.5 sessions" describes something that cannot happen.
   */
  integer?: boolean;
}) {
  const palette = ACCENTS[accent];
  const peak = Math.max(...columns.map((c) => c.value), 0);
  const top = integer ? Math.max(2, Math.ceil(peak / 2) * 2) : niceMax(peak);
  // Index rather than value: several weeks can share the peak, and labelling all of
  // them would be the "number on every point" failure. The first one carries it.
  const peakIndex = peak > 0 ? columns.findIndex((c) => c.value === peak) : -1;

  const ticks = [top, top / 2, 0];
  // Composed here rather than passed in, so the value is written once. Building it
  // at the call site is what let the table print "Week of Jul 6 — 18,686 kg" in the
  // period column and then "18,686 kg" again in the value column.
  const show = (value: number) => `${format(value)}${unit ?? ""}`;

  return (
    <figure className="m-0">
      <div className="flex gap-3">
        {/* Axis ticks carry every value the single direct label does not. */}
        <div
          className="flex w-12 shrink-0 flex-col justify-between text-right text-[10px] tabular-nums text-zinc-600"
          style={{ height }}
          aria-hidden="true"
        >
          {ticks.map((tick) => (
            <span key={tick} className="-translate-y-1/2 first:translate-y-0 last:-translate-y-full">
              {format(tick)}
            </span>
          ))}
        </div>

        <div className="min-w-0 flex-1">
          <div className="relative" style={{ height }}>
            {/* Hairline, solid, one step off the surface — recessive by construction. */}
            {ticks.map((tick) => (
              <div
                key={tick}
                className="absolute inset-x-0 border-t border-zinc-800"
                style={{ bottom: `${(tick / top) * 100}%` }}
                aria-hidden="true"
              />
            ))}

            {/* gap-0.5 is the 2px surface gap: neighbours read apart because of the
                air between them, not because of a border drawn around each. */}
            <ol className="absolute inset-0 flex items-end gap-0.5">
              {columns.map((column, index) => {
                const ratio = top > 0 ? column.value / top : 0;
                return (
                  <li
                    key={column.label}
                    className="group relative flex h-full min-w-0 flex-1 flex-col justify-end"
                  >
                    {index === peakIndex && (
                      // Absolutely positioned and nowrap so a value wider than its
                      // own column overhangs into the surrounding air instead of
                      // being clipped to "19,11…". A truncated number is worse than
                      // no number — the axis and the table still carry the value.
                      <span
                        className={cn(
                          "pointer-events-none absolute left-1/2 -translate-x-1/2 whitespace-nowrap text-[10px] font-medium tabular-nums",
                          palette.text,
                        )}
                        style={{ bottom: `calc(${ratio * 100}% + 4px)` }}
                      >
                        {format(column.value)}
                        {unit}
                      </span>
                    )}
                    <div
                      title={`${column.title} — ${show(column.value)}`}
                      className={cn(
                        "mx-auto w-full max-w-[24px] rounded-t-[4px] transition-opacity",
                        column.value > 0
                          ? cn(palette.fill, "group-hover:opacity-80")
                          : // A logged-nothing week is data, not a gap. A faint track
                            // says "zero here" where an absent bar would say "unknown".
                            "bg-zinc-800",
                      )}
                      style={{
                        height: column.value > 0 ? `max(2px, ${ratio * 100}%)` : "2px",
                      }}
                    />
                  </li>
                );
              })}
            </ol>
          </div>

          <ol className="mt-2 flex gap-0.5">
            {columns.map((column) => (
              <li
                key={column.label}
                className="min-w-0 flex-1 truncate text-center text-[10px] text-zinc-600"
              >
                {column.label}
              </li>
            ))}
          </ol>
        </div>
      </div>

      <ChartTable
        caption="Every value in this chart, as a table."
        rows={columns.map((c) => [c.title, show(c.value)])}
      />
    </figure>
  );
}

/**
 * The table view every chart carries. A native `<details>` — no JavaScript, so it
 * survives in a Server Component and with scripting off, which is exactly the
 * situation where a canvas-based chart leaves a reader with nothing.
 */
export function ChartTable({
  rows,
  caption,
  headers = ["Period", "Value"],
}: {
  rows: [string, string][];
  caption: string;
  headers?: [string, string];
}) {
  return (
    <details className="mt-4 group">
      <summary className="cursor-pointer text-xs text-zinc-500 hover:text-zinc-300">
        View as table
      </summary>
      <div className="mt-2 max-h-64 overflow-auto rounded-lg border border-zinc-800">
        <table className="w-full text-left text-xs">
          <caption className="sr-only">{caption}</caption>
          <thead className="sticky top-0 bg-zinc-900 text-zinc-500">
            <tr>
              <th scope="col" className="px-3 py-2 font-medium">
                {headers[0]}
              </th>
              <th scope="col" className="px-3 py-2 text-right font-medium">
                {headers[1]}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/70">
            {rows.map(([label, value]) => (
              <tr key={label}>
                <td className="px-3 py-1.5 text-zinc-400">{label}</td>
                <td className="px-3 py-1.5 text-right tabular-nums text-zinc-200">
                  {value}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
