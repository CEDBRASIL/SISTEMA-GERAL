import os
import requests
from fastapi import APIRouter, HTTPException

router = APIRouter()

OM_BASE = os.getenv("OM_BASE")
BASIC_B64 = os.getenv("BASIC_B64")


def _excluir_aluno(id_aluno: str) -> None:
    if not OM_BASE or not BASIC_B64:
        raise RuntimeError("Variáveis de ambiente OM não configuradas.")
    url = f"{OM_BASE}/alunos/{id_aluno}"
    r = requests.delete(url, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=10)
    if r.ok:
        dados = {}
        try:
            dados = r.json()
        except Exception:
            pass
        if not dados or dados.get("status") == "true":
            return
    raise RuntimeError(f"Falha ao excluir aluno: HTTP {r.status_code} | {r.text}")


@router.delete("/deletar/{id_aluno}", summary="Exclui um aluno pelo ID")
def deletar_aluno(id_aluno: str):
    try:
        _excluir_aluno(id_aluno)
        return {"message": "Aluno excluído com sucesso"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
