# Funções utilitárias para o sistema.


def formatar_numero_whatsapp(numero: str) -> str:
    """Remove caracteres não numéricos e garante prefixo '55'."""
    digitos = "".join(filter(str.isdigit, numero or ""))
    if not digitos.startswith("55"):
        digitos = "55" + digitos
    return digitos
