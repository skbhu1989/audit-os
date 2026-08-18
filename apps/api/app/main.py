import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import init_pool, close_pool
from .routers import auth, clients, engagements, data_ingestion, analytics, reconciliation, working_papers, ai_assistant, risk_engine, compliance_calendar, caro, ifc, disclosure_checklist, reporting, data_centre, pre_audit_dashboard, bank_and_challan, ap_ar, month_end_close, exceptions, root_cause_and_queries, control_tower, fixed_assets_inventory, loans_investments, intercompany, integrations, universal_import, universal_reconciliation, finance_intelligence


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await close_pool()


app = FastAPI(title="AI Audit OS API", version="0.1.0-phase3", lifespan=lifespan)

# Missing entirely until this pass — in dev, the Vite proxy hides the gap
# (same-origin from the browser's perspective), but any real deployment
# with the frontend on a different origin than the API would have every
# single request blocked by the browser with no CORS headers at all.
# ALLOWED_ORIGINS is a comma-separated list; defaults to the Vite dev
# server origin so local `npm run dev` (without the proxy) still works.
_allowed_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _allowed_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(clients.router)
app.include_router(engagements.router)
app.include_router(data_ingestion.router)
app.include_router(analytics.router)
app.include_router(reconciliation.router)
app.include_router(working_papers.router)
app.include_router(ai_assistant.router)
app.include_router(risk_engine.router)
app.include_router(compliance_calendar.router)
app.include_router(caro.router)
app.include_router(ifc.router)
app.include_router(disclosure_checklist.router)
app.include_router(reporting.router)
app.include_router(data_centre.router)
app.include_router(pre_audit_dashboard.router)
app.include_router(bank_and_challan.router)
app.include_router(ap_ar.router)
app.include_router(month_end_close.router)
app.include_router(exceptions.router)
app.include_router(root_cause_and_queries.router)
app.include_router(control_tower.router)
app.include_router(fixed_assets_inventory.router)
app.include_router(loans_investments.router)
app.include_router(intercompany.router)
app.include_router(integrations.router)
app.include_router(universal_import.router)
app.include_router(universal_reconciliation.router)
app.include_router(finance_intelligence.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
