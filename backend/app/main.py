from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db import init_db
from app.routers import auth, usage, billing, invoices, payments

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB indexes on startup
    init_db()
    yield

app = FastAPI(
    title="MeterMind AI API",
    description="Usage-based AI billing platform with PayPal integration",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(usage.router)
app.include_router(billing.router)
app.include_router(invoices.router)
app.include_router(payments.router)

@app.get("/", tags=["Health"])
def root():
    return {
        "status": "online",
        "service": "MeterMind AI Backend",
        "docs": "/docs"
    }

@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok"}
