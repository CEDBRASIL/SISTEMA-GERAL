# Funções utilitárias para o sistema.


def formatar_numero_whatsapp(numero: str) -> str:
    """Formata número de WhatsApp removendo o '9' e garantindo prefixo '55'."""

    # Extrai apenas os dígitos
    digitos = "".join(filter(str.isdigit, numero or ""))

    # Remove prefixo Brasil caso já esteja presente
    if digitos.startswith("55"):
        digitos = digitos[2:]

    # Remove o nono dígito (após o DDD) se existir
    if len(digitos) == 11 and digitos[2] == "9":
        digitos = digitos[:2] + digitos[3:]

    # Garante o prefixo brasileiro
    return "55" + digitos
