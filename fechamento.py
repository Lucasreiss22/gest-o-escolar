"""Fechamento de competência da folha: grava o contracheque de cada pessoa como foi emitido.

Competência fechada é lida do snapshot (contracheque, PDF, envio, financeiro, Simples); só a aberta é recalculada.
Reabrir apaga o snapshot e exige motivo; fechar e reabrir ficam no log.
"""

import json
import re
from datetime import date, datetime
from decimal import Decimal

_RE_COMPETENCIA = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
MOTIVO_MINIMO_REABERTURA = 10


def garantir_tabelas_fechamento(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS competencias_fechadas (
            competencia VARCHAR(7) PRIMARY KEY,
            fechada_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            fechada_por INT,
            fechada_nome VARCHAR(150),
            regime VARCHAR(40),
            pessoas INT DEFAULT 0,
            totais JSONB NOT NULL
        );
        CREATE TABLE IF NOT EXISTS folha_snapshot (
            competencia VARCHAR(7) NOT NULL,
            funcionario_id INT NOT NULL,
            item JSONB NOT NULL,
            PRIMARY KEY (competencia, funcionario_id)
        );
        CREATE TABLE IF NOT EXISTS competencias_fechamento_log (
            id SERIAL PRIMARY KEY,
            competencia VARCHAR(7) NOT NULL,
            acao VARCHAR(10) NOT NULL,
            usuario_id INT,
            usuario_nome VARCHAR(150),
            motivo TEXT,
            totais JSONB,
            em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def validar_competencia(competencia, hoje=None):
    competencia = (competencia or "").strip()[:7]
    if not _RE_COMPETENCIA.match(competencia):
        raise ValueError("Competência inválida.")
    hoje = hoje or date.today()
    if competencia > hoje.strftime("%Y-%m"):
        raise ValueError("Não é possível fechar uma competência futura.")
    return competencia


def info_fechamento(cursor, competencia):
    if not competencia:
        return None
    cursor.execute(
        "SELECT competencia, fechada_em, fechada_por, fechada_nome, regime, pessoas, totais "
        "FROM competencias_fechadas WHERE competencia = %s",
        (competencia,),
    )
    linha = cursor.fetchone()
    return dict(linha) if linha else None


def competencias_fechadas(cursor):
    cursor.execute("SELECT competencia FROM competencias_fechadas")
    return {(linha["competencia"] if isinstance(linha, dict) else linha[0]) for linha in cursor.fetchall() or []}


def _serializavel(valor):
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    return str(valor)


def _json(valor):
    return json.dumps(valor, ensure_ascii=False, default=_serializavel)


def _carregar(valor):
    if isinstance(valor, str):
        try:
            return json.loads(valor)
        except ValueError:
            return {}
    return valor or {}


def fechar_competencia(cursor, competencia, itens, totais, regime, usuario_id=None, usuario_nome=None, hoje=None):
    competencia = validar_competencia(competencia, hoje)
    cursor.execute(
        """
        INSERT INTO competencias_fechadas (competencia, fechada_por, fechada_nome, regime, pessoas, totais)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (competencia) DO NOTHING
        RETURNING competencia
        """,
        (competencia, usuario_id, usuario_nome, regime, len(itens or []), _json(totais or {})),
    )
    if not cursor.fetchone():
        raise ValueError("Esta competência já está fechada.")
    for item in itens or []:
        cursor.execute(
            "INSERT INTO folha_snapshot (competencia, funcionario_id, item) VALUES (%s, %s, %s::jsonb)",
            (competencia, item.get("id"), _json(item)),
        )
    cursor.execute(
        "INSERT INTO competencias_fechamento_log (competencia, acao, usuario_id, usuario_nome, totais) "
        "VALUES (%s, 'fechar', %s, %s, %s::jsonb)",
        (competencia, usuario_id, usuario_nome, _json(totais or {})),
    )
    return competencia


def reabrir_competencia(cursor, competencia, motivo, usuario_id=None, usuario_nome=None):
    motivo = (motivo or "").strip()
    if len(motivo) < MOTIVO_MINIMO_REABERTURA:
        raise ValueError(f"Escreva o motivo da reabertura (mínimo {MOTIVO_MINIMO_REABERTURA} caracteres).")
    cursor.execute(
        "DELETE FROM competencias_fechadas WHERE competencia = %s RETURNING totais",
        (competencia,),
    )
    linha = cursor.fetchone()
    if not linha:
        raise ValueError("Esta competência não está fechada.")
    totais = linha["totais"] if isinstance(linha, dict) else linha[0]
    cursor.execute("DELETE FROM folha_snapshot WHERE competencia = %s", (competencia,))
    cursor.execute(
        "INSERT INTO competencias_fechamento_log (competencia, acao, usuario_id, usuario_nome, motivo, totais) "
        "VALUES (%s, 'reabrir', %s, %s, %s, %s::jsonb)",
        (competencia, usuario_id, usuario_nome, motivo[:1000], _json(_carregar(totais))),
    )
    return _carregar(totais)


def folha_fechada(cursor, competencia):
    """(itens, totais) gravados no fechamento, ou None se a competência estiver aberta. Uma consulta."""
    if not competencia:
        return None
    cursor.execute(
        "SELECT c.totais, s.item FROM competencias_fechadas c "
        "LEFT JOIN folha_snapshot s ON s.competencia = c.competencia WHERE c.competencia = %s",
        (competencia,),
    )
    linhas = [
        (linha["totais"], linha["item"]) if isinstance(linha, dict) else (linha[0], linha[1])
        for linha in cursor.fetchall() or []
    ]
    if not linhas:
        return None
    itens = [_carregar(item) for _totais, item in linhas if item is not None]
    itens.sort(key=lambda i: (i.get("nome_completo") or "").lower())
    return itens, _carregar(linhas[0][0])


def item_fechado(cursor, competencia, funcionario_id):
    cursor.execute(
        "SELECT item FROM folha_snapshot WHERE competencia = %s AND funcionario_id = %s",
        (competencia, funcionario_id),
    )
    linha = cursor.fetchone()
    return _carregar(linha["item"] if isinstance(linha, dict) else linha[0]) if linha else None


def historico_fechamento(cursor, competencia):
    cursor.execute(
        "SELECT acao, usuario_nome, motivo, em FROM competencias_fechamento_log WHERE competencia = %s ORDER BY em DESC, id DESC",
        (competencia,),
    )
    return [dict(linha) for linha in cursor.fetchall() or []]
