"""
webhook.py – Recebe notificações do Mercado Pago e finaliza a matrícula.
Envia logs para o Discord.
"""

import os
import requests
from fastapi import APIRouter, HTTPException, Request
from datetime import datetime
import mercadopago
import json

# ──────────────────────────────────────────────────────────
# Funções Auxiliares de Logging (Definida localmente)
# ──────────────────────────────────────────────────────────
def _log(msg: str):
    """Função de logging simples para webhook.py."""
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] [MP Webhook] {msg}")

# ──────────────────────────────────────────────────────────
# Variáveis de Ambiente
# ──────────────────────────────────────────────────────────
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
# MP_TEST_ACCESS_TOKEN removido, pois não há mais sandbox aqui.
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
CADASTRO_API_URL = os.getenv("CADASTRO_API_URL", "https://api.cedbrasilia.com.br/cadastrar")


# ──────────────────────────────────────────────────────────
# Configuração Mercado Pago SDK (APENAS PRODUÇÃO)
# ──────────────────────────────────────────────────────────
sdk_prod = None
if MP_ACCESS_TOKEN:
    try:
        sdk_prod = mercadopago.SDK(access_token=MP_ACCESS_TOKEN)
        _log("SDK Mercado Pago (Produção) inicializado com sucesso em webhook.py.")
    except Exception as e:
        _log(f"ERRO ao inicializar SDK Mercado Pago (Produção): {e}.")

if not sdk_prod:
    _log("ERRO CRÍTICO: SDK do Mercado Pago (Produção) não pôde ser inicializado em webhook.py. As notificações NÃO FUNCIONARÃO.")

router = APIRouter()

# ──────────────────────────────────────────────────────────
# Função para enviar mensagem para o Discord
# ──────────────────────────────────────────────────────────
def send_discord_notification(message: str, success: bool = True):
    if not DISCORD_WEBHOOK_URL:
        _log("AVISO: DISCORD_WEBHOOK_URL não configurada. Notificação do Discord desabilitada.")
        return

    color = 3066993 if success else 15158332 # Green for success, Red for error
    
    payload = {
        "embeds": [
            {
                "title": "Status de Matrícula Automática (Webhook)",
                "description": message,
                "color": color,
                "timestamp": datetime.now().isoformat(),
                "footer": {"text": "Webhook MercadoPago"}
            }
        ]
    }
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status()
        _log(f"Notificação Discord enviada: {message[:100]}...")
    except requests.exceptions.RequestException as e:
        _log(f"ERRO ao enviar notificação Discord: {e}")

# ──────────────────────────────────────────────────────────
# Função para chamar o endpoint de cadastro/matrícula
# ──────────────────────────────────────────────────────────
def call_cadastrar_endpoint(student_data: dict, external_reference: str): # is_sandbox_transaction removido
    """
    Chama o endpoint /cadastrar para finalizar a matrícula no OM e enviar ChatPro.
    """
    _log(f"Chamando endpoint /cadastrar para external_reference: {external_reference}")
    
    # status_prefix removido, pois não há mais distinção sandbox/prod aqui.
    status_prefix = "" 

    try:
        response = requests.post(CADASTRO_API_URL, json=student_data, timeout=30)
        response.raise_for_status()
        cad_result = response.json()
        _log(f"Resposta do endpoint /cadastrar para {external_reference}: {cad_result}")
        
        if cad_result.get("status") == "ok":
            send_discord_notification(
                f"✅ Matrícula Finalizada via Webhook! ✅\n"
                f"Aluno: {student_data.get('nome')}\n"
                f"Email: {student_data.get('email')}\n"
                f"Cursos: {', '.join(student_data.get('cursos', []))}\n"
                f"ID Aluno OM: {cad_result.get('aluno_id')}\n"
                f"CPF Gerado: {cad_result.get('cpf')}\n"
                f"Ref. Externa: {external_reference}",
                success=True
            )
            return True
        else:
            send_discord_notification(
                f"❌ Erro ao Finalizar Matrícula via Webhook! ❌\n"
                f"Aluno: {student_data.get('nome')}\n"
                f"Ref. Externa: {external_reference}\n"
                f"Erro no /cadastrar: {cad_result.get('detail') or cad_result.get('message') or 'Erro desconhecido'}",
                success=False
            )
            return False
    except requests.exceptions.RequestException as e:
        _log(f"ERRO de conexão ao chamar /cadastrar para {external_reference}: {e}")
        send_discord_notification(
            f"⚠️ Erro de Conexão no Webhook para /cadastrar! ⚠️\n"
            f"Aluno: {student_data.get('nome')}\n"
            f"Ref. Externa: {external_reference}\n"
            f"Erro: {str(e)}",
            success=False
        )
        return False
    except Exception as e:
        _log(f"ERRO inesperado ao processar resposta de /cadastrar para {external_reference}: {e}")
        send_discord_notification(
            f"⚠️ Erro Inesperado no Webhook ao chamar /cadastrar! ⚠️\n"
            f"Aluno: {student_data.get('nome')}\n"
            f"Ref. Externa: {external_reference}\n"
            f"Erro: {str(e)}",
            success=False
        )
        return False


# ──────────────────────────────────────────────────────────
# Endpoint para Webhooks do Mercado Pago
# ──────────────────────────────────────────────────────────
@router.post("/webhook/mercadopago")
async def mercadopago_webhook(request: Request):
    request_body_data = {}
    try:
        request_body_data = await request.json()
        _log(f"Webhook body received: {request_body_data}")
    except json.JSONDecodeError:
        _log("Webhook body is not valid JSON. Proceeding with query parameters only.")

    topic = request.query_params.get("topic")
    if not topic:
        topic = request_body_data.get("type") or request_body_data.get("topic")

    resource_id = request.query_params.get("id")
    if not resource_id:
        resource_id = request_body_data.get("data", {}).get("id") or request_body_data.get("id")

    _log(f"Parsed topic: {topic}, Parsed Resource ID: {resource_id}")

    if not topic or not resource_id:
        _log(f"ERRO: 'topic' ou 'id'/'data.id' ausentes após parsing. Topic: {topic}, ID: {resource_id}")
        return {"status": "error", "message": "Missing parameters"}, 200

    if not sdk_prod: # Apenas SDK de produção
        _log(f"ERRO CRÍTICO: SDK do Mercado Pago não inicializado. Notificação não processada.")
        send_discord_notification("⚠️ ERRO CRÍTICO no Webhook MP! ⚠️\nSDK do Mercado Pago não inicializado. As notificações não podem ser processadas.", success=False)
        return {"status": "error", "message": "Internal SDK configuration error"}, 200

    resource_info_dict = None
    try:
        if topic == 'preapproval' or topic == 'subscription_preapproval':
            response_obj = sdk_prod.preapproval().get(resource_id)
        elif topic == 'payment':
            response_obj = sdk_prod.payment().get(resource_id)
        elif topic == 'merchant_order':
            response_obj = sdk_prod.merchant_orders().get(resource_id)
        else:
            response_obj = None # Tópico não tratado

        if response_obj and response_obj.get("status") in [200, 201]:
            resource_info_dict = response_obj
            _log(f"Recurso {resource_id} encontrado com SDK de PRODUÇÃO.")
        elif response_obj and response_obj.get("status") == 404:
            _log(f"Recurso {resource_id} NÃO encontrado com SDK de PRODUÇÃO (404).")
        elif response_obj:
            status_log = response_obj.get('status')
            _log(f"Erro inesperado ao buscar recurso {resource_id} com SDK de PRODUÇÃO. Status: {status_log}.")
        else:
            _log(f"SDK de PRODUÇÃO não retornou objeto para {resource_id} ou tópico {topic} não suportado.")

    except requests.exceptions.RequestException as e:
        if hasattr(e, 'response') and e.response.status_code == 404:
            _log(f"RequestException (404) ao buscar recurso {resource_id} com SDK de PRODUÇÃO.")
        else:
            _log(f"RequestException ao buscar recurso {resource_id} com SDK de PRODUÇÃO: {e}.")
    except Exception as e:
        _log(f"Erro genérico ao buscar recurso {resource_id} com SDK de PRODUÇÃO: {e}.")

    if not resource_info_dict:
        _log(f"ERRO: Recurso {resource_id} não encontrado ou dados inválidos. Notificação não processada.")
        send_discord_notification(f"⚠️ ERRO no Webhook MP! ⚠️\nRecurso '{resource_id}' (Tópico: '{topic}') NÃO ENCONTRADO ou dados inválidos. Verifique tokens e IDs.", success=False)
        return {"status": "error", "message": "Resource not found or invalid data"}, 200

    # Agora processa a notificação
    try:
        if topic == 'preapproval' or topic == 'subscription_preapproval':
            preapproval_data = resource_info_dict.get("response", {})
            mp_status = preapproval_data.get("status")
            payer_email = preapproval_data.get("payer_email")
            external_reference = preapproval_data.get("external_reference")
            preapproval_mp_id = preapproval_data.get("id")

            _log(f"Assinatura MP ID: {preapproval_mp_id}, Status MP: {mp_status}, Payer: {payer_email}, External Ref: {external_reference}")

            if not external_reference:
                _log(f"ERRO: External Reference não encontrado na notificação da assinatura {preapproval_mp_id}.")
                send_discord_notification(f"Webhook de Assinatura Recebido SEM External Reference para MP ID {preapproval_mp_id}, Payer: {payer_email}. Impossível processar.", success=False)
                return {"status": "error", "message": "External reference missing in notification"}, 200

            # --- RECUPERAÇÃO DE DADOS DO ALUNO (PRODUÇÃO) ---
            # ATENÇÃO: Em produção, você DEVE buscar esses dados de um banco de dados persistente
            # usando o `external_reference` ou `preapproval_mp_id`.
            # O exemplo abaixo é um placeholder.
            student_data_for_cadastrar = {
                "nome": "Nome Desconhecido (via Webhook)", # TODO: Buscar do DB
                "whatsapp": "00000000000", # TODO: Buscar do DB
                "email": payer_email, # Pode vir do MP
                "cursos": ["Curso Padrão (via Webhook)"] # TODO: Buscar do DB
            }
            _log(f"INFO: Transação de PRODUÇÃO. Dados do aluno para {external_reference} devem ser buscados de um banco de dados persistente.")
            # student_data_for_cadastrar = your_production_db_lookup(external_reference) # Exemplo de chamada ao DB


            if mp_status == 'authorized' or mp_status == 'active': # 'active' para assinaturas
                _log(f"Assinatura AUTORIZADA/ATIVA para external_ref: {external_reference}. Chamando endpoint /cadastrar...")
                call_cadastrar_endpoint(student_data_for_cadastrar, external_reference)
            
            elif mp_status == 'pending':
                _log(f"Assinatura PENDENTE para external_ref: {external_reference} (Payer: {payer_email}).")
                send_discord_notification(f"⏳ Assinatura PENDENTE no MP para {payer_email} (Ref: {external_reference}).\nMP Preapproval ID: {preapproval_mp_id}.\nAguardando autorização/compensação.", success=True)
                
            elif mp_status == 'paused':
                _log(f"Assinatura PAUSADA para external_ref: {external_reference} (Payer: {payer_email}).")
                send_discord_notification(f"⏸️ Assinatura PAUSADA no MP para {payer_email} (Ref: {external_reference}).\nMP Preapproval ID: {preapproval_mp_id}.", success=True) 

            elif mp_status == 'cancelled':
                _log(f"Assinatura CANCELADA para external_ref: {external_reference} (Payer: {payer_email}).")
                send_discord_notification(f"❌ Assinatura CANCELADA no MP para {payer_email} (Ref: {external_reference}).\nMP Preapproval ID: {preapproval_mp_id}.", success=False)
                
            else:
                _log(f"Assinatura com status MP '{mp_status}' para external_reference: {external_reference} (Payer: {payer_email}).")
                send_discord_notification(f"ℹ️ Status da Assinatura MP: '{mp_status}' para {payer_email} (Ref: {external_reference}).\nMP Preapproval ID: {preapproval_mp_id}.", success=False)


        elif topic == 'payment':
            payment_data = resource_info_dict.get("response", {})
            mp_status = payment_data.get("status")
            payer_email = payment_data.get("payer", {}).get("email")
            external_reference = payment_data.get("external_reference")
            mp_payment_id = payment_data.get("id")
            transaction_amount = payment_data.get("transaction_amount")
            
            _log(f"Pagamento MP ID: {mp_payment_id}, Status MP: {mp_status}, Payer: {payer_email}, External Ref: {external_reference}, Valor: {transaction_amount}")

            # --- RECUPERAÇÃO DE DADOS DO ALUNO PARA PAGAMENTO (PRODUÇÃO) ---
            # ATENÇÃO: Em produção, você DEVE buscar esses dados de um banco de dados persistente.
            student_data_for_cadastrar = {
                "nome": "Nome Desconhecido (via Webhook)", # TODO: Buscar do DB
                "whatsapp": "00000000000", # TODO: Buscar do DB
                "email": payer_email, # Pode vir do MP
                "cursos": ["Curso Padrão (via Webhook)"] # TODO: Buscar do DB
            }
            _log(f"INFO: Transação de PRODUÇÃO. Dados do aluno para {external_reference} (Pagamento) devem ser buscados de um banco de dados persistente.")
            # student_data_for_cadastrar = your_production_db_lookup(external_reference) # Exemplo de chamada ao DB
            
            if mp_status == 'approved':
                _log(f"Pagamento APROVADO para external_ref: {external_reference}. Chamando endpoint /cadastrar...")
                call_cadastrar_endpoint(student_data_for_cadastrar, external_reference)
            else:
                send_discord_notification(
                    f"💰 Webhook de Pagamento MP Recebido! 💰\n"
                    f"ID Pagamento MP: {mp_payment_id}\n"
                    f"Status: `{mp_status}`\n"
                    f"Valor: R$ {transaction_amount:.2f}\n"
                    f"Pagador: {payer_email}\n"
                    f"Ref. Externa: {external_reference or 'N/A'}",
                    success=(mp_status == 'approved')
                )

        elif topic == 'merchant_order':
            merchant_order_data = resource_info_dict.get("response", {})
            order_status = merchant_order_data.get("status")
            external_reference = merchant_order_data.get("external_reference")
            merchant_order_id = merchant_order_data.get("id")
            
            _log(f"Merchant Order ID: {merchant_order_id}, Status: {order_status}, External Ref: {external_reference}")

            payments = merchant_order_data.get("payments", [])
            approved_payment_found = False
            for payment in payments:
                if payment.get("status") == "approved":
                    approved_payment_found = True
                    payer_email = payment.get("payer", {}).get("email")
                    transaction_amount = payment.get("transaction_amount")
                    mp_payment_id = payment.get("id")

                    _log(f"Pagamento APROVADO encontrado na Merchant Order. ID: {mp_payment_id}, Payer: {payer_email}, Valor: {transaction_amount}")

                    # --- RECUPERAÇÃO DE DADOS DO ALUNO PARA MERCHANT_ORDER (PRODUÇÃO) ---
                    # ATENÇÃO: Em produção, você DEVE buscar esses dados de um banco de dados persistente.
                    student_data_for_cadastrar = {
                        "nome": "Nome Desconhecido (via Webhook)", # TODO: Buscar do DB
                        "whatsapp": "00000000000", # TODO: Buscar do DB
                        "email": payer_email, # Pode vir do MP
                        "cursos": ["Curso Padrão (via Webhook)"] # TODO: Buscar do DB
                    }
                    _log(f"INFO: Transação de PRODUÇÃO. Dados do aluno para {external_reference} (Merchant Order) devem ser buscados de um banco de dados persistente.")
                    # student_data_for_cadastrar = your_production_db_lookup(external_reference) # Exemplo de chamada ao DB
                    
                    call_cadastrar_endpoint(student_data_for_cadastrar, external_reference)
                    break 
            
            if not approved_payment_found:
                _log(f"Nenhum pagamento aprovado encontrado na Merchant Order {merchant_order_id}. Status da ordem: {order_status}.")
                send_discord_notification(
                    f"ℹ️ Merchant Order MP Recebida! ℹ️\n"
                    f"ID Ordem MP: {merchant_order_id}\n"
                    f"Status da Ordem: `{order_status}`\n"
                    f"Nenhum pagamento aprovado encontrado ainda.\n"
                    f"Ref. Externa: {external_reference or 'N/A'}",
                    success=False 
                )

        else:
            _log(f"Tópico desconhecido ou não tratado: {topic}. Resource ID: {resource_id}. Ignorando.")
            send_discord_notification(f"❓ Webhook MP com Tópico Desconhecido: '{topic}' (ID Recurso: {resource_id}). Ignorado.", success=False)

        return {"status": "success", "message": "Webhook notification processed."}, 200

    except requests.exceptions.RequestException as e:
        _log(f"ERRO no Webhook MP (RequestException): {e} - ID Recurso: {resource_id}, Tópico: {topic}")
        send_discord_notification(f"⚠️ ERRO GRAVE no Webhook MP (Conexão)! ⚠️\nErro: {str(e)}\nID Recurso: {resource_id}\nTópico: {topic}", success=False)
        return {"status": "error", "message": f"Network error processing webhook: {str(e)}"}, 200
    except Exception as e:
        _log(f"ERRO GERAL INESPERADO ao processar webhook: {str(e)} (Tipo: {type(e)}) - ID Recurso: {resource_id}, Tópico: {topic}")
        send_discord_notification(f"⚠️ ERRO INTERNO GRAVE no Webhook MP! ⚠️\nErro: {str(e)}\nID Recurso: {resource_id}\nTópico: {topic}", success=False)
        return {"status": "error", "message": f"Internal error processing webhook: {str(e)}"}, 200


# ──────────────────────────────────────────────────────────
# Endpoint de Retorno do Pagamento (Opcional, para feedback imediato ao usuário)
# ──────────────────────────────────────────────────────────
@router.get("/pagamento-status") # Este endpoint é chamado pelo redirect do MP (back_url)
async def pagamento_status_redirect(request: Request):
    """
    Endpoint para onde o Mercado Pago redireciona o usuário após a tentativa de pagamento/assinatura.
    Este é um feedback IMEDIATO ao usuário na interface dele.
    O status FINAL e a lógica de matrícula são tratados pelo WEBHOOK.
    """
    preapproval_id = request.query_params.get("preapproval_id") # ID da assinatura no MP
    external_reference = request.query_params.get("external_reference") # Nosso ID
    collection_status = request.query_params.get("collection_status") # Status da coleção (para pagamentos únicos)
    payment_id = request.query_params.get("payment_id") # ID do pagamento (para pagamentos únicos)

    _log(f"Usuário redirecionado. Preapproval ID: {preapproval_id}, External Ref: {external_reference}, Payment ID: {payment_id}, Collection Status: {collection_status}. Query Params: {request.query_params}")

    message = f"Obrigado! Sua solicitação de pagamento foi enviada."
    sub_message = "Você receberá uma notificação por e-mail assim que o status for confirmado. Acompanhe também pelo seu painel do Mercado Pago."

    # ATENÇÃO: Em produção, você DEVE buscar esses dados de um banco de dados persistente.
    # PENDING_ENROLLMENTS não é mais usado aqui.
    # from sandbox_matricular import PENDING_ENROLLMENTS as SANDBOX_PENDING_ENROLLMENTS # Removido
    # pending_data = SANDBOX_PENDING_ENROLLMENTS.get(external_reference) # Removido

    # Simula a recuperação de dados do aluno para o feedback
    pending_data_simulated = {
        "nome": "Aluno(a)" # TODO: Buscar nome real do DB usando external_reference
    }

    if pending_data_simulated: # Se dados pudessem ser recuperados
        nome_aluno = pending_data_simulated.get("nome", "Aluno(a)")
        message = f"Olá {nome_aluno}, obrigado! Sua solicitação de pagamento foi enviada ao Mercado Pago."
        
        if collection_status == 'approved':
            sub_message = "Seu pagamento foi aprovado! Estamos processando sua matrícula."
        elif collection_status == 'pending':
            sub_message = "Seu pagamento está pendente de aprovação. Aguarde a confirmação."
        elif collection_status == 'rejected':
            sub_message = "Seu pagamento foi recusado. Por favor, tente novamente ou utilize outro método."
        
    
    return {
        "title": "Processando Pagamento",
        "message": message,
        "sub_message": sub_message,
        "mp_preapproval_id": preapproval_id,
        "mp_payment_id": payment_id,
        "your_reference_id": external_reference,
        "important_note": "A confirmação final da sua matrícula e o status do pagamento serão enviados por e-mail e processados em segundo plano."
    }
