from fastapi import APIRouter, Request

router = APIRouter()

@router.post("/")
async def receber_webhook(request: Request):
    """
    Endpoint para receber webhooks de plataformas externas (ex: Mercado Pago, Kiwify etc.).
    """
    dados = await request.json()
    print("🔔 Webhook recebido:", dados)
    return {"status": "recebido"}
