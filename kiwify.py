from typing import List, Optional
import os
import json
import requests
import hmac
import hashlib
from urllib.parse import parse_qs
from fastapi import APIRouter, HTTPException, Request

from cursos import CURSOS_OM
from matricular import (
    _obter_token_unidade,
    _matricular_aluno_om,
    _send_whatsapp_chatpro,
    _send_discord_log,
    _cpf_em_uso,
    OM_BASE,
    BASIC_B64,
    UNIDADE_ID,
    _log,
)

router = APIRouter()

KIWIFY_TOKEN = os.getenv("KIWIFY_TOKEN")


def _cadastrar_somente_aluno_com_cpf(
    nome: str,
    whatsapp: str,
    email: Optional[str],
    cpf: str,
    token_key: str,
    senha_padrao: str = "123456",
) -> str:
    """Cadastra aluno na OM usando o CPF informado como login."""
    if _cpf_em_uso(cpf):
        raise RuntimeError("CPF já cadastrado na OM")

    email_validado = email or f"{whatsapp}@nao-informado.com"
    payload = {
        "token": token_key,
        "nome": nome,
        "email": email_validado,
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
        "senha": senha_padrao,
    }
    r = requests.post(
        f"{OM_BASE}/alunos",
        data=payload,
        headers={"Authorization": f"Basic {BASIC_B64}"},
        timeout=10,
    )
    _log(f"[CAD-KIWIFY] Status {r.status_code} | Retorno OM: {r.text}")
    if r.ok and r.json().get("status") == "true":
        return r.json()["data"]["id"]
    raise RuntimeError("Falha ao cadastrar o aluno na OM")


def _cadastrar_aluno_kiwify(
    nome: str,
    whatsapp: str,
    email: Optional[str],
    cpf: str,
    cursos_ids: List[int],
    token_key: str,
) -> str:
    aluno_id = _cadastrar_somente_aluno_com_cpf(nome, whatsapp, email, cpf, token_key)
    if cursos_ids:
        ok = _matricular_aluno_om(aluno_id, cursos_ids, token_key)
        if not ok:
            raise RuntimeError("Aluno cadastrado, mas falha na matrícula")
    else:
        _log(f"[MAT] Curso não informado para {nome}. Cadastro concluído sem matrícula.")
    return aluno_id


@router.post("", summary="Recebe Webhook da Kiwify para pedidos aprovados")
async def receber_webhook(request: Request, signature: Optional[str] = None):
    body_bytes = await request.body()

    if KIWIFY_TOKEN:
        if not signature:
            raise HTTPException(status_code=401, detail="Assinatura ausente")
        calc_sig = hmac.new(KIWIFY_TOKEN.encode(), body_bytes, hashlib.sha1).hexdigest()
        if signature != calc_sig:
            raise HTTPException(status_code=401, detail="Assinatura inválida")

    try:
        dados = json.loads(body_bytes.decode())
    except Exception:
        qs = parse_qs(body_bytes.decode())
        payload = (qs.get("payload") or qs.get("data"))
        if not payload:
            raise HTTPException(status_code=400, detail="Payload inválido")
        try:
            dados = json.loads(payload[0])
        except Exception:
            raise HTTPException(status_code=400, detail="Payload inválido")

    if dados.get("webhook_event_type") != "order_approved":
        return {"status": "ignored"}

    customer = dados.get("Customer", {})
    product = dados.get("Product", {})

    nome = customer.get("full_name")
    cpf = customer.get("CPF")
    whatsapp = customer.get("mobile")
    email = customer.get("email")
    curso_nome = product.get("product_name")

    if not all([nome, cpf, whatsapp, curso_nome]):
        raise HTTPException(status_code=400, detail="Dados incompletos no webhook")

    cursos_ids = CURSOS_OM.get(curso_nome)
    if not cursos_ids:
        raise HTTPException(status_code=404, detail=f"Curso '{curso_nome}' não mapeado")

    try:
        token = _obter_token_unidade()
        aluno_id = _cadastrar_aluno_kiwify(nome, whatsapp, email, cpf, cursos_ids, token)
        _send_whatsapp_chatpro(nome, whatsapp, [curso_nome], cpf)
        _send_discord_log(nome, cpf, whatsapp, cursos_ids)
        return {"status": "ok", "aluno_id": aluno_id, "cpf": cpf}
    except Exception as e:
        _log(f"❌ Erro em /kiwify: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Também aceita requisições com barra no final (/kiwify/)
router.add_api_route("/", receber_webhook, methods=["POST"], include_in_schema=False)