"""
sandbox_matricular.py – TESTE: Prepara o processo de matrícula e pagamento com Mercado Pago (SANDBOX).
A matrícula final no sistema OM será feita por um endpoint separado (cadastrar.py),
simulando o fluxo de webhook.
Inclui endpoint para gerar descrição de curso com Gemini API.
"""

import os
import threading
from typing import List, Tuple, Optional, Dict
import requests
from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone 
import uuid 
from cursos import CURSOS_OM # Assume que cursos.py existe
import mercadopago 
import json 

router = APIRouter()

# ──────────────────────────────────────────────────────────
# Variáveis de Ambiente (Puxadas via os.getenv)
# ──────────────────────────────────────────────────────────
OM_BASE = os.getenv("OM_BASE") # Base URL do sistema OM
BASIC_B64 = os.getenv("BASIC_B64") # Credenciais Basic Auth para OM
UNIDADE_ID = os.getenv("UNIDADE_ID") # ID da unidade no sistema OM

# TOKEN DE TESTE DO MERCADO PAGO
MP_TEST_ACCESS_TOKEN = os.getenv("MP_TEST_ACCESS_TOKEN") 

# URLs de retorno após o pagamento (para sandbox)
THANK_YOU_PAGE_URL = os.getenv("THANK_YOU_PAGE_URL_SANDBOX", os.getenv("THANK_YOU_PAGE_URL")) 

# Chave da API Gemini (pode ser a mesma, com valor padrão)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "") 

# Variáveis de Ambiente para ChatPro (REMOVIDAS DESTE ARQUIVO, AGORA NO CADASTRAR.PY)
# CHATPRO_URL = os.getenv("CHATPRO_URL")
# CHATPRO_TOKEN = os.getenv("CHATPRO_TOKEN")

# URL do Webhook do Discord para logs de eventos (colocado diretamente no código conforme solicitado)
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1377838283975036928/IgVvwyrBBWflKyXbIU9dgH4PhLwozHzrf-nJpj3w7dsZC-Ds9qN8_Toym3Tnbj-3jdU4"

# ──────────────────────────────────────────────────────────
# Armazenamento Temporário de Matrículas Pendentes
# ──────────────────────────────────────────────────────────
PENDING_ENROLLMENTS: Dict[str, Dict] = {}
# CPF_PREFIXO e cpf_lock não são mais usados aqui para matrícula, mas mantidos se houver outra dependência
CPF_PREFIXO = "20254158" # Prefixo de CPF para alunos de teste no sandbox
cpf_lock = threading.Lock() # Lock para garantir geração de CPF sequencial segura

# ──────────────────────────────────────────────────────────
# Funções Auxiliares de Logging
# ──────────────────────────────────────────────────────────
def _log(msg: str):
    """Função de logging simples para SANDBOX."""
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] [Sandbox Matricular] {msg}")

# ──────────────────────────────────────────────────────────
# Configuração Mercado Pago SDK (SANDBOX)
# ──────────────────────────────────────────────────────────
sdk_matricular_sandbox = None
if not MP_TEST_ACCESS_TOKEN:
    _log("ERRO CRÍTICO SANDBOX: MP_TEST_ACCESS_TOKEN não configurado. A integração com Mercado Pago (Sandbox) NÃO FUNCIONARÁ.")
    _log("Configure a variável de ambiente MP_TEST_ACCESS_TOKEN com seu token de teste.")
else:
    try:
        sdk_matricular_sandbox = mercadopago.SDK(access_token=MP_TEST_ACCESS_TOKEN)
        _log("SDK Mercado Pago (Sandbox) inicializado com sucesso.")
    except Exception as e:
        _log(f"ERRO CRÍTICO SANDBOX ao inicializar SDK Mercado Pago: {e}. A integração com Mercado Pago (Sandbox) PODE NÃO FUNCIONAR.")

# ──────────────────────────────────────────────────────────
# Funções de Lógica de Negócio (matrícula, etc.) - REMOVIDAS OU SIMPLIFICADAS
# As funções de OM agora residem principalmente em 'cadastrar.py'
# ──────────────────────────────────────────────────────────
# As funções _obter_token_unidade, _total_alunos, _proximo_cpf, _matricular_om, _cadastrar_aluno, matricular_aluno_final
# e _nome_para_ids foram removidas ou simplificadas deste arquivo, pois a lógica de matrícula OM
# será tratada pelo novo endpoint de 'cadastrar'.
# Apenas _nome_para_ids é mantida se for usada para a descrição do curso, mas não para matrícula OM.
# Para manter este arquivo mínimo e focado apenas na criação da preferência MP e Discord log da INICIAÇÃO:
# Removendo todas as funções relacionadas à matrícula OM.

def _send_discord_message(message: str):
    """Envia uma mensagem para o webhook do Discord."""
    if not DISCORD_WEBHOOK_URL:
        _log("AVISO SANDBOX: DISCORD_WEBHOOK_URL não configurada. Mensagem Discord NÃO será enviada.")
        return

    payload = {
        "content": message
    }
    headers = {
        "Content-Type": "application/json"
    }

    try:
        _log(f"Enviando mensagem Discord SANDBOX...")
        response = requests.post(DISCORD_WEBHOOK_URL, headers=headers, data=json.dumps(payload), timeout=10)
        response.raise_for_status() # Levanta um erro para status HTTP 4xx/5xx
        _log(f"Mensagem Discord SANDBOX enviada com sucesso. Status: {response.status_code}")
    except requests.exceptions.Timeout:
        _log(f"Timeout SANDBOX ao enviar mensagem Discord.")
    except requests.exceptions.HTTPError as http_err:
        _log(f"Erro HTTP SANDBOX ao enviar mensagem Discord: {http_err}. Resposta: {http_err.text}")
    except requests.exceptions.RequestException as e:
        _log(f"Erro de conexão SANDBOX ao enviar mensagem Discord: {e}")
    except Exception as e:
        _log(f"Erro inesperado SANDBOX ao enviar mensagem Discord: {e}")

# ──────────────────────────────────────────────────────────
# Endpoint de Matrícula (Inicia Pagamento ÚNICO MP - SANDBOX)
# ──────────────────────────────────────────────────────────
@router.post("/") 
async def endpoint_iniciar_matricula_sandbox(body: dict, request: Request): 
    nome = body.get("nome")
    whatsapp = body.get("whatsapp")
    email = body.get("email", "") 
    cursos_nomes = body.get("cursos", [])
    
    if not nome or not whatsapp or not cursos_nomes:
        _log(f"Dados inválidos SANDBOX para iniciar pagamento único: Nome='{nome}', WhatsApp='{whatsapp}', Cursos='{cursos_nomes}'")
        raise HTTPException(400, detail="Nome, whatsapp e pelo menos um curso são obrigatórios (Sandbox).")
    
    if not email: 
        _log("AVISO SANDBOX: Email não fornecido. Usando placeholder para Mercado Pago.")
        timestamp_uuid = uuid.uuid4().hex[:8]
        email = f"user_{timestamp_uuid}@placeholder.ced.sandbox.com" 

    curso_principal_nome = cursos_nomes[0] if cursos_nomes else "Curso Online (Sandbox)" # Ajustado para pagamento único
    
    thank_you_url_final = THANK_YOU_PAGE_URL
    if not thank_you_url_final: 
        _log("ERRO CRÍTICO SANDBOX: THANK_YOU_PAGE_URL (ou THANK_YOU_PAGE_URL_SANDBOX) não configurada.")
        raise HTTPException(500, detail="Configuração de pagamento indisponível (RETURN_URL Sandbox).")

    if not sdk_matricular_sandbox:
        _log("ERRO CRÍTICO SANDBOX: SDK do Mercado Pago (Sandbox) não inicializado.")
        raise HTTPException(500, detail="Serviço de pagamento indisponível no momento (SDK Error Sandbox).")

    pending_enrollment_id = str(uuid.uuid4()) # Usado como external_reference
    
    try:
        PENDING_ENROLLMENTS[pending_enrollment_id] = {
            "nome": nome, "whatsapp": whatsapp, "email": email,
            "cursos_nomes": cursos_nomes, "status": "pending_single_payment_sandbox", # Novo status
            "timestamp": datetime.now().isoformat()
        }
        _log(f"Pagamento único pendente SANDBOX ID: {pending_enrollment_id} para {nome} armazenada.")

        base_url = str(request.base_url)
        # A notification_url para pagamentos únicos é importante para saber o status final.
        notification_url_path = os.getenv("MP_SANDBOX_NOTIFICATION_PATH", "/api/webhook/mercadopago") 
        notification_url = f"{base_url.rstrip('/')}{notification_url_path}"
        _log(f"URL de notificação SANDBOX para MP (Pagamento Único) configurada como: {notification_url}")

        # --- DADOS PARA PREFERÊNCIA DE CHECKOUT ---
        preference_data = {
            "items": [
                {
                    "title": f"Pagamento Único SANDBOX: {curso_principal_nome}",
                    "quantity": 1,
                    "unit_price": 49.90,
                }
            ],
            "payer": {
                "email": email,
                "name": nome.split(" ")[0] if nome else None,
                "surname": " ".join(nome.split(" ")[1:]) if nome and " " in nome else None,
            },
            "external_reference": pending_enrollment_id,
            "notification_url": notification_url,
            "back_urls": { 
                "success": thank_you_url_final,
                "failure": thank_you_url_final, 
                "pending": thank_you_url_final   
            },
            "auto_return": "approved", 
            "statement_descriptor": "CED Educ" 
        }
        # --- FIM DOS DADOS PARA PREFERÊNCIA DE CHECKOUT ---
        
        _log(f"Criando Preferência de Pagamento MP (SANDBOX) com dados: {preference_data}")
        preference_response_dict = sdk_matricular_sandbox.preference().create(preference_data)
        
        _log(f"RESPOSTA COMPLETA DO MP SANDBOX (Preferência de Pagamento): {preference_response_dict}")
        
        if preference_response_dict and preference_response_dict.get("status") == 201: 
            response_data = preference_response_dict.get("response", {})
            init_point = response_data.get("sandbox_init_point", response_data.get("init_point"))
            mp_preference_id = response_data.get("id") 
            
            if not init_point or not mp_preference_id:
                _log(f"ERRO SANDBOX: init_point/sandbox_init_point ou ID da preferência ausentes na resposta do MP: {response_data}")
                PENDING_ENROLLMENTS.pop(pending_enrollment_id, None) 
                raise HTTPException(500, detail="Falha SANDBOX ao obter dados da criação da preferência MP.")

            _log(f"Preferência de Pagamento MP (SANDBOX) criada (ID: {mp_preference_id}). Redirect: {init_point}")
            PENDING_ENROLLMENTS[pending_enrollment_id]["mp_preference_id"] = mp_preference_id 
            
            # -------------------------------------------------------------
            # Lógica de matrícula OM e ChatPro REMOVIDA daqui.
            # Agora será acionada pelo novo endpoint /matricular em cadastrar.py
            # -------------------------------------------------------------
            
            # -------------------------------------------------------------
            # AÇÃO: Enviar log para o Discord Bot (mantido aqui para log da INICIAÇÃO do pagamento)
            # -------------------------------------------------------------
            _log("Preparando para enviar log de evento para o Discord (iniciação de pagamento).") 
            discord_log_message = (
                f"🎉 **Nova Preferência de Pagamento SANDBOX Criada!** 🎉\n"
                f"**Aluno (Potencial):** {nome}\n"
                f"**WhatsApp:** {whatsapp}\n"
                f"**E-mail:** {email}\n"
                f"**Curso(s):** {', '.join(cursos_nomes)}\n"
                f"**Ref. Interna (Pending ID):** `{pending_enrollment_id}`\n"
                f"**ID Preferência MP:** `{mp_preference_id}`\n"
                f"**Status MP:** `Preferência Criada (201)`\n"
                f"**Link Checkout Sandbox:** {init_point}"
            )
            _send_discord_message(discord_log_message)
            # -------------------------------------------------------------

            return {
                "status": "ok_sandbox_payment",
                "message": "Pagamento Único SANDBOX iniciado, redirecionando para o checkout de teste.",
                "redirect_url": init_point,
                "pending_enrollment_id": pending_enrollment_id,
                "mp_preference_id": mp_preference_id
            }
        else:
            error_details = preference_response_dict.get('response', preference_response_dict) if preference_response_dict else "Resposta vazia"
            status_code = preference_response_dict.get('status', 'N/A') if preference_response_dict else 'N/A'
            _log(f"Erro SANDBOX ao criar Preferência de Pagamento MP: Status {status_code} - Detalhes: {error_details}")
            PENDING_ENROLLMENTS.pop(pending_enrollment_id, None) 
            
            mp_error_message = "Falha SANDBOX ao iniciar o pagamento único com Mercado Pago."
            if isinstance(error_details, dict) and error_details.get("message"):
                mp_error_message = error_details.get("message")
                if error_details.get("cause") and isinstance(error_details["cause"], list) and len(error_details["cause"]) > 0:
                    first_cause = error_details["cause"][0]
                    if isinstance(first_cause, dict) and first_cause.get("description"):
                        mp_error_message = first_cause.get("description")
                    elif isinstance(first_cause, str): 
                        mp_error_message = first_cause

            raise HTTPException(status_code= int(status_code) if str(status_code).isdigit() else 500, detail=mp_error_message)

    except Exception as mp_e: 
        is_mp_exception = hasattr(mp_e, 'status_code') and hasattr(mp_e, 'message')
        
        if is_mp_exception:
            _log(f"Erro SANDBOX no SDK do Mercado Pago (Pagamento Único): Status {getattr(mp_e, 'status_code', 'N/A')} - Mensagem: {getattr(mp_e, 'message', str(mp_e))} - Causa: {getattr(mp_e, 'cause', 'N/A')}")
            
            error_detail = f"Erro SANDBOX no pagamento único ({getattr(mp_e, 'status_code', 'N/A')}): {getattr(mp_e, 'message', str(mp_e))}"
            cause = getattr(mp_e, 'cause', None)
            if cause and isinstance(cause, list) and len(cause) > 0 and isinstance(cause[0], dict) and cause[0].get('description'):
                error_detail = cause[0].get('description')
            elif cause and isinstance(cause, str): 
                error_detail = cause

            http_status_code = getattr(mp_e, 'status_code', 500)
            if not isinstance(http_status_code, int):
                http_status_code = 500
            
            if pending_enrollment_id in PENDING_ENROLLMENTS: 
                PENDING_ENROLLMENTS.pop(pending_enrollment_id, None) 
            raise HTTPException(status_code=http_status_code, detail=error_detail)
        else:
            _log(f"Erro GERAL SANDBOX em endpoint_iniciar_matricula (Pagamento Único): {str(mp_e)} (Tipo: {type(mp_e)})")
            if pending_enrollment_id in PENDING_ENROLLMENTS: 
                PENDING_ENROLLMENTS.pop(pending_enrollment_id, None)
            raise HTTPException(500, detail=f"Erro interno SANDBOX no servidor ao processar pagamento único: {str(mp_e)}")

# ──────────────────────────────────────────────────────────
# ENDPOINT: Gerar Descrição de Curso com Gemini API (SANDBOX)
# ──────────────────────────────────────────────────────────
@router.post("/generate-course-description") 
async def generate_course_description_sandbox(body: dict):
    course_name = body.get("course_name")

    if not course_name:
        raise HTTPException(400, detail="O nome do curso é obrigatório para gerar a descrição (Sandbox).")
    
    api_key_to_use = GEMINI_API_KEY 
    
    gemini_api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key_to_use}"

    prompt = f"Gere uma descrição envolvente e concisa para um curso de {course_name} focado em atrair novos alunos. Inclua 3-4 pontos-chave sobre o que o aluno aprenderá e os benefícios de se matricular. Use um tom entusiasmado e profissional. A descrição deve ter no máximo 150 palavras."
    
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}]
    }
    headers = {"Content-Type": "application/json"}

    try:
        _log(f"Enviando requisição SANDBOX para Gemini API para curso: {course_name}")
        response = requests.post(gemini_api_url, headers=headers, data=json.dumps(payload), timeout=30)
        response.raise_for_status() 
        
        gemini_result = response.json()
        
        if (gemini_result and 
            gemini_result.get("candidates") and 
            isinstance(gemini_result["candidates"], list) and 
            len(gemini_result["candidates"]) > 0 and
            gemini_result["candidates"][0].get("content") and 
            gemini_result["candidates"][0]["content"].get("parts") and
            isinstance(gemini_result["candidates"][0]["content"]["parts"], list) and
            len(gemini_result["candidates"][0]["content"]["parts"]) > 0 and
            gemini_result["candidates"][0]["content"]["parts"][0].get("text")):
            
            generated_text = gemini_result["candidates"][0]["content"]["parts"][0]["text"]
            _log(f"Descrição Gemini SANDBOX gerada para '{course_name}': {generated_text[:70]}...")
            return {"status": "ok_sandbox", "description": generated_text}
        else:
            _log(f"Resposta inesperada ou incompleta SANDBOX da API Gemini para '{course_name}': {gemini_result}")
            error_message_gemini = "Falha SANDBOX ao gerar descrição do curso (resposta inválida da IA)."
            if gemini_result and gemini_result.get("error") and gemini_result["error"].get("message"):
                error_message_gemini = gemini_result["error"]["message"]
            elif gemini_result and gemini_result.get("promptFeedback") and gemini_result["promptFeedback"].get("blockReason"):
                error_message_gemini = f"Conteúdo bloqueado pela IA (Sandbox): {gemini_result['promptFeedback']['blockReason']}"
            raise HTTPException(500, detail=error_message_gemini)

    except requests.exceptions.Timeout:
        _log(f"Timeout SANDBOX ao conectar com a API Gemini para '{course_name}'.")
        raise HTTPException(504, detail="Serviço SANDBOX de geração de descrição demorou muito para responder.")
    except requests.exceptions.HTTPError as http_err:
        _log(f"Erro HTTP SANDBOX da API Gemini para '{course_name}': {http_err}. Resposta: {http_err.text}")
        error_detail_gemini = f"Erro SANDBOX da API Gemini ({http_err.response.status_code})."
        try:
            err_json = http_err.response.json()
            if err_json.get("error", {}).get("message"):
                error_detail_gemini = err_json["error"]["message"]
        except ValueError:
            pass 
        raise HTTPException(http_err.response.status_code, detail=error_detail_gemini)

    except requests.exceptions.RequestException as e:
        _log(f"Erro de conexão SANDBOX com a API Gemini para '{course_name}': {e}")
        raise HTTPException(503, detail=f"Erro de comunicação SANDBOX ao gerar descrição: {e}") 
    except ValueError: 
        _log(f"Resposta inválida (não JSON) SANDBOX da API Gemini: {response.text if 'response' in locals() else 'N/A'}")
        raise HTTPException(500, detail="Falha SANDBOX ao processar resposta da IA (formato inválido).")
    except Exception as e:
        _log(f"Erro geral SANDBOX ao gerar descrição para '{course_name}': {e} (Tipo: {type(e)})")
        raise HTTPException(500, detail=f"Erro interno SANDBOX ao gerar descrição: {e}")
