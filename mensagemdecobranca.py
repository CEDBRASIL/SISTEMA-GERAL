# -*- coding: utf-8 -*-
"""Envio automatizado de mensagens de cobrança.

Este módulo consulta os pagamentos pendentes no ASAAS e envia
lembretes via WhatsApp quando faltam 7 dias, 1 dia ou no dia do
vencimento da fatura.
"""

import logging
import os
from datetime import date, datetime

import requests
from fastapi import APIRouter, HTTPException

from utils import formatar_numero_whatsapp

router = APIRouter(prefix="/mensagem-cobranca", tags=["Cobrança"])

ASAAS_KEY = os.getenv("ASAAS_KEY")
ASAAS_BASE_URL = os.getenv("ASAAS_BASE_URL", "https://api.asaas.com/v3")
WHATSAPP_URL = "https://whatsapptest-stij.onrender.com/send"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


CACHE_CLIENTES: dict[str, tuple[str | None, str | None]] = {}


def _headers() -> dict:
    if not ASAAS_KEY:
        raise HTTPException(500, "ASAAS_KEY não configurada")
    return {"Content-Type": "application/json", "access_token": ASAAS_KEY}


def _obter_cliente(cid: str) -> tuple[str | None, str | None]:
    if cid in CACHE_CLIENTES:
        return CACHE_CLIENTES[cid]
    try:
        resp = requests.get(
            f"{ASAAS_BASE_URL}/customers/{cid}", headers=_headers(), timeout=10
        )
        if resp.ok:
            data = resp.json()
            nome = data.get("name")
            telefone = data.get("mobilePhone") or data.get("phone")
            CACHE_CLIENTES[cid] = (nome, telefone)
            return nome, telefone
    except requests.RequestException as e:
        logger.exception("Erro ao obter cliente %s: %s", cid, e)
    return None, None


def _enviar_whatsapp(numero: str, mensagem: str) -> None:
    if not numero:
        return
    try:
        r = requests.get(
            WHATSAPP_URL,
            params={"para": formatar_numero_whatsapp(numero), "mensagem": mensagem},
            timeout=10,
        )
        r.raise_for_status()
        logger.info("Mensagem enviada para %s", numero)
    except Exception:
        logger.exception("Erro ao enviar WhatsApp para %s", numero)


def _listar_pagamentos_pendentes() -> list[dict]:
    pagamentos: list[dict] = []
    offset = 0
    limit = 100
    while True:
        try:
            resp = requests.get(
                f"{ASAAS_BASE_URL}/payments",
                params={"status": "PENDING", "limit": limit, "offset": offset},
                headers=_headers(),
                timeout=10,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise HTTPException(502, f"Erro ao listar pagamentos: {e}")
        data = resp.json()
        pagamentos.extend(data.get("data") or [])
        if data.get("hasMore"):
            offset += limit
        else:
            break
    return pagamentos


_DEF_MSG = (
    "\u26a0\ufe0f Pagamento da Assinatura Pendente \u26a0\ufe0f\n\n"
    "Olá, {nome}, tudo bem?\n\n"
    "Referente ao seu pagamento Assinatura dos Cursos  \ud83d\udcb3\n\n"
    "\ud83d\udea8 Valor pendente: R$ {valor}\n"
    "\ud83d\udcc5 Data de vencimento: {vencimento}\n\n"
    "Este pagamento é essencial para a continuidade dos nossos serviços."
    " Pedimos que regularize a situação o quanto antes para evitar a suspensão do seu acesso. \u23f3\n\n"
    "\ud83d\udd17 Clique aqui para realizar o pagamento agora: {link}\n\n"
    "Se precisar de mais informações, estamos à disposição! \ud83d\udcac"
)

_DEF_MSG_AMANHA = _DEF_MSG.replace(
    "Data de vencimento:", "Vence amanh\u00e3:")

_MSG_HOJE = (
    "\u26a0\ufe0f Cobran\u00e7a Pendente \u26a0\ufe0f\n\n"
    "Olá, {nome}, tudo bem?\n\n"
    "Notamos que o seu pagamento referente a Assinatura dos Cursos ainda não foi realizado. \ud83d\udcb3\n\n"
    "\ud83d\udea8 Valor pendente: R$ {valor}\n"
    "\ud83d\udcc5 Data de vencimento: {vencimento}\n\n"
    "Este pagamento é essencial para a continuidade dos nossos serviços."
    " Pedimos que regularize a situação o quanto antes para evitar a suspensão do seu acesso. \u23f3\n\n"
    "\ud83d\udd17 Clique aqui para realizar o pagamento agora: {link}\n\n"
    "Se precisar de mais informações, estamos à disposição! \ud83d\udcac"
)


def _montar_mensagem(dias: int, nome: str, valor: float, vencimento: str, link: str) -> str:
    valor_fmt = f"{valor:.2f}".replace(".", ",")
    if dias == 7:
        return _DEF_MSG.format(nome=nome, valor=valor_fmt, vencimento=vencimento, link=link)
    if dias == 1:
        return _DEF_MSG_AMANHA.format(nome=nome, valor=valor_fmt, vencimento=vencimento, link=link)
    return _MSG_HOJE.format(nome=nome, valor=valor_fmt, vencimento=vencimento, link=link)


@router.post("")
def enviar_mensagens():
    """Envia mensagens de cobrança conforme a proximidade do vencimento."""
    hoje = date.today()
    enviados = []
    for pagamento in _listar_pagamentos_pendentes():
        venc = pagamento.get("dueDate")
        if not venc:
            continue
        try:
            vencimento = datetime.strptime(venc, "%Y-%m-%d").date()
        except ValueError:
            continue
        dias = (vencimento - hoje).days
        if dias not in {7, 1, 0}:
            continue
        cid = pagamento.get("customer")
        nome, telefone = _obter_cliente(cid) if cid else (None, None)
        if not nome or not telefone:
            continue
        link = (
            pagamento.get("invoiceUrl")
            or pagamento.get("bankSlipUrl")
            or pagamento.get("transactionReceiptUrl")
            or ""
        )
        mensagem = _montar_mensagem(dias, nome, pagamento.get("value", 0), venc, link)
        _enviar_whatsapp(telefone, mensagem)
        enviados.append({"cliente": nome, "dias": dias, "vencimento": venc})
    return {"enviados": enviados}
