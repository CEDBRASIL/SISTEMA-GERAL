import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import cursos
import cursosom
import secure
import matricular
import alunos
import deletar
import kiwify
import asaas
import assinantes
import msgasaas
import cobrar
import bloquear
import login
import mensagemdecobranca
import site_page
from app import whatsapp


# ──────────────────────────────────────────────────────────
# Instância da aplicação FastAPI
# ──────────────────────────────────────────────────────────
app = FastAPI(
    title="API CED – Matrícula Automática",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# ──────────────────────────────────────────────────────────
# CORS – Domínios permitidos (ajustar via ORIGINS no .env)
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
# Registro dos roteadores
# ──────────────────────────────────────────────────────────
app.include_router(cursos.router,     prefix="/cursos",     tags=["Cursos"])
app.include_router(cursosom.router,   prefix="/cursosom",   tags=["Cursos OM"])
app.include_router(secure.router,                        tags=["Autenticação"])
app.include_router(matricular.router, prefix="/matricular", tags=["Matrícula"])
app.include_router(alunos.router,     prefix="/alunos",     tags=["Alunos"])
app.include_router(kiwify.router,     prefix="/kiwify", tags=["Kiwify"])
app.include_router(asaas.router,  tags=["Matrícula Assas"])
app.include_router(assinantes.router)
app.include_router(msgasaas.router)
app.include_router(cobrar.router)
app.include_router(deletar.router,    tags=["Excluir Aluno"])
app.include_router(bloquear.router,   tags=["Bloqueio"])
app.include_router(login.router,      prefix="/login",     tags=["Login"])
app.include_router(whatsapp.router)
app.include_router(mensagemdecobranca.router)
app.include_router(site_page.router)



# ──────────────────────────────────────────────────────────
# Health-check
# ──────────────────────────────────────────────────────────
@app.get("/", tags=["Status"])
def health():
    """Verifica se o serviço está operacional."""
    return {"status": "online", "version": app.version}

# ──────────────────────────────────────────────────────────
# Execução local / Render
# ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))  # Render define PORT dinamicamente
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
