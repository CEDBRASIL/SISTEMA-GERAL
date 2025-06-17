import os
from datetime import date
import requests
from fastapi import APIRouter, HTTPException

from asaas import _criar_ou_obter_cliente, _headers
from utils import parse_valor

router = APIRouter(prefix="/assinantes", tags=["Assinantes"])

ASAAS_KEY = os.getenv("ASAAS_KEY")
ASAAS_BASE_URL = os.getenv("ASAAS_BASE_URL", "https://api.asaas.com/v3")


@router.get("/")
def listar_assinantes():
    """Retorna uma lista formatada com os assinantes cadastrados."""

    if not ASAAS_KEY:
        raise HTTPException(500, "ASAAS_KEY não configurada")

    headers = {"Content-Type": "application/json", "access_token": ASAAS_KEY}

    try:
        resp = requests.get(
            f"{ASAAS_BASE_URL}/subscriptions", headers=headers, timeout=10
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise HTTPException(502, f"Erro ao obter assinaturas: {e}")

    dados = resp.json().get("data") or []
    assinantes = []

    for sub in dados:
        cid = sub.get("customer")
        valor = sub.get("value")
        curso = sub.get("description")
        vencimento = sub.get("nextDueDate")

        nome = None
        telefone = None
        if cid:
            try:
                c = requests.get(
                    f"{ASAAS_BASE_URL}/customers/{cid}",
                    headers=headers,
                    timeout=10,
                )
                if c.ok:
                    cust = c.json()
                    nome = cust.get("name")
                    telefone = cust.get("mobilePhone") or cust.get("phone")
            except requests.RequestException:
                pass

        assinantes.append(
            {
                "nome": nome,
                "numero": telefone,
                "valor": valor,
                "curso": curso,
                "vencimento": vencimento,
            }
        )

    return {"assinantes": assinantes}


@router.post("/")
def adicionar_assinante(dados: dict):
    """Cria uma nova assinatura no ASAAS."""

    nome = dados.get("nome")
    cpf = dados.get("cpf")
    phone = dados.get("whatsapp") or dados.get("phone")
    valor = parse_valor(dados.get("valor"))
    descricao = dados.get("descricao") or "Assinatura"
    ciclo = dados.get("ciclo") or dados.get("cycle") or "MONTHLY"
    vencimento = dados.get("vencimento") or dados.get("nextDueDate") or date.today().isoformat()
    billing = dados.get("billingType") or os.getenv("ASAAS_BILLING_TYPE", "UNDEFINED")

    if not nome or not cpf or not phone or valor is None:
        raise HTTPException(400, "Campos obrigatórios ausentes")
    if valor <= 0:
        raise HTTPException(400, "Valor inválido")

    cid = _criar_ou_obter_cliente(nome, cpf, phone)

    payload = {
        "customer": cid,
        "billingType": billing,
        "value": valor,
        "cycle": ciclo,
        "nextDueDate": vencimento,
        "description": descricao,
    }

    try:
        resp = requests.post(
            f"{ASAAS_BASE_URL}/subscriptions",
            json=payload,
            headers=_headers(),
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise HTTPException(502, f"Erro ao criar assinatura: {e}")

    return resp.json()


@router.put("/{assinatura_id}")
def alterar_assinante(assinatura_id: str, dados: dict):
    """Altera dados de uma assinatura existente."""

    payload = {}
    if "valor" in dados:
        val = parse_valor(dados.get("valor"))
        if val is None or val <= 0:
            raise HTTPException(400, "Valor inválido")
        payload["value"] = val
    if "descricao" in dados:
        payload["description"] = dados["descricao"]
    if "ciclo" in dados or "cycle" in dados:
        payload["cycle"] = dados.get("ciclo") or dados.get("cycle")
    if "vencimento" in dados or "nextDueDate" in dados:
        payload["nextDueDate"] = dados.get("vencimento") or dados.get("nextDueDate")
    if "billingType" in dados:
        payload["billingType"] = dados["billingType"]

    if not payload:
        raise HTTPException(400, "Nenhum campo para atualização informado")

    try:
        resp = requests.put(
            f"{ASAAS_BASE_URL}/subscriptions/{assinatura_id}",
            json=payload,
            headers=_headers(),
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise HTTPException(502, f"Erro ao atualizar assinatura: {e}")

    if resp.status_code == 200:
        return resp.json()
    return {"status": "atualizado"}


@router.delete("/{assinatura_id}")
def remover_assinante(assinatura_id: str):
    """Remove uma assinatura do ASAAS."""

    try:
        resp = requests.delete(
            f"{ASAAS_BASE_URL}/subscriptions/{assinatura_id}",
            headers=_headers(),
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise HTTPException(502, f"Erro ao remover assinatura: {e}")

    return {"status": "removido"}
