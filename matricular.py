"""
matricular.py – Prepara o processo de matrícula e pagamento com Mercado Pago (PRODUÇÃO).
A matrícula final no sistema OM será feita via webhook, chamando o endpoint /cadastrar.
Inclui endpoint para gerar descrição de curso com Gemini API.
"""

import os
import threading
from typing import List, Tuple, Optional, Dict
import requests
from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone 
import uuid 
from cursos import CURSOS_OM # Presumo que CURSOS_OM esteja definido em cursos.py
import mercadopago # Importar o SDK do Mercado Pago

import json # Para lidar com JSON da resposta da API Gemini

router = APIRouter()

# ──────────────────────────────────────────────────────────
# Variáveis de Ambiente (Puxadas via os.getenv)
# ──────────────────────────────────────────────────────────
OM_BASE = os.getenv("OM_BASE")
BASIC_B64 = os.getenv("BASIC_B64")
UNIDADE_ID = os.getenv("UNIDADE_ID")
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
THANK_YOU_PAGE_URL = os.getenv("THANK_YOU_PAGE_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# ──────────────────────────────────────────────────────────
# Armazenamento Temporário de Matrículas Pendentes
# ATENÇÃO: Em produção, isso deve ser um banco de dados persistente!
# `webhook.py` precisará acessar esses dados.
# ──────────────────────────────────────────────────────────
PENDING_ENROLLMENTS: Dict[str, Dict] = {}
# CPF_PREFIXO e cpf_lock não são mais usados aqui, pois a lógica de matrícula OM foi movida.
# CPF_PREFIXO = "20254158"
# cpf_lock = threading.Lock()

# ──────────────────────────────────────────────────────────
# Funções Auxiliares de Logging
# ──────────────────────────────────────────────────────────
def _log(msg: str):
    """Função de logging simples para matricular.py."""
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] [Matricular] {msg}")

# ──────────────────────────────────────────────────────────
# Configuração Mercado Pago SDK
# ──────────────────────────────────────────────────────────
sdk_matricular = None
if not MP_ACCESS_TOKEN:
    _log("ERRO CRÍTICO: MP_ACCESS_TOKEN não configurado para matricular.py. A integração com Mercado Pago NÃO FUNCIONARÁ.")
else:
    try:
        sdk_matricular = mercadopago.SDK(access_token=MP_ACCESS_TOKEN)
        _log("SDK Mercado Pago inicializado com sucesso em matricular.py.")
    except Exception as e:
        _log(f"ERRO CRÍTICO ao inicializar SDK Mercado Pago em matricular.py: {e}. A integração com Mercado Pago PODE NÃO FUNCIONAR.")

# ──────────────────────────────────────────────────────────
# Funções de Lógica de Negócio (REMOVIDAS OU SIMPLIFICADAS)
# A lógica de matrícula OM foi movida para cadastrar.py
# ──────────────────────────────────────────────────────────
# As funções _obter_token_unidade, _total_alunos, _proximo_cpf, _matricular_om, _cadastrar_aluno, matricular_aluno_final
# e _nome_para_ids foram removidas deste arquivo, pois a lógica de matrícula OM
# será tratada pelo novo endpoint de 'cadastrar'.


# ──────────────────────────────────────────────────────────
# Endpoint de Matrícula (Inicia Pagamento MP - PRODUÇÃO)
# ──────────────────────────────────────────────────────────
@router.post("/")
async def endpoint_iniciar_matricula(body: dict, request: Request): 
    nome = body.get("nome")
    whatsapp = body.get("whatsapp")
    email = body.get("email", "") 
    cursos_nomes = body.get("cursos", [])
    
    if not nome or not whatsapp or not cursos_nomes:
        _log(f"Dados inválidos para iniciar matrícula: Nome='{nome}', WhatsApp='{whatsapp}', Cursos='{cursos_nomes}'")
        raise HTTPException(400, detail="Nome, whatsapp e pelo menos um curso são obrigatórios.")
    
    if not email: 
        _log("AVISO: Email não fornecido. Usando placeholder para Mercado Pago.")
        timestamp_uuid = uuid.uuid4().hex[:8]
        email = f"user_{timestamp_uuid}@placeholder.ced.com"

    curso_principal_nome = cursos_nomes[0] if cursos_nomes else "Matrícula Curso Online"
    
    if not THANK_YOU_PAGE_URL: 
        _log("ERRO CRÍTICO: THANK_YOU_PAGE_URL não configurada no ambiente.")
        raise HTTPException(500, detail="Configuração de pagamento indisponível (RETURN_URL).")

    if not sdk_matricular:
        _log("ERRO CRÍTICO: SDK do Mercado Pago não inicializado em matricular.py.")
        raise HTTPException(500, detail="Serviço de pagamento indisponível no momento (SDK Error).")

    pending_enrollment_id = str(uuid.uuid4())
    
    try:
        # Armazena os dados do aluno para que o webhook possa recuperá-los
        PENDING_ENROLLMENTS[pending_enrollment_id] = {
            "nome": nome, "whatsapp": whatsapp, "email": email,
            "cursos_nomes": cursos_nomes, "status": "pending_payment",
            "timestamp": datetime.now().isoformat()
        }
        _log(f"Matrícula pendente ID: {pending_enrollment_id} para {nome} armazenada.")

        base_url = str(request.base_url) 
        notification_url = f"{base_url.rstrip('/')}/api/webhook/mercadopago"
        _log(f"URL de notificação para MP configurada como: {notification_url}")

        # --- MODIFICAÇÃO PARA ASSINATURA DINÂMICA ---
        # Para pagamentos únicos, use a API de preferências (checkout_pro)
        # Para assinaturas, use a API de preapproval
        # O código original parecia misturar conceitos de pagamento único e assinatura.
        # Vou assumir que este endpoint é para pagamentos *únicos* que usam checkout_pro.
        # Se for para assinaturas, a estrutura `preapproval_data` está mais próxima.
        # Vou usar a estrutura de PREFERÊNCIA de pagamento (para checkout pro) que é mais comum para "matrícula única".
        
        preference_data = {
            "items": [
                {
                    "title": f"Pagamento Único: {curso_principal_nome}",
                    "quantity": 1,
                    "unit_price": 49.90, # Valor fixo para teste, ajuste conforme sua lógica
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
                "success": THANK_YOU_PAGE_URL,
                "failure": THANK_YOU_PAGE_URL, 
                "pending": THANK_YOU_PAGE_URL   
            },
            "auto_return": "approved", # 'approved' ou 'all'
            "statement_descriptor": "CED Educ" # Máximo 10 caracteres
        }
        
        _log(f"Criando Preferência de Pagamento MP (PRODUÇÃO) com dados: {preference_data}")
        preference_response_dict = sdk_matricular.preference().create(preference_data)
        
        _log(f"RESPOSTA COMPLETA DO MP (Preferência de Pagamento): {preference_response_dict}")
        
        if preference_response_dict and preference_response_dict.get("status") == 201: 
            response_data = preference_response_dict.get("response", {})
            init_point = response_data.get("init_point") # Para produção, é 'init_point'
            mp_preference_id = response_data.get("id") 

            if not init_point or not mp_preference_id:
                _log(f"ERRO: init_point ou ID da preferência ausentes na resposta do MP: {response_data}")
                PENDING_ENROLLMENTS.pop(pending_enrollment_id, None) 
                raise HTTPException(500, detail="Falha ao obter dados da criação da preferência MP.")

            _log(f"Preferência de Pagamento MP (PRODUÇÃO) criada (ID: {mp_preference_id}). Redirect: {init_point}")
            PENDING_ENROLLMENTS[pending_enrollment_id]["mp_preference_id"] = mp_preference_id 
            
            return {
                "status": "ok",
                "message": "Matrícula iniciada, redirecionando para o pagamento.",
                "redirect_url": init_point,
                "pending_enrollment_id": pending_enrollment_id,
                "mp_preference_id": mp_preference_id
            }
        else:
            error_details = preference_response_dict.get('response', preference_response_dict) if preference_response_dict else "Resposta vazia"
            status_code = preference_response_dict.get('status', 'N/A') if preference_response_dict else 'N/A'
            _log(f"Erro ao criar Preferência de Pagamento MP (PRODUÇÃO): Status {status_code} - Detalhes: {error_details}")
            PENDING_ENROLLMENTS.pop(pending_enrollment_id, None) 
            
            mp_error_message = "Falha ao iniciar o pagamento com Mercado Pago."
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
            _log(f"Erro no SDK do Mercado Pago: Status {getattr(mp_e, 'status_code', 'N/A')} - Mensagem: {getattr(mp_e, 'message', str(mp_e))} - Causa: {getattr(mp_e, 'cause', 'N/A')}")
            
            error_detail = f"Erro no pagamento ({getattr(mp_e, 'status_code', 'N/A')}): {getattr(mp_e, 'message', str(mp_e))}"
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
            _log(f"Erro GERAL em endpoint_iniciar_matricula: {str(mp_e)} (Tipo: {type(mp_e)})")
            if pending_enrollment_id in PENDING_ENROLLMENTS: 
                PENDING_ENROLLMENTS.pop(pending_enrollment_id, None)
            raise HTTPException(500, detail=f"Erro interno no servidor ao processar matrícula: {str(mp_e)}")

# ──────────────────────────────────────────────────────────
# ENDPOINT: Gerar Descrição de Curso com Gemini API
# ──────────────────────────────────────────────────────────
@router.post("/generate-course-description")
async def generate_course_description(body: dict):
    course_name = body.get("course_name")

    if not course_name:
        raise HTTPException(400, detail="O nome do curso é obrigatório para gerar a descrição.")
    
    api_key_to_use = GEMINI_API_KEY 
    
    gemini_api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key_to_use}"

    prompt = f"Gere uma descrição envolvente e concisa para um curso de {course_name} focado em atrair novos alunos. Inclua 3-4 pontos-chave sobre o que o aluno aprenderá e os benefícios de se matricular. Use um tom entusiasmado e profissional. A descrição deve ter no máximo 150 palavras."
    
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}]
    }
    headers = {"Content-Type": "application/json"}

    try:
        _log(f"Enviando requisição para Gemini API para curso: {course_name}")
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
            _log(f"Descrição Gemini gerada para '{course_name}': {generated_text[:70]}...")
            return {"status": "ok", "description": generated_text}
        else:
            _log(f"Resposta inesperada ou incompleta da API Gemini para '{course_name}': {gemini_result}")
            error_message_gemini = "Falha ao gerar descrição do curso (resposta inválida da IA)."
            if gemini_result and gemini_result.get("error") and gemini_result["error"].get("message"):
                error_message_gemini = gemini_result["error"]["message"]
            elif gemini_result and gemini_result.get("promptFeedback") and gemini_result["promptFeedback"].get("blockReason"):
                error_message_gemini = f"Conteúdo bloqueado pela IA: {gemini_result['promptFeedback']['blockReason']}"
            raise HTTPException(500, detail=error_message_gemini)

    except requests.exceptions.Timeout:
        _log(f"Timeout ao conectar com a API Gemini para '{course_name}'.")
        raise HTTPException(504, detail="Serviço de geração de descrição demorou muito para responder.")
    except requests.exceptions.HTTPError as http_err:
        _log(f"Erro HTTP da API Gemini para '{course_name}': {http_err}. Resposta: {http_err.text}")
        error_detail_gemini = f"Erro da API Gemini ({http_err.response.status_code})."
        try:
            err_json = http_err.response.json()
            if err_json.get("error", {}).get("message"):
                error_detail_gemini = err_json["error"]["message"]
        except ValueError:
            pass 
        raise HTTPException(http_err.response.status_code, detail=error_detail_gemini)

    except requests.exceptions.RequestException as e:
        _log(f"Erro de conexão com a API Gemini para '{course_name}': {e}")
        raise HTTPException(503, detail=f"Erro de comunicação ao gerar descrição: {e}") 
    except ValueError: 
        _log(f"Resposta inválida (não JSON) da API Gemini: {response.text if 'response' in locals() else 'N/A'}")
        raise HTTPException(500, detail="Falha ao processar resposta da IA (formato inválido).")
    except Exception as e:
        _log(f"Erro geral ao gerar descrição para '{course_name}': {e} (Tipo: {type(e)})")
        raise HTTPException(500, detail=f"Erro interno ao gerar descrição: {e}")
