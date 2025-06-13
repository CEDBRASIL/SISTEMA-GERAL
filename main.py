import os
import re
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from wppconnect import WppConnect

import cursos
import cursosom
import secure
import matricular
import alunos
import deletar
import kiwify
import matricularasaas
import bloquear
import login


# ──────────────────────────────────────────────────────────
# Instância da aplicação FastAPI
# ──────────────────────────────────────────────────────────
app = FastAPI(
    title="CED Brasil WhatsApp API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# ──────────────────────────────────────────────────────────
# CORS – Domínio permitido (definido via ALLOWED_ORIGIN no .env)
# ──────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("ALLOWED_ORIGIN", "*")],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Inicia sessão com o WhatsApp ──────────────────────────
wpp = WppConnect(session="default", token=os.getenv("WA_TOKEN"))
status = {"qr": None, "state": "loading"}  # loading | ready


@wpp.onQRCode
def on_qr(base64_qr, ascii_qr, attempts):
    status["qr"] = base64_qr
    status["state"] = "loading"


@wpp.onReady
def on_ready():
    status["qr"] = None
    status["state"] = "ready"


class MsgBody(BaseModel):
    numero: str
    mensagem: str


REGEX_E164 = re.compile(r"^\+\d{10,15}$")


@app.get("/qr")
async def get_qr():
    return {"qr": status["qr"], "status": status["state"]}


@app.post("/send")
async def send_message(body: MsgBody):
    if not REGEX_E164.match(body.numero):
        raise HTTPException(status_code=422, detail="Número fora do padrão E.164")
    try:
        msg_id = await wpp.sendMessage(body.numero, body.mensagem)
        return {"success": True, "id": msg_id}
    except Exception as e:
        logging.exception("Erro ao enviar mensagem")
        raise HTTPException(500, str(e))

# ──────────────────────────────────────────────────────────
# Registro dos roteadores
# ──────────────────────────────────────────────────────────
app.include_router(cursos.router,     prefix="/cursos",     tags=["Cursos"])
app.include_router(cursosom.router,   prefix="/cursosom",   tags=["Cursos OM"])
app.include_router(secure.router,                        tags=["Autenticação"])
app.include_router(matricular.router, prefix="/matricular", tags=["Matrícula"])
app.include_router(alunos.router,     prefix="/alunos",     tags=["Alunos"])
app.include_router(kiwify.router,     prefix="/kiwify", tags=["Kiwify"])
app.include_router(matricularasaas.router,  tags=["Matrícula Assas"])
app.include_router(deletar.router,    tags=["Excluir Aluno"])
app.include_router(bloquear.router,   tags=["Bloqueio"])
app.include_router(login.router,      prefix="/login",     tags=["Login"])



# ──────────────────────────────────────────────────────────
# Health-check
# ──────────────────────────────────────────────────────────
@app.get("/", tags=["Status"])
def health_root():
    """Verifica se o serviço está operacional."""
    return {"status": "online", "version": app.version}


@app.get("/health")
async def health():
    return {"ok": True}

# ──────────────────────────────────────────────────────────
# Execução local / Render
# ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
