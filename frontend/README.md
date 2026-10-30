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
| `src/components/` | `SalesChart`, `BalanceChart`, `Accuracy`, `Copilot`, `Offers`, `MerchantSearch`; shared UI in `ui.tsx` |
| `src/components/three/` | Optional 3D scenes, collapsed by default. Lazy-loaded; labels use `Label.tsx`, not drei `<Html>` (see below) |
| `src/App.tsx` | App shell: top bar, navigation rail / bottom bar, footer |
| `src/index.css`, `src/theme.ts` | Design tokens; light-first with `data-theme="dark"` |
| `public/fonts/` | Subset of Material Symbols Rounded, self-hosted so icons work offline |

## Design and conventions

Material Design 3, light-first. Follow the skill in [`.claude/skills/mfp-google-ux/SKILL.md`](../.claude/skills/mfp-google-ux/SKILL.md); Claude Code picks it up automatically.

- **Colours:** use tokens, never hard-coded values. Text on a `--*-soft` background uses the matching `--on-*-soft` token, which keeps 4.5:1 contrast.
- **Icons:** `<Icon name="…" />` only renders names in the font subset: `arrow_back, check, check_circle, chevron_right, close, cloud_off, dark_mode, error, expand_more, experiment, info, label, light_mode, monitoring, search, send, storefront, science, warning`. To add one, download a new subset from Google Fonts (`icon_names=` in alphabetical order) over `public/fonts/material-symbols-rounded.woff2`.
- **Passport loading:** each endpoint has its own `useAsync` and each section is wrapped in `<Slot>`, so a failure stays in that section. `join()` combines the endpoints a section needs. Unknown stores show one page-level state.
- **Copilot:** a floating 💬 button that opens a non-modal chat panel. It stays mounted while closed, so the conversation survives; it resets per store because `Passport` is keyed by id.
- **3D labels:** do not use drei `<Html>`. Its nested React roots threw an uncaught `removeChild` error whenever a scene was removed. Use `three/Label.tsx`.
- **Screenshots:** full-page capture can resize Recharts and draw charts tiny. Use a tall viewport instead.

## Checks

```bash
npm run build          # type-check + production build
npm run lint
```

UX rules (CLAUDE.md): Thai copy, every warning has a date and an amount, synthetic data carries
`ข้อมูลจำลอง` / `ตัวอย่าง`, the credit signal always says `ทดลอง`, and the words "อนุมัติ" / "approve"
never appear.
