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

export function Card({ title, badges, action, children }: {
  title?: ReactNode;
  badges?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="card">
      {(title || badges || action) && (
        <div className="card-head">
          {title && <h2>{title}</h2>}
          {badges}
          <span className="spacer" />
          {action}
        </div>
      )}
      {children}
    </section>
  );
}
