from fastapi import APIRouter, HTTPException
import json, os, uuid

router = APIRouter()
ARQ = "pendentes.json"


def _load():
    return json.load(open(ARQ)) if os.path.exists(ARQ) else {}


def _save(data):
    json.dump(data, open(ARQ, "w"), ensure_ascii=False, indent=2)


@router.post("/pre_matricular")
def pre_matricular(dados: dict):
    """Grava pré-matrícula pendente (sem criar assinatura)."""
    obrig = {"nome", "whatsapp", "email", "curso"}
    if not obrig.issubset(dados):
        raise HTTPException(400, "Campos incompletos")
    pend = _load()
    ref = uuid.uuid4().hex
    pend[ref] = dados | {"status": "pendente"}
    _save(pend)
    return {"ok": True, "ref": ref}
