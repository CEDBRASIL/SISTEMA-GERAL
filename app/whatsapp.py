import os
import logging
import phonenumbers
from fastapi import APIRouter, HTTPException, BackgroundTasks
from utils import fix_whatsapp_number
from pydantic import BaseModel

try:
    from wppconnect import WppConnect
except Exception:  # pragma: no cover - lib opcional
    WppConnect = None

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])

# ─── sessão global ─────────────────────────────────
if WppConnect:
    wpp = WppConnect(session="default", token=os.getenv("WA_TOKEN"))
    STATUS = {"state": "loading", "qr": None}  # loading | ready
else:  # biblioteca ausente
    wpp = None
    STATUS = {"state": "disabled", "qr": None}

if wpp:

    @wpp.onQRCode
    def on_qr(base64_qr, *_):
        STATUS.update(state="loading", qr=base64_qr)

    @wpp.onReady
    def on_ready():
        STATUS.update(state="ready", qr=None)


# ─── modelos ────────────────────────────────
class Msg(BaseModel):
    numero: str
    mensagem: str


# ─── rotas ──────────────────────────────────
@router.get("/qr")
def qr():
    """Retorna QR em base64; 'disabled' se lib ausente."""
    return STATUS


@router.post("")
async def send(msg: Msg, bg: BackgroundTasks):
    if not wpp:
        raise HTTPException(501, "Biblioteca wppconnect indisponível")

    # Normaliza e valida o número no padrão brasileiro
    numero_e164 = fix_whatsapp_number(msg.numero, e164=True)
    try:
        p = phonenumbers.parse(numero_e164, None)
        if not phonenumbers.is_valid_number(p):
            raise ValueError()
    except Exception:
        raise HTTPException(
            422, "Número inválido (use formato 61999999999 ou +5561999999999)"
        )
    if STATUS["state"] != "ready":
        raise HTTPException(503, "Sessão WhatsApp ainda não conectada")

    chat_id = numero_e164.lstrip("+") + "@c.us"

    def _worker():
        try:
            wpp.sendMessage(chat_id, msg.mensagem)
        except Exception:
            logging.exception("Erro ao enviar mensagem via WPP")

    bg.add_task(_worker)
    return {"success": True}
