def fix_whatsapp_number(numero: str, e164: bool = False) -> str:
    """Formata numero para o padrao brasileiro com DDI 55.

    Exemplos
    --------
    >>> fix_whatsapp_number("6196660241")
    '556196660241'
    >>> fix_whatsapp_number("+556196660241", e164=True)
    '+556196660241'
    """
    digits = "".join(filter(str.isdigit, numero or ""))
    if not digits.startswith("55"):
        digits = "55" + digits
    return f"+{digits}" if e164 else digits
