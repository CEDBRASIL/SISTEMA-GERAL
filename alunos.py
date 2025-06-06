import os
import requests
from fastapi import APIRouter, HTTPException

router = APIRouter()

OM_BASE = os.getenv("OM_BASE")
BASIC_B64 = os.getenv("BASIC_B64")
UNIDADE_ID = os.getenv("UNIDADE_ID")


def _listar_alunos(page: int = 1, size: int = 1000) -> dict:
    if not OM_BASE or not BASIC_B64 or not UNIDADE_ID:
        raise RuntimeError("Variáveis de ambiente OM não configuradas.")
    url = f"{OM_BASE}/alunos?page={page}&size={size}&id_unidade={UNIDADE_ID}"
    r = requests.get(url, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=10)
    if r.ok and r.json().get("status") == "true":
        return r.json()
    raise RuntimeError(f"Falha ao obter lista de alunos: HTTP {r.status_code}")


def _obter_todos_alunos() -> list:
    alunos = []
    page = 1
    while True:
        dados = _listar_alunos(page=page)
        for item in dados.get("data", []):
            alunos.append(item)
        pagina = dados.get("pagina", {})
        total = int(pagina.get("total", 0))
        size = int(pagina.get("size", 1000))
        if page * size >= total:
            break
        page += 1
    return alunos


@router.get("/", summary="Lista todos os alunos da unidade")
def listar_alunos_endpoint():
    try:
        lista = _obter_todos_alunos()
        return {"alunos": lista}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
