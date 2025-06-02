# app/routers/assinatura.py

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import RedirectResponse
import httpx, os, logging
from typing import List

router = APIRouter()
logging.basicConfig(level=logging.INFO)

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
MP_BASE_URL = "https://api.mercadopago.com"
VALOR_ASSINATURA = 59.90

URL_SUCESSO = "https://www.cedbrasilia.com.br/obrigado"
URL_WEBHOOK = "https://www.cedbrasilia.com.br/webhook/mp"

@router.post("/api/assinatura")
async def criar_assinatura(
    nome: str = Form(...),
    email: str = Form(...),
    whatsapp: str = Form(...),
    cursos: List[str] = Form(...)
):
    if not cursos:
        raise HTTPException(status_code=400, detail="Selecione ao menos um curso.")

    metadata = {
        "nome": nome,
        "email": email,
        "whatsapp": whatsapp,
        "cursos": ",".join(cursos)
    }

    payload = {
        "reason": f"Assinatura CED – Cursos: {', '.join(cursos)}",
        "auto_recurring": {
            "frequency": 1,
            "frequency_type": "months",
            "transaction_amount": VALOR_ASSINATURA,
            "currency_id": "BRL",
            "start_date": "2025-06-01T00:00:00.000-03:00",
            "end_date": "2026-06-01T00:00:00.000-03:00"
        },
        "payer_email": email,
        "back_url": URL_SUCESSO,
        "notification_url": URL_WEBHOOK,
        "metadata": metadata
    }

    headers = {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(http2=True, timeout=15) as client:
        resp = await client.post(f"{MP_BASE_URL}/preapproval", json=payload, headers=headers)

    if resp.status_code not in [200, 201]:
        logging.error(f"[ASSINATURA] Erro Mercado Pago: {resp.text}")
        raise HTTPException(status_code=500, detail="Erro ao criar assinatura.")

    assinatura = resp.json()
    link = assinatura.get("init_point") or assinatura.get("sandbox_init_point")

    if not link:
        raise HTTPException(status_code=500, detail="Link da assinatura não retornado pelo Mercado Pago.")

    return RedirectResponse(url=link)
