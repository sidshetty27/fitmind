/**
 * A single-series trend line for the exercise small multiples.
 *
 * SVG here rather than boxes because this mark is a path — but it holds **no text**,
 * so uniform scaling is harmless and the component stays fully responsive without
 * measuring anything. The 2px stroke is pinned with `non-scaling-stroke` so the line
 * keeps its weight at every rendered width instead of thickening with the viewBox.
 *
 * One series, so no legend: the caption above each chart names the movement. The
 * latest point wears the end marker and the only direct label, which the caller
 * places in HTML beside the chart rather than inside the drawing.
 */

// Drawing space. Padding keeps the end marker and its surface ring clear of the
// edges — a dot clipped by its own viewBox is the classic SVG chart bug.
const WIDTH = 320;
const HEIGHT = 72;
const PAD_X = 6;
const PAD_Y = 8;

export function Sparkline({
  values,
  labels,
  accent = "#6366f1",
  /** Chart surface, for the 2px ring that keeps markers legible over the line. */
  surface = "#18181b",
}: {
  values: number[];
  /** One per value, for the point tooltips. Same length as `values`. */
  labels: string[];
  accent?: string;
  surface?: string;
}) {
  if (values.length === 0) return null;

  const min = Math.min(...values);
  const max = Math.max(...values);
  // A flat series has no range to divide by. Draw it down the middle rather than
  // dividing by zero or exaggerating noise into a full-height swing.
  const span = max - min || 1;
  const flat = max === min;

  const x = (index: number) =>
    values.length === 1
      ? WIDTH / 2
      : PAD_X + (index / (values.length - 1)) * (WIDTH - PAD_X * 2);
  const y = (value: number) =>
    flat
      ? HEIGHT / 2
      : HEIGHT - PAD_Y - ((value - min) / span) * (HEIGHT - PAD_Y * 2);

  const points = values.map((value, index) => ({ x: x(index), y: y(value), value }));
  const line = points.map((p) => `${p.x},${p.y}`).join(" ");
  const lastIndex = points.length - 1;
  const last = points[lastIndex];

  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      className="h-auto w-full"
      role="img"
      aria-label={`Trend across ${values.length} ${
        values.length === 1 ? "session" : "sessions"
      }, ending at ${values[lastIndex]}.`}
    >
      {points.length > 1 && (
        <>
          {/* A wash, not a block — the line carries the reading, the fill only
              anchors it to the baseline. */}
          <polygon
            points={`${PAD_X},${HEIGHT} ${line} ${WIDTH - PAD_X},${HEIGHT}`}
            fill={accent}
            opacity={0.1}
          />
          <polyline
            points={line}
            fill="none"
            stroke={accent}
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
        </>
      )}

      {points.map((point, index) => (
        <circle
          key={index}
          cx={point.x}
          cy={point.y}
          // The latest session is the one being read; earlier points stay small so
          // they do not compete with it, but keep a hit target worth hovering.
          r={index === lastIndex ? 4.5 : 3}
          fill={accent}
          stroke={surface}
          strokeWidth={2}
          opacity={index === lastIndex ? 1 : 0.55}
        >
          <title>{labels[index]}</title>
        </circle>
      ))}

      {/* Keeps the end marker legible where it would otherwise sit under the line. */}
      <circle cx={last.x} cy={last.y} r={4.5} fill={accent} stroke={surface} strokeWidth={2}>
        <title>{labels[lastIndex]}</title>
      </circle>
    </svg>
  );
}
