"""
sandbox_matricular.py – Este arquivo agora é usado para armazenar temporariamente os dados do aluno
no ambiente de sandbox antes do redirecionamento para o Mercado Pago.
Ele também mantém o endpoint para gerar descrição de curso com Gemini API.
"""

import os
from typing import List, Tuple, Optional, Dict
import requests
from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone 
import uuid 
from cursos import CURSOS_OM # Assume que cursos.py existe
import json 

router = APIRouter()

# ──────────────────────────────────────────────────────────
# Variáveis de Ambiente (Puxadas via os.getenv)
# ──────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "") 

# URL do Webhook do Discord para logs de eventos (colocado diretamente no código conforme solicitado)
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1377838283975036928/IgVvwyrBBWflKyXbIU9dgH4PhLwozHzrf-nJpj3w7dsZC-Ds9qN8_Toym3Tnbj-3jdU4"

# ──────────────────────────────────────────────────────────
# Armazenamento Temporário de Matrículas Pendentes (CRÍTICO PARA O NOVO FLUXO)
# ATENÇÃO: Em produção, isso DEVE ser um banco de dados persistente!
# Esta é uma solução em memória para fins de teste/sandbox.
# ──────────────────────────────────────────────────────────
PENDING_ENROLLMENTS: Dict[str, Dict] = {}

# ──────────────────────────────────────────────────────────
# Funções Auxiliares de Logging
# ──────────────────────────────────────────────────────────
def _log(msg: str):
    """Função de logging simples para SANDBOX."""
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] [Sandbox Matricular] {msg}")

# ──────────────────────────────────────────────────────────
# Configuração Mercado Pago SDK (Não mais usado para criar preferências aqui)
# ──────────────────────────────────────────────────────────
# sdk_matricular_sandbox = None # Removido, pois não criamos mais preferências aqui.


# ──────────────────────────────────────────────────────────
# NOVO ENDPOINT: Armazenar Dados do Aluno Temporariamente
# ──────────────────────────────────────────────────────────
@router.post("/store-student-data")
async def store_student_data(body: dict):
    nome = body.get("nome")
    whatsapp = body.get("whatsapp")
    email = body.get("email", "")
    cursos_nomes = body.get("cursos", [])

    if not nome or not whatsapp or not cursos_nomes:
        _log(f"Dados inválidos para armazenar: Nome='{nome}', WhatsApp='{whatsapp}', Cursos='{cursos_nomes}'")
        raise HTTPException(400, detail="Nome, whatsapp e pelo menos um curso são obrigatórios para armazenar dados.")
    
    external_reference = str(uuid.uuid4()) # Gerar um ID único para esta transação

    PENDING_ENROLLMENTS[external_reference] = {
        "nome": nome,
        "whatsapp": whatsapp,
        "email": email,
        "cursos_nomes": cursos_nomes,
        "timestamp": datetime.now().isoformat(),
        "status": "data_stored_pending_mp_redirect"
    }
    _log(f"Dados do aluno para {nome} armazenados temporariamente com external_reference: {external_reference}")

    # Enviar notificação para o Discord sobre o armazenamento inicial
    discord_log_message = (
        f"📝 **Dados de Aluno Armazenados (SANDBOX)!** 📝\n"
        f"**Aluno:** {nome}\n"
        f"**WhatsApp:** {whatsapp}\n"
        f"**E-mail:** {email}\n"
        f"**Curso(s):** {', '.join(cursos_nomes)}\n"
        f"**Ref. Externa (Temp ID):** `{external_reference}`\n"
        f"Status: `Aguardando redirecionamento para MP`"
    )
    _send_discord_message(discord_log_message)

    return {
        "status": "ok",
        "message": "Dados do aluno armazenados temporariamente. Use o external_reference para o redirecionamento.",
        "external_reference": external_reference
    }


# ──────────────────────────────────────────────────────────
# Funções Auxiliares de Discord
# ──────────────────────────────────────────────────────────
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
        response.raise_for_status() 
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
