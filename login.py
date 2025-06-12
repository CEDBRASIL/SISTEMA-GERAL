import os
import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

router = APIRouter()

OM_BASE = os.getenv("OM_BASE")  # exemplo: https://meuappdecursos.com.br/ws/v2
BASIC_B64 = os.getenv("BASIC_B64")


class LoginData(BaseModel):
    usuario: str
    senha: str


@router.post("/", summary="Realiza login do aluno na OM e redireciona para o EAD")
def login(dados: LoginData):
    """Recebe usuário e senha, obtém token da OM e redireciona para o EAD."""
    if not OM_BASE or not BASIC_B64:
        raise HTTPException(500, detail="Variáveis de ambiente OM não configuradas.")

    url = f"{OM_BASE}/alunos/token"
    headers = {"Authorization": f"Basic {BASIC_B64}"}
    payload = {"usuario": dados.usuario, "senha": dados.senha}

    try:
        r = requests.post(url, headers=headers, data=payload, timeout=8)
    except requests.RequestException as e:
        raise HTTPException(500, detail=f"Erro de conexão: {str(e)}")

    if r.ok and r.json().get("status") == "true":
        token = r.json()["data"]["token"]
        redirect_url = f"https://ead.cedbrasilia.com.br/index.php?pag=entrar&token={token}"
        return RedirectResponse(url=redirect_url, status_code=302)

    raise HTTPException(401, detail="Usuário ou senha inválidos.")
