"""
matricular.py – Prepara o processo de matrícula e pagamento com Mercado Pago.
A matrícula final no sistema OM é feita via webhook.
Inclui endpoint para gerar descrição de curso com Gemini API.
"""

import os
import threading
from typing import List, Tuple, Optional, Dict
import requests
from fastapi import APIRouter, HTTPException, Request
from datetime import datetime
import uuid # Para gerar IDs únicos para as matrículas pendentes
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
MP_PREAPPROVAL_PLAN_ID = os.getenv("MP_PREAPPROVAL_PLAN_ID")
THANK_YOU_PAGE_URL = os.getenv("THANK_YOU_PAGE_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# ──────────────────────────────────────────────────────────
# Armazenamento Temporário de Matrículas Pendentes
# ──────────────────────────────────────────────────────────
PENDING_ENROLLMENTS: Dict[str, Dict] = {}
CPF_PREFIXO = "20254158"
cpf_lock = threading.Lock()

# ──────────────────────────────────────────────────────────
# Funções Auxiliares
# ──────────────────────────────────────────────────────────
def _log(msg: str):
    """Função de logging simples."""
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
# Funções de Lógica de Negócio (matrícula, etc.)
# ──────────────────────────────────────────────────────────
def _obter_token_unidade() -> str:
    if not all([OM_BASE, BASIC_B64, UNIDADE_ID]):
        _log("ERRO: Variáveis OM não configuradas (_obter_token_unidade).")
        raise RuntimeError("Variáveis OM não configuradas. Verifique ambiente.")
    url = f"{OM_BASE}/unidades/token/{UNIDADE_ID}"
    try:
        r = requests.get(url, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=8)
        r.raise_for_status()
        response_json = r.json()
        if response_json.get("status") == "true" and response_json.get("data", {}).get("token"):
            return response_json["data"]["token"]
        _log(f"Falha ao obter token da unidade. Resposta: {r.text}")
        raise RuntimeError(f"Falha ao obter token da unidade: {response_json.get('info', 'Resposta inesperada')}")
    except requests.RequestException as e:
        _log(f"Erro de conexão ao obter token da unidade: {e}")
        raise RuntimeError(f"Erro de conexão ao obter token da unidade: {e}")
    except ValueError: # JSONDecodeError herda de ValueError
        _log(f"Resposta inválida (não JSON) ao obter token da unidade: {r.text if 'r' in locals() else 'N/A'}")
        raise RuntimeError("Resposta inválida (não JSON) ao obter token da unidade.")


def _total_alunos() -> int:
    if not all([OM_BASE, BASIC_B64, UNIDADE_ID]):
        _log("ERRO: Variáveis OM não configuradas (_total_alunos).")
        raise RuntimeError("Variáveis OM não configuradas para _total_alunos.")
    
    # Tentativa 1: Endpoint /alunos/total
    url_total = f"{OM_BASE}/alunos/total/{UNIDADE_ID}"
    try:
        r_total = requests.get(url_total, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=8)
        r_total.raise_for_status()
        response_json_total = r_total.json()
        if response_json_total.get("status") == "true" and response_json_total.get("data", {}).get("total") is not None:
            return int(response_json_total["data"]["total"])
        _log(f"Endpoint /alunos/total não retornou sucesso ou total. Resposta: {r_total.text}. Tentando contagem alternativa.")
    except requests.RequestException as e:
        _log(f"Erro de conexão no endpoint /alunos/total: {e}. Tentando contagem alternativa.")
    except (ValueError, TypeError) as e: # JSONDecodeError ou erro de conversão para int
        _log(f"Erro ao processar resposta de /alunos/total: {e}. Resposta: {r_total.text if 'r_total' in locals() else 'N/A'}. Tentando contagem alternativa.")

    # Tentativa 2: Endpoint /alunos com filtro (fallback)
    url_list = f"{OM_BASE}/alunos?unidade_id={UNIDADE_ID}&cpf_like={CPF_PREFIXO}"
    try:
        r_list = requests.get(url_list, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=8)
        r_list.raise_for_status()
        response_json_list = r_list.json()
        if response_json_list.get("status") == "true" and "data" in response_json_list:
            return len(response_json_list["data"])
        _log(f"Falha ao apurar total de alunos (contagem alternativa). Resposta: {r_list.text}")
        raise RuntimeError(f"Falha ao apurar total de alunos (contagem alternativa): {response_json_list.get('info', 'Resposta inesperada')}")
    except requests.RequestException as e:
        _log(f"Erro de conexão na contagem alternativa de alunos: {e}")
        raise RuntimeError(f"Erro de conexão na contagem alternativa de alunos: {e}")
    except ValueError:
        _log(f"Resposta inválida (não JSON) na contagem alternativa de alunos: {r_list.text if 'r_list' in locals() else 'N/A'}")
        raise RuntimeError("Resposta inválida (não JSON) na contagem alternativa de alunos.")


def _proximo_cpf(incr:int=0)->str:
    with cpf_lock:
        try:
            seq = _total_alunos() + 1 + incr
            return CPF_PREFIXO + str(seq).zfill(3)
        except RuntimeError as e:
            _log(f"Erro ao obter total de alunos para gerar CPF: {e}. Usando fallback para CPF.")
            # Fallback muito simples, idealmente teria uma estratégia melhor
            timestamp_fallback = str(int(datetime.now().timestamp()))[-3:]
            return CPF_PREFIXO + timestamp_fallback.zfill(3)


def _matricular_om(aluno_id:str, cursos_ids:List[int], token:str)->bool:
    if not all([OM_BASE, BASIC_B64]):
        _log("ERRO: Variáveis OM não configuradas (_matricular_om).")
        raise RuntimeError("Variáveis OM não configuradas para _matricular_om.")
    payload = {"token": token, "cursos": ",".join(map(str, cursos_ids))}
    url = f"{OM_BASE}/alunos/matricula/{aluno_id}"
    try:
        r = requests.post(url, data=payload, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=10)
        r.raise_for_status() # Levanta exceção para erros HTTP 4xx/5xx
        _log(f"[MAT OM] Status: {r.status_code}, Resposta: {r.text[:120]}")
        response_json = r.json()
        return response_json.get("status") == "true"
    except requests.RequestException as e:
        _log(f"Erro de conexão ao matricular no OM: {e}")
        return False
    except ValueError: # JSONDecodeError
        _log(f"Resposta inválida (não JSON) ao matricular no OM: {r.text if 'r' in locals() else 'N/A'}")
        return False


def _cadastrar_aluno(nome:str, whatsapp:str, email:str, cursos_ids:List[int], token:str, cpf:Optional[str]=None)->Tuple[Optional[str],Optional[str]]:
    if not all([OM_BASE, BASIC_B64, UNIDADE_ID]):
        _log("ERRO: Variáveis OM não configuradas (_cadastrar_aluno).")
        raise RuntimeError("Variáveis OM não configuradas para _cadastrar_aluno.")
    
    final_cpf = cpf if cpf else _proximo_cpf()

    for i in range(5): # Tentar algumas vezes com CPF diferente se o primeiro falhar por duplicidade
        if not cpf and i > 0 : # Se não foi fornecido um CPF e não é a primeira tentativa
            final_cpf = _proximo_cpf(i)

        payload = {
            "token": token, "nome": nome,
            "email": email or f"{whatsapp}@nao-informado.com",
            "whatsapp": whatsapp, "fone": whatsapp, "celular": whatsapp,
            "data_nascimento": "2000-01-01", "doc_cpf": final_cpf, "doc_rg": "000000000",
            "pais": "Brasil", "uf": "DF", "cidade": "Brasília",
            "endereco": "Não informado", "bairro": "Centro", "cep": "70000-000",
            "complemento": "", "numero": "0", "unidade_id": UNIDADE_ID, "senha": "123456"
        }
        url = f"{OM_BASE}/alunos"
        try:
            r = requests.post(url, data=payload, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=10)
            r.raise_for_status()
            response_json = r.json()
            _log(f"[CAD ALUNO] Status: {r.status_code}, CPF Tentado: {final_cpf}, Resposta: {r.text[:150]}")

            if response_json.get("status") == "true":
                aluno_id = response_json.get("data", {}).get("id")
                if aluno_id:
                    if _matricular_om(aluno_id, cursos_ids, token):
                        return aluno_id, final_cpf
                    else:
                        _log(f"Aluno {aluno_id} cadastrado, mas falha ao matricular nos cursos.")
                        # Considerar se deve levantar erro aqui ou retornar parcial
                        raise RuntimeError("Aluno cadastrado, mas falha ao matricular nos cursos OM.")
                else:
                    _log("Cadastro de aluno retornou true, mas sem ID do aluno.")
            
            # Se CPF já está em uso e não foi um CPF fornecido externamente, tenta próximo
            if "já está em uso" in response_json.get("info", "").lower() and not cpf:
                _log(f"CPF {final_cpf} já em uso. Tentando próximo.")
                continue # Tenta o próximo CPF no loop
            else: # Outro erro ou CPF fornecido externamente falhou
                _log(f"Falha ao cadastrar aluno (não relacionado a CPF duplicado ou CPF era fixo). Info: {response_json.get('info')}")
                break # Sai do loop de tentativas de CPF

        except requests.RequestException as e:
            _log(f"Erro de conexão ao cadastrar aluno: {e}")
            break # Sai do loop em caso de erro de conexão
        except ValueError: # JSONDecodeError
             _log(f"Resposta inválida (não JSON) ao cadastrar aluno: {r.text if 'r' in locals() else 'N/A'}")
             break

    _log(f"Não foi possível cadastrar/matricular o aluno {nome} após tentativas.")
    raise RuntimeError("Falha ao cadastrar/matricular aluno no sistema OM após tentativas.")


def _nome_para_ids(cursos_nomes:List[str])->List[int]:
    ids=[]
    for nome_curso in cursos_nomes:
        curso_ids = CURSOS_OM.get(nome_curso.strip())
        if curso_ids:
            ids.extend(curso_ids)
        else:
            _log(f"AVISO: Nome de curso '{nome_curso}' não encontrado em CURSOS_OM.")
    if not ids:
        _log("ERRO: Nenhum ID de disciplina encontrado para os cursos fornecidos em _nome_para_ids.")
    return ids

def matricular_aluno_final(nome:str, whatsapp:str, email:Optional[str], cursos_nomes:List[str])->Tuple[str,str,List[int]]:
    _log(f"Iniciando matrícula final para: {nome}, Cursos: {cursos_nomes}")
    cursos_ids = _nome_para_ids(cursos_nomes)
    if not cursos_ids:
        _log("ERRO CRÍTICO: Nenhum ID de disciplina encontrado para os cursos fornecidos. Matrícula não pode prosseguir.")
        raise RuntimeError("Nenhum ID de disciplina encontrado para os cursos fornecidos")
    
    try:
        token = _obter_token_unidade()
        aluno_id, cpf = _cadastrar_aluno(nome, whatsapp, email or "", cursos_ids, token)
        if aluno_id and cpf:
            _log(f"Matrícula final no OM bem-sucedida para {nome}. Aluno ID: {aluno_id}, CPF: {cpf}")
            return aluno_id, cpf, cursos_ids
        else:
            # _cadastrar_aluno já levanta RuntimeError em caso de falha total
            # Esta parte pode não ser alcançada se _cadastrar_aluno sempre levantar exceção em falha.
            _log("ERRO CRÍTICO: _cadastrar_aluno retornou None para aluno_id ou cpf sem levantar exceção.")
            raise RuntimeError("Falha inesperada no processo de cadastro do aluno.")

    except RuntimeError as e:
        _log(f"ERRO em matricular_aluno_final: {e}")
        raise # Re-levanta a exceção para ser tratada pelo chamador (webhook)
    except Exception as e:
        _log(f"ERRO inesperado em matricular_aluno_final: {e}")
        raise RuntimeError(f"Erro inesperado durante a matrícula final: {e}")


# ──────────────────────────────────────────────────────────
# Endpoint de Matrícula (Inicia Pagamento MP)
# ──────────────────────────────────────────────────────────
@router.post("/")
async def endpoint_iniciar_matricula(body: dict, request: Request): # Adicionado request para obter base_url
    nome = body.get("nome")
    whatsapp = body.get("whatsapp")
    email = body.get("email", "") # Email é usado no payer_email do MP, importante
    cursos_nomes = body.get("cursos", [])
    
    if not nome or not whatsapp or not cursos_nomes:
        _log(f"Dados inválidos para iniciar matrícula: Nome='{nome}', WhatsApp='{whatsapp}', Cursos='{cursos_nomes}'")
        raise HTTPException(400, detail="Nome, whatsapp e pelo menos um curso são obrigatórios.")
    
    if not email: # Mercado Pago requer um email para o pagador
        _log("AVISO: Email não fornecido. Usando placeholder para Mercado Pago.")
        # Usar um email placeholder mais robusto ou exigir email no frontend
        timestamp_uuid = uuid.uuid4().hex[:8]
        email = f"user_{timestamp_uuid}@placeholder.ced.com"


    curso_principal_nome = cursos_nomes[0] if cursos_nomes else "Matrícula Curso Online"
    
    if not MP_PREAPPROVAL_PLAN_ID:
        _log("ERRO CRÍTICO: MP_PREAPPROVAL_PLAN_ID não configurado no ambiente.")
        raise HTTPException(500, detail="Configuração de pagamento indisponível (PLAN_ID).")
    if not THANK_YOU_PAGE_URL: # URL de retorno após pagamento
        _log("ERRO CRÍTICO: THANK_YOU_PAGE_URL não configurada no ambiente.")
        raise HTTPException(500, detail="Configuração de pagamento indisponível (RETURN_URL).")

    if not sdk_matricular:
        _log("ERRO CRÍTICO: SDK do Mercado Pago não inicializado em matricular.py.")
        raise HTTPException(500, detail="Serviço de pagamento indisponível no momento (SDK Error).")

    pending_enrollment_id = str(uuid.uuid4())
    
    try:
        PENDING_ENROLLMENTS[pending_enrollment_id] = {
            "nome": nome, "whatsapp": whatsapp, "email": email,
            "cursos_nomes": cursos_nomes, "status": "pending_payment",
            "timestamp": datetime.now().isoformat()
        }
        _log(f"Matrícula pendente ID: {pending_enrollment_id} para {nome} armazenada.")

        base_url = str(request.base_url) 
        notification_url = f"{base_url.rstrip('/')}/api/webhook/mercadopago"
        _log(f"URL de notificação para MP configurada como: {notification_url}")


        preapproval_data = {
            "reason": f"Assinatura: {curso_principal_nome}",
            "preapproval_plan_id": MP_PREAPPROVAL_PLAN_ID,
            "payer_email": email, 
            "back_url": THANK_YOU_PAGE_URL, 
            "external_reference": pending_enrollment_id, 
            "notification_url": notification_url 
        }
        
        _log(f"Criando assinatura MP com dados: {preapproval_data}")
        preapproval_response_dict = sdk_matricular.preapproval().create(preapproval_data)
        
        if preapproval_response_dict and preapproval_response_dict.get("status") == 201: 
            response_data = preapproval_response_dict.get("response", {})
            init_point = response_data.get("init_point")
            mp_preapproval_id = response_data.get("id")

            if not init_point or not mp_preapproval_id:
                _log(f"ERRO: init_point ou ID da pré-aprovação ausentes na resposta do MP: {response_data}")
                PENDING_ENROLLMENTS.pop(pending_enrollment_id, None) 
                raise HTTPException(500, detail="Falha ao obter dados da criação da assinatura MP.")

            _log(f"Assinatura MP criada (ID: {mp_preapproval_id}). Redirect: {init_point}")
            PENDING_ENROLLMENTS[pending_enrollment_id]["mp_preapproval_id"] = mp_preapproval_id
            
            return {
                "status": "ok",
                "message": "Matrícula iniciada, redirecionando para o pagamento.",
                "redirect_url": init_point,
                "pending_enrollment_id": pending_enrollment_id
            }
        else:
            error_details = preapproval_response_dict.get('response', preapproval_response_dict) if preapproval_response_dict else "Resposta vazia"
            status_code = preapproval_response_dict.get('status', 'N/A') if preapproval_response_dict else 'N/A'
            _log(f"Erro ao criar assinatura MP: Status {status_code} - Detalhes: {error_details}")
            PENDING_ENROLLMENTS.pop(pending_enrollment_id, None)
            
            mp_error_message = "Falha ao iniciar o pagamento com Mercado Pago."
            if isinstance(error_details, dict) and error_details.get("message"):
                mp_error_message = error_details.get("message")
                if error_details.get("cause") and isinstance(error_details["cause"], list) and len(error_details["cause"]) > 0:
                     # Tenta pegar a descrição da primeira causa, se existir
                     first_cause = error_details["cause"][0]
                     if isinstance(first_cause, dict) and first_cause.get("description"):
                         mp_error_message = first_cause.get("description")
                     elif isinstance(first_cause, str): # Às vezes a causa é apenas uma string
                         mp_error_message = first_cause


            raise HTTPException(status_code= int(status_code) if str(status_code).isdigit() else 500, detail=mp_error_message)

    # CORREÇÃO APLICADA AQUI:
    except mercadopago.MPException as mp_e: # Alterado de mercadopago.exceptions.MPException
        _log(f"Erro no SDK do Mercado Pago (MPException): Status {getattr(mp_e, 'status_code', 'N/A')} - Mensagem: {getattr(mp_e, 'message', str(mp_e))} - Causa: {getattr(mp_e, 'cause', 'N/A')}")
        if pending_enrollment_id in PENDING_ENROLLMENTS: # Garante que o ID existe antes de tentar pop
            PENDING_ENROLLMENTS.pop(pending_enrollment_id, None) 
        
        error_detail = f"Erro no pagamento ({getattr(mp_e, 'status_code', 'N/A')}): {getattr(mp_e, 'message', str(mp_e))}"
        cause = getattr(mp_e, 'cause', None)
        if cause and isinstance(cause, list) and len(cause) > 0 and isinstance(cause[0], dict) and cause[0].get('description'):
            error_detail = cause[0].get('description')
        elif cause and isinstance(cause, str): # Se a causa for uma string simples
             error_detail = cause


        raise HTTPException(status_code=getattr(mp_e, 'status_code', 500) or 500, detail=error_detail)
    except Exception as e:
        _log(f"Erro GERAL em endpoint_iniciar_matricula: {str(e)} (Tipo: {type(e)})")
        if pending_enrollment_id in PENDING_ENROLLMENTS: 
            PENDING_ENROLLMENTS.pop(pending_enrollment_id, None)
        raise HTTPException(500, detail=f"Erro interno no servidor ao processar matrícula: {str(e)}")

# ──────────────────────────────────────────────────────────
# ENDPOINT: Gerar Descrição de Curso com Gemini API
# ──────────────────────────────────────────────────────────
@router.post("/generate-course-description")
async def generate_course_description(body: dict):
    course_name = body.get("course_name")

    if not course_name:
        raise HTTPException(400, detail="O nome do curso é obrigatório para gerar a descrição.")

    # GEMINI_API_KEY é preenchido pelo Canvas em tempo de execução
    # A URL deve ser para o modelo gemini-2.0-flash.
    # A chave de API será adicionada automaticamente pelo ambiente do Canvas se GEMINI_API_KEY for uma string vazia.
    
    # Se GEMINI_API_KEY for uma string vazia, o Canvas a injetará.
    # Se você tiver uma chave codificada, ela será usada.
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
            # Tentar extrair mensagem de erro da resposta do Gemini, se houver
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
            pass # Não era JSON
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

