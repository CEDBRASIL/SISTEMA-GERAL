"""
webhook.py
──────────
Recebe notificações de ASSINATURA (preapproval) do Mercado Pago
e conclui a matrícula automática:

1. Valida token secreto (MP_WEBHOOK_SECRET) presente nos headers.
2. Consulta a assinatura via API Mercado Pago:
     • produção   → MP_ACCESS_TOKEN
     • sandbox    → MP_TEST_ACCESS_TOKEN
3. Aceita somente status "authorized".
4. Busca pré-matrícula pendente por e-mail.
5. Finaliza matrícula, envia WhatsApp (ChatPro) e registra no Discord.

Variáveis de ambiente usadas
────────────────────────────
MP_ACCESS_TOKEN
MP_TEST_ACCESS_TOKEN
MP_WEBHOOK_SECRET
CHATPRO_URL
CHATPRO_TOKEN
DISCORD_WEBHOOK
"""

import os
import json
from typing import Dict

import requests
from fastapi import APIRouter, Request, BackgroundTasks, HTTPException

from chatpro import send_whatsapp
from discord_log import send_discord

router = APIRouter()

# Token secreto gerado no painel Mercado Pago
SECRET = os.getenv("MP_WEBHOOK_SECRET")

# Arquivo onde pre_matricular.py armazena pendentes
ARQ_PENDENTES = "pendentes.json"


# ──────────────────────────────────────────────────────────
# Utilitários de armazenamento
# ──────────────────────────────────────────────────────────
def _load_pendentes() -> Dict[str, Dict]:
    if os.path.exists(ARQ_PENDENTES):
        with open(ARQ_PENDENTES, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_pendentes(data: Dict[str, Dict]):
    with open(ARQ_PENDENTES, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ──────────────────────────────────────────────────────────
# Consulta assinatura no Mercado Pago
# ──────────────────────────────────────────────────────────
def _consulta_assinatura(pre_id: str) -> Dict:
    """Retorna JSON da assinatura (preapproval) via Mercado Pago."""
    sandbox = pre_id.startswith("TEST-")
    token = (
        os.getenv("MP_TEST_ACCESS_TOKEN") if sandbox else os.getenv("MP_ACCESS_TOKEN")
    )
    if not token:
        raise RuntimeError("Access-token Mercado Pago não configurado.")

    url = f"https://api.mercadopago.com/preapproval/{pre_id}"
    resp = requests.get(url, params={"access_token": token}, timeout=20)
    resp.raise_for_status()
    return resp.json()


# ──────────────────────────────────────────────────────────
# Processamento em background
# ──────────────────────────────────────────────────────────
def _processa(pre_id: str):
    try:
        ass = _consulta_assinatura(pre_id)
    except Exception as err:
        print("❌ Falha consulta MP:", err)
        return

    if ass.get("status") != "authorized":
        print(f"ℹ️ Assinatura {pre_id} status={ass.get('status')}")
        return

    email = (ass.get("payer_email") or "").lower()
    if not email:
        print("❌ payer_email ausente.")
        return

    pend = _load_pendentes()
    ref = next((k for k, v in pend.items() if v.get("email", "").lower() == email), None)
    if not ref:
        print("⚠️ Nenhuma pré-matrícula para", email)
        return

    dados = pend.pop(ref)
    _save_pendentes(pend)  # remove pendente

    # WhatsApp
    send_whatsapp(
        dados["whatsapp"],
        f"🎉 Olá {dados['nome']}, sua matrícula no curso {dados['curso']} "
        "foi confirmada! Bem-vindo(a) à CED."
    )

    # Discord
    send_discord(
        f"✅ **Matrícula confirmada**\n"
        f"Aluno: **{dados['nome']}**\n"
        f"Curso: *{dados['curso']}*\n"
        f"Ambiente: {'Sandbox' if pre_id.startswith('TEST-') else 'Produção'}"
    )

    print("✅ Matrícula finalizada para", dados["nome"])


# ──────────────────────────────────────────────────────────
# Endpoint Webhook  (/webhook  — sem barra final para evitar 307)
# ──────────────────────────────────────────────────────────
@router.post("")   # prefixo /webhook + ""  →  /webhook
async def receber_webhook(request: Request, background: BackgroundTasks):
    """Recebe notificações de preapproval do Mercado Pago."""
    # 1. Validar token secreto
    if SECRET:
        sig = (
            request.headers.get("X-Hook-Secret")
            or request.headers.get("x-signature")
            or request.headers.get("x-hook-secret")
        )
        if sig != SECRET:
            raise HTTPException(status_code=401, detail="signature mismatch")

    # 2. Extrair preapproval_id
    pre_id = request.query_params.get("id") or ""
    if not pre_id:
        try:
            body = await request.json()
            pre_id = str(body.get("data", {}).get("id", ""))
        except Exception:
            pass

    if not pre_id:
        raise HTTPException(status_code=400, detail="id não informado")

    # 3. Processar em background
    background.add_task(_processa, pre_id)
    return {"status": "received", "id": pre_id}
