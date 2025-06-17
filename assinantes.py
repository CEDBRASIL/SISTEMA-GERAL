import os
import requests
from fastapi import APIRouter, HTTPException

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
            }
        )

    return {"assinantes": assinantes}
