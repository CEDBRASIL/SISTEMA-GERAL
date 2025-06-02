from fastapi import APIRouter

router = APIRouter()

@router.get("/ping")
def ping():
    """
    Rota de teste simples para validar se o módulo assinatura_teste está funcionando.
    """
    return {"mensagem": "Assinatura Teste OK"}
