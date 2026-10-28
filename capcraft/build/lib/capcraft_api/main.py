"""CapCraft API. Run:  uvicorn capcraft_api.main:app --reload

CORS origins come from the CAPCRAFT_CORS environment variable (comma
separated). The default allows the Vite dev server."""
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, service
from .schemas import (DCFRequest, DCFResponse, Meta, PlanRequest, PlanResponse, SampleResponse,
                      WaccRequest, WaccResponse, XrayRequest, XrayResponse)

app = FastAPI(title="CapCraft API", version=__version__, description=service.DISCLAIMER)

origins = [o.strip() for o in os.environ.get("CAPCRAFT_CORS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
           if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["*"])


@app.exception_handler(ValueError)
async def value_error(_: Request, exc: ValueError):
    """The library explains bad inputs in plain words; pass that message on."""
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.get("/api/health")
def health():
    return {"status": "ok", "version": __version__}


@app.get("/api/meta", response_model=Meta)
def meta():
    return service.meta()


@app.post("/api/plan", response_model=PlanResponse)
def plan(req: PlanRequest):
    return service.plan(req)


@app.get("/api/xray/sample", response_model=SampleResponse)
def xray_sample():
    return service.sample()


@app.post("/api/xray", response_model=XrayResponse)
def xray(req: XrayRequest):
    return service.xray(req)


@app.post("/api/dcf", response_model=DCFResponse)
def dcf_endpoint(req: DCFRequest):
    return service.dcf_analysis(req)


@app.post("/api/wacc", response_model=WaccResponse)
def wacc(req: WaccRequest):
    return service.wacc(req)


# In production one process serves both: if the frontend has been built (web/dist),
# serve it from the same address. In development Vite serves it instead.
_dist = Path(__file__).resolve().parent.parent / "web" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="web")
