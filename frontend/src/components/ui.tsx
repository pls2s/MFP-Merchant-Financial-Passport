import { useRef, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { MockMissingError, NotFoundError } from "../api";

/** Material Symbols Rounded (self-hosted subset in public/fonts — add new names to that subset). */
export const Icon = ({ name, size = 20, filled = false }: { name: string; size?: number; filled?: boolean }) => (
  <span className="icon" aria-hidden style={{ fontSize: size, fontVariationSettings: `"FILL" ${filled ? 1 : 0}` }}>{name}</span>
);

/** Required on everything built from synthetic expenses (CLAUDE.md). */
export const SyntheticBadge = () => <span className="badge synthetic"><Icon name="science" size={14} />ข้อมูลจำลอง</span>;
/** Required on the credit signal (CLAUDE.md). */
export const ExperimentalBadge = () => <span className="badge experimental"><Icon name="experiment" size={14} />ทดลอง · ไม่ใช่คะแนนเครดิต</span>;
/** Required on mock product offers (CLAUDE.md). */
export const SampleBadge = () => <span className="badge synthetic"><Icon name="label" size={14} />ตัวอย่าง</span>;

export function Skeleton({ height = 120 }: { height?: number }) {
  return <div className="skeleton" style={{ height }} aria-label="กำลังโหลด" />;
}

export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  if (error instanceof NotFoundError) {
    return (
      <div className="state">
        <Icon name="error" size={40} />
        <p>ไม่พบร้านนี้</p>
        <Link className="btn tonal" to="/">กลับไปค้นหาร้าน</Link>
      </div>
    );
  }
  if (error instanceof MockMissingError) {
    return (
      <div className="state">
        <Icon name="info" size={40} />
        <p>ไม่มีข้อมูลตัวอย่างในโหมด mock</p>
        <div className="chips center">
          {[1, 2, 25, 817].map((id) => <Link key={id} className="btn chip" to={`/merchants/${id}`}>ร้าน {id}</Link>)}
        </div>
      </div>
    );
  }
  return (
    <div className="state">
      <Icon name="cloud_off" size={40} />
      <p>โหลดข้อมูลไม่สำเร็จ</p>
      {onRetry && <button className="btn tonal" onClick={onRetry}>ลองใหม่</button>}
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
          {value === o.key && <Icon name="check" size={16} />}
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Expand / collapse control for progressive disclosure. */
export function Disclosure({ open, onToggle, children }: { open: boolean; onToggle: () => void; children: ReactNode }) {
  return (
    <button className={`disclosure${open ? " open" : ""}`} aria-expanded={open} onClick={onToggle}>
      <Icon name="expand_more" />
      {children}
    </button>
  );
}

/** ⓘ button that opens a modal explanation. */
export function InfoDialog({ label, title, children }: { label: string; title: string; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  return (
    <>
      <button className="icon-btn" aria-label={label} title={label} onClick={() => ref.current?.showModal()}>
        <Icon name="info" />
      </button>
      <dialog ref={ref} className="dialog" onClick={(e) => { if (e.target === ref.current) ref.current?.close(); }}>
        <div className="dialog-body">
          <h2>{title}</h2>
          {children}
          <div className="dialog-actions">
            <button className="btn ghost" onClick={() => ref.current?.close()}>ปิด</button>
          </div>
        </div>
      </dialog>
    </>
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
            {on && <Icon name="check" size={16} />}
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

/** Legend entry that hides or shows its series. */
export function LegendChip({ on, onClick, children }: { on: boolean; onClick: () => void; children: ReactNode }) {
  return <button className="legend-chip" aria-pressed={on} onClick={onClick}>{children}</button>;
}

/** Legend swatches — mirror the mark (bar = rect, line = stroke, area = soft block). */
export const Swatch = ({ kind, color, dashed, opacity }: {
  kind: "bar" | "line" | "area"; color: string; dashed?: boolean; opacity?: number;
}) => (
  <i className={`swatch ${kind}${dashed ? " dashed" : ""}`} style={{ "--c": color, opacity } as React.CSSProperties} aria-hidden />
);
