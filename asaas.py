import os
from datetime import date
from typing import List

import requests
from fastapi import APIRouter, HTTPException, Request

from utils import formatar_numero_whatsapp
from matricular import realizar_matricula

router = APIRouter(prefix="/asaas", tags=["Matrícula Assas"])

ASAAS_KEY = os.getenv("ASAAS_KEY")
ASAAS_BASE_URL = os.getenv("ASAAS_BASE_URL", "https://api.asaas.com/v3")

WHATSAPP_URL = "https://whatsapptest-stij.onrender.com/send"
SENHA_PADRAO = os.getenv("SENHA_PADRAO", "1234567")


def _headers() -> dict:
    if not ASAAS_KEY:
        raise HTTPException(500, "ASAAS_KEY não configurada")
    return {"Content-Type": "application/json", "access_token": ASAAS_KEY}


def _criar_ou_obter_cliente(nome: str, cpf: str, phone: str) -> str:
    payload = {"name": nome, "cpfCnpj": cpf, "mobilePhone": phone}
    try:
        r = requests.post(f"{ASAAS_BASE_URL}/customers", json=payload, headers=_headers(), timeout=10)
    except requests.RequestException as e:
        raise HTTPException(502, f"Erro de conexão: {e}")

    if r.status_code == 409:
        s = requests.get(f"{ASAAS_BASE_URL}/customers?cpfCnpj={cpf}", headers=_headers(), timeout=10)
        if s.ok and s.json().get("data"):
            return s.json()["data"][0]["id"]
        raise HTTPException(s.status_code, s.text)
    if r.ok:
        return r.json().get("id")
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
        requests.get(
            WHATSAPP_URL,
            params={"para": formatar_numero_whatsapp(phone), "mensagem": mensagem},
            timeout=10,
        )
    except Exception:
        pass


def _enviar_whatsapp_checkout(nome: str, phone: str, url: str) -> None:
    mensagem = (
        f"Olá {nome} Tudo bem?\n\n"
        "Voce esta a um passo de transformar o seu futuro!\n"
        "Só falta você finalizar o seu pagamento!\n"
        "Enviamos no seu SMS\n"
        f"Ou Pelo link: {url}\n\n"
        "Qualquer coisa, estou a disposição para ajudar :)"
    )
    try:
        requests.get(
            WHATSAPP_URL,
            params={"para": formatar_numero_whatsapp(phone), "mensagem": mensagem},
            timeout=10,
        )
    except Exception:
        pass


@router.post("/checkout")
def criar_assinatura(dados: dict):
    nome = dados.get("nome")
    cpf = dados.get("cpf")
    phone = dados.get("whatsapp") or dados.get("phone")
    valor = dados.get("valor")
    descricao = dados.get("descricao") or dados.get("curso") or "Curso"
    cursos_ids: List[int] = dados.get("cursos_ids") or []
    billing_type = dados.get("billingType") or os.getenv("ASAAS_BILLING_TYPE", "UNDEFINED")
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
        r = requests.post(f"{ASAAS_BASE_URL}/payments", json=payload, headers=_headers(), timeout=10)
    except requests.RequestException as e:
        raise HTTPException(502, f"Erro de conexão: {e}")

    if not r.ok:
        raise HTTPException(r.status_code, r.text)

    data = r.json()
    url = data.get("invoiceUrl") or data.get("bankSlipUrl") or data.get("transactionReceiptUrl")

    if url:
        _enviar_whatsapp_checkout(nome, phone, url)

    return {
        "url": url,
        "customer": customer_id,
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
    cursos_ids = [int(x) for x in cursos_ref.split(",") if x.isdigit()]
    descricao = payment.get("description") or "Curso"

    c = requests.get(f"{ASAAS_BASE_URL}/customers/{customer_id}", headers=_headers(), timeout=10)
    if not c.ok:
        raise HTTPException(c.status_code, c.text)
    cust = c.json()
    nome = cust.get("name")
    cpf = cust.get("cpfCnpj")
    phone = cust.get("mobilePhone") or cust.get("phone")

    matricula = await realizar_matricula({"nome": nome, "whatsapp": phone, "cursos_ids": cursos_ids})
    _enviar_whatsapp(nome, phone, matricula.get("cpf", cpf), descricao)

    return {"status": "ok"}
