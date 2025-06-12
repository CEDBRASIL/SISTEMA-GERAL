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


def _gera_url_redirecionamento(usuario: str, senha: str) -> str:
    """Obtém o token da OM e monta a URL de redirecionamento para o EAD."""
    if not OM_BASE or not BASIC_B64:
        raise HTTPException(500, detail="Variáveis de ambiente OM não configuradas.")

    url = f"{OM_BASE}/alunos/token"
    headers = {"Authorization": f"Basic {BASIC_B64}"}
    payload = {"usuario": usuario, "senha": senha}

    try:
        r = requests.post(url, headers=headers, data=payload, timeout=8)
    except requests.RequestException as e:
        raise HTTPException(500, detail=f"Erro de conexão: {str(e)}")

    if r.ok and r.json().get("status") == "true":
        token = r.json()["data"]["token"]
        return f"https://ead.cedbrasilia.com.br/index.php?pag=entrar&token={token}"

    raise HTTPException(401, detail="Usuário ou senha inválidos.")


@router.post("/", summary="Realiza login do aluno na OM e redireciona para o EAD")
def login(dados: LoginData):
    """Recebe usuário e senha por POST e redireciona para o EAD."""
    redirect_url = _gera_url_redirecionamento(dados.usuario, dados.senha)
    return RedirectResponse(url=redirect_url, status_code=302)


@router.get("/", summary="Realiza login do aluno na OM e redireciona para o EAD")
def login_get(usuario: str, senha: str):
    """Recebe usuário e senha por GET e redireciona para o EAD."""
    redirect_url = _gera_url_redirecionamento(usuario, senha)
    return RedirectResponse(url=redirect_url, status_code=302)
