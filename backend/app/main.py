from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(
    title="Divepoint API",
    version="0.1.0",
    description="Data-first scaffold. Product endpoints are explicitly unimplemented.",
)


@app.get("/health")
def health():
    return {"status": "ok", "stage": "scaffold"}


def pending():
    return JSONResponse(
        status_code=501,
        content={"detail": "Not implemented: no verified dive data is available yet."},
    )


app.add_api_route("/v1/dives/plan", pending, methods=["POST"], tags=["dives"])
app.add_api_route("/v1/dives/{dive_id}", pending, methods=["GET"], tags=["dives"])
app.add_api_route("/v1/species/{aphia_id}", pending, methods=["GET"], tags=["species"])
app.add_api_route("/v1/dives/{dive_id}/ask", pending, methods=["POST"], tags=["guide"])
app.add_api_route("/v1/logbook", pending, methods=["GET", "POST"], tags=["logbook"])
