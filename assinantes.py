import os
import requests
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/assinantes", tags=["Assinantes"])

ASAAS_KEY = os.getenv("ASAAS_KEY")
ASAAS_BASE_URL = os.getenv("ASAAS_BASE_URL", "https://api.asaas.com/v3")


@router.get("/")
def listar_assinantes():
    """Retorna a lista de assinantes cadastrados no ASAAS."""
    if not ASAAS_KEY:
        raise HTTPException(500, "ASAAS_KEY não configurada")

    headers = {"Content-Type": "application/json", "access_token": ASAAS_KEY}
    url = f"{ASAAS_BASE_URL}/subscriptions"
    try:
        resp = requests.get(url, headers=headers, timeout=10)
    except requests.RequestException as e:
        raise HTTPException(502, f"Erro de conexão: {e}")

    if resp.ok:
        try:
            return resp.json()
        except Exception:
            return {"status": "ok"}

    raise HTTPException(resp.status_code, resp.text)
