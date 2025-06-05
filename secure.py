# secure.py
import os
import requests
from fastapi import APIRouter, HTTPException

router = APIRouter()

OM_BASE = os.getenv("OM_BASE")
BASIC_B64 = os.getenv("BASIC_B64")
UNIDADE_ID = os.getenv("UNIDADE_ID")

@router.head("/secure", summary="Obtem token da unidade")
def obter_token():
    if not all([OM_BASE, BASIC_B64, UNIDADE_ID]):
        raise HTTPException(500, detail="Variáveis de ambiente não configuradas corretamente.")
    
    try:
        url = f"{OM_BASE}/unidades/token/{UNIDADE_ID}"
        headers = {"Authorization": f"Basic {BASIC_B64}"}
        r = requests.get(url, headers=headers, timeout=8)

        if r.ok and r.json().get("status") == "true":
            return {"token": r.json()["data"]["token"]}
        else:
            raise HTTPException(status_code=400, detail="Falha ao obter token: " + r.text)

    except requests.RequestException as e:
        raise HTTPException(500, detail=f"Erro de conexão: {str(e)}")
