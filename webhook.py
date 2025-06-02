"""
webhook.py
──────────
Endpoint que recebe notificações de ASSINATURA (preapproval) do Mercado Pago.

• Confirma se o header contém o token secreto (MP_WEBHOOK_SECRET)
• Consulta a assinatura via API Mercado Pago:
    status == "authorized"  → pagamento inicial aprovado
• Remove matrícula do arquivo pendente, envia WhatsApp (ChatPro) e registra
  log no Discord.

Variáveis de ambiente necessárias
──────────────────────────────────
MP_ACCESS_TOKEN              # produção
MP_TEST_ACCESS_TOKEN      # sandbox
MP_WEBHOOK_SECRET            # token secreto gerado no painel Mercado Pago
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

# ──────────────────────────────────────────────────────────
# Configurações
# ──────────────────────────────────────────────────────────
SECRET = os.getenv("MP_WEBHOOK_SECRET")
ARQUIVO_JSON = "dados_pendentes.json"   # gerado por matricular.py


# ──────────────────────────────────────────────────────────
# Helpers de armazenamento local de matrículas
# ──────────────────────────────────────────────────────────
def _carregar_pendentes() -> Dict[str, Dict]:
    if os.path.exists(ARQUIVO_JSON):
        with open(ARQUIVO_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _salvar_pendentes(data: Dict[str, Dict]):
    with open(ARQUIVO_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ──────────────────────────────────────────────────────────
# Mercado Pago – consulta assinatura
# ──────────────────────────────────────────────────────────
def _consultar_assinatura(preapproval_id: str) -> Dict:
    """Consulta a API Mercado Pago e devolve o JSON da assinatura."""
    sandbox = preapproval_id.startswith("TEST-")
    token = os.getenv("MP_TEST_ACCESS_TOKEN") if sandbox else os.getenv("MP_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("Access-token do Mercado Pago não configurado.")

    url = f"https://api.mercadopago.com/preapproval/{preapproval_id}"
    resp = requests.get(url, params={"access_token": token}, timeout=20)
    resp.raise_for_status()
    return resp.json()


# ──────────────────────────────────────────────────────────
# Processamento em background
# ──────────────────────────────────────────────────────────
def _processar_preapproval(preapproval_id: str):
    try:
        assinatura = _consultar_assinatura(preapproval_id)
    except Exception as exc:
        print("❌ Falha ao consultar assinatura:", exc)
        return

    if assinatura.get("status") != "authorized":
        print(f"ℹ️ Assinatura {preapproval_id} não autorizada (status={assinatura.get('status')}).")
        return

    ref = str(assinatura.get("external_reference", "")).strip()
    if not ref:
        print("❌ external_reference ausente.")
        return

    pendentes = _carregar_pendentes()
    matricula = pendentes.pop(ref, None)
    if not matricula:
        print(f"⚠️ Matrícula {ref} não encontrada em pendentes.")
        return

    _salvar_pendentes(pendentes)  # remove a matrícula pendente

    # WhatsApp
    mensagem_wp = (
        f"🎉 Olá {matricula['nome']}, sua matrícula no curso {matricula['curso_nome']} "
        "foi confirmada! Bem-vindo(a) à CED."
    )
    send_whatsapp(matricula["whatsapp"], mensagem_wp)

    # Discord
    send_discord(
        f"✅ **Matrícula confirmada**\n"
        f"Aluno: **{matricula['nome']}**\n"
        f"Curso: *{matricula['curso_nome']}*\n"
        f"Ambiente: {'Sandbox' if preapproval_id.startswith('TEST-') else 'Produção'}"
    )

    print("✅ Matrícula finalizada para", matricula["nome"])


# ──────────────────────────────────────────────────────────
# Endpoint webhook  (ATENÇÃO: rota sem “/” final evita HTTP 307)
# ──────────────────────────────────────────────────────────
@router.post("")   # prefixo /webhook + "" = /webhook   (sem redirecionar)
async def receber_webhook(request: Request, background: BackgroundTasks):
    """
    Mercado Pago envia:
        • IPN (query: id=...&topic=preapproval)
        • Webhook JSON { "id": "...", "type": "subscription_preapproval", ... }
    """
    # ── 1. Validar token secreto ──
    if SECRET:
        header_secret = (
            request.headers.get("X-Hook-Secret")
            or request.headers.get("x-signature")
            or request.headers.get("x-hook-secret")
        )
        if header_secret != SECRET:
            raise HTTPException(status_code=401, detail="Webhook signature mismatch")

    # ── 2. Extrair preapproval_id ──
    preapproval_id = request.query_params.get("id") or ""
    if not preapproval_id:
        try:
            body = await request.json()
            preapproval_id = str(body.get("id", ""))
        except Exception:
            pass

    if not preapproval_id:
        raise HTTPException(status_code=400, detail="id não fornecido")

    # ── 3. Processar em background ──
    background.add_task(_processar_preapproval, preapproval_id)
    return {"status": "received", "id": preapproval_id}
