
"""
matricular.py – cadastra e matricula um aluno usando apenas NOME dos cursos.
"""

import os, threading
from typing import List, Tuple, Optional
import requests
from fastapi import APIRouter, HTTPException, Request
from datetime import datetime
from cursos import curso

router = APIRouter()

OM_BASE   = os.getenv("OM_BASE")
BASIC_B64 = os.getenv("BASIC_B64")
UNIDADE_ID = os.getenv("UNIDADE_ID")

CPF_PREFIXO = "20254158"
cpf_lock = threading.Lock()

def _log(msg: str):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}")

def _obter_token_unidade() -> str:
    if not all([OM_BASE, BASIC_B64, UNIDADE_ID]):
        raise RuntimeError("Variáveis OM não configuradas.")
    url = f"{OM_BASE}/unidades/token/{UNIDADE_ID}"
    r = requests.get(url, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=8)
    if r.ok and r.json().get("status") == "true":
        return r.json()["data"]["token"]
    raise RuntimeError("Falha ao obter token da unidade")

def _total_alunos() -> int:
    url = f"{OM_BASE}/alunos/total/{UNIDADE_ID}"
    r = requests.get(url, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=8)
    if r.ok and r.json().get("status") == "true":
        return int(r.json()["data"]["total"])
    url = f"{OM_BASE}/alunos?unidade_id={UNIDADE_ID}&cpf_like={CPF_PREFIXO}"
    r = requests.get(url, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=8)
    if r.ok and r.json().get("status") == "true":
        return len(r.json()["data"])
    raise RuntimeError("Falha ao apurar total de alunos")

def _proximo_cpf(incr:int=0)->str:
    with cpf_lock:
        seq = _total_alunos() + 1 + incr
        return CPF_PREFIXO + str(seq).zfill(3)

def _matricular_om(aluno_id:str, cursos_ids:List[int], token:str)->bool:
    payload = {"token": token, "cursos": ",".join(map(str, cursos_ids))}
    r = requests.post(f"{OM_BASE}/alunos/matricula/{aluno_id}",
                      data=payload,
                      headers={"Authorization": f"Basic {BASIC_B64}"},
                      timeout=10)
    _log(f"[MAT] {r.status_code} {r.text[:120]}")
    return r.ok and r.json().get("status") == "true"

def _cadastrar_aluno(nome:str, whatsapp:str, email:str, cursos_ids:List[int], token:str)->Tuple[str,str]:
    for i in range(60):
        cpf = _proximo_cpf(i)
        payload = {
            "token": token,
            "nome": nome,
            "email": email or f"{whatsapp}@nao-informado.com",
            "whatsapp": whatsapp,
            "fone": whatsapp,
            "celular": whatsapp,
            "data_nascimento": "2000-01-01",
            "doc_cpf": cpf,
            "doc_rg": "000000000",
            "pais": "Brasil",
            "uf": "DF",
            "cidade": "Brasília",
            "endereco": "Não informado",
            "bairro": "Centro",
            "cep": "70000-000",
            "complemento": "",
            "numero": "0",
            "unidade_id": UNIDADE_ID,
            "senha": "123456"
        }
        r = requests.post(f"{OM_BASE}/alunos", data=payload,
                          headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=10)
        if r.ok and r.json().get("status") == "true":
            aluno_id = r.json()["data"]["id"]
            if _matricular_om(aluno_id, cursos_ids, token):
                return aluno_id, cpf
        if "já está em uso" not in (r.json() or {}).get("info", "").lower():
            break
    raise RuntimeError("Falha ao cadastrar/matricular aluno")

def _nome_para_ids(cursos:List[str])->List[int]:
    ids=[]
    for nome in cursos:
        ids.extend(cursos.get(nome.strip(), []))
    return ids

def matricular_aluno(nome:str, whatsapp:str, email:Optional[str], cursos:List[str])->Tuple[str,str,List[int]]:
    cursos_ids = _nome_para_ids(cursos)
    if not cursos_ids:
        raise RuntimeError("Nenhum ID de disciplina encontrado para os cursos fornecidos")
    token = _obter_token_unidade()
    aluno_id, cpf = _cadastrar_aluno(nome, whatsapp, email or "", cursos_ids, token)
    return aluno_id, cpf, cursos_ids

@router.post("/")
async def endpoint_matricular(body: dict):
    nome = body.get("nome")
    whatsapp = body.get("whatsapp")
    email = body.get("email","")
    cursos = body.get("cursos",[])
    if not nome or not whatsapp or not cursos:
        raise HTTPException(400, detail="nome, whatsapp e cursos são obrigatórios")
    try:
        aluno_id, cpf, ids = matricular_aluno(nome, whatsapp, email, cursos)
        return {"status":"ok", "aluno_id": aluno_id, "cpf": cpf, "disciplinas_matriculadas": ids}
    except Exception as e:
        raise HTTPException(500, detail=str(e))
