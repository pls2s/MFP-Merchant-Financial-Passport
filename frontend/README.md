# MFP frontend (React + Vite)

Dashboard for the Merchant Financial Passport. Spec: [`docs/frontend/requirements.md`](../docs/frontend/requirements.md).

## Run

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173
```

Environment variables are read from the **repository-root `.env`** (`envDir: '..'` in `vite.config.ts`);
only `VITE_*` variables reach the browser.

| Variable | Meaning |
| --- | --- |
| `VITE_USE_MOCK=true` | Read `src/mocks/*.json` — no backend needed (stores 1, 2, 25, 817 only) |
| `VITE_USE_MOCK=false` | Call the FastAPI backend (`uvicorn backend.app.main:app --port 8000`) |
| `VITE_API_BASE_URL` | Backend URL, default `http://localhost:8000` |

One-off override without editing `.env`: `VITE_USE_MOCK=false npm run dev`.

## Structure

| Path | Content |
| --- | --- |
| `src/api.ts` | Every API call (mock or real) |
| `src/types.ts` | Contract types (copy of `docs/frontend/api-types.ts`) |
| `src/mocks/` | Real API responses (`python -m backend.export_mocks`, then copy from `docs/frontend/mocks/`) |
| `src/format.ts` | Thai dates (พ.ศ.), amounts without currency unit, percentages |
| `src/pages/` | `MerchantPicker`, `Passport`, `ModelResults` |
| `src/components/` | `SalesChart`, `Copilot`, `Offers`, shared badges and states |

## Checks

```bash
npm run build          # type-check + production build
npm run lint
```

UX rules (CLAUDE.md): Thai copy, every warning has a date and an amount, synthetic data carries
`ข้อมูลจำลอง` / `ตัวอย่าง`, the credit signal always says `ทดลอง`, and the words "อนุมัติ" / "approve"
never appear.
