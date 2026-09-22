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
    return smtp


def identidade_envio():
    """Quem aparece no envio: e-mail da escola + nome de quem disparou. Sem senha SMTP do funcionário."""
    nome_escola = "Gestão Escolar"
    email_escola = ""
    nome_pessoa = ""
    try:
        from flask import has_request_context, session
        if has_request_context():
            nome_escola = (session.get("escola_nome") or nome_escola).strip() or nome_escola
            nome_pessoa = (session.get("usuario_nome") or "").strip()
    except Exception:
        pass
    try:
        from database import _nome_banco_atual, obter_conexao
        if _nome_banco_atual(master=False):
            conexao = obter_conexao()
            if conexao:
                try:
                    with conexao.cursor() as cursor:
                        cursor.execute(
                            "SELECT nome_escola, email_contato FROM configuracoes WHERE id = 1"
                        )
                        row = cursor.fetchone() or {}
                    if isinstance(row, dict):
                        nome_escola = (row.get("nome_escola") or nome_escola or "").strip() or nome_escola
                        email_escola = (row.get("email_contato") or "").strip()
                except Exception:
                    pass
                finally:
                    try:
                        conexao.close()
                    except Exception:
                        pass
    except Exception:
        pass
    nome_visivel = nome_pessoa or nome_escola
    if nome_pessoa and nome_escola and nome_pessoa.lower() != nome_escola.lower():
        nome_visivel = f"{nome_pessoa} · {nome_escola}"
    return nome_visivel, nome_escola, email_escola


def identidade_escola():
    nome_visivel, _nome_escola, email_escola = identidade_envio()
    return nome_visivel, email_escola


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


def _chaves_api_email(cfg=None):
    cfg = cfg or carregar_config()
    return {
        "brevo": (cfg.get("BREVO_API_KEY") or os.environ.get("BREVO_API_KEY") or "").strip(),
        "resend": (cfg.get("RESEND_API_KEY") or os.environ.get("RESEND_API_KEY") or "").strip(),
        "sendgrid": (cfg.get("SENDGRID_API_KEY") or os.environ.get("SENDGRID_API_KEY") or "").strip(),
    }


def _tem_envio_https(cfg=None):
    return any(_chaves_api_email(cfg).values())


def _forcar_smtp():
    return (os.environ.get("SMTP_FORCE") or "").strip().lower() in {"1", "true", "yes", "on"}


def diagnostico_envio():
    cfg = carregar_config()
    smtp_ok = smtp_configurado()
    chaves = _chaves_api_email(cfg)
    https_ok = any(chaves.values())
    producao = ambiente_producao()
    if https_ok:
        meio = "Brevo" if chaves["brevo"] else ("Resend" if chaves["resend"] else "SendGrid")
        return {
            "smtp_user": bool(cfg.get("SMTP_USER")),
            "smtp_password": bool(cfg.get("SMTP_PASSWORD")),
            "smtp_host": cfg.get("SMTP_HOST") or "—",
            "smtp_port": cfg.get("SMTP_PORT") or 587,
            "producao_render": producao,
            "gmail_api": False,
            "resend": bool(chaves["resend"]),
            "brevo": bool(chaves["brevo"]),
            "status": "pronto",
            "detalhe": f"Envio automático por HTTPS ({meio}). O plano Free do Render bloqueia SMTP; a API não usa a porta 587.",
        }
    if smtp_ok and producao:
        return {
            "smtp_user": True,
            "smtp_password": True,
            "smtp_host": cfg.get("SMTP_HOST") or "smtp.gmail.com",
            "smtp_port": cfg.get("SMTP_PORT") or 587,
            "producao_render": True,
            "gmail_api": False,
            "resend": False,
            "brevo": False,
            "status": "bloqueado",
            "detalhe": (
                "SMTP_USER e SMTP_PASSWORD estão certos, mas o plano Free do Render bloqueia "
                "as portas 25, 465 e 587 (por isso aparece timed out). "
                "Para o e-mail sair sozinho: cadastre BREVO_API_KEY no Environment "
                "ou suba o serviço para um plano pago."
            ),
        }
    return {
        "smtp_user": bool(cfg.get("SMTP_USER")),
        "smtp_password": bool(cfg.get("SMTP_PASSWORD")),
        "smtp_host": cfg.get("SMTP_HOST") or "—",
        "smtp_port": cfg.get("SMTP_PORT") or 587,
        "producao_render": producao,
        "gmail_api": False,
        "resend": False,
        "brevo": False,
        "status": "pronto" if smtp_ok else "faltando",
        "detalhe": (
            "O servidor envia sozinho com SMTP_USER e SMTP_PASSWORD."
            if smtp_ok
            else "Faltam SMTP_USER e SMTP_PASSWORD, ou BREVO_API_KEY para envio por HTTPS."
        ),
    }


def _smtp_ipv4(host, porta, timeout=8):
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


def _smtp_ssl_ipv4(host, porta, timeout=8):
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


def _mensagem_smtp(erro):
    texto = str(erro or "").lower()
    codigo = getattr(erro, "errno", None)
    if (
        "timed out" in texto
        or "timeout" in texto
        or "network is unreachable" in texto
        or codigo in {101, 110, 111, 113}
    ):
        return (
            "O plano Free do Render bloqueia SMTP (portas 25, 465 e 587), então o Gmail dá timed out. "
            "A senha de app está certa. Cadastre BREVO_API_KEY no Environment para enviar por HTTPS, "
            "ou suba o serviço para um plano pago."
        )
    return str(erro)


def _tentar_smtp_gmail(cfg, msg, timeout=None):
    usuario = (cfg.get("SMTP_USER") or "").strip()
    senha_bruta = cfg.get("SMTP_PASSWORD") or ""
    host = (cfg.get("SMTP_HOST") or "smtp.gmail.com").strip() or "smtp.gmail.com"
    senhas = []
    for item in (senha_bruta, senha_smtp_normalizada(senha_bruta)):
        if item and item not in senhas:
            senhas.append(item)
    if timeout is None:
        timeout = 4 if ambiente_producao() else 12
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
                smtp = (
                    _smtp_ssl_ipv4(host, porta, timeout=timeout)
                    if usar_ssl
                    else _smtp_ipv4(host, porta, timeout=timeout)
                )
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
        raise RuntimeError(_mensagem_smtp(ultimo)) from ultimo
    raise RuntimeError("Não foi possível conectar ao Gmail para enviar o e-mail.")


def _montar_mensagem(remetente, destinos, assunto, corpo, html=None, anexos=None, nome_remetente=None, responder_para=None):
    from email.utils import formataddr
    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = formataddr(((nome_remetente or "Gestão Escolar").strip(), remetente))
    msg["To"] = ", ".join(destinos)
    if responder_para and email_valido(responder_para) and normalizar_email(responder_para) != normalizar_email(remetente):
        msg["Reply-To"] = formataddr(((nome_remetente or "Gestão Escolar").strip(), responder_para))
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


def _anexos_api(anexos):
    import base64
    itens = []
    for anexo in anexos or []:
        dados = anexo.get("dados") or b""
        if not dados:
            continue
        itens.append(
            {
                "nome": anexo.get("nome") or "documento.pdf",
                "tipo": anexo.get("tipo") or "application/pdf",
                "conteudo": base64.b64encode(dados).decode("ascii"),
            }
        )
    return itens


def _enviar_via_brevo(chave, remetente, destinos, assunto, corpo, html=None, anexos=None, nome_remetente=None, responder_para=None):
    import requests
    payload = {
        "sender": {"email": remetente, "name": (nome_remetente or "Gestão Escolar").strip()},
        "to": [{"email": item} for item in destinos],
        "subject": assunto,
        "textContent": corpo or "",
    }
    if responder_para and email_valido(responder_para):
        payload["replyTo"] = {"email": responder_para, "name": (nome_remetente or "Gestão Escolar").strip()}
    if html:
        payload["htmlContent"] = html
    arquivos = _anexos_api(anexos)
    if arquivos:
        payload["attachment"] = [{"name": item["nome"], "content": item["conteudo"]} for item in arquivos]
    resp = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        json=payload,
        headers={"accept": "application/json", "api-key": chave, "content-type": "application/json"},
        timeout=20,
    )
    if resp.status_code >= 300:
        raise RuntimeError(f"Brevo recusou o envio ({resp.status_code}): {resp.text[:400]}")
    return destinos


def _enviar_via_resend(chave, remetente, destinos, assunto, corpo, html=None, anexos=None, nome_remetente=None, responder_para=None):
    import requests
    nome = (nome_remetente or "Gestão Escolar").strip()
    payload = {
        "from": f"{nome} <{remetente}>",
        "to": list(destinos),
        "subject": assunto,
        "text": corpo or "",
    }
    if responder_para and email_valido(responder_para):
        payload["reply_to"] = responder_para
    if html:
        payload["html"] = html
    arquivos = _anexos_api(anexos)
    if arquivos:
        payload["attachments"] = [{"filename": item["nome"], "content": item["conteudo"]} for item in arquivos]
    resp = requests.post(
        "https://api.resend.com/emails",
        json=payload,
        headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"},
        timeout=20,
    )
    if resp.status_code >= 300:
        raise RuntimeError(f"Resend recusou o envio ({resp.status_code}): {resp.text[:400]}")
    return destinos


def _enviar_via_sendgrid(chave, remetente, destinos, assunto, corpo, html=None, anexos=None, nome_remetente=None, responder_para=None):
    import requests
    conteudo = [{"type": "text/plain", "value": corpo or ""}]
    if html:
        conteudo.append({"type": "text/html", "value": html})
    payload = {
        "personalizations": [{"to": [{"email": item} for item in destinos]}],
        "from": {"email": remetente, "name": (nome_remetente or "Gestão Escolar").strip()},
        "subject": assunto,
        "content": conteudo,
    }
    if responder_para and email_valido(responder_para):
        payload["reply_to"] = {"email": responder_para, "name": (nome_remetente or "Gestão Escolar").strip()}
    arquivos = _anexos_api(anexos)
    if arquivos:
        payload["attachments"] = [
            {
                "content": item["conteudo"],
                "filename": item["nome"],
                "type": item["tipo"],
                "disposition": "attachment",
            }
            for item in arquivos
        ]
    resp = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        json=payload,
        headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"},
        timeout=20,
    )
    if resp.status_code >= 300:
        raise RuntimeError(f"SendGrid recusou o envio ({resp.status_code}): {resp.text[:400]}")
    return destinos


def _enviar_via_https(remetente, destinos, assunto, corpo, html=None, anexos=None, nome_remetente=None, responder_para=None):
    chaves = _chaves_api_email()
    erros = []
    extra = {"nome_remetente": nome_remetente, "responder_para": responder_para}
    if chaves["brevo"]:
        try:
            return _enviar_via_brevo(chaves["brevo"], remetente, destinos, assunto, corpo, html=html, anexos=anexos, **extra)
        except Exception as e:
            erros.append(str(e))
    if chaves["resend"]:
        try:
            return _enviar_via_resend(chaves["resend"], remetente, destinos, assunto, corpo, html=html, anexos=anexos, **extra)
        except Exception as e:
            erros.append(str(e))
    if chaves["sendgrid"]:
        try:
            return _enviar_via_sendgrid(chaves["sendgrid"], remetente, destinos, assunto, corpo, html=html, anexos=anexos, **extra)
        except Exception as e:
            erros.append(str(e))
    if erros:
        raise RuntimeError(" | ".join(erros))
    raise RuntimeError("Nenhuma chave HTTPS de e-mail (BREVO_API_KEY, RESEND_API_KEY ou SENDGRID_API_KEY).")


def enviar_email(destinos, assunto, corpo, anexos=None, html=None, access_token=None):
    lista = []
    for item in destinos or []:
        if email_valido(item):
            lista.append(normalizar_email(item))
    if not lista:
        raise RuntimeError("Nenhum e-mail válido para envio. Cadastre o e-mail do responsável, professor ou destinatário.")

    cfg = carregar_config()
    smtp = carregar_smtp()
    nome_visivel, _nome_escola, email_escola = identidade_envio()
    remetente_sistema = (smtp.get("SMTP_FROM") or smtp.get("SMTP_USER") or cfg.get("SUPER_ADMIN_EMAIL") or "").strip()
    remetentes = []
    if email_escola and email_valido(email_escola):
        remetentes.append(email_escola)
    if remetente_sistema and remetente_sistema.lower() not in {item.lower() for item in remetentes}:
        remetentes.append(remetente_sistema)
    if not remetentes:
        raise RuntimeError(
            "Falta o e-mail principal da escola (Configurações) ou SMTP_FROM / SUPER_ADMIN_EMAIL do sistema."
        )
    responder_para = email_escola if email_valido(email_escola) else remetente_sistema
    erros = []
    producao = ambiente_producao()
    https_ok = _tem_envio_https(cfg)
    smtp_ok = smtp_configurado(smtp)

    def tentar_https():
        ultimo = None
        for de in remetentes:
            try:
                return _enviar_via_https(
                    de, lista, assunto, corpo, html=html, anexos=anexos,
                    nome_remetente=nome_visivel, responder_para=responder_para,
                )
            except Exception as e:
                ultimo = e
                print(f"HTTPS remetente {de}: {e}")
        raise ultimo or RuntimeError("Não foi possível enviar por HTTPS.")

    def tentar_smtp():
        if not smtp_ok:
            raise RuntimeError("Faltam SMTP_USER e SMTP_PASSWORD do sistema.")
        ultimo = None
        for de in remetentes:
            try:
                msg = _montar_mensagem(
                    de, lista, assunto, corpo, html=html, anexos=anexos,
                    nome_remetente=nome_visivel, responder_para=responder_para,
                )
                _tentar_smtp_gmail(smtp, msg)
                return lista
            except Exception as e:
                ultimo = e
                print(f"SMTP remetente {de}: {e}")
        raise ultimo or RuntimeError("Não foi possível enviar por SMTP.")

    def tentar_gmail_api():
        token = access_token
        de = remetentes[0]
        if not token:
            token, de_api = obter_access_token_gmail()
            de = de or de_api or remetentes[0]
        if not token:
            raise RuntimeError("Gmail API sem token.")
        return enviar_via_gmail_api(token, lista, assunto, corpo, remetente=de, anexos=anexos, html=html)

    ordem = []
    if producao and not _forcar_smtp():
        if not https_ok:
            print("envio: BREVO_API_KEY ausente no processo do Render")
            raise RuntimeError(
                "BREVO_API_KEY não está neste processo. No Render: Environment → "
                "Add Environment Variable, KEY exatamente BREVO_API_KEY, "
                "cole a chave xkeysib-..., Save Changes e espere o deploy acabar. "
                "Depois use Reenviar e-mail (não cadastre a escola de novo)."
            )
        ordem.append(("HTTPS", tentar_https))
    else:
        if smtp_ok:
            ordem.append(("SMTP", tentar_smtp))
        if https_ok:
            ordem.append(("HTTPS", tentar_https))
        ordem.append(("Gmail API", tentar_gmail_api))

    for nome, fn in ordem:
        try:
            fn()
            print(f"e-mail enviado via {nome} para {lista}")
            return lista
        except Exception as e:
            detalhe = _mensagem_smtp(e) if nome == "SMTP" else str(e)
            if nome == "Gmail API" and "sem token" in detalhe.lower():
                continue
            erros.append(detalhe)
            print(f"{nome}: {detalhe}")

    if erros:
        raise RuntimeError(" | ".join(erros))
    raise RuntimeError(
        "Sem meio de envio. No Render Free cadastre BREVO_API_KEY; em plano pago use SMTP_USER e SMTP_PASSWORD."
    )


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
