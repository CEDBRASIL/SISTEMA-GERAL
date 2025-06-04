from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
import requests
import os
import json
from cursos import CURSOS_OM  # Importa mapeamento de cursos local

router = APIRouter()

# 1. CONSTANTES E VARIÁVEIS DE AMBIENTE
OM_BASE        = os.getenv("OM_BASE")
BASIC_B64      = os.getenv("BASIC_B64")
CHATPRO_TOKEN  = os.getenv("CHATPRO_TOKEN")
CHATPRO_URL    = os.getenv("CHATPRO_URL")
UNIDADE_ID     = os.getenv("UNIDADE_ID")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")

# 2. VARIÁVEIS GLOBAIS
TOKEN_UNIDADE = None
MAPEAMENTO_CURSOS = {}

def enviar_log_discord(mensagem: str) -> None:
    try:
        payload = {"content": mensagem}
        headers = {"Content-Type": "application/json"}
        resp = requests.post(DISCORD_WEBHOOK, data=json.dumps(payload), headers=headers)
        if resp.status_code == 204:
            print("✅ Log enviado ao Discord com sucesso.")
        else:
            print("❌ Falha ao enviar log para Discord:", resp.text)
    except Exception as e:
        print("❌ Erro ao enviar log para Discord:", str(e))

def enviar_log(mensagem: str) -> None:
    enviar_log_discord(mensagem)

def obter_token_unidade() -> str:
    global TOKEN_UNIDADE
    try:
        resposta = requests.get(
            f"{OM_BASE}/unidades/token/{UNIDADE_ID}",
            headers={"Authorization": f"Basic {BASIC_B64}"},
        )
        dados = resposta.json()
        if dados.get("status") == "true":
            TOKEN_UNIDADE = dados["data"]["token"]
            mensagem = "🔁 Token atualizado com sucesso!"
            print(mensagem)
            enviar_log_discord(mensagem)
            return TOKEN_UNIDADE

        mensagem = f"❌ Erro ao obter token: {dados}"
        print(mensagem)
        enviar_log(mensagem)
    except Exception as e:
        mensagem = f"❌ Exceção ao obter token: {str(e)}"
        print(mensagem)
        enviar_log(mensagem)
    return None

def obter_mapeamento_cursos() -> dict:
    global MAPEAMENTO_CURSOS
    try:
        MAPEAMENTO_CURSOS = CURSOS_OM
        mensagem = "🔁 Mapeamento de cursos carregado com sucesso (local)."
        print(mensagem)
        enviar_log_discord(mensagem)
        return MAPEAMENTO_CURSOS
    except Exception as e:
        mensagem = f"❌ Erro ao carregar cursos do arquivo local: {str(e)}"
        print(mensagem)
        enviar_log(mensagem)
        return {}

# Inicializa token e cursos
TOKEN_UNIDADE = obter_token_unidade()
MAPEAMENTO_CURSOS = obter_mapeamento_cursos()

async def log_request_info(request: Request) -> None:
    mensagem = (
        f"\n�\udce5 Requisição recebida:\n"
        f"�\udd17 URL completa: {request.url}\n"
        f"�\udccd Método: {request.method}\n"
        f"�\udce6 Cabeçalhos: {dict(request.headers)}"
    )
    print(mensagem)
    enviar_log_discord(mensagem)

router.dependencies.append(Depends(log_request_info))

@router.get('/secure')
async def secure_check():
    novo = obter_token_unidade()
    if novo:
        return "🔐 Token atualizado com sucesso via /secure"
    return JSONResponse(content="❌ Falha ao atualizar token via /secure", status_code=500)

# ... O restante do arquivo permanece igual, incluindo webhook e busca de aluno,
# pois a única mudança relevante é o uso do arquivo local cursos.py
# Se quiser, posso colar o código completo da rota /webhook também com esse novo comportamento.
