import os
import logging
from datetime import date
from typing import List

import requests
from fastapi import APIRouter, HTTPException, Request

from utils import formatar_numero_whatsapp
from matricular import realizar_matricula
from cursos import CURSOS_OM

# Conjunto com todos os IDs de cursos válidos, usado para validar
# o campo `externalReference` recebido no webhook
VALID_CURSO_IDS = {cid for ids in CURSOS_OM.values() for cid in ids}

router = APIRouter(prefix="/asaas", tags=["Matrícula Assas"])

ASAAS_KEY = os.getenv("ASAAS_KEY")
ASAAS_BASE_URL = os.getenv("ASAAS_BASE_URL", "https://api.asaas.com/v3")

WHATSAPP_URL = "https://whatsapptest-stij.onrender.com/send"
SENHA_PADRAO = os.getenv("SENHA_PADRAO", "1234567")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _headers() -> dict:
    if not ASAAS_KEY:
        raise HTTPException(500, "ASAAS_KEY não configurada")
    return {"Content-Type": "application/json", "access_token": ASAAS_KEY}


def _criar_ou_obter_cliente(nome: str, cpf: str, phone: str) -> str:
    payload = {"name": nome, "cpfCnpj": cpf, "mobilePhone": phone}
    try:
        r = requests.post(
            f"{ASAAS_BASE_URL}/customers", json=payload, headers=_headers(), timeout=10
        )
    except requests.RequestException as e:
        raise HTTPException(502, f"Erro de conexão: {e}")

    if r.status_code == 409:
        s = requests.get(
            f"{ASAAS_BASE_URL}/customers?cpfCnpj={cpf}",
            headers=_headers(),
            timeout=10,
        )
        if s.ok and s.json().get("data"):
            cid = s.json()["data"][0]["id"]
            logger.info("Cliente existente encontrado: %s", cid)
            return cid
        raise HTTPException(s.status_code, s.text)
    if r.ok:
        cid = r.json().get("id")
        logger.info("Novo cliente criado: %s", cid)
        return cid
    raise HTTPException(r.status_code, r.text)


def _enviar_whatsapp(nome: str, phone: str, login: str, modulo: str) -> None:
    mensagem = (
        f"🎉 Bem-vindo à CED BRASIL!\n"
        f"Seu pagamento foi confirmado e sua matrícula está ativa!\n"
        f"LOGIN: {login}\n"
        f"SENHA: {SENHA_PADRAO}\n"
        f"MODULO ADQUIRIDO: {modulo}\n"
        f"Acesse o portal em 👉 www.cedbrasilia.com.br (clique em ENTRAR)\n"
        f"ou baixe nosso app:\n\n"
        f"📱 Android: https://play.google.com/store/apps/details?id=br.com.om.app&hl=pt_BR\n"
        f"🍎 iOS: https://apps.apple.com/br/app/meu-app-de-cursos/id1581898914\n\n"
        f"🚀 Bons estudos! Qualquer dúvida, conte com a nossa equipe!"
    )
    try:
        r = requests.get(
            WHATSAPP_URL,
            params={"para": formatar_numero_whatsapp(phone), "mensagem": mensagem},
            timeout=10,
        )
        r.raise_for_status()
        logger.info("WhatsApp enviado para %s", phone)
    except Exception:
        logger.exception("Erro ao enviar mensagem via WhatsApp")


def _enviar_whatsapp_checkout(nome: str, phone: str, url: str) -> None:
    mensagem = (
        f"👋 Olá {nome}, tudo bem?\n\n"
        f"Segue o link para pagamento do seu curso: {url}\n"
        "Também enviamos este link via SMS.\n"
        "Assim que o pagamento for confirmado, enviaremos seus dados de acesso.\n\n"
        "Qualquer dúvida, estou à disposição para ajudar!"
    )
    try:
        r = requests.get(
            WHATSAPP_URL,
            params={"para": formatar_numero_whatsapp(phone), "mensagem": mensagem},
            timeout=10,
        )
        r.raise_for_status()
        logger.info("WhatsApp de checkout enviado para %s", phone)
    except Exception:
        logger.exception("Erro ao enviar mensagem de checkout via WhatsApp")


@router.post("/checkout")
def criar_assinatura(dados: dict):
    nome = dados.get("nome")
    cpf = dados.get("cpf")
    phone = dados.get("whatsapp") or dados.get("phone")
    valor = dados.get("valor")
    descricao = dados.get("descricao") or dados.get("curso") or "Curso"
    cursos_ids: List[int] = dados.get("cursos_ids") or []
    billing_type = dados.get("billingType") or os.getenv(
        "ASAAS_BILLING_TYPE", "UNDEFINED"
    )
    callback_url = os.getenv("ASAAS_CALLBACK_URL")
    redirect_url = os.getenv("ASAAS_REDIRECT_URL")

    if not nome or not cpf or not phone or not valor:
        raise HTTPException(400, "Campos obrigatórios ausentes")

    customer_id = _criar_ou_obter_cliente(nome, cpf, phone)

    payload = {
        "customer": customer_id,
        "billingType": billing_type,
        "value": valor,
        "description": descricao,
        "dueDate": date.today().isoformat(),
        "externalReference": ",".join(map(str, cursos_ids)),
    }
    if callback_url:
        payload["callbackUrl"] = callback_url
    if redirect_url:
        payload["redirectUrl"] = redirect_url

    try:
        r = requests.post(
            f"{ASAAS_BASE_URL}/payments", json=payload, headers=_headers(), timeout=10
        )
    except requests.RequestException as e:
        raise HTTPException(502, f"Erro de conexão: {e}")

    if not r.ok:
        raise HTTPException(r.status_code, r.text)

    data = r.json()
    url = (
        data.get("chargeUrl")
        or data.get("invoiceUrl")
        or data.get("bankSlipUrl")
        or data.get("transactionReceiptUrl")
    )

    if url:
        _enviar_whatsapp_checkout(nome, phone, url)

    return {
        "url": url,
        "customer": customer_id,
    }


@router.post("/assinatura")
def criar_assinatura_recorrente(dados: dict):
    nome = dados.get("nome")
    cpf = dados.get("cpf")
    phone = dados.get("whatsapp") or dados.get("phone")
    valor = dados.get("valor")
    descricao = dados.get("descricao") or "Assinatura"
    cursos_ids: List[int] = dados.get("cursos_ids") or []
    billing_type = dados.get("billingType") or "PIX"
    cycle = dados.get("ciclo") or dados.get("cycle") or "MONTHLY"
    next_due = dados.get("dueDate") or date.today().isoformat()
    callback_url = os.getenv("ASAAS_CALLBACK_URL")
    redirect_url = os.getenv("ASAAS_REDIRECT_URL")

    if not nome or not cpf or not phone or not valor:
        raise HTTPException(400, "Campos obrigatórios ausentes")

    customer_id = _criar_ou_obter_cliente(nome, cpf, phone)
    logger.info("Cliente ASAAS %s criado/obtido para %s", customer_id, phone)

    payload = {
        "customer": customer_id,
        "billingType": billing_type,
        "value": valor,
        "cycle": cycle,
        "nextDueDate": next_due,
        "description": descricao,
        "externalReference": ",".join(map(str, cursos_ids)),
    }
    if callback_url:
        payload["callbackUrl"] = callback_url
    if redirect_url:
        payload["redirectUrl"] = redirect_url

    try:
        r = requests.post(
            f"{ASAAS_BASE_URL}/subscriptions",
            json=payload,
            headers=_headers(),
            timeout=10,
        )
    except requests.RequestException as e:
        raise HTTPException(502, f"Erro de conexão: {e}")

    if not r.ok:
        raise HTTPException(r.status_code, r.text)

    data = r.json()
    url = (
        data.get("chargeUrl")
        or data.get("invoiceUrl")
        or data.get("bankSlipUrl")
        or data.get("transactionReceiptUrl")
    )

    if url:
        logger.info("Enviando link de checkout para %s", phone)
        _enviar_whatsapp_checkout(nome, phone, url)

    logger.info(
        "Assinatura criada com sucesso para %s (customer=%s, subscription=%s)",
        nome,
        customer_id,
        data.get("id"),
    )
    return {
        "url": url,
        "customer": customer_id,
        "subscription": data.get("id"),
    }


@router.post("/webhook")
async def webhook(req: Request):
    evt = await req.json()
    if evt.get("event") not in {"PAYMENT_RECEIVED", "PAYMENT_CONFIRMED"}:
        return {"status": "ignored"}

    payment = evt.get("payment", {})
    customer_id = payment.get("customer") or evt.get("customer")
    if not customer_id:
        return {"status": "ignored"}

    cursos_ref = payment.get("externalReference", "")
    descricao = (payment.get("description") or "").strip()

    cursos_ids: List[int] = []

    # Prioriza sempre a descrição para localizar o curso correto
    if descricao:
        for nome_curso, ids in CURSOS_OM.items():
            if nome_curso.lower() == descricao.lower():
                cursos_ids = ids
                break

    # Caso a descrição não mapeie nenhum curso, verifica o externalReference
    if not cursos_ids and cursos_ref:
        for ref in cursos_ref.split(","):
            ref = ref.strip()
            if ref.isdigit():
                cid = int(ref)
                if cid in VALID_CURSO_IDS:
                    cursos_ids.append(cid)

    c = requests.get(
        f"{ASAAS_BASE_URL}/customers/{customer_id}", headers=_headers(), timeout=10
    )
    if not c.ok:
        raise HTTPException(c.status_code, c.text)
    cust = c.json()
    nome = cust.get("name")
    cpf = cust.get("cpfCnpj")
    phone = cust.get("mobilePhone") or cust.get("phone")

    dados_matricula = {"nome": nome, "whatsapp": phone}
    if cursos_ids:
        dados_matricula["cursos_ids"] = cursos_ids
    else:
        dados_matricula["cursos"] = [descricao]

    matricula = await realizar_matricula(dados_matricula)

    # A mensagem de boas-vindas é disparada pelo próprio modulo de matrícula

    return {"status": "ok"}
