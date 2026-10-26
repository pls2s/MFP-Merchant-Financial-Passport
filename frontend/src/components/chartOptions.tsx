import type { ReactNode } from "react";
import { Swatch } from "./ui";

// Shared by the page filter bar, <SalesChart> and <BalanceChart>.

export const RANGES = [
  { key: "4w", label: "4 สัปดาห์", back: 28 },
  { key: "3m", label: "3 เดือน", back: 91 },
  { key: "1y", label: "1 ปี", back: 365 },
] as const;
export type RangeKey = (typeof RANGES)[number]["key"];

export type SalesLayer = "promo" | "holiday" | "pastGaps" | "laterActual" | "simulated";
export const SALES_LAYERS: readonly { key: SalesLayer; label: string; swatch: ReactNode }[] = [
  { key: "promo", label: "วันโปรโมชัน", swatch: <Swatch kind="area" color="var(--series-promo)" /> },
  { key: "holiday", label: "วันหยุดนักขัตฤกษ์", swatch: <Swatch kind="line" color="var(--text-3)" dashed /> },
  { key: "pastGaps", label: "วันที่เงินเคยไม่พอ", swatch: <Swatch kind="line" color="var(--warn)" dashed /> },
  { key: "laterActual", label: "ยอดจริงหลังวันนี้", swatch: <Swatch kind="line" color="var(--series-actual)" /> },
  { key: "simulated", label: "ยอดขายจำลอง", swatch: <Swatch kind="line" color="var(--series-simulated)" dashed /> },
];

export type BalanceLayer = "expenses" | "pastGaps" | "longGaps";
export const BALANCE_LAYERS: readonly { key: BalanceLayer; label: string; swatch: ReactNode }[] = [
  { key: "expenses", label: "รายจ่ายรายวัน", swatch: <Swatch kind="bar" color="var(--series-expense)" /> },
  { key: "pastGaps", label: "วันที่เงินเคยไม่พอ", swatch: <Swatch kind="line" color="var(--warn)" dashed /> },
  { key: "longGaps", label: "เงินอาจไม่พอหลัง 14 วัน", swatch: <Swatch kind="line" color="var(--bad)" dashed opacity={0.55} /> },
];
