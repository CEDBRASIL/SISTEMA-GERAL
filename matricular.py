"""
matricular.py – Este arquivo agora é responsável por iniciar a criação de assinaturas (pré-aprovações)
dinamicamente no Mercado Pago (PRODUÇÃO).
Ele também mantém o endpoint para gerar descrição de curso com Gemini API.
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
OM_BASE = os.getenv("OM_BASE") # Mantido, embora não usado diretamente neste arquivo
BASIC_B64 = os.getenv("BASIC_B64") # Mantido
UNIDADE_ID = os.getenv("UNIDADE_ID") # Mantido
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
THANK_YOU_PAGE_URL = os.getenv("THANK_YOU_PAGE_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# O ID do plano de pré-aprovação de produção (fixo)
MP_PREAPPROVAL_PLAN_ID = os.getenv("MP_PREAPPROVAL_PLAN_ID")


# ──────────────────────────────────────────────────────────
# Armazenamento Temporário de Matrículas Pendentes (para produção)
# ATENÇÃO: Em produção, isso DEVE ser um banco de dados persistente!
# `webhook.py` precisará acessar esses dados.
# ──────────────────────────────────────────────────────────
PENDING_ENROLLMENTS: Dict[str, Dict] = {}


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
# NOVO ENDPOINT: Iniciar Assinatura (Cria pré-aprovação dinamicamente)
# ──────────────────────────────────────────────────────────
@router.post("/initiate-subscription")
async def initiate_subscription(body: dict, request: Request):
    nome = body.get("nome")
    whatsapp = body.get("whatsapp")
    email = body.get("email", "")
    cursos_nomes = body.get("cursos", []) # Assumindo que o frontend envia 'cursos'

    if not nome or not whatsapp or not cursos_nomes:
        _log(f"Dados inválidos para iniciar assinatura: Nome='{nome}', WhatsApp='{whatsapp}', Cursos='{cursos_nomes}'")
        raise HTTPException(400, detail="Nome, whatsapp e pelo menos um curso são obrigatórios para iniciar a assinatura.")

    if not email:
        _log("AVISO: Email não fornecido. Usando placeholder para Mercado Pago.")
        timestamp_uuid = uuid.uuid4().hex[:8]
        email = f"user_{timestamp_uuid}@placeholder.ced.com" # Email dummy para produção se não fornecido

    if not MP_PREAPPROVAL_PLAN_ID:
        _log("ERRO CRÍTICO: MP_PREAPPROVAL_PLAN_ID não configurado no ambiente para produção.")
        raise HTTPException(500, detail="Configuração de plano de assinatura indisponível.")

    if not THANK_YOU_PAGE_URL:
        _log("ERRO CRÍTICO: THANK_YOU_PAGE_URL não configurada no ambiente para produção.")
        raise HTTPException(500, detail="Configuração de retorno de pagamento indisponível.")

    if not sdk_matricular:
        _log("ERRO CRÍTICO: SDK do Mercado Pago não inicializado em matricular.py.")
        raise HTTPException(500, detail="Serviço de pagamento indisponível no momento (SDK Error).")

    external_reference = str(uuid.uuid4()) # ID único para esta transação no seu sistema

    try:
        # Armazena os dados do aluno para que o webhook possa recuperá-los
        # Em produção, isso DEVE ser salvo em um banco de dados persistente!
        PENDING_ENROLLMENTS[external_reference] = {
            "nome": nome,
            "whatsapp": whatsapp,
            "email": email,
            "cursos_nomes": cursos_nomes,
            "timestamp": datetime.now().isoformat(),
            "status": "pending_preapproval_creation"
        }
        _log(f"Dados do aluno para {nome} armazenados temporariamente com external_reference: {external_reference}")

        base_url = str(request.base_url)
        notification_url = f"{base_url.rstrip('/')}/api/webhook/mercadopago"
        _log(f"URL de notificação para MP configurada como: {notification_url}")

        # Dados para criar a pré-aprovação dinâmica (assinatura)
        preapproval_data = {
            "preapproval_plan_id": MP_PREAPPROVAL_PLAN_ID,
            "payer_email": email,
            "back_url": THANK_YOU_PAGE_URL,
            "external_reference": external_reference,
            "notification_url": notification_url,
            "reason": f"Assinatura Mensal: {cursos_nomes[0] if cursos_nomes else 'Curso Online'}", # Motivo da assinatura
        }

        _log(f"Criando pré-aprovação MP (PRODUÇÃO) com dados: {preapproval_data}")
        preapproval_response_dict = sdk_matricular.preapproval().create(preapproval_data)

        if preapproval_response_dict and preapproval_response_dict.get("status") in [200, 201]:
            response_data = preapproval_response_dict.get("response", {})
            init_point = response_data.get("init_point")
            mp_preapproval_id = response_data.get("id")

            if not init_point or not mp_preapproval_id:
                _log(f"ERRO: init_point ou ID da pré-aprovação ausentes na resposta do MP: {response_data}")
                PENDING_ENROLLMENTS.pop(external_reference, None)
                raise HTTPException(500, detail="Falha ao obter dados da criação da assinatura MP.")

            _log(f"Pré-aprovação MP (PRODUÇÃO) criada (ID: {mp_preapproval_id}). Redirect: {init_point}")
            PENDING_ENROLLMENTS[external_reference]["mp_preapproval_id"] = mp_preapproval_id
            PENDING_ENROLLMENTS[external_reference]["status"] = "preapproval_created_redirect_pending"

            return {
                "status": "ok",
                "message": "Assinatura iniciada, redirecionando para o pagamento.",
                "redirect_url": init_point,
                "preapproval_id": mp_preapproval_id, # Retorna o preapproval_id para o frontend
                "external_reference": external_reference
            }
        else:
            error_details = preapproval_response_dict.get('response', preapproval_response_dict) if preapproval_response_dict else "Resposta vazia"
            status_code = preapproval_response_dict.get('status', 'N/A') if preapproval_response_dict else 'N/A'
            _log(f"Erro ao criar pré-aprovação MP (PRODUÇÃO): Status {status_code} - Detalhes: {error_details}")
            PENDING_ENROLLMENTS.pop(external_reference, None)
            raise HTTPException(status_code=int(status_code) if str(status_code).isdigit() else 500, detail=error_details.get("message", "Falha ao iniciar a assinatura com Mercado Pago."))

    except Exception as e:
        _log(f"Erro GERAL em initiate_subscription: {str(e)} (Tipo: {type(e)})")
        if external_reference in PENDING_ENROLLMENTS:
            PENDING_ENROLLMENTS.pop(external_reference, None)
        raise HTTPException(500, detail=f"Erro interno no servidor ao processar assinatura: {str(e)}")


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
        _log(f"Erro HTTP da API Gemini para '{course_name}': {http_err}. Resposta: {http_err.response.text}")
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
