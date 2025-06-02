"""
webhook.py
──────────
Recebe notificações (webhooks/IPN) do Mercado Pago, confirma que a assinatura
(preapproval) está ATIVA e conclui a matrícula:

• Marca a matrícula como confirmada (remove do JSON pendentes)
• Envia WhatsApp de boas-vindas via ChatPro
• Registra o evento no Discord

Pré-requisitos:
  - Variáveis de ambiente:
        MP_ACCESS_TOKEN
        MP_ACCESS_TOKEN_SANDBOX
        CHATPRO_URL, CHATPRO_TOKEN
        DISCORD_WEBHOOK
  - Arquivo 'dados_pendentes.json' (gerado por matricular.py) na raiz
"""

import os
import json
import requests
from typing import Dict

from fastapi import APIRouter, Request, BackgroundTasks, HTTPException

from chatpro import send_whatsapp
from discord_log import send_discord

router = APIRouter()

# Arquivo onde matricular.py guarda pré-matrículas
ARQUIVO_JSON = "dados_pendentes.json"

# ──────────────────────────────────────────────────────────
# Helpers de armazenamento
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
# Consulta assinatura no Mercado Pago
# ──────────────────────────────────────────────────────────
def _consultar_assinatura(preapproval_id: str) -> Dict:
    """
    Consulta a assinatura no Mercado Pago usando o access_token correto
    (produção ou sandbox) e devolve o JSON.
    """
    is_sandbox = preapproval_id.startswith("TEST-")
    token = (
        os.getenv("MP_ACCESS_TOKEN_SANDBOX")
        if is_sandbox
        else os.getenv("MP_ACCESS_TOKEN")
    )

    if not token:
        raise RuntimeError("Access-token do Mercado Pago não configurado.")

    url = f"https://api.mercadopago.com/preapproval/{preapproval_id}"
    response = requests.get(url, params={"access_token": token}, timeout=20)
    response.raise_for_status()
    return response.json()


def _processar_confirmacao(preapproval_id: str):
    """Processa a confirmação em background."""
    try:
        assinatura = _consultar_assinatura(preapproval_id)
    except (requests.HTTPError, requests.RequestException) as exc:
        print("❌ Falha ao consultar assinatura:", exc)
        return

    # Verifica se já está autorizada
    if assinatura.get("status") != "authorized":
        print(f"📣 Assinatura {preapproval_id} ainda não autorizada (status={assinatura.get('status')}).")
        return

    ref = str(assinatura.get("external_reference", "")).strip()
    if not ref:
        print("❌ external_reference ausente; impossível correlacionar matrícula.")
        return

    pendentes = _carregar_pendentes()
    mat = pendentes.pop(ref, None)

    if not mat:
        print(f"⚠️ Matrícula pendente não encontrada para ref {ref}.")
        return

    # Atualiza armazenamento (remove pendente)
    _salvar_pendentes(pendentes)

    # Envia WhatsApp
    msg_wp = (
        f"🎉 Olá {mat['nome']}, sua matrícula no curso {mat['curso_nome']} foi confirmada!\n"
        "Em breve você receberá suas credenciais de acesso.\n"
        "Bem-vindo(a) à CED 🏆"
    )
    send_whatsapp(mat["whatsapp"], msg_wp)

    # Log no Discord
    send_discord(
        f"✅ **Matrícula confirmada**\n"
        f"Aluno: **{mat['nome']}**\n"
        f"Curso: *{mat['curso_nome']}*\n"
        f"Ambiente: {'Sandbox' if preapproval_id.startswith('TEST-') else 'Produção'}"
    )

    print("✅ Matrícula finalizada para", mat["nome"])


# ──────────────────────────────────────────────────────────
# Rota principal de webhook
# ──────────────────────────────────────────────────────────
@router.post("/")
async def receber_webhook(request: Request, background: BackgroundTasks):
    """
    Mercado Pago chama aqui quando a assinatura muda de status.

    Aceitamos:
        • body JSON → {"id": "...", "type": "preapproval", ...}
        • query-string   ?id=...&type=preapproval
    """
    preapproval_id: str = ""

    # Caso venha por query (IPN)
    if "id" in request.query_params:
        preapproval_id = request.query_params.get("id", "")

    # Caso venha JSON
    if not preapproval_id:
        try:
            body = await request.json()
            preapproval_id = str(body.get("id", ""))
        except Exception:
            body = {}
            # ignoramos se não for JSON

    if not preapproval_id:
        raise HTTPException(status_code=400, detail="preapproval_id não fornecido")

    # Processa em background para responder rápido ao MP
    background.add_task(_processar_confirmacao, preapproval_id)
    return {"status": "received", "id": preapproval_id}
