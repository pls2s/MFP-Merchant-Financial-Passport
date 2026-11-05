"""AWS Lambda entry point for the API (Lambda `api` in infra/template.yaml).
Local runs use `uvicorn backend.app.main:app` and never import this."""

from mangum import Mangum

from backend.app import main
from backend.app.data import DataStore
from backend.aws import fetch_artifacts

fetch_artifacts()

# Mangum runs FastAPI's lifespan on every invocation, which would reload every artifact per request.
# Load once per container instead and leave lifespan off.
main.store = DataStore.load()
handler = Mangum(main.app, lifespan="off")
