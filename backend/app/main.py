from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers import auth, reports, transactions, uploads

Base.metadata.create_all(bind=engine)

app = FastAPI(title="SpendSense", version="2.0.0")
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
