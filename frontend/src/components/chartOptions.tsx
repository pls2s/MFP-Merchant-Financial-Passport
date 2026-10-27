import type { ReactNode } from "react";
import { Swatch } from "./ui";

// Shared by the page filter bar, <SalesChart> and <BalanceChart>; MODELS by the model-results page.

// Colour follows the model, never its rank — hiding a model does not repaint the others.
export const MODELS = [
  { key: "seasonal_naive", label: "Seasonal naive", color: "var(--text-3)" },
  { key: "lightgbm", label: "LightGBM", color: "var(--series-lgbm)" },
  { key: "lstm", label: "LSTM", color: "var(--series-lstm)" },
  { key: "gru", label: "GRU", color: "var(--series-gru)" },
  { key: "ensemble", label: "LSTM+GRU 5 seed (โมเดลหลัก)", color: "var(--series-forecast)" },
] as const;
export type ModelKey = (typeof MODELS)[number]["key"];

export const RANGES = [
  { key: "4w", label: "4 สัปดาห์", back: 28 },
  { key: "3m", label: "3 เดือน", back: 91 },
  { key: "1y", label: "1 ปี", back: 365 },
] as const;
export type RangeKey = (typeof RANGES)[number]["key"];

export type SalesLayer = "promo" | "holiday" | "pastGaps" | "after";
export const SALES_LAYERS: readonly { key: SalesLayer; label: string; swatch: ReactNode }[] = [
  { key: "promo", label: "วันโปรโมชัน", swatch: <Swatch kind="area" color="var(--series-promo)" /> },
  { key: "holiday", label: "วันหยุดนักขัตฤกษ์", swatch: <Swatch kind="line" color="var(--text-3)" dashed /> },
  { key: "pastGaps", label: "วันที่เงินเคยไม่พอ", swatch: <Swatch kind="line" color="var(--warn)" dashed /> },
  // One toggle for both lines after today: real sales up to the data end, then synthetic (still labelled จำลอง).
  {
    key: "after", label: "ยอดขายหลังวันนี้ (จริง + จำลอง)",
    swatch: <><Swatch kind="line" color="var(--series-actual)" /><Swatch kind="line" color="var(--series-simulated)" dashed /></>,
  },
];

export type BalanceLayer = "expenses" | "pastGaps" | "longGaps";
export const BALANCE_LAYERS: readonly { key: BalanceLayer; label: string; swatch: ReactNode }[] = [
  { key: "expenses", label: "รายจ่ายรายวัน", swatch: <Swatch kind="bar" color="var(--series-expense)" /> },
  { key: "pastGaps", label: "วันที่เงินเคยไม่พอ", swatch: <Swatch kind="line" color="var(--warn)" dashed /> },
  { key: "longGaps", label: "เงินอาจไม่พอหลัง 14 วัน", swatch: <Swatch kind="line" color="var(--bad)" dashed opacity={0.55} /> },
];
