import os
import requests
from fastapi import APIRouter, HTTPException
from datetime import datetime

router = APIRouter()

# Variáveis de ambiente necessárias
BASIC_B64 = os.getenv("BASIC_B64")
UNIDADE_ID = os.getenv("UNIDADE_ID")
OM_BASE = os.getenv("OM_BASE")

def _log(msg: str):
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{agora}] {msg}")

def obter_token_unidade() -> str:
    """
    Faz chamada GET em /unidades/token/{UNIDADE_ID} para obter o token da unidade na OM.
    """
    if not all([OM_BASE, BASIC_B64, UNIDADE_ID]):
        raise RuntimeError("Variáveis OM não configuradas (OM_BASE, BASIC_B64, UNIDADE_ID).")

    url = f"{OM_BASE}/unidades/token/{UNIDADE_ID}"  
    r = requests.get(url, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=8)
    if r.ok and r.json().get("status") == "true":
        token = r.json()["data"]["token"]
        return token
    

    raise RuntimeError(f"Falha ao obter token da unidade: HTTP {r.status_code}")

@router.get("/secure", summary="Renova o token da unidade na OM")
async def renovar_token():
    """
    Renova (reconsulta) o token da unidade na API da OM e retorna o novo valor.
    Usar para manter uptime (UptimeRobot, etc.).
    """
    try:
        token = obter_token_unidade()
        _log("🔄 Token renovado com sucesso via /secure")
        return {"status": "ok", "token": token}
    except Exception as e:
        _log(f"❌ Falha ao renovar token: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao renovar token: {str(e)}")

@router.get("/token", summary="Consulta o token atual da unidade na OM")
async def consultar_token():
    """
    Retorna o token atual da unidade sem forçar renovação extra.
    Útil para debug e verificação.
    """
    try:
        token = obter_token_unidade()
        _log("ℹ️ Token consultado com sucesso via /token")
        return {"status": "ok", "token": token}
    except Exception as e:
        _log(f"❌ Falha ao consultar token: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao consultar token: {str(e)}")
