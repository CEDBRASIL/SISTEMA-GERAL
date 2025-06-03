"""
webhook.py – Recebe notificações do Mercado Pago e finaliza a matrícula.
Envia logs para o Discord.
"""

import os
import requests
from fastapi import APIRouter, HTTPException, Request
from datetime import datetime
import mercadopago

# Importa as funções e o armazenamento temporário de matricular.py
from matricular import _log, matricular_aluno_final, PENDING_ENROLLMENTS

router = APIRouter()

# ──────────────────────────────────────────────────────────
# Variáveis de Ambiente
# ──────────────────────────────────────────────────────────
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

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
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10) # Aumentado timeout
        response.raise_for_status()
        _log(f"Notificação Discord enviada: {message[:100]}...")
    except requests.exceptions.RequestException as e:
        _log(f"ERRO ao enviar notificação Discord: {e}")

# ──────────────────────────────────────────────────────────
# Endpoint para Webhooks do Mercado Pago
# ──────────────────────────────────────────────────────────
@router.post("/webhook/mercadopago")
async def mercadopago_webhook(request: Request):
    topic = request.query_params.get("topic")
    notification_id = request.query_params.get("id") # O ID aqui é da notificação, não do recurso em si

    _log(f"[MP Webhook] Recebido topic: {topic}, Notification ID: {notification_id}")

    if not topic or not notification_id:
        _log("[MP Webhook] ERRO: 'topic' ou 'id' ausentes nos query parameters.")
        # MP espera 200 ou 201, mesmo em erro nosso para não ficar reenviando indefinidamente.
        return {"status": "error", "message": "Missing parameters"}, 200 

    if not sdk_webhook:
        _log("[MP Webhook] ERRO CRÍTICO: SDK do Mercado Pago não inicializado em webhook.py.")
        send_discord_notification("⚠️ ERRO CRÍTICO no Webhook MP! ⚠️\nSDK do Mercado Pago não inicializado. As notificações não podem ser processadas.", success=False)
        return {"status": "error", "message": "Internal SDK configuration error"}, 200

    try:
        if topic == 'preapproval':
            # Com o ID da notificação, obtemos os dados da pré-aprovação
            preapproval_info_dict = sdk_webhook.preapproval().get(notification_id)
            
            if not (preapproval_info_dict and preapproval_info_dict.get("status") in [200, 201]):
                error_details = preapproval_info_dict.get('response', preapproval_info_dict) if preapproval_info_dict else "Resposta vazia"
                status_code = preapproval_info_dict.get('status', 'N/A') if preapproval_info_dict else 'N/A'
                _log(f"[MP Webhook] ERRO ao buscar dados da pré-aprovação ID {notification_id}. Status MP: {status_code}, Detalhes: {error_details}")
                send_discord_notification(f"⚠️ ERRO no Webhook MP! ⚠️\nFalha ao buscar detalhes da assinatura (ID Notif: {notification_id}).\nStatus MP: {status_code}\nDetalhes: {str(error_details)[:200]}", success=False)
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

            pending_data = PENDING_ENROLLMENTS.get(external_reference)
            if not pending_data:
                _log(f"[MP Webhook] Aluno pendente não encontrado para external_reference: {external_reference}. MP ID: {preapproval_mp_id}. Possível webhook tardio/duplicado ou dado expirado/não encontrado.")
                send_discord_notification(f"Webhook de Assinatura Recebido: Status {mp_status} para {payer_email} (MP ID: {preapproval_mp_id}).\nID de Ref. Externa '{external_reference}' NÃO encontrado no sistema. Pode ser tardio, duplicado ou expirado.", success=False)
                return {"status": "success", "message": "External reference not found or already processed."}, 200

            # Atualizar o status no PENDING_ENROLLMENTS com o status do MP
            pending_data["mp_status"] = mp_status
            pending_data["mp_preapproval_id_confirmed"] = preapproval_mp_id # Guardar o ID do MP confirmado

            if mp_status == 'authorized': # Assinatura autorizada (pagamento inicial aprovado)
                if pending_data.get("status") == "matriculado":
                    _log(f"[MP Webhook] Aluno {external_reference} (Nome: {pending_data.get('nome')}) já consta como 'matriculado'. Ignorando webhook 'authorized' duplicado ou tardio.")
                    send_discord_notification(f"Webhook 'authorized' para Assinatura MP ID {preapproval_mp_id} (Ref: {external_reference}).\nAluno '{pending_data.get('nome')}' já estava matriculado.", success=True)
                    return {"status": "success", "message": "Already processed as matriculado."}, 200

                _log(f"Assinatura AUTORIZADA para external_ref: {external_reference}. Tentando finalizar matrícula...")
                try:
                    aluno_id, cpf, disciplinas_ids = matricular_aluno_final(
                        nome=pending_data["nome"],
                        whatsapp=pending_data["whatsapp"],
                        email=pending_data["email"],
                        cursos_nomes=pending_data["cursos_nomes"]
                    )
                    pending_data["status"] = "matriculado"
                    pending_data["aluno_id_om"] = aluno_id # ID do aluno no sistema OM
                    pending_data["cpf_gerado"] = cpf
                    pending_data["matricula_finalizada_em"] = datetime.now().isoformat()
                    _log(f"Matrícula FINALIZADA para {pending_data['nome']} (ID OM: {aluno_id}, CPF: {cpf}). External Ref: {external_reference}")
                    send_discord_notification(f"🎉 Matrícula APROVADA e FINALIZADA! 🎉\nAluno: {pending_data['nome']}\nEmail: {pending_data['email']}\nCursos: {', '.join(pending_data['cursos_nomes'])}\nID Aluno OM: {aluno_id}\nCPF Gerado: {cpf}\nMP Preapproval ID: {preapproval_mp_id}\nRef. Externa: {external_reference}", success=True)
                
                except RuntimeError as e_mat: # Erro específico de matricular_aluno_final
                    _log(f"ERRO CRÍTICO ao finalizar matrícula para {external_reference} (Nome: {pending_data['nome']}): {str(e_mat)}")
                    pending_data["status"] = "erro_matricula_om"
                    pending_data["erro_matricula_om_msg"] = str(e_mat)
                    send_discord_notification(f"⚠️ ERRO GRAVE na Matrícula Final OM! ⚠️\nAluno: {pending_data['nome']} (Ref: {external_reference})\nStatus MP: Autorizado ({mp_status})\nErro OM: {str(e_mat)}\nMP Preapproval ID: {preapproval_mp_id}", success=False)
                except Exception as e_geral: # Outro erro inesperado
                    _log(f"ERRO INESPERADO ao finalizar matrícula para {external_reference} (Nome: {pending_data['nome']}): {str(e_geral)}")
                    pending_data["status"] = "erro_inesperado_matricula"
                    pending_data["erro_inesperado_matricula_msg"] = str(e_geral)
                    send_discord_notification(f"⚠️ ERRO INESPERADO na Matrícula Final! ⚠️\nAluno: {pending_data['nome']} (Ref: {external_reference})\nStatus MP: Autorizado ({mp_status})\nErro: {str(e_geral)}\nMP Preapproval ID: {preapproval_mp_id}", success=False)


            elif mp_status == 'pending': # Assinatura pendente de autorização
                _log(f"Assinatura PENDENTE para external_ref: {external_reference} (Nome: {pending_data.get('nome')}).")
                pending_data["status"] = "payment_pending_mp"
                send_discord_notification(f"⏳ Assinatura PENDENTE no MP para {pending_data.get('nome')} (Ref: {external_reference}).\nMP Preapproval ID: {preapproval_mp_id}.\nAguardando autorização/compensação.", success=True)
            
            elif mp_status == 'paused': # Assinatura pausada
                _log(f"Assinatura PAUSADA para external_ref: {external_reference} (Nome: {pending_data.get('nome')}).")
                pending_data["status"] = "subscription_paused_mp"
                send_discord_notification(f"⏸️ Assinatura PAUSADA no MP para {pending_data.get('nome')} (Ref: {external_reference}).\nMP Preapproval ID: {preapproval_mp_id}.", success=True) # Neutro, nem sucesso nem falha total

            elif mp_status == 'cancelled': # Assinatura cancelada
                _log(f"Assinatura CANCELADA para external_ref: {external_reference} (Nome: {pending_data.get('nome')}).")
                pending_data["status"] = "subscription_cancelled_mp"
                send_discord_notification(f"❌ Assinatura CANCELADA no MP para {pending_data.get('nome')} (Ref: {external_reference}).\nMP Preapproval ID: {preapproval_mp_id}.", success=False)
                # Considerar remover de PENDING_ENROLLMENTS ou marcar como inativo permanentemente
                # PENDING_ENROLLMENTS.pop(external_reference, None)
            
            else: # Outros status (ex: rejected, etc.)
                _log(f"Assinatura com status MP '{mp_status}' para external_ref: {external_reference} (Nome: {pending_data.get('nome')}).")
                pending_data["status"] = f"subscription_{mp_status}_mp"
                send_discord_notification(f"ℹ️ Status da Assinatura MP: '{mp_status}' para {pending_data.get('nome')} (Ref: {external_reference}).\nMP Preapproval ID: {preapproval_mp_id}.", success=False)


        elif topic == 'payment':
            # Você pode querer processar notificações de pagamento se sua lógica de assinatura
            # depender de pagamentos recorrentes individuais. Por agora, está ignorando.
            _log(f"[MP Webhook] Notificação de 'payment' recebida (ID: {notification_id}). Ignorando para fluxo de matrícula inicial focado em 'preapproval'.")
            # payment_info = sdk_webhook.payment().get(notification_id) # Exemplo se fosse processar
            # _log(f"[MP Webhook] Detalhes do pagamento: {payment_info}")
            send_discord_notification(f"ℹ️ Webhook de Pagamento MP Recebido (ID Notif: {notification_id}).\nIgnorando, pois o foco é em 'preapproval' para assinaturas.", success=True)


        else:
            _log(f"[MP Webhook] Tópico desconhecido ou não tratado: {topic}. Notification ID: {notification_id}. Ignorando.")
            send_discord_notification(f"❓ Webhook MP com Tópico Desconhecido: '{topic}' (ID Notif: {notification_id}). Ignorado.", success=False)

        return {"status": "success", "message": "Webhook notification processed."}, 200

    except mercadopago.exceptions.MPException as mp_e:
        _log(f"[MP Webhook] ERRO no SDK do Mercado Pago (MPException): Status {mp_e.status_code} - Mensagem: {mp_e.message} - Causa: {mp_e.cause} - ID Notif: {notification_id}")
        send_discord_notification(f"⚠️ ERRO GRAVE no Webhook MP (SDK)! ⚠️\nErro ao processar notificação.\nStatus MP SDK: {mp_e.status_code}\nMensagem: {mp_e.message}\nID Notif: {notification_id}\nTópico: {topic}", success=False)
        # Retornar 200 para o MP não reenviar indefinidamente se for um erro nosso que não pode ser resolvido por reenvio
        return {"status": "error", "message": f"SDK error processing webhook: {mp_e.message}"}, 200
    except Exception as e:
        _log(f"[MP Webhook] ERRO GERAL INESPERADO ao processar webhook: {str(e)} (Tipo: {type(e)}) - ID Notif: {notification_id}, Tópico: {topic}")
        send_discord_notification(f"⚠️ ERRO INTERNO GRAVE no Webhook MP! ⚠️\nErro: {str(e)}\nID Notif: {notification_id}\nTópico: {topic}", success=False)
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
    # Parâmetros comuns de redirect para pré-aprovação (assinatura)
    preapproval_id = request.query_params.get("preapproval_id") # ID da assinatura no MP
    external_reference = request.query_params.get("external_reference") # Nosso ID
    # O status da assinatura em si (authorized, pending, etc.) virá pelo webhook.
    # O redirect pode não ter um "status" explícito da transação inicial da mesma forma que um pagamento único.

    _log(f"[MP Redirect] Usuário redirecionado. Preapproval ID: {preapproval_id}, External Ref: {external_reference}. Query Params: {request.query_params}")

    message = f"Obrigado! Sua solicitação de assinatura (ID: {preapproval_id or 'N/A'}) foi enviada."
    sub_message = "Você receberá uma notificação por e-mail assim que o status for confirmado. Acompanhe também pelo seu painel do Mercado Pago."

    # Tentar buscar dados da matrícula pendente para personalizar a mensagem
    if external_reference and external_reference in PENDING_ENROLLMENTS:
        pending_data = PENDING_ENROLLMENTS[external_reference]
        nome_aluno = pending_data.get("nome", "Aluno(a)")
        message = f"Olá {nome_aluno}, obrigado! Sua solicitação de assinatura foi enviada ao Mercado Pago."
        
        # Uma verificação rápida do status no MP (opcional, pode adicionar latência)
        # if sdk_webhook and preapproval_id:
        #     try:
        #         info = sdk_webhook.preapproval().get(preapproval_id)
        #         if info and info.get("status") == 200 and info.get("response", {}).get("status"):
        #             mp_current_status = info["response"]["status"]
        #             if mp_current_status == 'authorized':
        #                 sub_message = "Seu primeiro pagamento parece ter sido aprovado! Estamos processando sua matrícula."
        #             elif mp_current_status == 'pending':
        #                 sub_message = "Seu pagamento está pendente de aprovação no Mercado Pago. Aguarde a confirmação."
        #     except Exception:
        #         _log(f"Falha ao buscar status imediato do MP para {preapproval_id} no redirect.")
        #         pass # Segue com a mensagem padrão
    
    # Esta página é apenas um feedback visual. A lógica de matrícula ocorre no webhook.
    # Idealmente, esta rota retornaria HTML para o usuário ou redirecionaria para uma página de "obrigado" no frontend.
    # Por ora, retorna JSON.
    return {
        "title": "Processando Assinatura",
        "message": message,
        "sub_message": sub_message,
        "mp_preapproval_id": preapproval_id,
        "your_reference_id": external_reference,
        "important_note": "A confirmação final da sua matrícula e o status do pagamento serão enviados por e-mail e processados em segundo plano."
    }

