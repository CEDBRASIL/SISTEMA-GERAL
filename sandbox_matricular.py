"""
sandbox_matricular.py – TESTE: Prepara o processo de matrícula e pagamento com Mercado Pago (SANDBOX).
A matrícula final no sistema OM é feita via webhook.
Inclui endpoint para gerar descrição de curso com Gemini API.
"""

import os
import threading
from typing import List, Tuple, Optional, Dict
import requests
from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone 
import uuid 
from cursos import CURSOS_OM 
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

# Variáveis de Ambiente para ChatPro
CHATPRO_URL = os.getenv("CHATPRO_URL")
CHATPRO_TOKEN = os.getenv("CHATPRO_TOKEN")

# URL do Webhook do Discord para logs de eventos (colocado diretamente no código conforme solicitado)
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1377838283975036928/IgVvwyrBBWflKyXbIU9dgH4PhLwozHzrf-nJpj3w7dsZC-Ds9qN8_Toym3Tnbj-3jdU4"

# ──────────────────────────────────────────────────────────
# Armazenamento Temporário de Matrículas Pendentes
# ──────────────────────────────────────────────────────────
PENDING_ENROLLMENTS: Dict[str, Dict] = {}
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
# Funções de Lógica de Negócio (matrícula, etc.) - Idênticas às de produção, mas usando sdk_matricular_sandbox
# ──────────────────────────────────────────────────────────
def _obter_token_unidade() -> str:
    """Obtém o token da unidade no sistema OM."""
    if not all([OM_BASE, BASIC_B64, UNIDADE_ID]):
        _log("ERRO SANDBOX: Variáveis OM não configuradas (_obter_token_unidade).")
        raise RuntimeError("Variáveis OM não configuradas. Verifique ambiente.")
    url = f"{OM_BASE}/unidades/token/{UNIDADE_ID}"
    try:
        r = requests.get(url, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=8)
        r.raise_for_status()
        response_json = r.json()
        if response_json.get("status") == "true" and response_json.get("data", {}).get("token"):
            return response_json["data"]["token"]
        _log(f"Falha SANDBOX ao obter token da unidade. Resposta: {r.text}")
        raise RuntimeError(f"Falha SANDBOX ao obter token da unidade: {response_json.get('info', 'Resposta inesperada')}")
    except requests.RequestException as e:
        _log(f"Erro de conexão SANDBOX ao obter token da unidade: {e}")
        raise RuntimeError(f"Erro de conexão SANDBOX ao obter token da unidade: {e}")
    except ValueError: 
        _log(f"Resposta inválida (não JSON) SANDBOX ao obter token da unidade: {r.text if 'r' in locals() else 'N/A'}")
        raise RuntimeError("Resposta inválida (não JSON) SANDBOX ao obter token da unidade.")


def _total_alunos() -> int:
    """Apurar o total de alunos cadastrados no sistema OM para a unidade."""
    if not all([OM_BASE, BASIC_B64, UNIDADE_ID]):
        _log("ERRO SANDBOX: Variáveis OM não configuradas (_total_alunos).")
        raise RuntimeError("Variáveis OM não configuradas para _total_alunos.")
    
    url_total = f"{OM_BASE}/alunos/total/{UNIDADE_ID}"
    try:
        r_total = requests.get(url_total, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=8)
        r_total.raise_for_status()
        response_json_total = r_total.json()
        if response_json_total.get("status") == "true" and response_json_total.get("data", {}).get("total") is not None:
            return int(response_json_total["data"]["total"])
        _log(f"Endpoint /alunos/total SANDBOX não retornou sucesso ou total. Resposta: {r_total.text}. Tentando contagem alternativa.")
    except requests.RequestException as e:
        _log(f"Erro de conexão SANDBOX no endpoint /alunos/total: {e}. Tentando contagem alternativa.")
    except (ValueError, TypeError) as e: 
        _log(f"Erro SANDBOX ao processar resposta de /alunos/total: {e}. Resposta: {r_total.text if 'r_total' in locals() else 'N/A'}. Tentando contagem alternativa.")

    url_list = f"{OM_BASE}/alunos?unidade_id={UNIDADE_ID}&cpf_like={CPF_PREFIXO}"
    try:
        r_list = requests.get(url_list, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=8)
        r_list.raise_for_status()
        response_json_list = r_list.json()
        if response_json_list.get("status") == "true" and "data" in response_json_list:
            return len(response_json_list["data"])
        _log(f"Falha SANDBOX ao apurar total de alunos (contagem alternativa). Resposta: {r_list.text}")
        raise RuntimeError(f"Falha SANDBOX ao apurar total de alunos (contagem alternativa): {response_json_list.get('info', 'Resposta inesperada')}")
    except requests.RequestException as e:
        _log(f"Erro de conexão SANDBOX na contagem alternativa de alunos: {e}")
        raise RuntimeError(f"Erro de conexão SANDBOX na contagem alternativa de alunos: {e}")
    except ValueError:
        _log(f"Resposta inválida (não JSON) SANDBOX na contagem alternativa de alunos: {r_list.text if 'r_list' in locals() else 'N/A'}")
        raise RuntimeError("Resposta inválida (não JSON) SANDBOX na contagem alternativa de alunos.")


def _proximo_cpf(incr:int=0)->str:
    """Gera um próximo CPF de teste único para o sandbox."""
    with cpf_lock:
        try:
            seq = _total_alunos() + 1 + incr
            return CPF_PREFIXO + str(seq).zfill(3)
        except RuntimeError as e:
            _log(f"Erro SANDBOX ao obter total de alunos para gerar CPF: {e}. Usando fallback para CPF.")
            timestamp_fallback = str(int(datetime.now().timestamp()))[-3:]
            return CPF_PREFIXO + timestamp_fallback.zfill(3)


def _matricular_om(aluno_id:str, cursos_ids:List[int], token:str)->bool:
    """Matricula um aluno em cursos específicos no sistema OM."""
    if not all([OM_BASE, BASIC_B64]):
        _log("ERRO SANDBOX: Variáveis OM não configuradas (_matricular_om).")
        raise RuntimeError("Variáveis OM não configuradas para _matricular_om.")
    payload = {"token": token, "cursos": ",".join(map(str, cursos_ids))}
    url = f"{OM_BASE}/alunos/matricula/{aluno_id}"
    try:
        r = requests.post(url, data=payload, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=10)
        r.raise_for_status() 
        _log(f"[MAT OM SANDBOX] Status: {r.status_code}, Resposta: {r.text[:120]}")
        response_json = r.json()
        return response_json.get("status") == "true"
    except requests.RequestException as e:
        _log(f"Erro de conexão SANDBOX ao matricular no OM: {e}")
        return False
    except ValueError: 
        _log(f"Resposta inválida (não JSON) SANDBOX ao matricular no OM: {r.text if 'r' in locals() else 'N/A'}")
        return False


def _cadastrar_aluno(nome:str, whatsapp:str, email:str, cursos_ids:List[int], token:str, cpf:Optional[str]=None)->Tuple[Optional[str],Optional[str]]:
    """Cadastra um novo aluno no sistema OM e tenta matriculá-lo nos cursos."""
    if not all([OM_BASE, BASIC_B64, UNIDADE_ID]):
        _log("ERRO SANDBOX: Variáveis OM não configuradas (_cadastrar_aluno).")
        raise RuntimeError("Variáveis OM não configuradas para _cadastrar_aluno.")
    
    final_cpf = cpf if cpf else _proximo_cpf()

    for i in range(5): # Tenta gerar CPF único até 5 vezes
        if not cpf and i > 0 : # Se não foi fornecido um CPF, tenta o próximo
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
            _log(f"[CAD ALUNO SANDBOX] Status: {r.status_code}, CPF Tentado: {final_cpf}, Resposta: {r.text[:150]}")

            if response_json.get("status") == "true":
                aluno_id = response_json.get("data", {}).get("id")
                if aluno_id:
                    if _matricular_om(aluno_id, cursos_ids, token):
                        return aluno_id, final_cpf
                    else:
                        _log(f"Aluno {aluno_id} (Sandbox) cadastrado, mas falha ao matricular nos cursos.")
                        raise RuntimeError("Aluno (Sandbox) cadastrado, mas falha ao matricular nos cursos OM.")
                else:
                    _log("Cadastro de aluno (Sandbox) retornou true, mas sem ID do aluno.")
            
            if "já está em uso" in response_json.get("info", "").lower() and not cpf:
                _log(f"CPF {final_cpf} (Sandbox) já em uso. Tentando próximo.")
                continue # Tenta novamente com um novo CPF
            else: 
                _log(f"Falha SANDBOX ao cadastrar aluno (não relacionado a CPF duplicado ou CPF era fixo). Info: {response_json.get('info')}")
                break # Sai do loop se o erro não for CPF duplicado ou se o CPF era fixo

        except requests.RequestException as e:
            _log(f"Erro de conexão SANDBOX ao cadastrar aluno: {e}")
            break # Sai do loop em caso de erro de conexão
        except ValueError: 
            _log(f"Resposta inválida (não JSON) SANDBOX ao cadastrar aluno: {r.text if 'r' in locals() else 'N/A'}")
            break # Sai do loop em caso de resposta não JSON

    _log(f"Não foi possível cadastrar/matricular o aluno {nome} (Sandbox) após tentativas.")
    raise RuntimeError("Falha ao cadastrar/matricular aluno no sistema OM (Sandbox) após tentativas.")


def _nome_para_ids(cursos_nomes:List[str])->List[int]:
    """Converte nomes de cursos em IDs de disciplina do sistema OM."""
    ids=[]
    for nome_curso in cursos_nomes:
        curso_ids = CURSOS_OM.get(nome_curso.strip())
        if curso_ids:
            ids.extend(curso_ids)
        else:
            _log(f"AVISO SANDBOX: Nome de curso '{nome_curso}' não encontrado em CURSOS_OM.")
    if not ids:
        _log("ERRO SANDBOX: Nenhum ID de disciplina encontrado para os cursos fornecidos em _nome_para_ids.")
    return ids

def matricular_aluno_final(nome:str, whatsapp:str, email:Optional[str], cursos_nomes:List[str])->Tuple[str,str,List[int]]:
    """Função principal para matricular o aluno no sistema OM."""
    _log(f"Iniciando matrícula final SANDBOX para: {nome}, Cursos: {cursos_nomes}")
    cursos_ids = _nome_para_ids(cursos_nomes)
    if not cursos_ids:
        _log("ERRO CRÍTICO SANDBOX: Nenhum ID de disciplina encontrado. Matrícula não pode prosseguir.")
        raise RuntimeError("Nenhum ID de disciplina encontrado para os cursos fornecidos (Sandbox)")
    
    try:
        token = _obter_token_unidade()
        aluno_id, cpf = _cadastrar_aluno(nome, whatsapp, email or "", cursos_ids, token)
        if aluno_id and cpf:
            _log(f"Matrícula final SANDBOX no OM bem-sucedida para {nome}. Aluno ID: {aluno_id}, CPF: {cpf}")
            return aluno_id, cpf, cursos_ids
        else:
            _log("ERRO CRÍTICO SANDBOX: _cadastrar_aluno retornou None para aluno_id ou cpf sem levantar exceção.")
            raise RuntimeError("Falha inesperada no processo de cadastro do aluno (Sandbox).")

    except RuntimeError as e:
        _log(f"ERRO SANDBOX em matricular_aluno_final: {e}")
        raise 
    except Exception as e:
        _log(f"ERRO inesperado SANDBOX em matricular_aluno_final: {e}")
        raise RuntimeError(f"Erro inesperado SANDBOX durante a matrícula final: {e}")

def _send_chatpro_message(whatsapp: str, message: str):
    """Envia uma mensagem via API ChatPro."""
    if not CHATPRO_URL or not CHATPRO_TOKEN:
        _log("AVISO SANDBOX: CHATPRO_URL ou CHATPRO_TOKEN não configurados. Mensagem ChatPro NÃO será enviada.")
        return

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHATPRO_TOKEN}"
    }
    # Formata o número de WhatsApp para o padrão esperado pelo ChatPro (apenas dígitos, incluindo código do país)
    # Assumindo que o whatsapp vem no formato "(XX) XXXXX-XXXX" ou "(XX) XXXX-XXXX"
    # E que o código do país é 55 (Brasil). Ajuste se necessário.
    whatsapp_clean = whatsapp.replace("(", "").replace(")", "").replace(" ", "").replace("-", "")
    if not whatsapp_clean.startswith("55"): # Adiciona código do país se não presente
        whatsapp_clean = "55" + whatsapp_clean

    payload = {
        "number": whatsapp_clean,
        "message": message
    }

    try:
        _log(f"Enviando mensagem ChatPro SANDBOX para {whatsapp_clean}...")
        response = requests.post(CHATPRO_URL, headers=headers, data=json.dumps(payload), timeout=10)
        response.raise_for_status() # Levanta um erro para status HTTP 4xx/5xx
        _log(f"Mensagem ChatPro SANDBOX enviada com sucesso para {whatsapp_clean}. Resposta: {response.text}")
    except requests.exceptions.Timeout:
        _log(f"Timeout SANDBOX ao enviar mensagem ChatPro para {whatsapp_clean}.")
    except requests.exceptions.HTTPError as http_err:
        _log(f"Erro HTTP SANDBOX ao enviar mensagem ChatPro para {whatsapp_clean}: {http_err}. Resposta: {http_err.text}")
    except requests.exceptions.RequestException as e:
        _log(f"Erro de conexão SANDBOX ao enviar mensagem ChatPro para {whatsapp_clean}: {e}")
    except Exception as e:
        _log(f"Erro inesperado SANDBOX ao enviar mensagem ChatPro para {whatsapp_clean}: {e}")

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
            "auto_return": "approved", # Corrigido para "approved"
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
            # AÇÃO ADICIONADA: Matricular o aluno e enviar mensagem ChatPro
            # ATENÇÃO: Em produção, isso deve ser feito via webhook do MP
            # -------------------------------------------------------------
            aluno_id = None
            cpf_aluno = None
            cursos_ids = []
            try:
                aluno_id, cpf_aluno, cursos_ids = matricular_aluno_final(nome, whatsapp, email, cursos_nomes)
                _log(f"Aluno {nome} (ID: {aluno_id}, CPF: {cpf_aluno}) matriculado no OM (Sandbox) após criação da preferência MP.")
                
                # Mensagem de confirmação para o aluno via ChatPro
                chatpro_message = (
                    f"Olá {nome}! 🎉\n\n"
                    "Seu pagamento foi efetuado com sucesso no ambiente de TESTE do CED! "
                    "Sua matrícula para o(s) curso(s) de "
                    f"{', '.join(cursos_nomes)} está sendo processada. "
                    "Em breve, você receberá um e-mail com os detalhes de acesso."
                    "\n\nObrigado por escolher o CED!"
                )
                _send_chatpro_message(whatsapp, chatpro_message)

            except Exception as e:
                _log(f"ERRO SANDBOX: Falha ao matricular aluno ou enviar mensagem ChatPro APÓS criação da preferência MP: {e}")
                # Não levantamos HTTPException aqui para não impedir o redirecionamento
                # Mas é crucial logar e monitorar esses erros em produção.
            
            # -------------------------------------------------------------
            # AÇÃO ADICIONADA: Enviar log para o Discord Bot
            # -------------------------------------------------------------
            _log("Preparando para enviar log de evento para o Discord.") # NOVO LOG DE DEPURACAO
            discord_log_message = (
                f"🎉 **Nova Matrícula SANDBOX Iniciada!** 🎉\n"
                f"**Aluno:** {nome}\n"
                f"**WhatsApp:** {whatsapp}\n"
                f"**E-mail:** {email}\n"
                f"**Curso(s):** {', '.join(cursos_nomes)}\n"
                f"**Ref. Interna (Pending ID):** `{pending_enrollment_id}`\n"
                f"**ID Preferência MP:** `{mp_preference_id}`\n"
                f"**Status MP:** `Preferência Criada (201)`\n"
                f"**Aluno OM ID:** `{aluno_id if aluno_id else 'N/A (Erro)'}`\n"
                f"**CPF Gerado:** `{cpf_aluno if cpf_aluno else 'N/A (Erro)'}`\n"
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
            
            if pending_enrollment_id in PENDENCIES: 
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
