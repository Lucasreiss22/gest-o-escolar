import os

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass


def _bool(nome, padrao=False):
    bruto = (os.environ.get(nome) or "").strip().lower()
    if not bruto:
        return padrao
    return bruto in {"1", "true", "yes", "on"}


def _int_env(nome, padrao):
    bruto = (os.environ.get(nome) or "").strip()
    try:
        return int(bruto)
    except (TypeError, ValueError):
        return padrao


def ambiente_producao():
    return _bool("RENDER") or (os.environ.get("FLASK_ENV") or "").lower() == "production"


def carregar_config():
    secret = os.environ.get("SECRET_KEY") or "chave_secreta_gestao_escolar"
    smtp_user = (os.environ.get("SMTP_USER") or os.environ.get("MAIL_USERNAME") or "").strip()
    smtp_pass = (os.environ.get("SMTP_PASSWORD") or os.environ.get("MAIL_PASSWORD") or "").replace(" ", "").strip()
    super_email = (os.environ.get("SUPER_ADMIN_EMAIL") or "lucaslagoasreis@gmail.com").strip().lower()
    smtp_user = smtp_user or (super_email if smtp_pass else "")
    smtp_from = (os.environ.get("SMTP_FROM") or os.environ.get("MAIL_DEFAULT_SENDER") or smtp_user).strip()
    return {
        "SECRET_KEY": secret,
        "DATABASE_URL": "".join((os.environ.get("DATABASE_URL") or "").split()).replace("[", "").replace("]", ""),
        "DB_HOST": os.environ.get("DB_HOST", "localhost"),
        "DB_PORT": os.environ.get("DB_PORT", "5432"),
        "DB_NAME": os.environ.get("DB_NAME", "gestao_escolar"),
        "DB_USER": os.environ.get("DB_USER", "postgres"),
        "DB_PASSWORD": os.environ.get("DB_PASSWORD", "123456"),
        "DB_SSLMODE": os.environ.get("DB_SSLMODE") or ("require" if os.environ.get("DATABASE_URL") else "prefer"),
        "GOOGLE_CLIENT_ID": os.environ.get("GOOGLE_CLIENT_ID", "").strip(),
        "GOOGLE_CLIENT_SECRET": os.environ.get("GOOGLE_CLIENT_SECRET", "").strip(),
        "ADMIN_EMAILS": os.environ.get("ADMIN_EMAILS", "").strip(),
        "SMTP_HOST": (os.environ.get("SMTP_HOST") or os.environ.get("MAIL_SERVER") or "").strip() or ("smtp.gmail.com" if smtp_pass else ""),
        "SMTP_PORT": _int_env("SMTP_PORT", _int_env("MAIL_PORT", 587)),
        "SMTP_USER": smtp_user,
        "SMTP_PASSWORD": smtp_pass,
        "SMTP_FROM": smtp_from,
        "SMTP_TLS": _bool("SMTP_TLS", True),
        "BREVO_API_KEY": (os.environ.get("BREVO_API_KEY") or "").strip(),
        "RESEND_API_KEY": (os.environ.get("RESEND_API_KEY") or "").strip(),
        "SENDGRID_API_KEY": (os.environ.get("SENDGRID_API_KEY") or "").strip(),
        "PREFERRED_URL_SCHEME": "https" if ambiente_producao() else "http",
        "SUPER_ADMIN_EMAIL": super_email,
    }
