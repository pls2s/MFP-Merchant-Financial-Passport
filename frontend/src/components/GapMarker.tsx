import { money, thaiDateShort } from "../format";
import type { Gap } from "../types";

/**
 * Red callout for a day the cash may run short, drawn as a Recharts ReferenceLine label:
 * "⚠ 22 ก.ค. ขาด 7,945". `row` staggers callouts of nearby days; `flip` puts the pill on the
 * left of the line when the day is near the right edge of the chart.
 */
export function GapPill({ viewBox, gap, row, flip }: {
  viewBox?: { x: number; y: number };
  gap: Gap;
  row: number;
  flip: boolean;
}) {
  if (!viewBox) return null;
  const text = `⚠ ${thaiDateShort(gap.date)} ขาด ${money(gap.shortfall)}`;
  const width = text.length * 6.6 + 16;
  const height = 22;
  const x = flip ? viewBox.x - width - 4 : viewBox.x + 4;
  const y = viewBox.y + 2 + row * (height + 4);
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} rx={11} fill="var(--bad)" />
      <text x={x + width / 2} y={y + height / 2 + 4} textAnchor="middle" fill="#fff" fontSize={12} fontWeight={600}>
        {text}
      </text>
    </g>
  );
}
