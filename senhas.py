import hmac

from werkzeug.security import check_password_hash, generate_password_hash

_PREFIXOS_HASH = ("scrypt:", "pbkdf2:")


def gerar_hash(senha):
    return generate_password_hash(senha or "")


def eh_hash(valor):
    return isinstance(valor, str) and valor.startswith(_PREFIXOS_HASH) and valor.count("$") >= 2


def conferir_senha(armazenada, informada):
    """(confere, precisa_regravar). Senhas antigas em texto puro ainda entram e devem virar hash."""
    if not armazenada or not informada:
        return False, False
    if eh_hash(armazenada):
        try:
            return check_password_hash(armazenada, informada), False
        except (ValueError, TypeError):
            return False, False
    informada_b = informada.encode("utf-8")
    ok = hmac.compare_digest(armazenada.encode("utf-8"), informada_b) or hmac.compare_digest(
        armazenada.strip().encode("utf-8"), informada_b
    )
    return ok, ok
