"""
matricular.py – Este arquivo agora contém apenas o endpoint para gerar descrição de curso com Gemini API.
A lógica de iniciação de pagamento e matrícula foi movida ou será tratada por outros módulos.
"""

import os
from typing import List, Tuple, Optional, Dict
import requests
from fastapi import APIRouter, HTTPException, Request
from datetime import datetime
import json
from cursos import CURSOS_OM # Presumo que CURSOS_OM esteja definido em cursos.py

router = APIRouter()

# ──────────────────────────────────────────────────────────
# Variáveis de Ambiente (Puxadas via os.getenv)
# ──────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# ──────────────────────────────────────────────────────────
# Funções Auxiliares de Logging
# ──────────────────────────────────────────────────────────
def _log(msg: str):
    """Função de logging simples para matricular.py."""
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] [Matricular] {msg}")

# ──────────────────────────────────────────────────────────
# Endpoint de Matrícula (REMOVIDO - Lógica movida para outro lugar)
# O endpoint principal de iniciação de pagamento foi removido deste arquivo.
# ──────────────────────────────────────────────────────────

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
