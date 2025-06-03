# webhook.py

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
# Certifique-se de que matricular.py está no mesmo diretório ou acessível no PYTHONPATH
from matricular import _log, matricular_aluno_final, PENDING_ENROLLMENTS

router = APIRouter()

# ──────────────────────────────────────────────────────────
# Variáveis de Ambiente (Puxadas via os.getenv)
# Certifique-se de que estas variáveis estão configuradas no seu ambiente Render.com
# ──────────────────────────────────────────────────────────
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

# ──────────────────────────────────────────────────────────
# Configuração Mercado Pago
# ──────────────────────────────────────────────────────────
if not MP_ACCESS_TOKEN:
    _log("ERRO: MP_ACCESS_TOKEN não configurado para webhook.py. A integração com Mercado Pago não funcionará.")
else:
    mercadopago.config({
        "access_token": MP_ACCESS_TOKEN
    })

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
                "title": "Status de Matrícula Automática",
                "description": message,
                "color": color,
                "timestamp": datetime.now().isoformat()
            }
        ]
    }
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
        response.raise_for_status()
        _log(f"Notificação Discord enviada: {message}")
    except requests.exceptions.RequestException as e:
        _log(f"ERRO ao enviar notificação Discord: {e}")

# ──────────────────────────────────────────────────────────
# Endpoint para Webhooks do Mercado Pago
# ──────────────────────────────────────────────────────────
@router.post("/webhook/mercadopago")
async def mercadopago_webhook(request: Request):
    """
    Endpoint para receber notificações (webhooks) do Mercado Pago.
    Processa a confirmação de pagamento e finaliza a matrícula.
    """
    topic = request.query_params.get("topic")
    id = request.query_params.get("id")

    _log(f"[MP Webhook] Recebido topic: {topic}, ID: {id}")

    if not topic or not id:
        _log("[MP Webhook] Missing 'topic' or 'id' in query parameters.")
        return {"status": "error", "message": "Missing parameters"}, 400

    try:
        if topic == 'preapproval':
            preapproval_info = mercadopago.preapproval.get(id)
            status = preapproval_info.body.get("status")
            payer_email = preapproval_info.body.get("payer_email")
            external_reference = preapproval_info.body.get("external_reference")

            _log(f"[MP Webhook] Assinatura ID: {id}, Status: {status}, Payer: {payer_email}, External Ref: {external_reference}")

            pending_data = PENDING_ENROLLMENTS.get(external_reference)
            if not pending_data:
                _log(f"[MP Webhook] Aluno pendente não encontrado para external_reference: {external_reference}. Possível webhook duplicado ou dado expirado.")
                send_discord_notification(f"Webhook de Assinatura Recebido: Status {status} para {payer_email}. ID de Ref. Externa '{external_reference}' não encontrado no sistema. Pode ser duplicado ou expirado.", success=False)
                return {"status": "success", "message": "External reference not found or already processed."}, 200

            if status == 'authorized':
                if pending_data.get("status") == "matriculado":
                    _log(f"[MP Webhook] Aluno {external_reference} já matriculado. Ignorando webhook duplicado.")
                    send_discord_notification(f"Webhook de Assinatura Recebido: Status {status} para {payer_email}. Aluno '{pending_data['nome']}' já estava matriculado. (ID: {external_reference})", success=True)
                    return {"status": "success", "message": "Already processed."}, 200

                _log(f"Assinatura APROVADA para aluno_id: {external_reference}. Finalizando matrícula...")
                
                try:
                    aluno_id, cpf, disciplinas_ids = matricular_aluno_final(
                        nome=pending_data["nome"],
                        whatsapp=pending_data["whatsapp"],
                        email=pending_data["email"],
                        cursos_nomes=pending_data["cursos_nomes"]
                    )
                    pending_data["status"] = "matriculado"
                    pending_data["aluno_id"] = aluno_id
                    pending_data["cpf"] = cpf
                    _log(f"Matrícula FINALIZADA para {pending_data['nome']} (ID: {aluno_id}, CPF: {cpf}).")
                    send_discord_notification(f"🎉 Matrícula APROVADA e FINALIZADA! 🎉\nAluno: {pending_data['nome']}\nEmail: {pending_data['email']}\nWhatsApp: {pending_data['whatsapp']}\nCursos: {', '.join(pending_data['cursos_nomes'])}\nID Aluno OM: {aluno_id}\nCPF Gerado: {cpf}\nMP Preapproval ID: {id}", success=True)

                except Exception as e:
                    _log(f"ERRO ao finalizar matrícula para {external_reference}: {str(e)}")
                    send_discord_notification(f"⚠️ ERRO na Matrícula Final! ⚠️\nAluno: {pending_data['nome']}\nStatus MP: Aprovado\nErro: {str(e)}\nID Ref. Externa: {external_reference}", success=False)

            elif status == 'pending':
                _log(f"Assinatura PENDENTE para aluno_id: {external_reference}.")
                pending_data["status"] = "payment_pending"
                send_discord_notification(f"Assinatura PENDENTE para {pending_data['nome']}. Aguardando compensação.", success=True)
            elif status == 'cancelled':
                _log(f"Assinatura CANCELADA para aluno_id: {external_reference}.")
                pending_data["status"] = "payment_cancelled"
                send_discord_notification(f"Assinatura CANCELADA para {pending_data['nome']}.", success=False)
            elif status == 'rejected':
                _log(f"Assinatura REJEITADA para aluno_id: {external_reference}.")
                pending_data["status"] = "payment_rejected"
                send_discord_notification(f"Assinatura REJEITADA para {pending_data['nome']}.", success=False)

            return {"status": "success", "message": "Webhook de pré-aprovação processado."}, 200

        elif topic == 'payment':
            return {"status": "success", "message": "Webhook de pagamento processado (ignorando para matrícula inicial)."}, 200

        else:
            _log(f"[MP Webhook] Tópico desconhecido: {topic}. Ignorando.")
            return {"status": "success", "message": "Tópico desconhecido"}, 200

    except mercadopago.exceptions.MPRestException as mp_e:
        _log(f"Erro no SDK do Mercado Pago ao buscar webhook: {mp_e.status_code} - {mp_e.message}")
        send_discord_notification(f"⚠️ ERRO no Webhook MP! ⚠️\nErro ao buscar detalhes da assinatura/pagamento.\nStatus: {mp_e.status_code}\nMensagem: {mp_e.message}\nID: {id}", success=False)
        raise HTTPException(mp_e.status_code, detail=f"Erro ao processar webhook: {mp_e.message}")
    except Exception as e:
        _log(f"Erro ao processar webhook geral: {str(e)}")
        send_discord_notification(f"⚠️ ERRO interno no Webhook! ⚠️\nErro: {str(e)}\nID: {id}\nTópico: {topic}", success=False)
        raise HTTPException(500, detail=f"Erro interno no webhook: {str(e)}")

# ──────────────────────────────────────────────────────────
# Endpoint de Retorno do Pagamento (Opcional, para feedback imediato)
# ──────────────────────────────────────────────────────────
@router.get("/pagamento-status")
async def pagamento_status(request: Request):
    """
    Endpoint para onde o Mercado Pago pode redirecionar o usuário após o pagamento.
    Este é um feedback imediato ao usuário, mas o status final deve vir do webhook.
    """
    status = request.query_params.get("status")
    collection_id = request.query_params.get("collection_id")
    collection_status = request.query_params.get("collection_status")
    payment_id = request.query_params.get("payment_id")
    external_reference = request.query_params.get("external_reference")

    _log(f"[MP Redirect] Status: {status}, Collection ID: {collection_id}, External Ref: {external_reference}")

    if collection_status == "approved":
        message = f"Pagamento aprovado! Sua matrícula está sendo processada. Você receberá um e-mail de confirmação em breve."
    elif collection_status == "pending":
        message = f"Pagamento pendente. Aguardando compensação. Você receberá um e-mail de confirmação assim que o pagamento for aprovado."
    else:
        message = f"Pagamento não aprovado. Status: {collection_status}. Por favor, tente novamente ou entre em contato."
    
    return {"message": message}

