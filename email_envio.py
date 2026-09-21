import os
import re
import smtplib
from email.message import EmailMessage

from config import ambiente_producao, carregar_config

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def email_valido(valor):
    texto = (valor or "").strip()
    return bool(EMAIL_RE.match(texto))


def normalizar_email(valor):
    return (valor or "").strip().lower()


def _parece_senha_app(valor):
    texto = (valor or "").strip()
    compacto = re.sub(r"\s+", "", texto)
    return bool(re.fullmatch(r"[A-Za-z]{16}", compacto) or re.fullmatch(r"[A-Za-z]{4}(?:\s+[A-Za-z]{4}){3}", texto))


def senha_smtp_normalizada(valor):
    return re.sub(r"\s+", "", (valor or "").strip())


def corrigir_smtp(smtp):
    dados = dict(smtp or {})
    host = (dados.get("SMTP_HOST") or "").strip()
    senha = dados.get("SMTP_PASSWORD") or ""
    usuario = (dados.get("SMTP_USER") or "").strip()
    if _parece_senha_app(host):
        senha = senha_smtp_normalizada(host)
        host = "smtp.gmail.com"
    elif _parece_senha_app(senha):
        senha = senha_smtp_normalizada(senha)
    if "gmail.com" in usuario.lower() or " " in host or "." not in host:
        host = "smtp.gmail.com"
    dados["SMTP_HOST"] = host or "smtp.gmail.com"
    dados["SMTP_PASSWORD"] = senha
    try:
        dados["SMTP_PORT"] = int(dados.get("SMTP_PORT") or 587)
    except (TypeError, ValueError):
        dados["SMTP_PORT"] = 587
    dados["SMTP_USER"] = usuario
    dados["SMTP_FROM"] = (dados.get("SMTP_FROM") or usuario).strip()
    if dados.get("SMTP_TLS") is None:
        dados["SMTP_TLS"] = True
    return dados


def smtp_configurado(cfg=None):
    dados = cfg or carregar_smtp()
    return bool(dados.get("SMTP_HOST") and dados.get("SMTP_USER") and dados.get("SMTP_PASSWORD") and dados.get("SMTP_FROM"))


def carregar_smtp():
    cfg = carregar_config()
    smtp = {
        "SMTP_HOST": cfg["SMTP_HOST"],
        "SMTP_PORT": cfg["SMTP_PORT"],
        "SMTP_USER": cfg["SMTP_USER"],
        "SMTP_PASSWORD": cfg["SMTP_PASSWORD"],
        "SMTP_FROM": cfg["SMTP_FROM"],
        "SMTP_TLS": cfg["SMTP_TLS"],
    }
    smtp = corrigir_smtp(smtp)
    if smtp_configurado(smtp):
        return smtp
    try:
        from database import obter_conexao
        conexao = obter_conexao(master=True)
    except Exception:
        conexao = None
    if conexao:
        try:
            with conexao.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT smtp_host, smtp_port, smtp_user, smtp_password, smtp_from, smtp_tls
                    FROM plataforma_smtp WHERE id = 1
                    """
                )
                row = cursor.fetchone() or {}
            if isinstance(row, dict) and row.get("smtp_user") and (
                row.get("smtp_password") or _parece_senha_app(row.get("smtp_host"))
            ):
                smtp["SMTP_HOST"] = (row.get("smtp_host") or "").strip()
                smtp["SMTP_PORT"] = int(row.get("smtp_port") or 587)
                smtp["SMTP_USER"] = (row.get("smtp_user") or "").strip()
                smtp["SMTP_PASSWORD"] = row.get("smtp_password") or ""
                smtp["SMTP_FROM"] = (row.get("smtp_from") or row.get("smtp_user") or "").strip()
                smtp["SMTP_TLS"] = bool(row.get("smtp_tls") if row.get("smtp_tls") is not None else True)
                smtp = corrigir_smtp(smtp)
        except Exception:
            pass
        finally:
            conexao.close()
    if smtp_configurado(smtp):
        return smtp
    from database import _nome_banco_atual, obter_conexao
    if not _nome_banco_atual(master=False):
        return smtp
    try:
        conexao = obter_conexao()
    except Exception:
        conexao = None
    if not conexao:
        return smtp
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                SELECT smtp_host, smtp_port, smtp_user, smtp_password, smtp_from, smtp_tls
                FROM configuracoes WHERE id = 1
                """
            )
            row = cursor.fetchone() or {}
        if not isinstance(row, dict):
            return smtp
        if row.get("smtp_host"):
            smtp["SMTP_HOST"] = (row.get("smtp_host") or "").strip()
        if row.get("smtp_port"):
            smtp["SMTP_PORT"] = int(row.get("smtp_port") or 587)
        if row.get("smtp_user"):
            smtp["SMTP_USER"] = (row.get("smtp_user") or "").strip()
        if row.get("smtp_password"):
            smtp["SMTP_PASSWORD"] = row.get("smtp_password") or ""
        remetente = (row.get("smtp_from") or row.get("smtp_user") or "").strip()
        if remetente:
            smtp["SMTP_FROM"] = remetente
        if row.get("smtp_tls") is not None:
            smtp["SMTP_TLS"] = bool(row.get("smtp_tls"))
    except Exception:
        pass
    finally:
        conexao.close()
    return corrigir_smtp(smtp)


def emails_contato_aluno(cursor, aluno_id):
    destinos = []
    cursor.execute("SELECT email FROM alunos WHERE id = %s", (aluno_id,))
    row = cursor.fetchone() or {}
    if email_valido(row.get("email") if isinstance(row, dict) else None):
        destinos.append(normalizar_email(row["email"]))
    cursor.execute(
        "SELECT email FROM responsaveis_aluno WHERE aluno_id = %s AND COALESCE(email, '') <> ''",
        (aluno_id,),
    )
    for item in cursor.fetchall() or []:
        bruto = item.get("email") if isinstance(item, dict) else item[0]
        if email_valido(bruto):
            destinos.append(normalizar_email(bruto))
    vistos = []
    for email in destinos:
        if email not in vistos:
            vistos.append(email)
    return vistos


def obter_access_token_gmail():
    cfg = carregar_config()
    cid = (cfg.get("GOOGLE_CLIENT_ID") or "").strip()
    secret = (cfg.get("GOOGLE_CLIENT_SECRET") or "").strip()
    refresh = ""
    remetente = (cfg.get("SMTP_FROM") or cfg.get("SMTP_USER") or "").strip()
    try:
        from database import obter_conexao
        conexao = obter_conexao(master=True)
    except Exception:
        conexao = None
    if conexao:
        try:
            with conexao.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT google_client_id, google_client_secret, google_refresh_token, smtp_user, smtp_from
                    FROM plataforma_smtp WHERE id = 1
                    """
                )
                row = cursor.fetchone() or {}
            if isinstance(row, dict):
                cid = cid or (row.get("google_client_id") or "").strip()
                secret = secret or (row.get("google_client_secret") or "").strip()
                refresh = (row.get("google_refresh_token") or "").strip()
                remetente = remetente or (row.get("smtp_from") or row.get("smtp_user") or "").strip()
        except Exception:
            pass
        finally:
            conexao.close()
    if not (cid and secret and refresh) or "@" in cid:
        return None, remetente
    try:
        import json
        import urllib.parse
        import urllib.request
        dados = urllib.parse.urlencode(
            {
                "client_id": cid,
                "client_secret": secret,
                "refresh_token": refresh,
                "grant_type": "refresh_token",
            }
        ).encode("utf-8")
        req = urllib.request.Request("https://oauth2.googleapis.com/token", data=dados, method="POST")
        with urllib.request.urlopen(req, timeout=8) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return (payload.get("access_token") or "").strip() or None, remetente
    except Exception:
        return None, remetente


def diagnostico_envio():
    cfg = carregar_config()
    smtp_ok = smtp_configurado()
    return {
        "smtp_user": bool(cfg.get("SMTP_USER")),
        "smtp_password": bool(cfg.get("SMTP_PASSWORD")),
        "smtp_host": cfg.get("SMTP_HOST") or "—",
        "smtp_port": cfg.get("SMTP_PORT") or 587,
        "producao_render": ambiente_producao(),
        "gmail_api": False,
        "resend": False,
        "brevo": False,
        "status": "pronto" if smtp_ok else "faltando",
        "detalhe": (
            "O servidor envia sozinho com SMTP_USER e SMTP_PASSWORD do Render. Ninguém é redirecionado ao Google."
            if smtp_ok
            else "Faltam SMTP_USER e SMTP_PASSWORD no Environment do Render."
        ),
    }


def _smtp_ipv4(host, porta, timeout=12):
    import socket
    original = socket.getaddrinfo

    def so_ipv4(hostname, port, family=0, type=0, proto=0, flags=0):
        infos = original(hostname, port, socket.AF_INET, type, proto, flags)
        if infos:
            return infos
        return original(hostname, port, family, type, proto, flags)

    socket.getaddrinfo = so_ipv4
    try:
        return smtplib.SMTP(host, porta, timeout=timeout)
    finally:
        socket.getaddrinfo = original


def _smtp_ssl_ipv4(host, porta, timeout=12):
    import socket
    original = socket.getaddrinfo

    def so_ipv4(hostname, port, family=0, type=0, proto=0, flags=0):
        infos = original(hostname, port, socket.AF_INET, type, proto, flags)
        if infos:
            return infos
        return original(hostname, port, family, type, proto, flags)

    socket.getaddrinfo = so_ipv4
    try:
        return smtplib.SMTP_SSL(host, porta, timeout=timeout)
    finally:
        socket.getaddrinfo = original


def _tentar_smtp_gmail(cfg, msg):
    usuario = (cfg.get("SMTP_USER") or "").strip()
    senha_bruta = cfg.get("SMTP_PASSWORD") or ""
    host = (cfg.get("SMTP_HOST") or "smtp.gmail.com").strip() or "smtp.gmail.com"
    senhas = []
    for item in (senha_bruta, senha_smtp_normalizada(senha_bruta)):
        if item and item not in senhas:
            senhas.append(item)
    try:
        porta_cfg = int(cfg.get("SMTP_PORT") or 587)
    except (TypeError, ValueError):
        porta_cfg = 587
    tentativas = [(False, 587)]
    if porta_cfg == 465:
        tentativas = [(True, 465), (False, 587)]
    elif porta_cfg not in {587, 0}:
        tentativas = [(False, porta_cfg), (False, 587)]
    ultimo = None
    for senha in senhas:
        for usar_ssl, porta in tentativas:
            try:
                smtp = _smtp_ssl_ipv4(host, porta) if usar_ssl else _smtp_ipv4(host, porta)
                with smtp:
                    if not usar_ssl:
                        smtp.starttls()
                    smtp.login(usuario, senha)
                    smtp.send_message(msg)
                return
            except smtplib.SMTPAuthenticationError as e:
                ultimo = e
            except (OSError, smtplib.SMTPException) as e:
                ultimo = e
    if isinstance(ultimo, smtplib.SMTPAuthenticationError):
        raise RuntimeError(
            "O Gmail recusou a senha de app. Confira SMTP_USER e SMTP_PASSWORD no Environment do Render."
        ) from ultimo
    if ultimo:
        raise ultimo
    raise RuntimeError("Não foi possível conectar ao Gmail para enviar o e-mail.")


def _montar_mensagem(remetente, destinos, assunto, corpo, html=None, anexos=None):
    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = remetente
    msg["To"] = ", ".join(destinos)
    msg.set_content(corpo)
    if html:
        msg.add_alternative(html, subtype="html")
    for anexo in anexos or []:
        nome = anexo.get("nome") or "documento.pdf"
        dados = anexo.get("dados") or b""
        tipo = anexo.get("tipo") or "application/pdf"
        main, _, sub = tipo.partition("/")
        msg.add_attachment(dados, maintype=main or "application", subtype=sub or "pdf", filename=nome)
    return msg


def enviar_email(destinos, assunto, corpo, anexos=None, html=None, access_token=None):
    lista = []
    for item in destinos or []:
        if email_valido(item):
            lista.append(normalizar_email(item))
    if not lista:
        raise RuntimeError("Nenhum e-mail válido para envio. Cadastre o e-mail do responsável, professor ou destinatário.")

    cfg = carregar_config()
    smtp = {
        "SMTP_HOST": (cfg.get("SMTP_HOST") or os.environ.get("SMTP_HOST") or "smtp.gmail.com").strip(),
        "SMTP_PORT": cfg.get("SMTP_PORT") or int(os.environ.get("SMTP_PORT") or 587),
        "SMTP_USER": (cfg.get("SMTP_USER") or os.environ.get("SMTP_USER") or "").strip(),
        "SMTP_PASSWORD": cfg.get("SMTP_PASSWORD") or os.environ.get("SMTP_PASSWORD") or "",
        "SMTP_FROM": (cfg.get("SMTP_FROM") or os.environ.get("SMTP_FROM") or cfg.get("SMTP_USER") or "").strip(),
        "SMTP_TLS": True,
    }
    smtp = corrigir_smtp(smtp)
    if not smtp_configurado(smtp):
        raise RuntimeError("Faltam SMTP_USER e SMTP_PASSWORD no Environment do Render.")
    msg = _montar_mensagem(
        smtp.get("SMTP_FROM") or smtp.get("SMTP_USER"),
        lista,
        assunto,
        corpo,
        html=html,
        anexos=anexos,
    )
    _tentar_smtp_gmail(smtp, msg)
    print(f"e-mail enviado via SMTP para {lista}")
    return lista


def bytes_pdf(buffer):
    buffer.seek(0)
    return buffer.read()


def exigencia_email(valor, rotulo="E-mail"):
    texto = (valor or "").strip()
    if not texto:
        raise ValueError(f"{rotulo} é obrigatório e precisa ser um endereço válido.")
    if not email_valido(texto):
        raise ValueError(f"{rotulo} inválido. Use um endereço real, por exemplo nome@dominio.com.")
    return normalizar_email(texto)


def enviar_via_gmail_api(access_token, destinos, assunto, corpo, remetente=None, anexos=None, html=None):
    import base64
    import json
    import urllib.error
    import urllib.request

    lista = [normalizar_email(item) for item in (destinos or []) if email_valido(item)]
    if not lista:
        raise RuntimeError("Nenhum e-mail válido para envio.")
    if not access_token:
        raise RuntimeError("Login Google sem permissão de envio.")
    de = (remetente or "").strip() or lista[0]
    msg = _montar_mensagem(de, lista, assunto, corpo, html=html, anexos=anexos)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode().rstrip("=")
    req = urllib.request.Request(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        data=json.dumps({"raw": raw}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        detalhe = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gmail recusou o envio: {e.code} {detalhe}") from e
    return lista
