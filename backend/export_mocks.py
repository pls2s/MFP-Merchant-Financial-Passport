"""Export mock JSON for the frontend from the real API responses.

Usage:
    python -m backend.export_mocks

Writes docs/frontend/mocks/*.json — copy them into frontend/src/mocks/. The copilot
mock uses the template answer (no API key needed), so it is reproducible.
"""

import json
import os

from fastapi.testclient import TestClient

from ai.cashflow_forecast.preprocess import ROOT
from backend.app.main import app

MOCKS_DIR = ROOT / "docs" / "frontend" / "mocks"
# Demo stores with a gap (1, 25, 817) and one ordinary store without a gap (2).
MERCHANTS = (1, 2, 25, 817)


def main() -> None:
    os.environ["LLM_API_KEY"] = ""  # template copilot answer, deterministic
    MOCKS_DIR.mkdir(parents=True, exist_ok=True)
    with TestClient(app) as client:
        files = {
            "merchants.json": client.get("/api/v1/merchants").json(),
            "model-results.json": client.get("/api/v1/model-results").json(),
        }
        for m in MERCHANTS:
            base = f"/api/v1/merchants/{m}"
            files[f"forecast-{m}.json"] = client.get(f"{base}/forecast").json()
            files[f"sales-history-{m}.json"] = client.get(f"{base}/sales-history", params={"days": 365}).json()
            files[f"cash-balance-{m}.json"] = client.get(f"{base}/cash-balance").json()
            files[f"long-forecast-{m}.json"] = client.get(f"{base}/long-forecast").json()
            files[f"seasonal-outlook-{m}.json"] = client.get(f"{base}/seasonal-outlook").json()
            files[f"cash-flow-gaps-{m}.json"] = client.get(f"{base}/cash-flow-gaps").json()
            files[f"credit-signal-{m}.json"] = client.get(f"{base}/credit-signal").json()
            files[f"copilot-{m}.json"] = client.post(f"{base}/copilot", json={"question": None}).json()
    for name, body in files.items():
        (MOCKS_DIR / name).write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n")
    print(f"Saved {len(files)} mocks → {MOCKS_DIR}")


if __name__ == "__main__":
    main()
