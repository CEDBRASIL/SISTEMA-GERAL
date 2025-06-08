import os
from fastapi import FastAPI, Request, HTTPException
import requests
import APIRouter

# CHAMADA ROUTER 

router = APIRouter()

# Placeholder matricular function - adapt as needed
try:
    from matricular import matricular  # type: ignore
except Exception:  # pragma: no cover - fallback if not available
    def matricular(**kwargs):
        """Fallback matricular implementation."""
        print("Matricular called with", kwargs)

ASAAS_KEY = os.getenv("ASAAS_KEY")
ASAAS_BASE_URL = os.getenv("ASAAS_BASE_URL")
CHATPRO_TOKEN = os.getenv("CHATPRO_TOKEN")
CHATPRO_URL = os.getenv("CHATPRO_URL")

app = FastAPI()

@app.post("/matricularasaas")
async def matricular_asaas(data: dict):
    nome = data.get("nome")
    cpf = data.get("cpf")
    phone = data.get("phone")

    if not nome or not cpf or not phone:
        raise HTTPException(400, "Campos 'nome', 'cpf' e 'phone' são obrigatórios")

    cpf_digits = "".join(filter(str.isdigit, str(cpf)))
    if len(cpf_digits) != 11:
        raise HTTPException(400, "CPF deve possuir 11 dígitos")

    # Pré-matrícula opcional poderia ser registrada aqui

    return {"status": "ok"}

@app.post("/webhooks/asaas")
async def asaas_webhook(req: Request):
    evt = await req.json()
    if evt.get("event") != "PAYMENT_RECEIVED":
        return {"status": "ignored"}

    customer = evt.get("customer", {})
    nome = customer.get("name") or customer.get("nome")
    cpf = customer.get("cpf") or customer.get("document")
    phone = customer.get("phone") or customer.get("cellphone")

    try:
        matricular(cpf=cpf, nome=nome)
    except Exception as e:  # pragma: no cover - propagate error
        raise HTTPException(500, detail=str(e))

    try:
        requests.post(
            f"{CHATPRO_URL}/sendMessage",
            headers={"Authorization": f"Bearer {CHATPRO_TOKEN}"},
            json={
                "to": phone,
                "message": f"Olá {nome}, sua matrícula foi confirmada com sucesso!"
            },
            timeout=10,
        )
    except Exception:
        pass  # Falha no WhatsApp não impede resposta

    return {"status": "ok"}
