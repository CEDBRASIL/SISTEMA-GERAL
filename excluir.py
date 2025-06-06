import requests
from fastapi import APIRouter, HTTPException

router = APIRouter()

BASE_URL = "https://api.cedbrasilia.com.br/excluir"

@router.delete("/{aluno_id}", summary="Exclui um aluno pelo ID")
def excluir_aluno(aluno_id: str):
    """Envia uma requisição para excluir um aluno no sistema externo."""
    try:
        resp = requests.delete(f"{BASE_URL}/{aluno_id}", timeout=10)
        if resp.ok:
            # assume API returns JSON
            try:
                return resp.json()
            except ValueError:
                return {"message": resp.text}
        raise HTTPException(resp.status_code, resp.text)
    except requests.RequestException as e:
        raise HTTPException(500, str(e))

