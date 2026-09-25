import calendar
import re
import secrets
from datetime import datetime, timedelta

import psycopg2

import json

from config import carregar_config
from database import (
    _schema_seguro,
    definir_banco_escola,
    limpar_banco_escola,
    obter_conexao,
    obter_conexao_nova,
)
from email_envio import enviar_email, exigencia_email, normalizar_email, smtp_configurado
from permissoes import PACOTES_INICIAIS, TELAS_PLANO


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
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS plataforma_pacotes (
                    codigo VARCHAR(40) PRIMARY KEY,
                    nome VARCHAR(80) NOT NULL,
                    descricao TEXT,
                    valor NUMERIC(12,2),
                    telas TEXT NOT NULL,
                    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            for tabela, coluna, spec in (
                ("plataforma_smtp", "google_client_id", "VARCHAR(200)"),
                ("plataforma_smtp", "google_client_secret", "VARCHAR(200)"),
                ("plataforma_smtp", "google_refresh_token", "TEXT"),
                ("plataforma_escolas", "pacote", "VARCHAR(40)"),
                ("plataforma_escolas", "cobranca_modo", "VARCHAR(20) DEFAULT 'fixo'"),
                ("plataforma_escolas", "cobranca_fixo", "NUMERIC(12,2)"),
                ("plataforma_escolas", "cobranca_percentual", "NUMERIC(8,2) DEFAULT 0"),
                ("plataforma_escolas", "cobranca_base", "VARCHAR(20) DEFAULT 'recebido'"),
                ("plataforma_escolas", "regime", "VARCHAR(20) DEFAULT 'outro'"),
                ("plataforma_escolas", "desconto_modo", "VARCHAR(20) DEFAULT 'nenhum'"),
                ("plataforma_escolas", "desconto_percentual", "NUMERIC(8,2) DEFAULT 0"),
                ("plataforma_escolas", "desconto_valor", "NUMERIC(12,2)"),
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
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS plataforma_cobrancas (
                    id SERIAL PRIMARY KEY,
                    escola_id INT NOT NULL,
                    competencia VARCHAR(7) NOT NULL,
                    pacote VARCHAR(40),
                    descricao VARCHAR(180),
                    valor NUMERIC(12,2) NOT NULL DEFAULT 0,
                    data_vencimento DATE,
                    data_pagamento DATE,
                    forma_pagamento VARCHAR(40),
                    juros_percentual NUMERIC(8,4) DEFAULT 0,
                    juros_valor NUMERIC(12,2) DEFAULT 0,
                    multa_valor NUMERIC(12,2) DEFAULT 0,
                    status VARCHAR(30) DEFAULT 'Pendente',
                    UNIQUE (escola_id, competencia)
                );
                CREATE TABLE IF NOT EXISTS plataforma_faturamento_manual (
                    id SERIAL PRIMARY KEY,
                    escola_id INT NOT NULL,
                    competencia VARCHAR(7) NOT NULL,
                    valor NUMERIC(12,2) NOT NULL DEFAULT 0,
                    UNIQUE (escola_id, competencia)
                );
                CREATE TABLE IF NOT EXISTS plataforma_custos (
                    id SERIAL PRIMARY KEY,
                    descricao VARCHAR(180) NOT NULL,
                    categoria VARCHAR(80) DEFAULT 'Outros',
                    valor NUMERIC(12,2) NOT NULL DEFAULT 0,
                    data_custo DATE NOT NULL DEFAULT CURRENT_DATE,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            for coluna, spec in (
                ("juros_percentual", "NUMERIC(8,4) DEFAULT 0"),
                ("juros_valor", "NUMERIC(12,2) DEFAULT 0"),
                ("multa_valor", "NUMERIC(12,2) DEFAULT 0"),
            ):
                cursor.execute(
                    """
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'plataforma_cobrancas' AND column_name = %s
                    """,
                    (coluna,),
                )
                if not cursor.fetchone():
                    cursor.execute(f"ALTER TABLE plataforma_cobrancas ADD COLUMN {coluna} {spec}")
            for codigo, nome, descricao, telas in PACOTES_INICIAIS:
                cursor.execute(
                    """
                    INSERT INTO plataforma_pacotes (codigo, nome, descricao, telas)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (codigo) DO NOTHING
                    """,
                    (codigo, nome, descricao, json.dumps(telas)),
                )
            from nfse import garantir_tabela_plataforma
            garantir_tabela_plataforma(cursor)
            for coluna, spec in (
                ("cnpj", "VARCHAR(20)"),
                ("nfse_email", "VARCHAR(150)"),
                ("nfse_logradouro", "VARCHAR(150)"),
                ("nfse_numero", "VARCHAR(20)"),
                ("nfse_bairro", "VARCHAR(100)"),
                ("nfse_codigo_municipio", "VARCHAR(10)"),
                ("nfse_uf", "CHAR(2)"),
                ("nfse_cep", "VARCHAR(9)"),
            ):
                cursor.execute(
                    f"ALTER TABLE plataforma_escolas ADD COLUMN IF NOT EXISTS {coluna} {spec}"
                )
        conexao.commit()
    except Exception as e:
        try:
            conexao.rollback()
        except Exception:
            pass
        print(f"Erro ao garantir tabelas da plataforma: {e}")
    finally:
        conexao.close()


def buscar_admin_plataforma(email):
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
    except Exception as e:
        print(f"buscar_escola_por_email: {e}")
        return None
    finally:
        conexao.close()


def listar_escolas():
    conexao = obter_conexao(master=True)
    if not conexao:
        return []
    try:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT * FROM plataforma_escolas ORDER BY nome")
            return cursor.fetchall() or []
    finally:
        conexao.close()


def _telas_validas(bruto):
    codigos = {codigo for codigo, _rotulo in TELAS_PLANO}
    if isinstance(bruto, str):
        try:
            bruto = json.loads(bruto)
        except Exception:
            bruto = []
    if not isinstance(bruto, list):
        return []
    return [codigo for codigo in bruto if codigo in codigos]


def listar_pacotes():
    garantir_plataforma()
    conexao = obter_conexao(master=True)
    if not conexao:
        return []
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                "SELECT codigo, nome, descricao, valor, telas FROM plataforma_pacotes ORDER BY nome"
            )
            linhas = []
            for row in cursor.fetchall() or []:
                item = dict(row)
                item["telas"] = _telas_validas(item.get("telas"))
                linhas.append(item)
            return linhas
    finally:
        conexao.close()


def salvar_pacote(codigo, valor, telas):
    codigo = (codigo or "").strip().lower()
    conhecidos = {item[0] for item in PACOTES_INICIAIS}
    if codigo not in conhecidos:
        raise ValueError("Pacote não encontrado.")
    telas_ok = _telas_validas(telas)
    if not telas_ok:
        raise ValueError("Marque ao menos uma tela no pacote.")
    conexao = obter_conexao(master=True)
    if not conexao:
        raise RuntimeError("Sem conexão com o banco da plataforma.")
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                UPDATE plataforma_pacotes
                SET valor = %s, telas = %s, atualizado_em = CURRENT_TIMESTAMP
                WHERE codigo = %s
                """,
                (valor, json.dumps(telas_ok), codigo),
            )
        conexao.commit()
    finally:
        conexao.close()
    return next(p for p in listar_pacotes() if p["codigo"] == codigo)


def definir_pacote_escola(escola_id, codigo):
    garantir_plataforma()
    escola = buscar_escola_por_id(escola_id)
    if not escola:
        raise ValueError("Escola não encontrada.")
    codigo = (codigo or "").strip().lower()
    if codigo:
        if codigo not in {p["codigo"] for p in listar_pacotes()}:
            raise ValueError("Escolha um pacote cadastrado.")
    else:
        codigo = None
    conexao = obter_conexao(master=True)
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                "UPDATE plataforma_escolas SET pacote = %s WHERE id = %s",
                (codigo, escola_id),
            )
        conexao.commit()
    finally:
        conexao.close()
    return buscar_escola_por_id(escola_id)


def _numero(valor):
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return 0.0


def _competencia_valida(competencia):
    competencia = (competencia or "").strip()[:7]
    datetime.strptime(competencia, "%Y-%m")
    return competencia


def _vencimento_da_competencia(competencia, dia):
    ano, mes = [int(parte) for parte in competencia.split("-")]
    try:
        dia = int(dia or 10)
    except (TypeError, ValueError):
        dia = 10
    ultimo = calendar.monthrange(ano, mes)[1]
    dia = min(max(dia, 1), ultimo)
    return datetime(ano, mes, dia).date()


def atualizar_status_cobrancas_plataforma():
    conexao = obter_conexao(master=True)
    if not conexao:
        return
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                UPDATE plataforma_cobrancas
                SET status = CASE
                    WHEN data_vencimento < CURRENT_DATE THEN 'Atrasado'
                    ELSE 'Pendente'
                END
                WHERE COALESCE(status, '') <> 'Pago'
                """
            )
        conexao.commit()
    finally:
        conexao.close()


_MODOS_COBRANCA = ("fixo", "percentual", "misto", "por_aluno")
_MODOS_DESCONTO = ("nenhum", "percentual", "valor_fixo", "misto", "bolsa")
_BASES_COBRANCA = ("recebido", "lancado")


def _moeda_curta(valor):
    n = _numero(valor)
    sinal = "-" if n < 0 else ""
    inteiro, frac = f"{abs(n):.2f}".split(".")
    grupos = []
    while inteiro:
        grupos.append(inteiro[-3:])
        inteiro = inteiro[:-3]
    return sinal + ".".join(reversed(grupos)) + "," + frac


def _percentual_campo(valor):
    n = _numero(valor)
    if n <= 0:
        return ""
    texto = f"{n:.2f}".replace(".", ",")
    if texto.endswith(",00"):
        return texto[:-3]
    return texto.rstrip("0").rstrip(",")


def _regra_cobranca(escola, pacote):
    modo = (escola.get("cobranca_modo") or "fixo").strip().lower()
    if modo not in _MODOS_COBRANCA:
        modo = "fixo"
    base = (escola.get("cobranca_base") or "recebido").strip().lower()
    if base not in _BASES_COBRANCA:
        base = "recebido"
    pacote_valor = _numero(pacote.get("valor")) if pacote else 0.0
    bruto_fixo = escola.get("cobranca_fixo")
    if bruto_fixo is None or str(bruto_fixo).strip() == "":
        fixo = pacote_valor
        fixo_proprio = False
    else:
        fixo = _numero(bruto_fixo)
        fixo_proprio = True
    return {
        "modo": modo,
        "base": base,
        "fixo": fixo,
        "fixo_proprio": fixo_proprio,
        "percentual": _numero(escola.get("cobranca_percentual")),
        "pacote_valor": pacote_valor,
        "pacote_nome": (pacote or {}).get("nome") or "",
        "telas": list((pacote or {}).get("telas") or []),
    }


def faturamento_manual_escola(escola_id, competencia):
    if not escola_id:
        return 0.0
    conexao = None
    try:
        conexao = obter_conexao_nova()
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                SELECT valor FROM plataforma_faturamento_manual
                WHERE escola_id = %s AND competencia = %s
                """,
                (escola_id, competencia),
            )
            row = cursor.fetchone()
        return _numero(row.get("valor")) if row else 0.0
    except Exception:
        return 0.0
    finally:
        if conexao:
            try:
                conexao.close()
            except Exception:
                pass


def salvar_faturamento_manual(escola_id, competencia, valor):
    competencia = _competencia_valida(competencia)
    conexao = obter_conexao(master=True)
    if not conexao:
        raise RuntimeError("Sem conexão com o banco da plataforma.")
    try:
        with conexao.cursor() as cursor:
            if valor is None:
                cursor.execute(
                    "DELETE FROM plataforma_faturamento_manual WHERE escola_id = %s AND competencia = %s",
                    (escola_id, competencia),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO plataforma_faturamento_manual (escola_id, competencia, valor)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (escola_id, competencia)
                    DO UPDATE SET valor = EXCLUDED.valor
                    """,
                    (escola_id, competencia, valor),
                )
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()


def receita_mensal_escola(db_nome, competencia):
    vazio = {"recebido": 0.0, "lancado": 0.0, "alunos": 0, "ok": False}
    if not _schema_seguro(db_nome):
        return vazio
    conexao = None
    try:
        conexao = obter_conexao_nova()
        with conexao.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{db_nome}", public')
            cursor.execute(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = %s AND table_name = 'financeiro_mensalidades'
                """,
                (db_nome,),
            )
            if not cursor.fetchone():
                return vazio
            cursor.execute(
                """
                SELECT COALESCE(SUM(valor), 0) AS lancado,
                       COALESCE(SUM(CASE WHEN status = 'Pago' THEN valor ELSE 0 END), 0) AS recebido
                FROM financeiro_mensalidades
                WHERE to_char(data_vencimento, 'YYYY-MM') = %s
                """,
                (competencia,),
            )
            totais = cursor.fetchone() or {}
            alunos = 0
            cursor.execute(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = %s AND table_name = 'alunos'
                """,
                (db_nome,),
            )
            if cursor.fetchone():
                try:
                    cursor.execute(
                        """
                        SELECT COUNT(*) AS n FROM alunos
                        WHERE COALESCE(NULLIF(status::text, ''), situacao::text, 'ativo') ILIKE 'ativo'
                        """
                    )
                    alunos = int((cursor.fetchone() or {}).get("n") or 0)
                except Exception:
                    conexao.rollback()
                    cursor.execute(f'SET search_path TO "{db_nome}", public')
                    cursor.execute(
                        """
                        SELECT COUNT(DISTINCT aluno_id) AS n
                        FROM financeiro_mensalidades
                        WHERE to_char(data_vencimento, 'YYYY-MM') = %s
                        """,
                        (competencia,),
                    )
                    alunos = int((cursor.fetchone() or {}).get("n") or 0)
        return {
            "recebido": _numero(totais.get("recebido")),
            "lancado": _numero(totais.get("lancado")),
            "alunos": alunos,
            "ok": True,
        }
    except Exception as e:
        print(f"receita_mensal_escola {db_nome}: {e}")
        return vazio
    finally:
        if conexao:
            try:
                conexao.close()
            except Exception:
                pass


def calcular_cobranca_escola(escola, pacote, competencia):
    regra = _regra_cobranca(escola, pacote)
    regime = (escola.get("regime") or "outro").strip().lower()
    if regime != "simples":
        regime = "outro"
    modo = "fixo"
    alunos = 0
    ok = True
    faturamento = 0.0
    percentual = 0.0
    base = regra["pacote_valor"]
    if regra["fixo_proprio"] and regra["fixo"] > 0:
        base = regra["fixo"]
        resumo = "Valor fixo informado"
    elif base > 0:
        resumo = "Valor de tabela do pacote"
    else:
        resumo = "Pacote sem valor de tabela"
    valor = round(base, 2)
    desconto = (escola.get("desconto_modo") or "nenhum").strip().lower()
    if desconto not in _MODOS_DESCONTO:
        desconto = "nenhum"
    desconto_pct = min(100.0, max(0.0, _numero(escola.get("desconto_percentual"))))
    desconto_valor = max(0.0, _numero(escola.get("desconto_valor")))
    bruto = valor
    if desconto == "percentual":
        valor = round(bruto * (1 - desconto_pct / 100.0), 2)
        resumo = f"{resumo} · desconto de {_percentual_campo(desconto_pct) or '0'}%"
    elif desconto == "valor_fixo":
        valor = round(max(0.0, bruto - desconto_valor), 2)
        resumo = f"{resumo} · desconto de R$ {_moeda_curta(desconto_valor)}"
    elif desconto == "misto":
        valor = round(max(0.0, bruto * (1 - desconto_pct / 100.0) - desconto_valor), 2)
        resumo = (
            f"{resumo} · desconto de {_percentual_campo(desconto_pct) or '0'}% "
            f"e R$ {_moeda_curta(desconto_valor)}"
        )
    elif desconto == "bolsa":
        valor = 0.0
        resumo = f"{resumo} · bolsa"
    return {
        **regra,
        "modo": modo,
        "regime": regime,
        "simples": regime == "simples",
        "desconto_modo": desconto,
        "desconto_percentual": desconto_pct,
        "desconto_valor": desconto_valor,
        "desconto_percentual_campo": _percentual_campo(desconto_pct),
        "bruto": bruto,
        "faturamento": faturamento,
        "recebido": 0.0,
        "lancado": 0.0,
        "base_valor": faturamento,
        "alunos": alunos,
        "valor": valor,
        "resumo": resumo,
        "ok": ok,
        "percentual_campo": _percentual_campo(percentual),
    }


def preparar_cobranca_escolas(escolas, pacotes, competencia):
    mapa = {p["codigo"]: p for p in pacotes or []}
    saida = []
    for escola in escolas or []:
        item = dict(escola)
        pacote = mapa.get(item.get("pacote") or "")
        item["pacote_info"] = pacote
        item["calculo"] = calcular_cobranca_escola(item, pacote, competencia)
        saida.append(item)
    return saida


def salvar_regra_cobranca_escola(
    escola_id, modo, fixo_bruto, percentual_bruto, faturamento_bruto,
    desconto_modo, desconto_percentual_bruto, desconto_valor_bruto, competencia,
):
    garantir_plataforma()
    escola = buscar_escola_por_id(escola_id)
    if not escola:
        raise ValueError("Escola não encontrada.")
    modo = (modo or "fixo").strip().lower()
    if modo not in _MODOS_COBRANCA:
        raise ValueError("Escolha como calcular: valor fixo, porcentagem, os dois ou por aluno.")
    desconto_modo = (desconto_modo or "nenhum").strip().lower()
    if desconto_modo not in _MODOS_DESCONTO:
        raise ValueError("Escolha a modalidade de desconto: nenhuma, percentual, valor fixo, os dois ou bolsa.")
    regime = "simples" if modo in {"percentual", "misto"} else (escola.get("regime") or "outro")
    percentual = min(100.0, max(0.0, _numero(percentual_bruto)))
    desconto_pct = min(100.0, max(0.0, _numero(desconto_percentual_bruto)))
    desconto_valor = None
    if str(desconto_valor_bruto or "").strip():
        desconto_valor = _numero(desconto_valor_bruto)
        if desconto_valor < 0:
            raise ValueError("O desconto em valor fixo não pode ser negativo.")
    fixo = None
    if str(fixo_bruto or "").strip():
        fixo = _numero(fixo_bruto)
        if fixo < 0:
            raise ValueError("O valor fixo não pode ser negativo.")
    faturamento = None
    if modo in {"percentual", "misto"} and str(faturamento_bruto or "").strip():
        faturamento = _numero(faturamento_bruto)
        if faturamento < 0:
            raise ValueError("O faturamento manual não pode ser negativo.")
    conexao = obter_conexao(master=True)
    if not conexao:
        raise RuntimeError("Sem conexão com o banco da plataforma.")
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                UPDATE plataforma_escolas
                SET cobranca_modo = %s,
                    cobranca_fixo = %s,
                    cobranca_percentual = %s,
                    regime = %s,
                    desconto_modo = %s,
                    desconto_percentual = %s,
                    desconto_valor = %s
                WHERE id = %s
                """,
                (modo, fixo, percentual, regime, desconto_modo, desconto_pct, desconto_valor, escola["id"]),
            )
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()
    if modo in {"percentual", "misto"}:
        salvar_faturamento_manual(escola["id"], competencia, faturamento)
    escola = buscar_escola_por_id(escola_id)
    pacote = None
    if escola.get("pacote"):
        pacote = next((p for p in listar_pacotes() if p["codigo"] == escola.get("pacote")), None)
    return escola, calcular_cobranca_escola(escola, pacote, competencia)


def _descricao_assinatura(calculo, rotulo):
    nome = calculo.get("pacote_nome") or "Todas as telas"
    return f"Assinatura {nome} {rotulo} · {calculo.get('resumo') or 'valor fixo'}"[:180]


def gerar_cobrancas_plataforma(competencia, dia_vencimento=10):
    garantir_plataforma()
    competencia = _competencia_valida(competencia)
    vencimento = _vencimento_da_competencia(competencia, dia_vencimento)
    rotulo = vencimento.strftime("%m/%Y")
    pacotes = {p["codigo"]: p for p in listar_pacotes()}
    previstas = []
    sem_valor = []
    for escola in listar_escolas():
        if escola.get("ativo") is False:
            continue
        pacote = pacotes.get(escola.get("pacote") or "")
        calculo = calcular_cobranca_escola(escola, pacote, competencia)
        if calculo["valor"] <= 0:
            sem_valor.append(escola.get("nome") or escola.get("email_admin"))
            continue
        previstas.append((escola, pacote, calculo))
    conexao = obter_conexao(master=True)
    if not conexao:
        raise RuntimeError("Sem conexão com o banco da plataforma.")
    criadas = 0
    ja_existiam = 0
    try:
        with conexao.cursor() as cursor:
            for escola, pacote, calculo in previstas:
                cursor.execute(
                    """
                    INSERT INTO plataforma_cobrancas
                        (escola_id, competencia, pacote, descricao, valor, data_vencimento, status)
                    VALUES (%s, %s, %s, %s, %s, %s, 'Pendente')
                    ON CONFLICT (escola_id, competencia) DO NOTHING
                    RETURNING id
                    """,
                    (
                        escola["id"],
                        competencia,
                        (pacote or {}).get("codigo"),
                        _descricao_assinatura(calculo, rotulo),
                        calculo["valor"],
                        vencimento,
                    ),
                )
                if cursor.fetchone():
                    criadas += 1
                else:
                    ja_existiam += 1
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()
    atualizar_status_cobrancas_plataforma()
    return {"criadas": criadas, "ja_existiam": ja_existiam, "sem_valor": sem_valor}


def atualizar_cobrancas_abertas_plataforma(competencia):
    garantir_plataforma()
    competencia = _competencia_valida(competencia)
    pacotes = {p["codigo"]: p for p in listar_pacotes()}
    escolas = {e["id"]: e for e in listar_escolas()}
    conexao = obter_conexao(master=True)
    if not conexao:
        raise RuntimeError("Sem conexão com o banco da plataforma.")
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, escola_id, data_vencimento
                FROM plataforma_cobrancas
                WHERE competencia = %s AND COALESCE(status, '') <> 'Pago'
                """,
                (competencia,),
            )
            abertas = [dict(row) for row in cursor.fetchall() or []]
            atualizadas = 0
            for cobranca in abertas:
                escola = escolas.get(cobranca["escola_id"])
                if not escola:
                    continue
                pacote = pacotes.get(escola.get("pacote") or "")
                calculo = calcular_cobranca_escola(escola, pacote, competencia)
                if calculo["valor"] <= 0:
                    cursor.execute(
                        "DELETE FROM plataforma_cobrancas WHERE id = %s AND COALESCE(status, '') <> 'Pago'",
                        (cobranca["id"],),
                    )
                    atualizadas += cursor.rowcount
                    continue
                venc = cobranca.get("data_vencimento")
                rotulo = venc.strftime("%m/%Y") if hasattr(venc, "strftime") else competencia[5:7] + "/" + competencia[:4]
                cursor.execute(
                    """
                    UPDATE plataforma_cobrancas
                    SET valor = %s, pacote = %s, descricao = %s
                    WHERE id = %s AND COALESCE(status, '') <> 'Pago'
                    """,
                    (
                        calculo["valor"],
                        (pacote or {}).get("codigo"),
                        _descricao_assinatura(calculo, rotulo),
                        cobranca["id"],
                    ),
                )
                atualizadas += cursor.rowcount
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()
    return atualizadas


def criar_cobranca_plataforma(escola_id, valor, vencimento, descricao):
    garantir_plataforma()
    escola = buscar_escola_por_id(escola_id)
    if not escola:
        raise ValueError("Escola não encontrada.")
    if isinstance(vencimento, str):
        vencimento = datetime.strptime(vencimento[:10], "%Y-%m-%d").date()
    valor = _numero(valor)
    if valor <= 0:
        raise ValueError("Informe o valor da assinatura.")
    descricao = (descricao or "").strip() or f"Assinatura {vencimento.strftime('%m/%Y')}"
    competencia = vencimento.strftime("%Y-%m")
    conexao = obter_conexao(master=True)
    if not conexao:
        raise RuntimeError("Sem conexão com o banco da plataforma.")
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                SELECT id FROM plataforma_cobrancas
                WHERE escola_id = %s AND competencia = %s
                """,
                (escola["id"], competencia),
            )
            if cursor.fetchone():
                raise ValueError(f"{escola['nome']} já tem assinatura em {competencia}.")
            status = "Atrasado" if vencimento < datetime.now().date() else "Pendente"
            cursor.execute(
                """
                INSERT INTO plataforma_cobrancas
                    (escola_id, competencia, pacote, descricao, valor, data_vencimento, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (escola["id"], competencia, escola.get("pacote"), descricao, valor, vencimento, status),
            )
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()
    return competencia


def editar_cobranca_plataforma(cobranca_id, valor, vencimento, descricao):
    garantir_plataforma()
    if isinstance(vencimento, str):
        vencimento = datetime.strptime(vencimento[:10], "%Y-%m-%d").date()
    valor = _numero(valor)
    if valor <= 0:
        raise ValueError("Informe o valor da assinatura.")
    descricao = (descricao or "").strip() or f"Assinatura {vencimento.strftime('%m/%Y')}"
    competencia = vencimento.strftime("%Y-%m")
    conexao = obter_conexao(master=True)
    if not conexao:
        raise RuntimeError("Sem conexão com o banco da plataforma.")
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                "SELECT escola_id, status FROM plataforma_cobrancas WHERE id = %s",
                (cobranca_id,),
            )
            atual = cursor.fetchone()
            if not atual:
                raise ValueError("Assinatura não encontrada.")
            cursor.execute(
                """
                SELECT id FROM plataforma_cobrancas
                WHERE escola_id = %s AND competencia = %s AND id <> %s
                """,
                (atual["escola_id"], competencia, cobranca_id),
            )
            if cursor.fetchone():
                raise ValueError("Esta escola já tem outra assinatura nesse mês.")
            cursor.execute(
                """
                UPDATE plataforma_cobrancas
                SET valor = %s,
                    descricao = %s,
                    data_vencimento = %s,
                    competencia = %s,
                    status = CASE
                        WHEN status = 'Pago' THEN 'Pago'
                        WHEN %s < CURRENT_DATE THEN 'Atrasado'
                        ELSE 'Pendente'
                    END
                WHERE id = %s
                """,
                (valor, descricao, vencimento, competencia, vencimento, cobranca_id),
            )
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()
    return competencia


def baixar_cobrancas_plataforma(ids, forma, data_pagamento, juros_percentual=0, multa_valor=0):
    garantir_plataforma()
    ids = [int(item) for item in ids]
    if not ids:
        raise ValueError("Selecione ao menos uma assinatura.")
    if isinstance(data_pagamento, str):
        data_pagamento = datetime.strptime(data_pagamento[:10], "%Y-%m-%d").date()
    forma = (forma or "Pix").strip() or "Pix"
    try:
        juros_percentual = float(juros_percentual or 0)
    except (TypeError, ValueError):
        juros_percentual = 0.0
    try:
        multa_valor = float(multa_valor or 0)
    except (TypeError, ValueError):
        multa_valor = 0.0
    if juros_percentual < 0:
        juros_percentual = 0.0
    if multa_valor < 0:
        multa_valor = 0.0
    conexao = obter_conexao(master=True)
    if not conexao:
        raise RuntimeError("Sem conexão com o banco da plataforma.")
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                UPDATE plataforma_cobrancas
                SET status = 'Pago',
                    forma_pagamento = %s,
                    data_pagamento = %s,
                    juros_percentual = %s,
                    juros_valor = ROUND(COALESCE(valor, 0)::numeric * %s / 100.0, 2),
                    multa_valor = %s
                WHERE id = ANY(%s) AND COALESCE(status, '') <> 'Pago'
                """,
                (forma, data_pagamento, juros_percentual, juros_percentual, multa_valor, ids),
            )
            baixadas = cursor.rowcount
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()
    return baixadas


def tirar_baixa_cobrancas_plataforma(ids):
    garantir_plataforma()
    ids = [int(item) for item in ids]
    if not ids:
        raise ValueError("Selecione ao menos uma assinatura.")
    conexao = obter_conexao(master=True)
    if not conexao:
        raise RuntimeError("Sem conexão com o banco da plataforma.")
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                UPDATE plataforma_cobrancas
                SET status = CASE
                        WHEN data_vencimento < CURRENT_DATE THEN 'Atrasado'
                        ELSE 'Pendente'
                    END,
                    forma_pagamento = NULL,
                    data_pagamento = NULL,
                    juros_percentual = 0,
                    juros_valor = 0,
                    multa_valor = 0
                WHERE id = ANY(%s) AND status = 'Pago'
                """,
                (ids,),
            )
            alteradas = cursor.rowcount
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()
    return alteradas


def excluir_cobranca_plataforma(cobranca_id):
    garantir_plataforma()
    conexao = obter_conexao(master=True)
    if not conexao:
        raise RuntimeError("Sem conexão com o banco da plataforma.")
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                "DELETE FROM plataforma_cobrancas WHERE id = %s RETURNING id",
                (cobranca_id,),
            )
            apagada = cursor.fetchone()
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()
    if not apagada:
        raise ValueError("Assinatura não encontrada.")


def criar_custo_plataforma(descricao, categoria, valor, data_custo):
    garantir_plataforma()
    descricao = (descricao or "").strip()
    if not descricao:
        raise ValueError("Informe a descrição do custo.")
    valor = _numero(valor)
    if valor <= 0:
        raise ValueError("Informe o valor do custo.")
    categoria = (categoria or "Outros").strip() or "Outros"
    if isinstance(data_custo, str):
        data_custo = datetime.strptime(data_custo[:10], "%Y-%m-%d").date()
    conexao = obter_conexao(master=True)
    if not conexao:
        raise RuntimeError("Sem conexão com o banco da plataforma.")
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO plataforma_custos (descricao, categoria, valor, data_custo)
                VALUES (%s, %s, %s, %s)
                """,
                (descricao, categoria, valor, data_custo),
            )
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()
    return data_custo.strftime("%Y-%m")


def excluir_custo_plataforma(custo_id):
    garantir_plataforma()
    conexao = obter_conexao(master=True)
    if not conexao:
        raise RuntimeError("Sem conexão com o banco da plataforma.")
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                "DELETE FROM plataforma_custos WHERE id = %s RETURNING id",
                (custo_id,),
            )
            apagado = cursor.fetchone()
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()
    if not apagado:
        raise ValueError("Custo não encontrado.")


def sincronizar_valores_escolas(competencia):
    """Lança e atualiza as assinaturas em aberto com o pacote e o desconto de cada escola."""
    gerar_cobrancas_plataforma(competencia, 10)
    atualizar_cobrancas_abertas_plataforma(competencia)


def painel_financeiro_plataforma(competencia, status="", busca=""):
    garantir_plataforma()
    competencia = _competencia_valida(competencia)
    try:
        sincronizar_valores_escolas(competencia)
    except Exception as e:
        print(f"sincronizar_valores_escolas {competencia}: {e}")
    atualizar_status_cobrancas_plataforma()
    status = (status or "").strip()
    if status not in {"Pago", "Pendente", "Atrasado"}:
        status = ""
    busca = (busca or "").strip()
    conexao = obter_conexao(master=True)
    vazio = {
        "cobrancas": [],
        "custos": [],
        "sem_valor": [],
        "sem_lancamento": [],
        "totais": {
            "recebido": 0.0,
            "pendente": 0.0,
            "atrasado": 0.0,
            "previsto": 0.0,
            "custos": 0.0,
            "liquido": 0.0,
            "qtd_pago": 0,
            "qtd_pendente": 0,
            "qtd_atrasado": 0,
            "qtd": 0,
        },
    }
    if not conexao:
        return vazio
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN status = 'Pago' THEN valor ELSE 0 END), 0) AS recebido,
                    COALESCE(SUM(CASE WHEN status = 'Pendente' THEN valor ELSE 0 END), 0) AS pendente,
                    COALESCE(SUM(CASE WHEN status = 'Atrasado' THEN valor ELSE 0 END), 0) AS atrasado,
                    COALESCE(SUM(CASE WHEN status = 'Pago' THEN 1 ELSE 0 END), 0) AS qtd_pago,
                    COALESCE(SUM(CASE WHEN status = 'Pendente' THEN 1 ELSE 0 END), 0) AS qtd_pendente,
                    COALESCE(SUM(CASE WHEN status = 'Atrasado' THEN 1 ELSE 0 END), 0) AS qtd_atrasado,
                    COUNT(*) AS qtd
                FROM plataforma_cobrancas
                WHERE competencia = %s
                """,
                (competencia,),
            )
            totais_row = cursor.fetchone() or {}
            filtros = ["c.competencia = %s"]
            params = [competencia]
            if status:
                filtros.append("c.status = %s")
                params.append(status)
            if busca:
                filtros.append("(e.nome ILIKE %s OR e.email_admin ILIKE %s OR c.descricao ILIKE %s)")
                like = f"%{busca}%"
                params.extend([like, like, like])
            cursor.execute(
                f"""
                SELECT c.*, e.nome AS escola_nome, e.email_admin, e.ativo AS escola_ativa
                FROM plataforma_cobrancas c
                JOIN plataforma_escolas e ON e.id = c.escola_id
                WHERE {' AND '.join(filtros)}
                ORDER BY
                    CASE c.status WHEN 'Atrasado' THEN 0 WHEN 'Pendente' THEN 1 ELSE 2 END,
                    e.nome
                """,
                params,
            )
            cobrancas = []
            for row in cursor.fetchall() or []:
                item = dict(row)
                item["valor"] = _numero(item.get("valor"))
                cobrancas.append(item)
            cursor.execute(
                """
                SELECT * FROM plataforma_custos
                WHERE to_char(data_custo, 'YYYY-MM') = %s
                ORDER BY data_custo, id
                """,
                (competencia,),
            )
            custos = []
            for row in cursor.fetchall() or []:
                item = dict(row)
                item["valor"] = _numero(item.get("valor"))
                custos.append(item)
            cursor.execute(
                """
                SELECT e.id, e.nome, e.email_admin, e.db_nome, e.pacote,
                       e.cobranca_modo, e.cobranca_fixo, e.cobranca_percentual, e.regime,
                       e.desconto_modo, e.desconto_percentual, e.desconto_valor,
                       p.nome AS pacote_nome, p.valor AS pacote_valor
                FROM plataforma_escolas e
                LEFT JOIN plataforma_pacotes p ON p.codigo = e.pacote
                LEFT JOIN plataforma_cobrancas c
                    ON c.escola_id = e.id AND c.competencia = %s
                WHERE e.ativo IS TRUE AND c.id IS NULL
                ORDER BY e.nome
                """,
                (competencia,),
            )
            sem_valor = []
            sem_lancamento = []
            for row in cursor.fetchall() or []:
                item = dict(row)
                pacote = None
                if item.get("pacote"):
                    pacote = {
                        "codigo": item.get("pacote"),
                        "nome": item.get("pacote_nome"),
                        "valor": item.get("pacote_valor"),
                        "telas": [],
                    }
                calculo = calcular_cobranca_escola(item, pacote, competencia)
                item["pacote_valor"] = calculo["valor"]
                item["calculo"] = calculo
                if calculo["valor"] > 0:
                    sem_lancamento.append(item)
                else:
                    sem_valor.append(item)
        recebido = _numero(totais_row.get("recebido"))
        pendente = _numero(totais_row.get("pendente"))
        atrasado = _numero(totais_row.get("atrasado"))
        custos_total = sum(item["valor"] for item in custos)
        return {
            "cobrancas": cobrancas,
            "custos": custos,
            "sem_valor": sem_valor,
            "sem_lancamento": sem_lancamento,
            "totais": {
                "recebido": recebido,
                "pendente": pendente,
                "atrasado": atrasado,
                "previsto": recebido + pendente + atrasado,
                "custos": custos_total,
                "liquido": recebido - custos_total,
                "qtd_pago": int(totais_row.get("qtd_pago") or 0),
                "qtd_pendente": int(totais_row.get("qtd_pendente") or 0),
                "qtd_atrasado": int(totais_row.get("qtd_atrasado") or 0),
                "qtd": int(totais_row.get("qtd") or 0),
            },
        }
    finally:
        conexao.close()


def telas_contratadas(escola):
    if not escola or not escola.get("pacote"):
        return None
    for pacote in listar_pacotes():
        if pacote["codigo"] == escola.get("pacote"):
            return pacote["telas"]
    return None


def buscar_escola_por_id(escola_id):
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
            cursor.execute("DELETE FROM plataforma_faturamento_manual WHERE escola_id = %s", (escola_id,))
            cursor.execute("DELETE FROM plataforma_cobrancas WHERE escola_id = %s", (escola_id,))
            cursor.execute("DELETE FROM plataforma_escolas WHERE id = %s", (escola_id,))
        conexao.commit()
    finally:
        conexao.close()
    if re.fullmatch(r"[a-z][a-z0-9_]{1,62}", db_nome or ""):
        admin = None
        try:
            admin = obter_conexao_nova()
            admin.autocommit = True
            with admin.cursor() as cursor:
                cursor.execute(f'DROP SCHEMA IF EXISTS "{db_nome}" CASCADE')
        except Exception as e:
            print(f"DROP SCHEMA {db_nome}: {e}")
        finally:
            if admin:
                try:
                    admin.close()
                except Exception:
                    pass
    return escola


def definir_senha_escola_por_admin(escola_id, senha):
    """Último recurso: o admin da plataforma define a senha da escola, sem código."""
    escola = buscar_escola_por_id(escola_id)
    if not escola:
        raise ValueError("Escola não encontrada.")
    if not escola.get("ativo", True):
        raise ValueError("Retome a escola antes de redefinir a senha.")
    ativar_escola(escola, senha)
    return buscar_escola_por_id(escola_id)


def regenerar_convite_escola(escola_id):
    escola = buscar_escola_por_id(escola_id)
    if not escola:
        raise ValueError("Escola não encontrada.")
    if not escola.get("ativo", True):
        raise ValueError("Retome a escola antes de reenviar o convite.")
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


def _codigo_otp_limpo(codigo):
    return "".join(ch for ch in str(codigo or "") if ch.isdigit())


def gerar_otp(email, finalidade):
    garantir_plataforma()
    email_n = normalizar_email(email)
    conexao = obter_conexao(master=True)
    if not conexao:
        return f"{secrets.randbelow(1000000):06d}"
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                SELECT codigo FROM plataforma_otp
                WHERE LOWER(email) = %s AND usado = FALSE AND expira > NOW()
                ORDER BY id DESC LIMIT 1
                """,
                (email_n,),
            )
            existente = cursor.fetchone()
            if existente and existente.get("codigo"):
                return existente["codigo"]
            codigo = f"{secrets.randbelow(1000000):06d}"
            expira = datetime.now() + timedelta(minutes=20)
            cursor.execute(
                "UPDATE plataforma_otp SET usado = TRUE WHERE LOWER(email) = %s AND usado = FALSE",
                (email_n,),
            )
            cursor.execute(
                """
                INSERT INTO plataforma_otp (email, codigo, finalidade, expira)
                VALUES (%s, %s, %s, %s)
                """,
                (email_n, codigo, finalidade, expira),
            )
        conexao.commit()
        return codigo
    except Exception as e:
        try:
            conexao.rollback()
        except Exception:
            pass
        print(f"OTP não gravou no Postgres (o código ainda vale nesta sessão): {e}")
        return f"{secrets.randbelow(1000000):06d}"
    finally:
        conexao.close()


def validar_otp(email, codigo, finalidade=None):
    codigo = _codigo_otp_limpo(codigo)
    if len(codigo) != 6:
        return False
    try:
        from flask import has_request_context, session
        if has_request_context():
            local = _codigo_otp_limpo(session.get("otp_local"))
            email_sessao = normalizar_email(session.get("login_email") or "")
            if local and codigo == local and email_sessao == normalizar_email(email):
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
                WHERE LOWER(email) = %s AND codigo = %s
                  AND usado = FALSE AND expira > NOW()
                ORDER BY id DESC LIMIT 1
                """,
                (normalizar_email(email), codigo),
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
    try:
        conexao = obter_conexao_nova()
    except Exception as e:
        raise RuntimeError("Sem conexão com o Postgres para criar o espaço da escola.") from e
    try:
        conexao.autocommit = True
        with conexao.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{db_nome}"')
    except Exception as e:
        raise RuntimeError(
            "Não foi possível criar o espaço da escola no Supabase. "
            f"Detalhe: {e}"
        ) from e
    finally:
        try:
            conexao.close()
        except Exception:
            pass


def bootstrap_banco_escola(nome_escola, email_admin):
    conexao = obter_conexao()
    if not conexao:
        raise RuntimeError("Não conectou no espaço da escola recém-criado.")
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
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS configuracoes (
                    id INT PRIMARY KEY,
                    nome_escola VARCHAR(180),
                    ano_letivo INT,
                    email_contato VARCHAR(150),
                    regime_tributario VARCHAR(40) DEFAULT 'simples_nacional'
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS funcionarios (
                    id SERIAL PRIMARY KEY,
                    nome_completo VARCHAR(150),
                    email VARCHAR(150),
                    cargo VARCHAR(80),
                    telefone VARCHAR(30),
                    cpf VARCHAR(14),
                    data_nascimento DATE,
                    usuario_id INT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS alunos (
                    id SERIAL PRIMARY KEY,
                    matricula VARCHAR(20),
                    nome_completo VARCHAR(150) NOT NULL,
                    email VARCHAR(150),
                    telefone_principal VARCHAR(30),
                    status VARCHAR(20) DEFAULT 'ativo'
                )
                """
            )
            cursor.execute(
                """
                INSERT INTO configuracoes (id, nome_escola, ano_letivo, email_contato)
                VALUES (1, %s, EXTRACT(YEAR FROM CURRENT_DATE)::INT, %s)
                ON CONFLICT (id) DO UPDATE SET nome_escola = EXCLUDED.nome_escola
                """,
                (nome_escola, email_admin),
            )
            conexao.commit()
    finally:
        conexao.close()


def cadastrar_escola(nome, email_admin):
    garantir_plataforma()
    nome = (nome or "").strip()
    email_admin = exigencia_email(email_admin, "E-mail da escola")
    if not nome:
        raise ValueError("Informe o nome da escola.")
    if eh_super_admin(email_admin):
        raise ValueError("Este e-mail é o administrador da plataforma e não pode ser usado como escola.")
    ja_na_escola = localizar_escola_do_email(email_admin)
    if ja_na_escola and (ja_na_escola.get("email_admin") or "").lower() != email_admin:
        raise ValueError(
            "Este e-mail já pertence a um professor ou funcionário de uma escola. "
            "Cadastre a pessoa em Usuários da escola, com o perfil Professor. Não crie uma escola nova."
        )
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


def _papel_pelo_cargo(cargo):
    texto = (cargo or "").lower()
    if "professor" in texto:
        return "professor"
    if "secret" in texto:
        return "secretaria"
    if "diret" in texto or "direç" in texto or "direc" in texto:
        return "direcao"
    if "financ" in texto:
        return "financeiro"
    if "supervis" in texto:
        return "supervisor"
    if "admin" in texto:
        return "admin"
    return "funcionario"


def _pessoa_no_schema(cursor, schema, email):
    nome = _schema_seguro(schema)
    if not nome or nome == "public":
        return None
    cursor.execute(
        f'SELECT papel FROM "{nome}".usuarios WHERE LOWER(TRIM(email)) = %s LIMIT 1',
        (email,),
    )
    usuario = cursor.fetchone()
    if usuario:
        return {"origem": "usuario", "papel": usuario.get("papel") or "funcionario"}
    cursor.execute(
        f'SELECT id, nome_completo, cargo FROM "{nome}".funcionarios WHERE LOWER(TRIM(email)) = %s LIMIT 1',
        (email,),
    )
    pessoa = cursor.fetchone()
    if pessoa:
        return {
            "origem": "funcionario",
            "papel": _papel_pelo_cargo(pessoa.get("cargo")),
            "funcionario_id": pessoa.get("id"),
            "nome": pessoa.get("nome_completo"),
        }
    return None


def localizar_escola_do_email(email):
    """Encontra a escola pelo e-mail do admin, de um usuário ou de alguém da folha."""
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
                    if _pessoa_no_schema(cursor, escola.get("db_nome"), email):
                        return escola
            except Exception as e:
                print(f"localizar escola {escola.get('db_nome')}: {e}")
            finally:
                conexao.close()
        finally:
            limpar_banco_escola(token)
    return None


def garantir_login_colaborador(email, escola):
    """Cria o acesso ao painel se a pessoa já está na folha e ainda não tem login."""
    email = normalizar_email(email)
    if not escola or (escola.get("email_admin") or "").lower() == email:
        return False
    schema = _schema_seguro(escola.get("db_nome"))
    if not schema:
        return False
    token = definir_banco_escola(schema)
    try:
        conexao = obter_conexao()
        if not conexao:
            return False
        try:
            with conexao.cursor() as cursor:
                pessoa = _pessoa_no_schema(cursor, schema, email)
                if not pessoa or pessoa.get("origem") == "usuario":
                    return False
                papel = pessoa.get("papel") or "funcionario"
                nome = pessoa.get("nome") or email
                cursor.execute(
                    f'''
                    INSERT INTO "{schema}".usuarios (nome, email, senha, papel)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (email) DO NOTHING
                    RETURNING id
                    ''',
                    (nome, email, secrets.token_urlsafe(9), papel),
                )
                criado = cursor.fetchone()
            conexao.commit()
            if criado and pessoa.get("funcionario_id"):
                try:
                    with conexao.cursor() as cursor:
                        cursor.execute(
                            f'UPDATE "{schema}".funcionarios SET usuario_id = %s WHERE id = %s AND usuario_id IS NULL',
                            (criado["id"], pessoa["funcionario_id"]),
                        )
                    conexao.commit()
                except Exception as e:
                    print(f"vincular funcionario ao login: {e}")
                    try:
                        conexao.rollback()
                    except Exception:
                        pass
            return bool(criado)
        except Exception as e:
            print(f"garantir login colaborador: {e}")
            try:
                conexao.rollback()
            except Exception:
                pass
            return False
        finally:
            conexao.close()
    finally:
        limpar_banco_escola(token)


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
                    "SELECT * FROM usuarios WHERE LOWER(email) = %s",
                    (normalizar_email(email),),
                )
                usuario = cursor.fetchone()
        except Exception as e:
            print(f"usuario_da_escola: {e}")
            try:
                conexao.rollback()
            except Exception:
                pass
            usuario = None
        finally:
            conexao.close()
    finally:
        limpar_banco_escola(token)
    if usuario and usuario.get("senha") == senha:
        return usuario, escola
    return None, escola
