import os, json, requests
from fastapi import APIRouter, Request, HTTPException
from matricular import matricular_aluno

router = APIRouter()

MP_TOKEN = os.getenv("MP_TEST_ACCESS_TOKEN")
ARQUIVO_JSON = "dados_pendentes.json"

def buscar_dados_por_email(email: str):
    if not os.path.exists(ARQUIVO_JSON):
        return None
    with open(ARQUIVO_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data.get(email)

def buscar_assinatura(subscription_id: str):
    url = f"https://api.mercadopago.com/preapproval/{subscription_id}"
    headers = {"Authorization": f"Bearer {MP_TOKEN}"}
    r = requests.get(url, headers=headers, timeout=10)
    if r.ok:
        return r.json()
    return None

@router.post("/webhook")
async def webhook_mp(request: Request):
    try:
        body = await request.json()
        print("[WEBHOOK DEBUG]", json.dumps(body, indent=2))

        _type = body.get("type")
        _id = body.get("data", {}).get("id")

        if _type != "preapproval" or not _id:
            return {"ignored": True}

        if not MP_TOKEN:
            raise HTTPException(500, detail="MP_TOKEN não configurado")

        assinatura = buscar_assinatura(_id)
        if not assinatura or assinatura.get("status") != "authorized":
            return {"ignored": True}

        email = assinatura.get("payer_email") or assinatura.get("payer", {}).get("email")
        if not email:
            raise HTTPException(400, detail="Email do pagador não encontrado")

        dados = buscar_dados_por_email(email)
        if not dados:
            raise HTTPException(404, detail=f"Dados do aluno não encontrados para {email}")

        nome = dados["nome"]
        whatsapp = dados["whatsapp"]
        cursos = dados["cursos"]

        aluno_id, cpf, ids = matricular_aluno(nome, whatsapp, email, cursos)

        print(f"[MATRICULADO] {nome} | {cpf} | {cursos}")

        return {"status": "matriculado", "cpf": cpf, "aluno_id": aluno_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
