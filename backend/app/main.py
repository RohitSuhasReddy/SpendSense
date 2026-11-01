from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import Base, engine
from app.routers import auth, reports, transactions, uploads
from app.services.llm_transport import install_resilient_llm_transport

install_resilient_llm_transport()
Base.metadata.create_all(bind=engine)


def _migrate_legacy_categories() -> None:
    """Keep existing local data compatible with the cleaner category names."""
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE transactions SET category='Travel' WHERE category='Travel & Transport'")
        )
        connection.execute(
            text("UPDATE merchant_mappings SET category='Travel' WHERE category='Travel & Transport'")
        )


_migrate_legacy_categories()

app = FastAPI(title="SpendSense", version="2.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(uploads.router)
app.include_router(transactions.router)
app.include_router(reports.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "SpendSense"}
