"""
webhook.py – Recebe notificações do Mercado Pago e finaliza a matrícula.
Envia logs para o Discord.
"""

import os
import requests
from fastapi import APIRouter, HTTPException, Request
from datetime import datetime
import mercadopago
import json # Necessário para enviar JSON para o endpoint /cadastrar

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
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL") # Para webhooks de produção
# URL do endpoint de cadastro que será chamado pelo webhook
CADASTRO_API_URL = os.getenv("CADASTRO_API_URL", "https://api.cedbrasilia.com.br/cadastrar")


# ──────────────────────────────────────────────────────────
# Configuração Mercado Pago SDK
# ──────────────────────────────────────────────────────────
sdk_webhook = None
if not MP_ACCESS_TOKEN:
    _log("ERRO CRÍTICO: MP_ACCESS_TOKEN não configurado para webhook.py. A integração com Mercado Pago NÃO FUNCIONARÁ.")
else:
    try:
        sdk_webhook = mercadopago.SDK(access_token=MP_ACCESS_TOKEN)
        _log("SDK Mercado Pago inicializado com sucesso em webhook.py.")
    except Exception as e:
        _log(f"ERRO CRÍTICO ao inicializar SDK Mercado Pago em webhook.py: {e}. A integração com Mercado Pago PODE NÃO FUNCIONAR.")

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
def call_cadastrar_endpoint(student_data: dict, external_reference: str):
    """
    Chama o endpoint /cadastrar para finalizar a matrícula no OM e enviar ChatPro.
    """
    _log(f"Chamando endpoint /cadastrar para external_reference: {external_reference}")
    try:
        response = requests.post(CADASTRO_API_URL, json=student_data, timeout=15)
        response.raise_for_status() # Levanta exceção para status HTTP 4xx/5xx
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
    # Get topic, checking for 'type' as an alternative if 'topic' is not present
    topic = request.query_params.get("topic")
    if not topic:
        topic = request.query_params.get("type") # Mercado Pago sometimes sends 'type' instead of 'topic'

    # Get resource ID, checking 'id' first, then 'data.id'
    resource_id = request.query_params.get("id")
    if not resource_id:
        resource_id = request.query_params.get("data.id")

    _log(f"[MP Webhook] Recebido topic: {topic}, Resource ID: {resource_id}")

    if not topic or not resource_id:
        _log(f"[MP Webhook] ERRO: 'topic' ou 'id'/'data.id' ausentes nos query parameters. Topic: {topic}, ID: {resource_id}")
        return {"status": "error", "message": "Missing parameters"}, 200 # MP espera 200/201

    if not sdk_webhook:
        _log("[MP Webhook] ERRO CRÍTICO: SDK do Mercado Pago não inicializado em webhook.py.")
        send_discord_notification("⚠️ ERRO CRÍTICO no Webhook MP! ⚠️\nSDK do Mercado Pago não inicializado. As notificações não podem ser processadas.", success=False)
        return {"status": "error", "message": "Internal SDK configuration error"}, 200

    try:
        # Tópico 'preapproval' para assinaturas
        if topic == 'preapproval':
            preapproval_info_dict = sdk_webhook.preapproval().get(resource_id)
            
            if not (preapproval_info_dict and preapproval_info_dict.get("status") in [200, 201]):
                error_details = preapproval_info_dict.get('response', preapproval_info_dict) if preapproval_info_dict else "Resposta vazia"
                status_code = preapproval_info_dict.get('status', 'N/A') if preapproval_info_dict else 'N/A'
                _log(f"[MP Webhook] ERRO ao buscar dados da pré-aprovação ID {resource_id}. Status MP: {status_code}, Detalhes: {error_details}")
                send_discord_notification(f"⚠️ ERRO no Webhook MP! ⚠️\nFalha ao buscar detalhes da assinatura (ID Recurso: {resource_id}).\nStatus MP: {status_code}\nDetalhes: {str(error_details)[:200]}", success=False)
                return {"status": "error", "message": "Failed to fetch preapproval details"}, 200

            preapproval_data = preapproval_info_dict.get("response", {})
            mp_status = preapproval_data.get("status")
            payer_email = preapproval_data.get("payer_email")
            external_reference = preapproval_data.get("external_reference") # Este é o nosso pending_enrollment_id
            preapproval_mp_id = preapproval_data.get("id") # ID da pré-aprovação no MP

            _log(f"[MP Webhook] Assinatura MP ID: {preapproval_mp_id}, Status MP: {mp_status}, Payer: {payer_email}, External Ref (Nosso ID): {external_reference}")

            if not external_reference:
                _log(f"[MP Webhook] ERRO: External Reference (nosso ID de matrícula pendente) não encontrado na notificação da assinatura {preapproval_mp_id}.")
                send_discord_notification(f"Webhook de Assinatura Recebido SEM External Reference para MP ID {preapproval_mp_id}, Payer: {payer_email}. Impossível processar.", success=False)
                return {"status": "error", "message": "External reference missing in notification"}, 200

            # --- ATENÇÃO: RECUPERAÇÃO DE DADOS DO ALUNO ---
            # Em um cenário de produção, você buscaria esses dados de um banco de dados persistente
            # usando o `external_reference` ou `preapproval_mp_id`.
            # A importação de PENDING_ENROLLMENTS de `sandbox_matricular` é apenas para simulação de teste.
            # Para este exemplo, vamos simular que os dados do aluno viriam de um DB.
            # Como não temos um DB aqui, vou criar um dicionário dummy para simular os dados.
            # Você DEVE substituir isso pela sua lógica de busca em DB.
            
            # Simulando a recuperação de dados do aluno (IDEALMENTE DE UM BANCO DE DADOS!)
            # Para o contexto de teste, vamos assumir que o external_reference ou o email do pagador
            # pode ser usado para inferir os dados necessários.
            # Se você usa PENDING_ENROLLMENTS de sandbox_matricular, certifique-se que ele é acessível
            # e persistente o suficiente para o seu ambiente.
            
            # Exemplo de como você buscaria os dados do aluno de um DB:
            # student_data_from_db = your_database_lookup_function(external_reference)
            # if not student_data_from_db:
            #    _log("Erro: Dados do aluno não encontrados no DB para external_reference.")
            #    send_discord_notification("Erro: Dados do aluno não encontrados no DB para external_reference.", success=False)
            #    return {"status": "error", "message": "Student data not found"}, 200

            # Para manter o exemplo funcional sem um DB, vou criar um dummy student_data
            # com base no que o webhook do MP pode fornecer.
            # O ideal é que o `external_reference` seja a chave para o seu DB.
            student_data_for_cadastrar = {
                "nome": "Nome Desconhecido (via Webhook)", # Substituir por nome real do DB
                "whatsapp": "00000000000", # Substituir por whatsapp real do DB
                "email": payer_email,
                "cursos": ["Curso Padrão (via Webhook)"] # Substituir por cursos reais do DB
            }
            # Se você *ainda* estiver usando PENDING_ENROLLMENTS de `sandbox_matricular`
            # e tiver certeza que ele é acessível, pode descomentar e usar:
            # from sandbox_matricular import PENDING_ENROLLMENTS as SANDBOX_PENDING_ENROLLMENTS
            # pending_data = SANDBOX_PENDING_ENROLLMENTS.get(external_reference)
            # if pending_data:
            #     student_data_for_cadastrar = {
            #         "nome": pending_data.get("nome"),
            #         "whatsapp": pending_data.get("whatsapp"),
            #         "email": pending_data.get("email"),
            #         "cursos": pending_data.get("cursos_nomes")
            #     }
            # else:
            #     _log(f"AVISO: Dados de matrícula pendente não encontrados em PENDING_ENROLLMENTS para {external_reference}. Usando dados genéricos.")


            if mp_status == 'authorized': # Assinatura autorizada (pagamento inicial aprovado)
                _log(f"Assinatura AUTORIZADA para external_ref: {external_reference}. Chamando endpoint /cadastrar...")
                call_cadastrar_endpoint(student_data_for_cadastrar, external_reference)
            
            elif mp_status == 'pending': # Assinatura pendente de autorização
                _log(f"Assinatura PENDENTE para external_ref: {external_reference} (Payer: {payer_email}).")
                send_discord_notification(f"⏳ Assinatura PENDENTE no MP para {payer_email} (Ref: {external_reference}).\nMP Preapproval ID: {preapproval_mp_id}.\nAguardando autorização/compensação.", success=True)
                
            elif mp_status == 'paused': # Assinatura pausada
                _log(f"Assinatura PAUSADA para external_ref: {external_reference} (Payer: {payer_email}).")
                send_discord_notification(f"⏸️ Assinatura PAUSADA no MP para {payer_email} (Ref: {external_reference}).\nMP Preapproval ID: {preapproval_mp_id}.", success=True) 

            elif mp_status == 'cancelled': # Assinatura cancelada
                _log(f"Assinatura CANCELADA para external_ref: {external_reference} (Payer: {payer_email}).")
                send_discord_notification(f"❌ Assinatura CANCELADA no MP para {payer_email} (Ref: {external_reference}).\nMP Preapproval ID: {preapproval_mp_id}.", success=False)
                
            else: # Outros status (ex: rejected, etc.)
                _log(f"Assinatura com status MP '{mp_status}' para external_ref: {external_reference} (Payer: {payer_email}).")
                send_discord_notification(f"ℹ️ Status da Assinatura MP: '{mp_status}' para {payer_email} (Ref: {external_reference}).\nMP Preapproval ID: {preapproval_mp_id}.", success=False)


        # Tópico 'payment' para pagamentos avulsos ou recorrentes
        elif topic == 'payment':
            payment_info_dict = sdk_webhook.payment().get(resource_id)
            
            if not (payment_info_dict and payment_info_dict.get("status") in [200, 201]):
                error_details = payment_info_dict.get('response', payment_info_dict) if payment_info_dict else "Resposta vazia"
                status_code = payment_info_dict.get('status', 'N/A') if payment_info_dict else 'N/A'
                _log(f"[MP Webhook] ERRO ao buscar dados do pagamento ID {resource_id}. Status MP: {status_code}, Detalhes: {error_details}")
                send_discord_notification(f"⚠️ ERRO no Webhook MP! ⚠️\nFalha ao buscar detalhes do pagamento (ID Recurso: {resource_id}).\nStatus MP: {status_code}\nDetalhes: {str(error_details)[:200]}", success=False)
                return {"status": "error", "message": "Failed to fetch payment details"}, 200

            payment_data = payment_info_dict.get("response", {})
            mp_status = payment_data.get("status")
            payer_email = payment_data.get("payer", {}).get("email")
            external_reference = payment_data.get("external_reference") # Nosso ID, se usado
            mp_payment_id = payment_data.get("id") # ID do pagamento no MP
            transaction_amount = payment_data.get("transaction_amount")
            
            _log(f"[MP Webhook] Pagamento MP ID: {mp_payment_id}, Status MP: {mp_status}, Payer: {payer_email}, External Ref: {external_reference}, Valor: {transaction_amount}")

            # Se o external_reference for usado para pagamentos únicos, você pode buscar os dados
            # do aluno aqui e chamar o endpoint /cadastrar.
            # Para este exemplo, vou apenas logar e enviar para o Discord.
            send_discord_notification(
                f"💰 Webhook de Pagamento MP Recebido! 💰\n"
                f"ID Pagamento MP: {mp_payment_id}\n"
                f"Status: `{mp_status}`\n"
                f"Valor: R$ {transaction_amount:.2f}\n"
                f"Pagador: {payer_email}\n"
                f"Ref. Externa: {external_reference or 'N/A'}",
                success=(mp_status == 'approved')
            )

        else:
            _log(f"[MP Webhook] Tópico desconhecido ou não tratado: {topic}. Resource ID: {resource_id}. Ignorando.")
            send_discord_notification(f"❓ Webhook MP com Tópico Desconhecido: '{topic}' (ID Recurso: {resource_id}). Ignorado.", success=False)

        return {"status": "success", "message": "Webhook notification processed."}, 200

    except mercadopago.exceptions.MPException as mp_e:
        _log(f"[MP Webhook] ERRO no SDK do Mercado Pago (MPException): Status {mp_e.status_code} - Mensagem: {mp_e.message} - Causa: {mp_e.cause} - ID Recurso: {resource_id}")
        send_discord_notification(f"⚠️ ERRO GRAVE no Webhook MP (SDK)! ⚠️\nErro ao processar notificação.\nStatus MP SDK: {mp_e.status_code}\nMensagem: {mp_e.message}\nID Recurso: {resource_id}\nTópico: {topic}", success=False)
        return {"status": "error", "message": f"SDK error processing webhook: {mp_e.message}"}, 200
    except Exception as e:
        _log(f"[MP Webhook] ERRO GERAL INESPERADO ao processar webhook: {str(e)} (Tipo: {type(e)}) - ID Recurso: {resource_id}, Tópico: {topic}")
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

    _log(f"[MP Redirect] Usuário redirecionado. Preapproval ID: {preapproval_id}, External Ref: {external_reference}, Payment ID: {payment_id}, Collection Status: {collection_status}. Query Params: {request.query_params}")

    message = f"Obrigado! Sua solicitação de pagamento foi enviada."
    sub_message = "Você receberá uma notificação por e-mail assim que o status for confirmado. Acompanhe também pelo seu painel do Mercado Pago."

    # Tentar buscar dados da matrícula pendente para personalizar a mensagem
    # ATENÇÃO: Importar PENDING_ENROLLMENTS de `sandbox_matricular` para fins de teste.
    # Em produção, você buscaria esses dados de um banco de dados persistente.
    from sandbox_matricular import PENDING_ENROLLMENTS as SANDBOX_PENDING_ENROLLMENTS
    pending_data = SANDBOX_PENDING_ENROLLMENTS.get(external_reference)

    if pending_data:
        nome_aluno = pending_data.get("nome", "Aluno(a)")
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
