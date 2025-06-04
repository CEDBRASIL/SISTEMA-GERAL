import requests
from typing import Optional, List
from fastapi import APIRouter, HTTPException

from cursos import cursos  # Agora puxando da variável 'cursos' da CED
from matricular import (
    _obter_token_unidade,
    _matricular_aluno_om,
    _send_whatsapp_chatpro,
    _send_discord_log,
    BASIC_B64,
    OM_BASE,
    UNIDADE_ID,
    _log,
)

router = APIRouter()

def _cadastrar_aluno_com_cpf(
    nome: str,
    whatsapp: str,
    email: Optional[str],
    cpf: str,
    cursos_ids: List[int],
    token_key: str,
    senha_padrao: str = "123456",
) -> str:
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
    _log(f"[CAD] Status {r.status_code} | Retorno OM: {r.text}")
    if not (r.ok and r.json().get("status") == "true"):
        raise RuntimeError("Falha ao cadastrar o aluno")

    aluno_id = r.json()["data"]["id"]

    if cursos_ids:
        ok_matri = _matricular_aluno_om(aluno_id, cursos_ids, token_key)
        if not ok_matri:
            raise RuntimeError("Aluno cadastrado, mas falha ao matricular em disciplinas.")
    return aluno_id


def _buscar_aluno_id_por_cpf(cpf: str) -> Optional[str]:
    r = requests.get(
        f"{OM_BASE}/alunos",
        headers={"Authorization": f"Basic {BASIC_B64}"},
        params={"cpf": cpf},
        timeout=10,
    )
    if r.ok and r.json().get("status") == "true":
        data = r.json().get("data") or []
        if data:
            return data[0].get("id")
    return None


def _excluir_aluno_om(aluno_id: str) -> None:
    r = requests.delete(
        f"{OM_BASE}/alunos/{aluno_id}",
        headers={"Authorization": f"Basic {BASIC_B64}"},
        timeout=10,
    )
    _log(f"[DEL] Status {r.status_code} | Retorno OM: {r.text}")
    if not (r.ok and r.json().get("status") == "true"):
        raise RuntimeError("Falha ao excluir aluno")


@router.post("/", summary="Webhook Kiwify - eventos de pedido")
async def receber_webhook(dados: dict):
    evento = dados.get("webhook_event_type")

    if evento == "order_refunded":
        customer = dados.get("Customer", {})
        cpf = customer.get("CPF")
        if not cpf:
            raise HTTPException(400, detail="CPF não informado")

        aluno_id = _buscar_aluno_id_por_cpf(cpf)
        if not aluno_id:
            raise HTTPException(404, detail="Aluno não encontrado")
        try:
            _excluir_aluno_om(aluno_id)
            return {"status": "excluido", "aluno_id": aluno_id}
        except RuntimeError as e:
            _log(f"❌ Erro ao excluir aluno: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    if evento != "order_approved":
        return {"status": "ignorado"}

    customer = dados.get("Customer", {})
    product = dados.get("Product", {})

    nome = customer.get("full_name") or customer.get("first_name")
    cpf = customer.get("CPF")
    whatsapp = customer.get("mobile")
    email = customer.get("email")
    curso_nome = product.get("product_name")

    if not all([nome, cpf, whatsapp]):
        raise HTTPException(400, detail="Dados incompletos no payload")

    cursos_ids: List[int] = []
    chave = next((k for k in cursos if k.lower() == (curso_nome or "").lower()), None)
    if chave:
        cursos_ids.extend(cursos[chave])

    try:
        token_unit = _obter_token_unidade()
        aluno_id = _cadastrar_aluno_com_cpf(nome, whatsapp, email, cpf, cursos_ids, token_unit)
        _send_whatsapp_chatpro(nome, whatsapp, [curso_nome], cpf)
        _send_discord_log(nome, cpf, whatsapp, cursos_ids)
        return {"status": "ok", "aluno_id": aluno_id, "cpf": cpf}
    except RuntimeError as e:
        _log(f"❌ Erro em /kiwify: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        _log(f"❌ Erro inesperado em /kiwify: {str(e)}")
        raise HTTPException(status_code=500, detail="Erro inesperado. Consulte os logs para mais detalhes.")
