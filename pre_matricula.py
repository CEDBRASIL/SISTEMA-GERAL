import os, json
from fastapi import APIRouter, HTTPException, Request
from typing import Dict
from datetime import datetime

router = APIRouter()

ARQUIVO_JSON = "dados_pendentes.json"

def salvar_dados_temporarios(dados: Dict):
    try:
        if os.path.exists(ARQUIVO_JSON):
            with open(ARQUIVO_JSON, "r", encoding="utf-8") as f:
                existentes = json.load(f)
        else:
            existentes = {}

        email = dados.get("email")
        if not email:
            raise ValueError("Email é obrigatório para identificação.")

        existentes[email] = {
            **dados,
            "data_envio": datetime.now().isoformat()
        }

        with open(ARQUIVO_JSON, "w", encoding="utf-8") as f:
            json.dump(existentes, f, indent=2, ensure_ascii=False)

    except Exception as e:
        raise RuntimeError(f"Erro ao salvar dados: {e}")

@router.post("/api/matricular")
async def receber_pre_matricula(body: Dict):
    try:
        salvar_dados_temporarios(body)
        return {"status": "ok", "mensagem": "Dados salvos com sucesso"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
