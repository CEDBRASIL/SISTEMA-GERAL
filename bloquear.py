import os
import requests
from fastapi import APIRouter, HTTPException

router = APIRouter()

OM_BASE = os.getenv("OM_BASE")
BASIC_B64 = os.getenv("BASIC_B64")
UNIDADE_ID = os.getenv("UNIDADE_ID")


def _obter_token_unidade() -> str:
    if not all([OM_BASE, BASIC_B64, UNIDADE_ID]):
        raise RuntimeError("Variáveis de ambiente OM não configuradas.")
    url = f"{OM_BASE}/unidades/token/{UNIDADE_ID}"
    r = requests.get(url, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=8)
    if r.ok and r.json().get("status") == "true":
        return r.json()["data"]["token"]
    raise RuntimeError(f"Falha ao obter token da unidade: HTTP {r.status_code}")


def _alterar_bloqueio(id_aluno: str, bloqueado: int) -> None:
    if bloqueado not in (0, 1):
        raise ValueError("bloqueado deve ser 0 ou 1")
    token = _obter_token_unidade()
    url = f"{OM_BASE}/alunos/{id_aluno}"
    payload = {"token": token, "bloqueado": str(bloqueado)}
    r = requests.post(
        url,
        data=payload,
        headers={"Authorization": f"Basic {BASIC_B64}"},
        timeout=10,
    )
    if r.ok:
        dados = {}
        try:
            dados = r.json()
        except Exception:
            pass
        if not dados or dados.get("status") == "true":
            return
    raise RuntimeError(f"Falha ao definir bloqueio: HTTP {r.status_code} | {r.text}")


@router.post("/bloquear/{id_aluno}", summary="Define o status de bloqueio do aluno")
def bloquear(id_aluno: str, status: int):
    try:
        _alterar_bloqueio(id_aluno, status)
        return {"message": "Status atualizado"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
