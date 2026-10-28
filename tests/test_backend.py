import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:  # runs the startup lifespan (loads data)
        yield c


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["merchants"] == 1115 and body["as_of"] == "2015-07-17"


def test_merchants_list_and_search(client):
    items = client.get("/api/v1/merchants").json()
    assert len(items) == 1115
    assert {m["merchant_id"] for m in items if m["is_demo"]} == {1, 25, 817}
    found = client.get("/api/v1/merchants", params={"q": "817"}).json()
    assert any(m["merchant_id"] == 817 for m in found)


def test_forecast_contract(client):
    body = client.get("/api/v1/merchants/1/forecast").json()
    assert body["merchant_id"] == 1 and body["horizon_days"] == 14
    point = body["points"][0]
    assert set(point) == {"date", "forecast", "lower", "upper", "actual"}
    assert set(body["metrics"]) == {"wape", "mae", "rmse"}


def test_unknown_merchant_is_404(client):
    assert client.get("/api/v1/merchants/999999/forecast").status_code == 404


def test_cash_flow_gaps_demo_store(client):
    body = client.get("/api/v1/merchants/1/cash-flow-gaps").json()
    assert body["is_synthetic_expense"] is True
    first = body["gaps"][0]
    assert first["date"] == "2015-07-22" and first["shortfall"] > 0
    amounts = [c["amount"] for c in first["contributors"]]
    assert amounts == sorted(amounts, reverse=True)


def test_min_buffer_never_reduces_gaps(client):
    base = client.get("/api/v1/merchants/2/cash-flow-gaps").json()["gaps"]
    buffered = client.get("/api/v1/merchants/2/cash-flow-gaps", params={"min_buffer": 1_000_000}).json()["gaps"]
    assert len(buffered) >= len(base) and len(buffered) >= 1
    assert client.get("/api/v1/merchants/2/cash-flow-gaps", params={"min_buffer": -1}).status_code == 422


def test_credit_signal_is_experimental(client):
    body = client.get("/api/v1/merchants/1/credit-signal").json()
    assert body["status"] == "experimental" and 0 <= body["score"] <= 100
    text = str(body).lower()
    assert "approve" not in text and "อนุมัติ" not in text


def test_copilot_falls_back_without_key(client, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "")
    body = client.post("/api/v1/merchants/1/copilot", json={"question": "ต้องระวังอะไร"}).json()
    assert body["source"] == "template"
    assert "22 ก.ค. 2558" in body["answer"]
    assert body["is_synthetic_expense"] is True
    assert client.post("/api/v1/merchants/1/copilot").status_code == 200  # body is optional


def test_model_results(client):
    rows = client.get("/api/v1/model-results").json()
    assert {r["model"] for r in rows} >= {"seasonal_naive", "lightgbm", "lstm", "gru", "ensemble"}
    assert {r["split"] for r in rows} == {"val", "test"}


def test_shortfall_risk_demo_store(client):
    body = client.get("/api/v1/merchants/1/shortfall-risk").json()
    assert body["is_synthetic_expense"] is True and len(body["days"]) == 14
    assert all(0 <= d["p_shortfall"] <= 1 for d in body["days"])
    assert body["p_any"] >= max(d["p_shortfall"] for d in body["days"])
    gap_day = client.get("/api/v1/merchants/1/cash-flow-gaps").json()["gaps"][0]["date"]
    assert next(d for d in body["days"] if d["date"] == gap_day)["p_shortfall"] > 0.5


def test_model_experiments(client):
    body = client.get("/api/v1/model-experiments").json()
    assert {r["model"] for r in body["seed_ensemble"]} == {"lightgbm", "lstm", "gru", "ensemble"}
    k5 = [r for r in body["seed_ensemble_k"] if r["k"] == 5]
    assert len(k5) == 4 and all(r["std"] is None for r in k5)
    assert {r["seed"] for r in body["seeds"]} == {42, 1, 2, 3, 4}
    curves = {p["config"] for p in body["learning_curves"]}
    assert set(body["chosen_configs"].values()) <= curves


def test_cors_allows_vite_dev_server(client):
    resp = client.options("/api/v1/merchants", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_sales_history_hides_future_sales_but_keeps_flags(client):
    body = client.get("/api/v1/merchants/1/sales-history", params={"days": 365}).json()
    pts = body["points"]
    assert body["as_of"] == "2015-07-17"
    assert pts[0]["date"] == "2014-07-18" and pts[-1]["date"] == "2015-07-31"
    past = [p for p in pts if p["date"] <= "2015-07-17"]
    future = [p for p in pts if p["date"] > "2015-07-17"]
    assert all(p["sales"] is None for p in future) and any(p["promo"] for p in future)
    assert all(p["sales"] == 0 for p in past if not p["open"])
    assert client.get("/api/v1/merchants/1/sales-history", params={"days": 1000}).status_code == 422


def test_cash_balance_matches_gaps(client):
    bal = client.get("/api/v1/merchants/1/cash-balance").json()
    gaps = client.get("/api/v1/merchants/1/cash-flow-gaps").json()
    assert bal["is_synthetic_expense"] is True
    by_date = {p["date"]: p for p in bal["points"]}
    first = gaps["gaps"][0]
    assert by_date[first["date"]]["balance"] == first["balance_after"]
    assert by_date[first["date"]]["is_forecast"] is True
    assert by_date["2015-07-17"]["is_forecast"] is False


def test_cash_balance_long_projection(client):
    bal = client.get("/api/v1/merchants/1/cash-balance").json()
    by_date = {p["date"]: p for p in bal["points"]}
    assert bal["points"][-1]["date"] == "2016-07-31"
    assert [by_date[d]["horizon"] for d in ("2015-07-17", "2015-07-18", "2015-08-01", "2015-10-10")] == \
        ["actual", "14d", "3m", "1y"]
    # the 14-day part is unchanged by the longer projection
    gaps = client.get("/api/v1/merchants/1/cash-flow-gaps").json()["gaps"]
    assert all(by_date[g["date"]]["balance"] == g["balance_after"] for g in gaps)
    assert all(g["date"] >= "2015-08-01" and g["horizon"] in ("3m", "1y") for g in bal["long_gaps"])


def test_long_forecast_has_84_days_and_real_backtest(client):
    body = client.get("/api/v1/merchants/1/long-forecast").json()
    pts = body["points"]
    assert len(pts) == 84 and pts[0]["date"] == "2015-07-18"
    assert all(p["lower"] <= p["forecast"] <= p["upper"] for p in pts)
    assert pts[-1]["synthetic_inputs"] and not pts[0]["synthetic_inputs"]
    # First 14 days equal the main 14-day forecast (same models, actual inputs).
    main = {p["date"]: p["forecast"] for p in client.get("/api/v1/merchants/1/forecast").json()["points"]}
    assert all(abs(p["forecast"] - main[p["date"]]) < 1 for p in pts[:14])
    bt = body["backtest"]
    assert bt["origin"] == "2015-05-08" and len(bt["points"]) == 84 and 0 < bt["wape_all_stores"] < 0.2


def test_seasonal_outlook_is_labelled_and_backtested(client):
    body = client.get("/api/v1/merchants/1/seasonal-outlook").json()
    assert body["is_model_forecast"] is False
    assert [m["month"] for m in body["months"]][:2] == ["2015-08", "2015-09"] and len(body["months"]) == 24
    assert [m["backtested"] for m in body["months"]] == [True] * 12 + [False] * 12
    assert all(m["lower"] <= m["outlook"] <= m["upper"] for m in body["months"] if m["outlook"] is not None)
    assert body["backtest"]["origin"] == "2014-07-31" and len(body["backtest"]["months"]) == 12


def test_synthetic_sales_are_separate_and_labelled(client):
    body = client.get("/api/v1/merchants/1/sales-history", params={"days": 30}).json()
    syn = body["synthetic"]
    assert syn["is_real"] is False and "จำลอง" in syn["label"]
    assert syn["points"][0]["date"] == "2015-08-01" and len(syn["points"]) == 366
    assert all(p["date"] <= "2015-07-31" for p in body["points"])  # real points never go past the data
    long = client.get("/api/v1/merchants/1/sales-history", params={"days": 30, "synthetic_days": 1096}).json()
    assert long["synthetic"]["points"][-1]["date"] == "2018-07-31"
