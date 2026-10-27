import type { ReactNode } from "react";
import { MockMissingError, NotFoundError } from "../api";

/** Required on everything built from synthetic expenses (CLAUDE.md). */
export const SyntheticBadge = () => <span className="badge synthetic">ข้อมูลจำลอง</span>;
/** Required on the credit signal (CLAUDE.md). */
export const ExperimentalBadge = () => <span className="badge experimental">ทดลอง · ไม่ใช่คะแนนเครดิต</span>;
/** Required on mock product offers (CLAUDE.md). */
export const SampleBadge = () => <span className="badge">ตัวอย่าง</span>;

export function Skeleton({ height = 120 }: { height?: number }) {
  return <div className="skeleton" style={{ height }} aria-label="กำลังโหลด" />;
}

export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  let message = "โหลดข้อมูลไม่สำเร็จ";
  if (error instanceof NotFoundError) message = "ไม่พบร้านนี้";
  if (error instanceof MockMissingError) message = "ไม่มีข้อมูลตัวอย่างในโหมด mock (มีเฉพาะร้าน 1, 2, 25, 817)";
  return (
    <div className="state">
      <p>{message}</p>
      {onRetry && !(error instanceof NotFoundError) && !(error instanceof MockMissingError) && (
        <button className="btn" onClick={onRetry}>ลองใหม่</button>
      )}
    </div>
  );
}

export function Card({ title, badges, action, id, eyebrow, children, className = "" }: {
  title?: ReactNode;
  badges?: ReactNode;
  action?: ReactNode;
  id?: string;
  eyebrow?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className}`} id={id}>
      {(title || badges || action) && (
        <div className="card-head">
          <div className="card-title">
            {eyebrow && <div className="eyebrow">{eyebrow}</div>}
            {title && <h2>{title}</h2>}
          </div>
          {badges}
          <span className="spacer" />
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

/** Single choice (range, split, metric). */
export function Segmented<K extends string>({ options, value, onChange, label }: {
  options: readonly { key: K; label: ReactNode }[];
  value: K;
  onChange: (k: K) => void;
  label: string;
}) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button key={o.key} role="radio" aria-checked={value === o.key} className={value === o.key ? "on" : ""}
          onClick={() => onChange(o.key)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Multi choice — chart layers, model visibility. Each chip carries its legend swatch. */
export function ChipGroup<K extends string>({ options, value, onChange, label }: {
  options: readonly { key: K; label: ReactNode; swatch?: ReactNode; disabled?: boolean }[];
  value: ReadonlySet<K>;
  onChange: (next: Set<K>) => void;
  label: string;
}) {
  return (
    <div className="chip-group" role="group" aria-label={label}>
      {options.map((o) => {
        const on = value.has(o.key);
        return (
          <button key={o.key} className={`chip${on ? " on" : ""}`} aria-pressed={on} disabled={o.disabled}
            onClick={() => {
              const next = new Set(value);
              if (on) next.delete(o.key);
              else next.add(o.key);
              onChange(next);
            }}>
            <span className="chip-check" aria-hidden>{on ? "✓" : "+"}</span>
            {o.swatch}
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

export type ViewMode = "chart" | "table";

export function ViewToggle({ value, onChange }: { value: ViewMode; onChange: (v: ViewMode) => void }) {
  return (
    <Segmented label="รูปแบบการแสดงผล" value={value} onChange={onChange}
      options={[{ key: "chart", label: "กราฟ" }, { key: "table", label: "ตาราง" }]} />
  );
}

/** Table twin of a chart: every value the chart shows is readable without hovering. */
export function DataTable({ columns, rows, highlight }: {
  columns: { key: string; label: string; align?: "left" | "right" }[];
  rows: Record<string, ReactNode>[];
  highlight?: (i: number) => "bad" | "warn" | "muted" | undefined;
}) {
  return (
    <div className="table-wrap scroll">
      <table>
        <thead>
          <tr>{columns.map((c) => <th key={c.key} className={c.align === "left" ? "left" : ""}>{c.label}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className={highlight?.(i) ?? ""}>
              {columns.map((c) => <td key={c.key} className={c.align === "left" ? "left" : "num"}>{r[c.key] ?? "—"}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Legend swatches — mirror the mark (bar = rect, line = stroke, area = soft block). */
export const Swatch = ({ kind, color, dashed, opacity }: {
  kind: "bar" | "line" | "area"; color: string; dashed?: boolean; opacity?: number;
}) => (
  <i className={`swatch ${kind}${dashed ? " dashed" : ""}`} style={{ "--c": color, opacity } as React.CSSProperties} aria-hidden />
);
