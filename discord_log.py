"""
discord_log.py
──────────────
Utilitário simples para registrar eventos em um canal Discord via Webhook.

Variável de ambiente necessária:
    DISCORD_WEBHOOK  → URL completa do webhook gerado no Discord

Uso:
    from discord_log import send_discord

    send_discord("✅ Matrícula confirmada para João Silva – Curso Administração.")
"""

import os
import json
from typing import Optional

import requests

# ──────────────────────────────────────────────────────────
# Carregar webhook do ambiente
# ──────────────────────────────────────────────────────────
DISCORD_WEBHOOK: Optional[str] = os.getenv("DISCORD_WEBHOOK")

if not DISCORD_WEBHOOK:
    raise EnvironmentError(
        "Variável DISCORD_WEBHOOK não definida no ambiente."
    )

# ──────────────────────────────────────────────────────────
# Função principal
# ──────────────────────────────────────────────────────────
def send_discord(message: str, username: str = "CED Bot") -> bool:
    """
    Envia uma mensagem simples ao canal Discord configurado.

    Args:
        message  : Texto (Markdown permitido) a ser postado.
        username : Nome que aparecerá no Discord (padrão: 'CED Bot').

    Returns:
        True  → HTTP 2xx (sucesso)
        False → HTTP != 2xx ou exceção
    """
    payload = {
        "username": username,
        "content": message
    }

    try:
        resp = requests.post(
            DISCORD_WEBHOOK,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        if 200 <= resp.status_code < 300:
            return True
        print("❌ Discord webhook retorno:", resp.status_code, resp.text)
        return False
    except requests.RequestException as exc:
        print("❌ Erro ao enviar webhook Discord:", exc)
        return False


# ──────────────────────────────────────────────────────────
# Execução rápida de teste (opcional)
# ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    teste_msg = "🔔 Teste automático do webhook Discord OK."
    ok = send_discord(teste_msg)
    print("Webhook enviado 👉", ok)
