"""
main.py
───────
Ponto de entrada da API FastAPI da CED.

Inclui roteadores:
    • /cursos             → lista de cursos (cursos.py)
    • /api/auth           → autenticação (secure.py)
    • /api                → matrícula (matricular.py)
    • /api/webhook        → webhooks (webhook.py)
    • /cadastrar          → cadastro/matrícula OM e ChatPro (cadastrar.py)

CORS aberto por padrão; ajuste a lista ORIGINS no .env se precisar restringir.
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import cursos
import secure
import matricular
import alunos

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
app.include_router(cursos.router,          prefix="/cursos",      tags=["Cursos"])
app.include_router(secure.router,          tags=["Autenticação"])
app.include_router(matricular.router,  prefix="/matricular",  tags=["Matrícula"])
app.include_router(alunos.router,       prefix="/alunos",     tags=["Alunos"])





# ──────────────────────────────────────────────────────────
# Health-check simples
# ──────────────────────────────────────────────────────────
@app.get("/", tags=["Status"])
def health():
    """Verifica se o serviço está operacional."""
    return {"status": "online", "version": app.version}
