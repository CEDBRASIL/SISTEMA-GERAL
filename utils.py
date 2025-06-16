# Funções utilitárias para o sistema.


def formatar_numero_whatsapp(numero: str) -> str:
    """Formata número de WhatsApp garantindo o prefixo `55`."""

    # Extrai apenas os dígitos informados
    digitos = "".join(filter(str.isdigit, numero or ""))

    # Remove prefixo Brasil caso já esteja presente
    if digitos.startswith("55"):
        digitos = digitos[2:]

    # Mantém o nono dígito, compatível com celulares atuais
    return "55" + digitos
