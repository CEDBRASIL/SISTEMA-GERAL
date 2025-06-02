"""
main.py
───────
Ponto de entrada da API FastAPI da CED.

Inclui roteadores:
    • /cursos              → lista de cursos (cursos.py)
    • /api/auth            → autenticação (secure.py)
    • /api/matricular      → pré-matrícula + criação de assinatura (matricular.py)
    • /webhook             → confirmação Mercado Pago (webhook.py)

CORS aberto por padrão; ajuste a lista ORIGINS no .env se precisar restringir.
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import cursos
import secure
import matricular
import webhook
import pre_matricular

# ──────────────────────────────────────────────────────────
# Instância FastAPI
# ──────────────────────────────────────────────────────────
app = FastAPI(
    title="API CED – Matrícula Automática",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# ──────────────────────────────────────────────────────────
# CORS – libere apenas os domínios necessários em PROD
# Ex.: ORIGINS=https://www.cedbrasilia.com.br,https://ced-frontend.onrender.com
# ──────────────────────────────────────────────────────────
origins = [
    origin.strip()
    for origin in os.getenv("ORIGINS", "*").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────────────────
# Registrar roteadores
# ──────────────────────────────────────────────────────────
app.include_router(cursos.router,      prefix="/cursos",      tags=["Cursos"])
app.include_router(secure.router,      prefix="/api/auth",    tags=["Autenticação"])
app.include_router(matricular.router,  prefix="/api",         tags=["Matrícula"])
app.include_router(webhook.router,     prefix="/webhook",     tags=["Webhooks"])
app.include_router(pre_matricular.router, prefix="/api", tags=["Matrícula"])

# ──────────────────────────────────────────────────────────
# Health-check simples
# ──────────────────────────────────────────────────────────
@app.get("/", tags=["Status"])
def health():
    """Verifica se o serviço está operacional."""
    return {"status": "online", "version": app.version}
