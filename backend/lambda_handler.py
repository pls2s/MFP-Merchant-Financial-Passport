"""AWS Lambda entry point for the API (Lambda `mfp-api` in infra/steps/2-api.tf).
Local runs use `uvicorn backend.app.main:app` and never import this."""

_handler = None


def handler(event, context):
    # Loading happens on the first request, not at import: Lambda gives the init phase only 10 s and
    # restarts it on timeout, while importing pandas, downloading the artifacts and loading them takes
    # longer. The first request runs under the function's 30 s timeout instead.
    global _handler
    if _handler is None:
        from mangum import Mangum

        from backend.app import main
        from backend.app.data import DataStore
        from backend.aws import fetch_artifacts

        fetch_artifacts()
        # Mangum runs FastAPI's lifespan on every invocation, which would reload every artifact per
        # request. Load once per container instead and leave lifespan off.
        main.store = DataStore.load()
        _handler = Mangum(main.app, lifespan="off")
    # The EventBridge warm-up ping (infra/steps/4-automation.tf) only needs the container loaded.
    if event.get("warmup"):
        return {"warm": True}
    return _handler(event, context)
