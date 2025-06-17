# -*- coding: utf-8 -*-
"""Envio de link de fatura via WhatsApp para clientes ASAAS."""

import os
import logging
from datetime import date

import requests
from fastapi import APIRouter, HTTPException

from utils import formatar_numero_whatsapp

router = APIRouter(prefix="/msgasaas", tags=["Mensagem ASAAS"])

ASAAS_KEY = os.getenv("ASAAS_KEY")
ASAAS_BASE_URL = os.getenv("ASAAS_BASE_URL", "https://api.asaas.com/v3")
WHATSAPP_URL = "https://whatsapptest-stij.onrender.com/send"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _headers() -> dict:
    if not ASAAS_KEY:
        raise HTTPException(500, "ASAAS_KEY não configurada")
    return {"Content-Type": "application/json", "access_token": ASAAS_KEY}


def _criar_fatura(customer_id: str, valor: float, descricao: str) -> str:
    payload = {
        "customer": customer_id,
        "billingType": os.getenv("ASAAS_BILLING_TYPE", "UNDEFINED"),
        "value": valor,
        "description": descricao,
        "dueDate": date.today().isoformat(),
    }
    try:
        r = requests.post(
            f"{ASAAS_BASE_URL}/payments",
            json=payload,
            headers=_headers(),
            timeout=10,
        )
    except requests.RequestException as e:
        raise HTTPException(502, f"Erro de conexão: {e}")

    if not r.ok:
        raise HTTPException(r.status_code, r.text)

    data = r.json()
    return (
        data.get("invoiceUrl")
        or data.get("bankSlipUrl")
        or data.get("transactionReceiptUrl")
    )


def _enviar_whatsapp(nome: str, phone: str, url: str) -> None:
    mensagem = (
        f"👋 Olá {nome}!\n\n"
        f"Segue o link para pagamento do seu curso: {url}\n\n"
        "Qualquer dúvida estamos à disposição."
    )
    try:
        r = requests.get(
            WHATSAPP_URL,
            params={"para": formatar_numero_whatsapp(phone), "mensagem": mensagem},
            timeout=10,
        )
        r.raise_for_status()
        logger.info("Mensagem enviada para %s", phone)
    except Exception:
        logger.exception("Erro ao enviar mensagem via WhatsApp")


@router.post("")
def enviar_link_fatura(dados: dict):
    """Envia a fatura via WhatsApp. Cria a cobrança se necessário."""
    nome = dados.get("nome")
    phone = dados.get("whatsapp") or dados.get("phone")
    fatura_url = dados.get("fatura_url") or dados.get("invoice_url")
    customer_id = dados.get("customer") or dados.get("customer_id")
    valor = dados.get("valor")
    descricao = dados.get("descricao") or dados.get("curso") or "Curso"

    if not nome or not phone:
        raise HTTPException(400, "'nome' e 'phone' são obrigatórios")

    if not fatura_url:
        if not customer_id or not valor:
            raise HTTPException(400, "Campos para criação de fatura ausentes")
        fatura_url = _criar_fatura(customer_id, valor, descricao)
        if not fatura_url:
            raise HTTPException(500, "Falha ao criar fatura")

    _enviar_whatsapp(nome, phone, fatura_url)
    return {"status": "ok", "fatura_url": fatura_url}

