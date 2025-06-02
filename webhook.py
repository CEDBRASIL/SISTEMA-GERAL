"""
webhook.py
──────────
Recebe notificações de ASSINATURA (preapproval) do Mercado Pago
e conclui a matrícula automática:

1. Valida o token secreto (MP_WEBHOOK_SECRET) presente nos headers.
2. Consulta a assinatura via API Mercado Pago usando MP_ACCESS_TOKEN.
3. Prossegue somente se status == "authorized".
4. Busca pré-matrícula pendente pelo e-mail do pagador.
5. Finaliza matrícula, envia WhatsApp (ChatPro) e registra no Discord.

Variáveis de ambiente necessárias
──────────────────────────────────
MP_ACCESS_TOKEN
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

SECRET = os.getenv("MP_WEBHOOK_SECRET")              # token do painel MP
MP_TOKEN = os.getenv("MP_ACCESS_TOKEN")              # token privado produção
ARQ_PENDENTES = "pendentes.json"                     # gerado por pre_matricular.py


# ────────────────────────── utilidades de arquivo ──────────────────────────
def _load_pendentes() -> Dict[str, Dict]:
    if os.path.exists(ARQ_PENDENTES):
        with open(ARQ_PENDENTES, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_pendentes(data: Dict[str, Dict]):
    with open(ARQ_PENDENTES, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ───────────────────── consulta assinatura no Mercado Pago ─────────────────
def _consulta(pre_id: str) -> Dict:
    if not MP_TOKEN:
        raise RuntimeError("MP_ACCESS_TOKEN não configurado.")
    url = f"https://api.mercadopago.com/preapproval/{pre_id}"
    resp = requests.get(url, params={"access_token": MP_TOKEN}, timeout=20)
    resp.raise_for_status()
    return resp.json()


# ─────────────────── processamento de confirmação em segundo plano ──────────
def _processa(pre_id: str):
    try:
        assinatura = _consulta(pre_id)
    except Exception as err:
        print("❌ Falha consulta MP:", err)
        return

    if assinatura.get("status") != "authorized":
        print(f"ℹ️ Assinatura {pre_id} status={assinatura.get('status')}")
        return

    # e-mail pode vir em payer_email ou em payer.email
    email = (assinatura.get("payer_email")
             or assinatura.get("payer", {}).get("email", "")
             ).lower()

    if not email:
        print("❌ e-mail do pagador ausente.")
        return

    pend = _load_pendentes()
    ref = next((k for k, v in pend.items()
                if v.get("email", "").lower() == email), None)
    if not ref:
        print("⚠️ Nenhuma pré-matrícula para", email)
        return

    dados = pend.pop(ref)
    _save_pendentes(pend)          # remove pendente salva

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
        f"Curso: *{dados['curso']}*"
    )

    print("✅ Matrícula finalizada para", dados["nome"])


# ───────────────────────────── endpoint /webhook ───────────────────────────
@router.post("")        # prefixo /webhook + ""  ⇒  /webhook  (sem redirecionar)
async def receber_webhook(request: Request, background: BackgroundTasks):
    # 1. Validação do token secreto (se definido)
    if SECRET:
        sig = (request.headers.get("X-Hook-Secret")
               or request.headers.get("x-signature")
               or request.headers.get("x-hook-secret"))
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

    # 3. Processar em background para responder rápido ao MP
    background.add_task(_processa, pre_id)
    return {"status": "received", "id": pre_id}
