import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _bool(nome, padrao=False):
    bruto = (os.environ.get(nome) or "").strip().lower()
    if not bruto:
        return padrao
    return bruto in {"1", "true", "yes", "on"}


def ambiente_producao():
    return _bool("RENDER") or (os.environ.get("FLASK_ENV") or "").lower() == "production"


def carregar_config():
    secret = os.environ.get("SECRET_KEY") or "chave_secreta_gestao_escolar"
    return {
        "SECRET_KEY": secret,
        "DATABASE_URL": os.environ.get("DATABASE_URL", "").strip(),
        "DB_HOST": os.environ.get("DB_HOST", "localhost"),
        "DB_PORT": os.environ.get("DB_PORT", "5432"),
        "DB_NAME": os.environ.get("DB_NAME", "gestao_escolar"),
        "DB_USER": os.environ.get("DB_USER", "postgres"),
        "DB_PASSWORD": os.environ.get("DB_PASSWORD", "123456"),
        "DB_SSLMODE": os.environ.get("DB_SSLMODE") or ("require" if os.environ.get("DATABASE_URL") else "prefer"),
        "GOOGLE_CLIENT_ID": os.environ.get("GOOGLE_CLIENT_ID", "").strip(),
        "GOOGLE_CLIENT_SECRET": os.environ.get("GOOGLE_CLIENT_SECRET", "").strip(),
        "ADMIN_EMAILS": os.environ.get("ADMIN_EMAILS", "").strip(),
        "SMTP_HOST": os.environ.get("SMTP_HOST", "").strip(),
        "SMTP_PORT": int(os.environ.get("SMTP_PORT") or 587),
        "SMTP_USER": os.environ.get("SMTP_USER", "").strip(),
        "SMTP_PASSWORD": os.environ.get("SMTP_PASSWORD", "").strip(),
        "SMTP_FROM": os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER") or "",
        "SMTP_TLS": _bool("SMTP_TLS", True),
        "PREFERRED_URL_SCHEME": "https" if ambiente_producao() else "http",
        "SUPER_ADMIN_EMAIL": (os.environ.get("SUPER_ADMIN_EMAIL") or "lucaslagoasreis@gmail.com").strip().lower(),
    }
