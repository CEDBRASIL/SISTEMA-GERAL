import os
import requests
import unicodedata
import difflib
import datetime
import json
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
import gspread
from google.oauth2.service_account import Credentials
from cursos import CURSOS_OM

# --- Roteador do FastAPI ---
router = APIRouter()

# --- Configuração de Variáveis de Ambiente ---
OM_BASE = os.getenv("OM_BASE")
BASIC_B64 = os.getenv("BASIC_B64")
CHATPRO_TOKEN = os.getenv("CHATPRO_TOKEN")
CHATPRO_URL = os.getenv("CHATPRO_URL")
UNIDADE_ID = os.getenv("UNIDADE_ID")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")

# Variáveis para credenciais do Google
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON") # Para segredos em texto
GOOGLE_SHEETS_CREDENTIALS_PATH = os.getenv("GOOGLE_SHEETS_CREDENTIALS_PATH") # Para arquivos secretos
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME")

# --- Variáveis Globais (Cache) ---
TOKEN_UNIDADE: str | None = None
CURSOS_OM_CACHE: dict = {} # Cache para os cursos carregados da API

# --- Funções Auxiliares ---

def enviar_log_discord(mensagem: str) -> None:
    """Envia uma mensagem de log para um canal do Discord."""
    if not DISCORD_WEBHOOK:
        print("Discord webhook não configurado")
        return
    try:
        requests.post(DISCORD_WEBHOOK, json={"content": mensagem}, timeout=5)
    except Exception as e:
        print(f"❌ Erro ao enviar log para Discord: {e}")

def obter_token_unidade() -> str | None:
    """Busca e atualiza o token de autenticação da unidade."""
    global TOKEN_UNIDADE
    try:
        resp = requests.get(
            f"{OM_BASE}/unidades/token/{UNIDADE_ID}",
            headers={"Authorization": f"Basic {BASIC_B64}"},
        )
        dados = resp.json()
        if resp.ok and dados.get("status") == "true":
            TOKEN_UNIDADE = dados["data"]["token"]
            enviar_log_discord("🔁 Token de unidade atualizado com sucesso!")
            return TOKEN_UNIDADE
        enviar_log_discord(f"❌ Erro ao obter token: {dados}")
    except Exception as e:
        enviar_log_discord(f"❌ Exceção ao obter token: {e}")
    return None

def atualizar_cache_cursos_om() -> None:
    """Busca todos os cursos da API e os armazena em cache."""
    global CURSOS_OM_CACHE
    enviar_log_discord("🔄 Atualizando cache de cursos a partir da API...")
    try:
        resp = requests.get(f"{OM_BASE}/cursos/", headers={"Authorization": f"Basic {BASIC_B64}"})
        if not resp.ok:
            enviar_log_discord(f"❌ Falha ao buscar cursos da API: {resp.text}")
            return
        
        cursos_data = resp.json().get("data", [])
        novo_cache = {curso["nome"]: [curso["id"]] for curso in cursos_data if "nome" in curso and "id" in curso}
        
        if not novo_cache:
            enviar_log_discord("⚠️ Nenhum curso encontrado na API para popular o cache.")
            return

        CURSOS_OM_CACHE = novo_cache
        enviar_log_discord(f"✅ Cache de cursos atualizado com sucesso. {len(CURSOS_OM_CACHE)} cursos carregados.")

    except Exception as e:
        enviar_log_discord(f"❌ Exceção ao atualizar cache de cursos: {e}")

def buscar_aluno_por_cpf(cpf: str) -> str | None:
    """Busca o ID de um aluno no sistema OM pelo CPF."""
    try:
        resp = requests.get(
            f"{OM_BASE}/alunos",
            headers={"Authorization": f"Basic {BASIC_B64}"},
            params={"cpf": cpf},
        )
        if not resp.ok:
            enviar_log_discord(f"❌ Falha ao buscar aluno por CPF: {resp.text}")
            return None
        alunos = resp.json().get("data", [])
        return alunos[0].get("id") if alunos else None
    except Exception as e:
        enviar_log_discord(f"❌ Erro ao buscar aluno por CPF: {e}")
        return None

def enviar_whatsapp_chatpro(nome: str, celular: str, plano: str, cpf: str, senha_padrao: str = "123456") -> None:
    """Envia uma mensagem de boas-vindas via ChatPro."""
    if not CHATPRO_TOKEN or not CHATPRO_URL:
        enviar_log_discord("⚠️ Variáveis do ChatPro não configuradas. Mensagem não enviada.")
        return

    numero_telefone = "".join(filter(str.isdigit, celular))

    mensagem = (
        f"👋 Olá, {nome}!\n\n"
        f"🎉 Seja bem-vindo(a) ao CED BRASIL!\n\n"
        f"📚 Curso adquirido: {plano}\n\n"
        f"🔐 Seu login: {cpf}\n"
        f"🔑 Sua senha: {senha_padrao}\n\n"
        f"🌐 Portal do Aluno: https://ead.cedbrasilia.com.br\n"
        f"🤖 APP Android: https://play.google.com/store/apps/datasafety?id=br.com.om.app&hl=pt_BR\n"
        f"🍎 APP iOS: https://apps.apple.com/br/app/meu-app-de-cursos/id1581898914\n\n"
        f"Qualquer dúvida, estamos à disposição. Boa jornada de estudos! 🚀"
    )

    payload = {"number": numero_telefone, "message": mensagem}
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "Authorization": CHATPRO_TOKEN,
    }
    try:
        r = requests.post(CHATPRO_URL, json=payload, headers=headers, timeout=10)
        if r.ok:
            enviar_log_discord(f"✅ WhatsApp enviado para {numero_telefone}. Resposta: {r.text}")
        else:
            enviar_log_discord(
                f"❌ Falha ao enviar WhatsApp para {numero_telefone}. HTTP {r.status_code} | {r.text}"
            )
    except Exception as e:
        enviar_log_discord(f"❌ Erro ao enviar WhatsApp para {numero_telefone}: {e}")

def _normalize(text: str) -> str:
    """Remove acentos e converte para caixa baixa."""
    return unicodedata.normalize("NFKD", text or "").encode("ASCII", "ignore").decode().lower()

def obter_cursos_ids(nome_plano: str):
    """Mapeia o nome do plano da Kiwify para IDs de curso usando o cache da API
    ou o mapeamento estático de ``cursos.CURSOS_OM`` como fallback."""

    if not nome_plano:
        return None

    norm_plano = _normalize(nome_plano)

    # 1) Busca no cache de cursos obtidos da API
    for key, value in CURSOS_OM_CACHE.items():
        if _normalize(key) == norm_plano:
            return value

    nomes_norm = {_normalize(k): k for k in CURSOS_OM_CACHE}
    match = difflib.get_close_matches(norm_plano, nomes_norm.keys(), n=1, cutoff=0.8)
    if match:
        return CURSOS_OM_CACHE[nomes_norm[match[0]]]

    # 2) Fallback para o dicionário estático
    for key, value in CURSOS_OM.items():
        if _normalize(key) == norm_plano:
            enviar_log_discord(f"ℹ️ Plano encontrado via fallback estatico: '{key}'")
            return value

    nomes_norm_static = {_normalize(k): k for k in CURSOS_OM}
    match_static = difflib.get_close_matches(norm_plano, nomes_norm_static.keys(), n=1, cutoff=0.8)
    if match_static:
        key = nomes_norm_static[match_static[0]]
        enviar_log_discord(f"ℹ️ Plano aproximado encontrado via fallback: '{key}'")
        return CURSOS_OM[key]

    return None

def adicionar_aluno_planilha(dados: dict) -> None:
    """Adiciona uma nova linha com dados do aluno na Planilha Google."""
    if not GOOGLE_SHEET_NAME or (not GOOGLE_CREDENTIALS_JSON and not GOOGLE_SHEETS_CREDENTIALS_PATH):
        enviar_log_discord("⚠️ Variáveis do Google Sheets não configuradas. Etapa ignorada.")
        return
        
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = None
        
        if GOOGLE_CREDENTIALS_JSON:
            # Método 1: Carrega a partir da string da variável de ambiente (MAIS SEGURO PARA PRODUÇÃO)
            creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        elif GOOGLE_SHEETS_CREDENTIALS_PATH:
            # Método 2: Carrega a partir do arquivo (bom para Render "Secret Files" e local)
            creds = Credentials.from_service_account_file(GOOGLE_SHEETS_CREDENTIALS_PATH, scopes=scopes)

        if not creds:
             enviar_log_discord("❌ Falha ao carregar credenciais do Google.")
             return

        client = gspread.authorize(creds)
        sheet = client.open(GOOGLE_SHEET_NAME).sheet1

        proxima_cobranca = (datetime.datetime.now() + datetime.timedelta(days=30)).strftime("%d/%m/%Y")
        linha_para_adicionar = [
            dados.get("nome"), dados.get("celular"), dados.get("email"), dados.get("cpf"),
            proxima_cobranca, dados.get("metodo_pagamento"), dados.get("plano_assinatura"),
        ]
        
        sheet.append_row(linha_para_adicionar)
        enviar_log_discord(f"📊 Aluno '{dados.get('nome')}' adicionado à planilha com sucesso!")
    except Exception as e:
        enviar_log_discord(f"❌ ERRO GOOGLE SHEETS: {e}")

# --- Dependências e Lógica Principal do Webhook ---

def log_request_info(request: Request):
    """Dependência para logar todas as requisições."""
    mensagem = (
        f"\n📥 Requisição de {request.client.host}:\n"
        f"🔗 URL: {request.url} | Método: {request.method}"
    )
    print(mensagem)
    enviar_log_discord(mensagem)

router.dependencies.append(Depends(log_request_info))

async def _process_webhook(payload: dict):
    """Processa o payload do webhook da Kiwify."""
    try:
        evento = payload.get("webhook_event_type")

        if evento == "order_refunded":
            customer = payload.get("Customer", {})
            cpf = customer.get("CPF", "").replace(".", "").replace("-", "")
            if not cpf: raise HTTPException(400, "CPF não encontrado no payload de reembolso.")
            aluno_id = buscar_aluno_por_cpf(cpf)
            if not aluno_id: raise HTTPException(404, "Aluno não encontrado para o CPF informado.")
            
            resp_exclusao = requests.delete(f"{OM_BASE}/alunos/{aluno_id}", headers={"Authorization": f"Basic {BASIC_B64}"})
            if not resp_exclusao.ok:
                enviar_log_discord(f"❌ ERRO AO EXCLUIR ALUNO {aluno_id}: {resp_exclusao.text}")
                raise HTTPException(500, f"Falha ao excluir aluno: {resp_exclusao.text}")
            
            enviar_log_discord(f"✅ Conta do aluno com ID {aluno_id} (CPF: {cpf}) excluída com sucesso.")
            return {"message": "Conta do aluno excluída com sucesso."}

        if evento != "order_approved":
            return {"message": "Evento ignorado"}

        customer = payload.get("Customer", {})
        nome = customer.get("full_name")
        cpf = customer.get("CPF", "").replace(".", "").replace("-", "")
        email = customer.get("email")
        celular = customer.get("mobile") or "(00) 00000-0000"
        
        plano_assinatura = payload.get("Product", {}).get("product_offer_name")
        metodo_pagamento = payload.get("payment_method", "Não informado")

        cursos_ids = obter_cursos_ids(plano_assinatura)
        if not cursos_ids: raise HTTPException(400, f"Plano '{plano_assinatura}' não mapeado.")

        dados_aluno_om = {
            "token": TOKEN_UNIDADE, "nome": nome, "data_nascimento": "2000-01-01",
            "email": email, "fone": celular, "senha": "123456", "celular": celular,
            "doc_cpf": cpf, "doc_rg": "0", "pais": "Brasil", "uf": customer.get("state", ""),
            "cidade": customer.get("city", ""), "endereco": f"{customer.get('street', '')}, {customer.get('number', '')}",
            "complemento": customer.get("complement", ""), "bairro": customer.get("neighborhood", ""), "cep": customer.get("zipcode", ""),
        }
        
        resp_cadastro = requests.post(f"{OM_BASE}/alunos", data=dados_aluno_om, headers={"Authorization": f"Basic {BASIC_B64}"})
        aluno_response = resp_cadastro.json()
        if not resp_cadastro.ok or aluno_response.get("status") != "true":
            enviar_log_discord(f"❌ ERRO CADASTRO: {resp_cadastro.text}")
            raise HTTPException(500, f"Falha ao criar aluno: {resp_cadastro.text}")
        
        aluno_id = aluno_response.get("data", {}).get("id")
        if not aluno_id: raise HTTPException(500, "ID do aluno não retornado após cadastro.")

        dados_matricula = {"token": TOKEN_UNIDADE, "cursos": ",".join(map(str, cursos_ids))}
        resp_matricula = requests.post(f"{OM_BASE}/alunos/matricula/{aluno_id}", data=dados_matricula, headers={"Authorization": f"Basic {BASIC_B64}"})
        if not resp_matricula.ok or resp_matricula.json().get("status") != "true":
            enviar_log_discord(f"❌ ERRO MATRÍCULA (Aluno ID {aluno_id}): {resp_matricula.text}")
            raise HTTPException(500, f"Falha ao matricular: {resp_matricula.text}")

        enviar_whatsapp_chatpro(nome, celular, plano_assinatura, cpf)

        adicionar_aluno_planilha({
            "nome": nome, "celular": celular, "email": email, "cpf": cpf,
            "metodo_pagamento": metodo_pagamento, "plano_assinatura": plano_assinatura,
        })

        return {"message": "Aluno processado com sucesso!", "aluno_id": aluno_id}

    except HTTPException as http_exc:
        enviar_log_discord(f"❌ Erro de HTTP tratado: {http_exc.status_code} - {http_exc.detail}")
        raise http_exc
    except Exception as e:
        enviar_log_discord(f"❌ EXCEÇÃO GERAL NO PROCESSAMENTO: {e}")
        raise HTTPException(500, str(e))

# --- Rotas da API ---

@router.post("/webhook")
async def webhook_kiwify(request: Request):
    payload = await request.json()
    order_payload = payload.get("order", payload)
    return await _process_webhook(order_payload)

@router.post("/")
async def webhook_root(request: Request):
    payload = await request.json()
    order_payload = payload.get("order", payload)
    return await _process_webhook(order_payload)

@router.get("/secure/refresh-all")
async def secure_refresh_all():
    """Força a atualização manual do token e do cache de cursos."""
    token_ok = obter_token_unidade()
    atualizar_cache_cursos_om()
    if token_ok:
        return "🔐 Token e cache de cursos atualizados com sucesso!"
    return JSONResponse(content="❌ Falha ao atualizar token", status_code=500)

# --- Inicialização da Aplicação ---
@router.on_event("startup")
async def startup_event():
    """Executa na inicialização da aplicação."""
    obter_token_unidade()
    atualizar_cache_cursos_om()
