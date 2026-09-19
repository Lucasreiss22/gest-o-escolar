import re
import secrets
from datetime import datetime, timedelta

import psycopg2

from config import carregar_config
from database import definir_banco_escola, limpar_banco_escola, obter_conexao
from email_envio import enviar_email, exigencia_email, normalizar_email, smtp_configurado


def email_super_admin():
    return (carregar_config().get("SUPER_ADMIN_EMAIL") or "lucaslagoasreis@gmail.com").strip().lower()


def eh_super_admin(email):
    return normalizar_email(email) == email_super_admin()


def garantir_plataforma():
    conexao = obter_conexao(master=True)
    if not conexao:
        return
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS plataforma_admins (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(150) UNIQUE NOT NULL,
                    nome VARCHAR(150),
                    senha VARCHAR(255),
                    email_confirmado BOOLEAN DEFAULT FALSE,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS plataforma_escolas (
                    id SERIAL PRIMARY KEY,
                    nome VARCHAR(180) NOT NULL,
                    email_admin VARCHAR(150) UNIQUE NOT NULL,
                    db_nome VARCHAR(80) UNIQUE NOT NULL,
                    convite_token VARCHAR(64) UNIQUE,
                    convite_codigo VARCHAR(10),
                    convite_expira TIMESTAMP,
                    senha_definida BOOLEAN DEFAULT FALSE,
                    ativo BOOLEAN DEFAULT TRUE,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS plataforma_otp (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(150) NOT NULL,
                    codigo VARCHAR(10) NOT NULL,
                    finalidade VARCHAR(40) NOT NULL,
                    expira TIMESTAMP NOT NULL,
                    usado BOOLEAN DEFAULT FALSE
                );
                CREATE TABLE IF NOT EXISTS plataforma_smtp (
                    id INT PRIMARY KEY DEFAULT 1,
                    smtp_host VARCHAR(120),
                    smtp_port INT DEFAULT 587,
                    smtp_user VARCHAR(150),
                    smtp_password VARCHAR(255),
                    smtp_from VARCHAR(150),
                    smtp_tls BOOLEAN DEFAULT TRUE
                );
                """
            )
            cursor.execute(
                "SELECT 1 FROM plataforma_admins WHERE LOWER(email) = %s",
                (email_super_admin(),),
            )
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO plataforma_admins (email, nome) VALUES (%s, %s)",
                    (email_super_admin(), "Administrador da plataforma"),
                )
            cursor.execute(
                "INSERT INTO plataforma_smtp (id) VALUES (1) ON CONFLICT (id) DO NOTHING"
            )
            for tabela, coluna, spec in (
                ("plataforma_smtp", "google_client_id", "VARCHAR(200)"),
                ("plataforma_smtp", "google_client_secret", "VARCHAR(200)"),
                ("plataforma_smtp", "google_refresh_token", "TEXT"),
            ):
                cursor.execute(
                    """
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = %s AND column_name = %s
                    """,
                    (tabela, coluna),
                )
                if not cursor.fetchone():
                    cursor.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {spec}")
        conexao.commit()
    except Exception as e:
        conexao.rollback()
        print(f"Erro ao garantir tabelas da plataforma: {e}")
    finally:
        conexao.close()


def buscar_admin_plataforma(email):
    garantir_plataforma()
    conexao = obter_conexao(master=True)
    if not conexao:
        return None
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM plataforma_admins WHERE LOWER(email) = %s",
                (normalizar_email(email),),
            )
            return cursor.fetchone()
    finally:
        conexao.close()


def salvar_senha_plataforma(email, senha, nome=None):
    conexao = obter_conexao(master=True)
    if not conexao:
        raise RuntimeError("Sem conexão com o banco da plataforma.")
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                UPDATE plataforma_admins
                SET senha = %s, email_confirmado = TRUE, nome = COALESCE(%s, nome)
                WHERE LOWER(email) = %s
                RETURNING *
                """,
                (senha, nome, normalizar_email(email)),
            )
            row = cursor.fetchone()
        conexao.commit()
        return row
    finally:
        conexao.close()


def buscar_escola_por_email(email):
    garantir_plataforma()
    conexao = obter_conexao(master=True)
    if not conexao:
        return None
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM plataforma_escolas WHERE LOWER(email_admin) = %s",
                (normalizar_email(email),),
            )
            return cursor.fetchone()
    finally:
        conexao.close()


def listar_escolas():
    garantir_plataforma()
    conexao = obter_conexao(master=True)
    if not conexao:
        return []
    try:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT * FROM plataforma_escolas ORDER BY nome")
            return cursor.fetchall() or []
    finally:
        conexao.close()


def buscar_escola_por_id(escola_id):
    garantir_plataforma()
    conexao = obter_conexao(master=True)
    if not conexao:
        return None
    try:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT * FROM plataforma_escolas WHERE id = %s", (escola_id,))
            return cursor.fetchone()
    finally:
        conexao.close()


def definir_status_escola(escola_id, ativa):
    escola = buscar_escola_por_id(escola_id)
    if not escola:
        raise ValueError("Escola não encontrada.")
    conexao = obter_conexao(master=True)
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                "UPDATE plataforma_escolas SET ativo = %s WHERE id = %s",
                (bool(ativa), escola_id),
            )
        conexao.commit()
    finally:
        conexao.close()
    return buscar_escola_por_id(escola_id)


def excluir_escola(escola_id):
    escola = buscar_escola_por_id(escola_id)
    if not escola:
        raise ValueError("Escola não encontrada.")
    db_nome = escola["db_nome"]
    conexao = obter_conexao(master=True)
    try:
        with conexao.cursor() as cursor:
            cursor.execute("DELETE FROM plataforma_escolas WHERE id = %s", (escola_id,))
        conexao.commit()
    finally:
        conexao.close()
    if re.fullmatch(r"[a-z][a-z0-9_]{1,62}", db_nome or ""):
        admin = _conectar_postgres()
        admin.autocommit = True
        try:
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
                    (db_nome,),
                )
                cursor.execute(f'DROP DATABASE IF EXISTS "{db_nome}"')
        finally:
            admin.close()
    return escola


def regenerar_convite_escola(escola_id):
    escola = buscar_escola_por_id(escola_id)
    if not escola:
        raise ValueError("Escola não encontrada.")
    if not escola.get("ativo", True):
        raise ValueError("Retome a escola antes de redefinir a senha.")
    convite_token = secrets.token_urlsafe(24)
    convite_codigo = f"{secrets.randbelow(1000000):06d}"
    expira = datetime.now() + timedelta(days=7)
    conexao = obter_conexao(master=True)
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                UPDATE plataforma_escolas
                SET convite_token = %s, convite_codigo = %s, convite_expira = %s, senha_definida = FALSE
                WHERE id = %s
                RETURNING *
                """,
                (convite_token, convite_codigo, expira, escola_id),
            )
            atualizada = cursor.fetchone()
        conexao.commit()
        return atualizada
    finally:
        conexao.close()


def gerar_otp(email, finalidade):
    garantir_plataforma()
    codigo = f"{secrets.randbelow(1000000):06d}"
    expira = datetime.now() + timedelta(minutes=20)
    conexao = obter_conexao(master=True)
    if not conexao:
        return codigo
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                "UPDATE plataforma_otp SET usado = TRUE WHERE LOWER(email) = %s AND finalidade = %s",
                (normalizar_email(email), finalidade),
            )
            cursor.execute(
                """
                INSERT INTO plataforma_otp (email, codigo, finalidade, expira)
                VALUES (%s, %s, %s, %s)
                """,
                (normalizar_email(email), codigo, finalidade, expira),
            )
        conexao.commit()
    finally:
        conexao.close()
    return codigo


def validar_otp(email, codigo, finalidade):
    codigo = (codigo or "").strip()
    try:
        from flask import has_request_context, session
        if has_request_context():
            local = (session.get("otp_local") or "").strip()
            if local and codigo == local and session.get("login_email") == normalizar_email(email):
                session.pop("otp_local", None)
                return True
    except Exception:
        pass
    conexao = obter_conexao(master=True)
    if not conexao:
        return False
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                SELECT id FROM plataforma_otp
                WHERE LOWER(email) = %s AND codigo = %s AND finalidade = %s
                  AND usado = FALSE AND expira > NOW()
                ORDER BY id DESC LIMIT 1
                """,
                (normalizar_email(email), (codigo or "").strip(), finalidade),
            )
            row = cursor.fetchone()
            if not row:
                return False
            cursor.execute("UPDATE plataforma_otp SET usado = TRUE WHERE id = %s", (row["id"],))
        conexao.commit()
        return True
    finally:
        conexao.close()


def enviar_codigo(email, codigo, assunto, corpo, html=None, access_token=None):
    try:
        enviar_email([email], assunto, corpo, html=html, access_token=access_token)
        return True, None
    except Exception as e:
        return False, str(e)


def salvar_smtp_plataforma(host, porta, usuario, senha, remetente=None):
    garantir_plataforma()
    conexao = obter_conexao(master=True)
    if not conexao:
        raise RuntimeError("Sem conexão com o banco.")
    try:
        with conexao.cursor() as cursor:
            from email_envio import _parece_senha_app, corrigir_smtp, senha_smtp_normalizada
            cursor.execute("SELECT smtp_host, smtp_password FROM plataforma_smtp WHERE id = 1")
            atual = cursor.fetchone() or {}
            host_salvo = (atual.get("smtp_host") if isinstance(atual, dict) else "") or ""
            senha_salva = (atual.get("smtp_password") if isinstance(atual, dict) else "") or ""
            if not senha:
                if _parece_senha_app(host_salvo):
                    senha = senha_smtp_normalizada(host_salvo)
                else:
                    senha = senha_salva
            dados = corrigir_smtp({
                "SMTP_HOST": host or host_salvo,
                "SMTP_PORT": porta,
                "SMTP_USER": usuario,
                "SMTP_PASSWORD": senha,
                "SMTP_FROM": remetente or usuario,
                "SMTP_TLS": True,
            })
            cursor.execute(
                """
                INSERT INTO plataforma_smtp (id, smtp_host, smtp_port, smtp_user, smtp_password, smtp_from, smtp_tls)
                VALUES (1, %s, %s, %s, %s, %s, TRUE)
                ON CONFLICT (id) DO UPDATE SET
                    smtp_host = EXCLUDED.smtp_host,
                    smtp_port = EXCLUDED.smtp_port,
                    smtp_user = EXCLUDED.smtp_user,
                    smtp_password = CASE WHEN EXCLUDED.smtp_password = '' THEN plataforma_smtp.smtp_password ELSE EXCLUDED.smtp_password END,
                    smtp_from = EXCLUDED.smtp_from,
                    smtp_tls = TRUE
                """,
                (
                    dados["SMTP_HOST"],
                    int(dados["SMTP_PORT"] or 587),
                    dados["SMTP_USER"],
                    dados["SMTP_PASSWORD"],
                    dados["SMTP_FROM"],
                ),
            )
        conexao.commit()
    finally:
        conexao.close()


def credenciais_google():
    cfg = carregar_config()
    cid = (cfg.get("GOOGLE_CLIENT_ID") or "").strip()
    secret = (cfg.get("GOOGLE_CLIENT_SECRET") or "").strip()
    refresh = ""
    garantir_plataforma()
    conexao = obter_conexao(master=True)
    if conexao:
        try:
            with conexao.cursor() as cursor:
                cursor.execute(
                    "SELECT google_client_id, google_client_secret, google_refresh_token FROM plataforma_smtp WHERE id = 1"
                )
                row = cursor.fetchone() or {}
            if isinstance(row, dict):
                cid = cid or (row.get("google_client_id") or "").strip()
                secret = secret or (row.get("google_client_secret") or "").strip()
                refresh = (row.get("google_refresh_token") or "").strip()
        except Exception:
            pass
        finally:
            conexao.close()
    return {"client_id": cid, "client_secret": secret, "refresh_token": refresh}


def salvar_google_oauth(client_id, client_secret):
    garantir_plataforma()
    conexao = obter_conexao(master=True)
    if not conexao:
        raise RuntimeError("Sem conexão com o banco.")
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO plataforma_smtp (id, google_client_id, google_client_secret)
                VALUES (1, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    google_client_id = EXCLUDED.google_client_id,
                    google_client_secret = CASE
                        WHEN EXCLUDED.google_client_secret = '' THEN plataforma_smtp.google_client_secret
                        ELSE EXCLUDED.google_client_secret
                    END
                """,
                ((client_id or "").strip(), (client_secret or "").strip()),
            )
        conexao.commit()
    finally:
        conexao.close()


def salvar_google_refresh(refresh_token):
    if not refresh_token:
        return
    conexao = obter_conexao(master=True)
    if not conexao:
        return
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                "UPDATE plataforma_smtp SET google_refresh_token = %s WHERE id = 1",
                (refresh_token,),
            )
        conexao.commit()
    finally:
        conexao.close()


def _slug_db(nome):
    base = re.sub(r"[^a-z0-9]+", "_", (nome or "").lower()).strip("_")[:28] or "escola"
    if base[0].isdigit():
        base = "e_" + base
    return f"esc_{base}_{secrets.token_hex(3)}"


def _conectar_postgres():
    cfg = carregar_config()
    dsn = (cfg.get("DATABASE_URL") or "").strip()
    if dsn.startswith("postgres://"):
        dsn = "postgresql://" + dsn[len("postgres://"):]
    if dsn:
        base, sep, resto = dsn.rpartition("/")
        query = ""
        if sep:
            _nome, qsep, qtd = resto.partition("?")
            if qsep:
                query = "?" + qtd
            dsn = f"{base}/postgres{query}"
        return psycopg2.connect(dsn, sslmode=cfg.get("DB_SSLMODE") or "require")
    return psycopg2.connect(
        host=cfg["DB_HOST"],
        port=cfg["DB_PORT"],
        dbname="postgres",
        user=cfg["DB_USER"],
        password=cfg["DB_PASSWORD"],
        sslmode=cfg.get("DB_SSLMODE") or "prefer",
    )


def criar_banco_escola(db_nome):
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,62}", db_nome):
        raise ValueError("Nome de banco inválido.")
    conexao = _conectar_postgres()
    conexao.autocommit = True
    try:
        with conexao.cursor() as cursor:
            cursor.execute(f'CREATE DATABASE "{db_nome}"')
    finally:
        conexao.close()


def bootstrap_banco_escola(nome_escola, email_admin):
    from database import garantir_tabelas_folha, garantir_tabelas_pedagogicas

    conexao = obter_conexao()
    if not conexao:
        raise RuntimeError("Não conectou no banco da escola recém-criado.")
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS usuarios (
                    id SERIAL PRIMARY KEY,
                    nome VARCHAR(150) NOT NULL,
                    email VARCHAR(150) UNIQUE NOT NULL,
                    senha VARCHAR(255),
                    papel VARCHAR(40) DEFAULT 'admin'
                );
                CREATE TABLE IF NOT EXISTS configuracoes (
                    id INT PRIMARY KEY,
                    nome_escola VARCHAR(180),
                    ano_letivo INT,
                    email_contato VARCHAR(150),
                    regime_tributario VARCHAR(40) DEFAULT 'simples_nacional'
                );
                CREATE TABLE IF NOT EXISTS funcionarios (
                    id SERIAL PRIMARY KEY,
                    nome_completo VARCHAR(150),
                    email VARCHAR(150),
                    cargo VARCHAR(80),
                    telefone VARCHAR(30),
                    usuario_id INT
                );
                CREATE TABLE IF NOT EXISTS alunos (
                    id SERIAL PRIMARY KEY,
                    matricula VARCHAR(20),
                    nome_completo VARCHAR(150) NOT NULL,
                    email VARCHAR(150),
                    telefone_principal VARCHAR(30),
                    status VARCHAR(20) DEFAULT 'ativo'
                );
                INSERT INTO configuracoes (id, nome_escola, ano_letivo, email_contato)
                VALUES (1, %s, EXTRACT(YEAR FROM CURRENT_DATE)::INT, %s)
                ON CONFLICT (id) DO UPDATE SET nome_escola = EXCLUDED.nome_escola;
                """,
                (nome_escola, email_admin),
            )
        conexao.commit()
    finally:
        conexao.close()
    garantir_tabelas_pedagogicas()
    garantir_tabelas_folha()


def cadastrar_escola(nome, email_admin):
    garantir_plataforma()
    nome = (nome or "").strip()
    email_admin = exigencia_email(email_admin, "E-mail da escola")
    if not nome:
        raise ValueError("Informe o nome da escola.")
    if eh_super_admin(email_admin):
        raise ValueError("Este e-mail é o administrador da plataforma e não pode ser usado como escola.")
    existente = buscar_escola_por_email(email_admin)
    if existente:
        raise ValueError(
            "Já existe uma escola com este e-mail. Use Acessar dados, Redefinir senha "
            "ou marque Recadastrar (apaga a escola atual e o banco)."
        )
    db_nome = _slug_db(nome)
    criar_banco_escola(db_nome)
    token = definir_banco_escola(db_nome)
    try:
        bootstrap_banco_escola(nome, email_admin)
    finally:
        limpar_banco_escola(token)
    convite_token = secrets.token_urlsafe(24)
    convite_codigo = f"{secrets.randbelow(1000000):06d}"
    expira = datetime.now() + timedelta(days=7)
    conexao = obter_conexao(master=True)
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO plataforma_escolas (
                    nome, email_admin, db_nome, convite_token, convite_codigo, convite_expira
                ) VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (nome, email_admin, db_nome, convite_token, convite_codigo, expira),
            )
            escola = cursor.fetchone()
        conexao.commit()
        return escola
    finally:
        conexao.close()


def atualizar_email_admin_escola(token, email_admin):
    email_admin = exigencia_email(email_admin, "E-mail da escola")
    if eh_super_admin(email_admin):
        raise ValueError("Este e-mail é o administrador da plataforma e não pode ser usado como escola.")
    escola = buscar_escola_por_token(token)
    if not escola:
        raise ValueError("Escola não encontrada.")
    if escola.get("senha_definida"):
        raise ValueError("Esta escola já definiu senha. Não dá para trocar o e-mail do admin aqui.")
    outra = buscar_escola_por_email(email_admin)
    if outra and outra["id"] != escola["id"]:
        raise ValueError("Já existe uma escola com este e-mail.")
    antigo = escola["email_admin"]
    conexao = obter_conexao(master=True)
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                "UPDATE plataforma_escolas SET email_admin = %s WHERE id = %s",
                (email_admin, escola["id"]),
            )
        conexao.commit()
    finally:
        conexao.close()
    tenant = definir_banco_escola(escola["db_nome"])
    try:
        conexao = obter_conexao()
        if conexao:
            try:
                with conexao.cursor() as cursor:
                    cursor.execute(
                        "UPDATE configuracoes SET email_contato = %s WHERE id = 1",
                        (email_admin,),
                    )
                    cursor.execute(
                        "UPDATE usuarios SET email = %s WHERE LOWER(email) = %s",
                        (email_admin, antigo),
                    )
                conexao.commit()
            finally:
                conexao.close()
    finally:
        limpar_banco_escola(tenant)
    return buscar_escola_por_token(token)


def buscar_escola_por_token(token):
    conexao = obter_conexao(master=True)
    if not conexao:
        return None
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM plataforma_escolas WHERE convite_token = %s",
                (token,),
            )
            return cursor.fetchone()
    finally:
        conexao.close()


def ativar_escola(escola, senha):
    if not senha or len(senha) < 6:
        raise ValueError("A senha deve ter pelo menos 6 caracteres.")
    token = definir_banco_escola(escola["db_nome"])
    try:
        conexao = obter_conexao()
        if not conexao:
            raise RuntimeError("Não conectou no banco da escola.")
        try:
            with conexao.cursor() as cursor:
                cursor.execute("SELECT id FROM usuarios WHERE LOWER(email) = %s", (escola["email_admin"],))
                if cursor.fetchone():
                    cursor.execute(
                        "UPDATE usuarios SET senha = %s, papel = 'admin', nome = %s WHERE LOWER(email) = %s",
                        (senha, escola["nome"], escola["email_admin"]),
                    )
                else:
                    cursor.execute(
                        "INSERT INTO usuarios (nome, email, senha, papel) VALUES (%s, %s, %s, 'admin')",
                        (escola["nome"], escola["email_admin"], senha),
                    )
            conexao.commit()
        finally:
            conexao.close()
    finally:
        limpar_banco_escola(token)
    master = obter_conexao(master=True)
    try:
        with master.cursor() as cursor:
            cursor.execute(
                """
                UPDATE plataforma_escolas
                SET senha_definida = TRUE, convite_codigo = NULL
                WHERE id = %s
                """,
                (escola["id"],),
            )
        master.commit()
    finally:
        master.close()


def localizar_escola_do_email(email):
    """Encontra a escola pelo e-mail do admin ou de qualquer usuário daquele banco."""
    email = normalizar_email(email)
    direta = buscar_escola_por_email(email)
    if direta:
        return direta
    for escola in listar_escolas():
        if not escola.get("ativo", True):
            continue
        token = definir_banco_escola(escola["db_nome"])
        try:
            conexao = obter_conexao()
            if not conexao:
                continue
            try:
                with conexao.cursor() as cursor:
                    cursor.execute(
                        "SELECT 1 FROM usuarios WHERE LOWER(email) = %s LIMIT 1",
                        (email,),
                    )
                    if cursor.fetchone():
                        return escola
            finally:
                conexao.close()
        finally:
            limpar_banco_escola(token)
    return None


def usuario_da_escola(email, senha, escola=None):
    escola = escola or localizar_escola_do_email(email)
    if not escola or not escola.get("senha_definida") or not escola.get("ativo", True):
        return None, escola
    token = definir_banco_escola(escola["db_nome"])
    try:
        conexao = obter_conexao()
        if not conexao:
            return None, escola
        try:
            with conexao.cursor() as cursor:
                cursor.execute(
                    "SELECT id, nome, senha, papel FROM usuarios WHERE LOWER(email) = %s",
                    (normalizar_email(email),),
                )
                usuario = cursor.fetchone()
        finally:
            conexao.close()
    finally:
        limpar_banco_escola(token)
    if usuario and usuario.get("senha") == senha:
        return usuario, escola
    return None, escola
