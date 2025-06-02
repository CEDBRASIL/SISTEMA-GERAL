"""
chatpro.py
──────────
Módulo utilitário para envio de mensagens WhatsApp via ChatPro.

• Requer variáveis de ambiente:
  - CHATPRO_URL    → Endpoint base da sua instância ChatPro
  - CHATPRO_TOKEN  → Token ou API-Key fornecida pelo ChatPro

• Uso:
    from chatpro import send_whatsapp

    ok = send_whatsapp("+5561987654321", "Olá, matrícula confirmada!")
    if not ok:
        # tomar ação de fallback / log
"""

import os
import re
import json
from typing import Optional

import requests

# ──────────────────────────────────────────────────────────
# Carregar credenciais do ambiente
# ──────────────────────────────────────────────────────────
CHATPRO_URL: str = os.getenv("CHATPRO_URL", "").rstrip("/")
CHATPRO_TOKEN: str = os.getenv("CHATPRO_TOKEN", "")

if not CHATPRO_URL or not CHATPRO_TOKEN:
    raise EnvironmentError(
        "Variáveis CHATPRO_URL ou CHATPRO_TOKEN não definidas."
    )

# ──────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────
def _sanitize_phone(phone: str) -> str:
    """
    Converte o número informado para formato internacional:
    - Remove qualquer caractere não numérico
    - Garante prefixo '+'
    Ex.: '61 9 8765-4321' → '+5561987654321'
    """
    digits = re.sub(r"\D", "", phone)
    if not digits.startswith("55"):
        digits = "55" + digits  # assume Brasil se não houver DDI
    return f"+{digits}"

# ──────────────────────────────────────────────────────────
# Função principal
# ──────────────────────────────────────────────────────────
def send_whatsapp(phone: str, message: str) -> bool:
    """
    Envia uma mensagem de texto simples para o número informado via ChatPro.

    Retorna:
        True  → requisição aceita (HTTP 2xx)
        False → falha (HTTP ≠ 2xx ou exceção)
    """
    numero = _sanitize_phone(phone)
    payload = {
        "number": numero,
        "message": message
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHATPRO_TOKEN}"
    }

    try:
        response = requests.post(
            CHATPRO_URL,
            headers=headers,
            data=json.dumps(payload),
            timeout=15
        )
        if 200 <= response.status_code < 300:
            return True
        print("❌ ChatPro retorno:", response.status_code, response.text)
        return False
    except requests.RequestException as exc:
        print("❌ Erro ao contactar ChatPro:", exc)
        return False


# ──────────────────────────────────────────────────────────
# Execução rápida de teste (opcional)
# ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    teste = os.getenv("TEST_PHONE")
    if teste:
        print("Enviando teste para", teste)
        ok = send_whatsapp(teste, "Teste automático ChatPro OK ✅")
        print("Sucesso" if ok else "Falhou")
