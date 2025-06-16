# Funções utilitárias para o sistema.


def formatar_numero_whatsapp(numero: str) -> str:
    """Formata o telefone para envio via WhatsApp.

    - Garante o prefixo brasileiro ``55``.
    - Remove quaisquer caracteres não numéricos.
    - Remove o nono dígito logo após o DDD, caso presente.
    """

    # Extrai apenas os dígitos informados
    digitos = "".join(filter(str.isdigit, numero or ""))

    # Remove prefixo Brasil caso já esteja presente
    if digitos.startswith("55"):
        digitos = digitos[2:]

    # Remove o nono dígito (ex.: 61912345678 -> 6112345678)
    if len(digitos) >= 11 and digitos[2] == "9":
        digitos = digitos[:2] + digitos[3:]

    return "55" + digitos
