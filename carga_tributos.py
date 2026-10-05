"""Leitura agregada dos dados tributários de cada unidade (poucas consultas por unidade) e cache curto.

As unidades da rede ficam em schemas diferentes do mesmo banco. A conexão é uma só por worker, então
as outras unidades são lidas com o nome do schema na consulta, sem trocar o search_path do cursor aberto.
"""

import json
import re
import time

from simples_nacional import (
    _ORIGENS_CONGELADAS,
    _rotulo_comp,
    competencia_add,
    janela_competencias,
    receita_para_apuracao,
)
from tributacao import normalizar_regime_apuracao

TTL_CACHE = 60
_CACHE = {}
_VERSOES = {}

CAMPOS_HERDADOS = (
    "regime_tributario",
    "regime_apuracao",
    "simples_atividade",
    "simples_rbt12_criterio",
    "presuncao_irpj_pct",
    "presuncao_csll_pct",
    "presuncao_fundamento",
    "pis_cofins_incluir_mora",
    "presumido_aplicar_lc224",
    "lucro_real_periodo",
    "lucro_real_estimativa_modo",
    "pis_cofins_lucro_real",
)
ROTULOS_HERDADOS = {
    "regime_tributario": "Regime tributário",
    "regime_apuracao": "Regime de apuração",
    "simples_atividade": "Atividade no Simples",
    "simples_rbt12_criterio": "Critério da RBT12",
    "presuncao_irpj_pct": "Presunção do IRPJ",
    "presuncao_csll_pct": "Presunção da CSLL",
    "presuncao_fundamento": "Fundamento da presunção",
    "pis_cofins_incluir_mora": "Juros e multa no PIS/COFINS",
    "presumido_aplicar_lc224": "Acréscimo da LC 224/2025",
    "lucro_real_periodo": "Período do Lucro Real",
    "lucro_real_estimativa_modo": "Estimativa mensal",
    "pis_cofins_lucro_real": "PIS/COFINS no Lucro Real",
}
PADROES_TRIBUTARIOS = {
    "regime_apuracao": "competencia",
    "simples_atividade": "ensino",
    "simples_rbt12_criterio": "mesmo_regime",
    "presuncao_irpj_pct": 32.0,
    "presuncao_csll_pct": 32.0,
    "presuncao_fundamento": None,
    "iss_aliquota_pct": 5.0,
    "pis_cofins_incluir_mora": True,
    "presumido_aplicar_lc224": True,
    "lucro_real_periodo": "trimestral",
    "lucro_real_estimativa_modo": "balancete",
    "pis_cofins_lucro_real": "cumulativo_ensino",
}


def schema_valido(nome):
    texto = (nome or "").strip()
    return texto if re.fullmatch(r"[a-z][a-z0-9_]{0,62}", texto) else ""


def tabela(schema, nome):
    schema = schema_valido(schema)
    return f'"{schema}".{nome}' if schema else nome


# ---------------------------------------------------------------- cache

def versao_schema(schema):
    return _VERSOES.get(schema or "", 0)


def invalidar_schema(schema):
    """Chamado em toda gravação (POST) da escola: os próximos cálculos releem o banco."""
    chave = schema or ""
    _VERSOES[chave] = _VERSOES.get(chave, 0) + 1
    for k in [k for k in _CACHE if k[0] == chave]:
        _CACHE.pop(k, None)


def cache_buscar(schema, *chave):
    item = _CACHE.get((schema or "", versao_schema(schema)) + chave)
    if not item:
        return None
    criado, valor = item
    if time.monotonic() - criado > TTL_CACHE:
        return None
    return valor


def cache_guardar(schema, valor, *chave):
    if len(_CACHE) > 500:
        _CACHE.clear()
    _CACHE[(schema or "", versao_schema(schema)) + chave] = (time.monotonic(), valor)
    return valor


# ---------------------------------------------------------------- leitura

def _f(valor):
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return 0.0


def _como_dict(cursor, linha):
    if linha is None:
        return None
    if isinstance(linha, dict):
        return dict(linha)
    return {col[0]: valor for col, valor in zip(cursor.description, linha)}


def _linhas(cursor):
    """fetchall como dicts, com cursor comum ou RealDictCursor."""
    return [_como_dict(cursor, l) for l in cursor.fetchall() or []]


def _linha(cursor):
    return _como_dict(cursor, cursor.fetchone())


def _savepoint(cursor, nome, funcao):
    cursor.execute(f"SAVEPOINT {nome}")
    try:
        resultado = funcao()
        cursor.execute(f"RELEASE SAVEPOINT {nome}")
        return resultado
    except Exception:
        cursor.execute(f"ROLLBACK TO SAVEPOINT {nome}")
        raise


def carregar_unidade(cursor, schema, mes_apuracao, meses_antes=12):
    """Receita por vencimento e por pagamento, juros/multa, folha e competências gravadas da janela.

    Três consultas por unidade, qualquer que seja o tamanho da janela.
    """
    inicio = competencia_add(mes_apuracao, -meses_antes)
    fim_exclusivo = competencia_add(mes_apuracao, 1)
    mes_num = int(mes_apuracao[5:7])
    fim_trimestre_exclusivo = competencia_add(mes_apuracao, ((mes_num - 1) // 3 + 1) * 3 - mes_num + 1)
    t_mens = tabela(schema, "financeiro_mensalidades")
    dados = {
        "schema": schema, "mes": mes_apuracao, "inicio": inicio,
        "venc": {}, "pago": {}, "juros": {}, "multa": {}, "qtd_mora": {}, "venc_futuro": {},
        "primeira_venc": None, "primeira_pago": None, "gravados": {}, "folha": {},
    }

    def _mensalidades():
        cursor.execute(
            f"""
            SELECT 'v' AS tipo, TO_CHAR(data_vencimento, 'YYYY-MM') AS comp,
                   SUM(valor::numeric) AS receita, 0 AS juros, 0 AS multa, 0 AS qtd
            FROM {t_mens}
            WHERE data_vencimento >= %s::date AND data_vencimento < %s::date
              AND LOWER(COALESCE(status, '')) IN ('pago', 'pendente', 'atrasado')
            GROUP BY 2
            UNION ALL
            SELECT 'p', TO_CHAR(data_pagamento, 'YYYY-MM'),
                   SUM(valor::numeric), SUM(COALESCE(juros_valor, 0)), SUM(COALESCE(multa_valor, 0)),
                   COUNT(*) FILTER (WHERE COALESCE(juros_valor, 0) > 0 OR COALESCE(multa_valor, 0) > 0)
            FROM {t_mens}
            WHERE LOWER(COALESCE(status, '')) = 'pago' AND data_pagamento IS NOT NULL
              AND data_pagamento >= %s::date AND data_pagamento < %s::date
            GROUP BY 2
            UNION ALL
            SELECT 'iv', MIN(TO_CHAR(data_vencimento, 'YYYY-MM')), 0, 0, 0, 0
            FROM {t_mens}
            WHERE LOWER(COALESCE(status, '')) NOT IN ('cancelado', 'cancelada')
            UNION ALL
            SELECT 'ip', MIN(TO_CHAR(data_pagamento, 'YYYY-MM')), 0, 0, 0, 0
            FROM {t_mens}
            WHERE LOWER(COALESCE(status, '')) = 'pago' AND data_pagamento IS NOT NULL
            UNION ALL
            SELECT 'vf', TO_CHAR(data_vencimento, 'YYYY-MM'), SUM(valor::numeric), 0, 0, 0
            FROM {t_mens}
            WHERE data_vencimento >= %s::date AND data_vencimento < %s::date
              AND LOWER(COALESCE(status, '')) IN ('pago', 'pendente', 'atrasado')
            GROUP BY 2
            """,
            (f"{inicio}-01", f"{fim_exclusivo}-01", f"{inicio}-01", f"{fim_exclusivo}-01",
             f"{fim_exclusivo}-01", f"{fim_trimestre_exclusivo}-01"),
        )
        return _linhas(cursor)

    for linha in _savepoint(cursor, "carga_mens", _mensalidades):
        tipo, comp = linha["tipo"], linha["comp"]
        if tipo == "v" and comp:
            dados["venc"][comp] = _f(linha["receita"])
        elif tipo == "p" and comp:
            dados["pago"][comp] = _f(linha["receita"])
            dados["juros"][comp] = round(_f(linha["juros"]), 2)
            dados["multa"][comp] = round(_f(linha["multa"]), 2)
            dados["qtd_mora"][comp] = int(linha["qtd"] or 0)
        elif tipo == "iv":
            dados["primeira_venc"] = comp
        elif tipo == "ip":
            dados["primeira_pago"] = comp
        elif tipo == "vf" and comp:
            dados["venc_futuro"][comp] = _f(linha["receita"])

    def _gravados():
        cursor.execute(
            f"SELECT competencia, receita_bruta, folha_encargos, origem, observacao FROM {tabela(schema, 'simples_competencias')}"
        )
        return _linhas(cursor)

    try:
        dados["gravados"] = {l["competencia"]: dict(l) for l in _savepoint(cursor, "carga_simples", _gravados)}
    except Exception:
        dados["gravados"] = {}

    def _folha_itens():
        cursor.execute(
            f"""
            SELECT 'i' AS origem, competencia, SUM(custo_escola::numeric) AS total
            FROM {tabela(schema, 'folha_itens')}
            WHERE competencia >= %s AND competencia <= %s
            GROUP BY competencia
            """,
            (inicio, mes_apuracao),
        )
        return _linhas(cursor)

    def _folha():
        cursor.execute(
            f"""
            SELECT 'f' AS origem, c.competencia, COALESCE(SUM((s.item->>'custo_escola')::numeric), 0) AS total
            FROM {tabela(schema, 'competencias_fechadas')} c
            LEFT JOIN {tabela(schema, 'folha_snapshot')} s ON s.competencia = c.competencia
            WHERE c.competencia >= %s AND c.competencia <= %s
            GROUP BY c.competencia
            UNION ALL
            SELECT 'i', competencia, SUM(custo_escola::numeric)
            FROM {tabela(schema, 'folha_itens')}
            WHERE competencia >= %s AND competencia <= %s
            GROUP BY competencia
            """,
            (inicio, mes_apuracao, inicio, mes_apuracao),
        )
        return _linhas(cursor)

    try:
        linhas_folha = _savepoint(cursor, "carga_folha", _folha)
    except Exception:
        try:
            linhas_folha = _savepoint(cursor, "carga_folha", _folha_itens)
        except Exception:
            linhas_folha = []
    dados["folha"], dados["folha_fechada"] = folha_por_competencia(linhas_folha)
    return dados


def folha_por_competencia(linhas):
    """Folha e encargos por mês: o snapshot nos meses fechados, `folha_itens` nos abertos.
    Devolve (folha, folha_fechada)."""
    fechada = {l["competencia"]: _f(l["total"]) for l in linhas if l.get("origem") == "f" and l.get("competencia")}
    folha = {l["competencia"]: _f(l["total"]) for l in linhas if l.get("origem") != "f" and l.get("competencia")}
    folha.update(fechada)
    return folha, fechada


def carregar_unidade_cache(cursor, schema_cache, schema_consulta, mes_apuracao):
    dados = cache_buscar(schema_cache, "unidade", mes_apuracao)
    if dados is None:
        dados = cache_guardar(schema_cache, carregar_unidade(cursor, schema_consulta, mes_apuracao), "unidade", mes_apuracao)
    return dados


def ler_config(cursor, schema=None):
    def _ler():
        cursor.execute(f"SELECT * FROM {tabela(schema, 'configuracoes')} WHERE id = 1")
        return _linha(cursor) or {}

    try:
        return _savepoint(cursor, "carga_config", _ler)
    except Exception:
        return {}


def ler_escolas_plataforma(cursor):
    def _ler():
        cursor.execute(
            "SELECT id, nome, db_nome, tipo_unidade, matriz_id, cnpj FROM public.plataforma_escolas ORDER BY id"
        )
        return _linhas(cursor)

    try:
        return _savepoint(cursor, "carga_plataforma", _ler)
    except Exception:
        return []


# ---------------------------------------------------------------- Lucro Real (tabelas no schema da matriz)

SALDO_INICIAL = "0000-00"


def garantir_tabelas_lucro_real(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS lucro_real_ajustes (
            id SERIAL PRIMARY KEY,
            competencia VARCHAR(7) NOT NULL,
            tipo VARCHAR(10) NOT NULL CHECK (tipo IN ('adicao', 'exclusao')),
            tributo VARCHAR(10) NOT NULL DEFAULT 'ambos' CHECK (tributo IN ('irpj', 'csll', 'ambos')),
            descricao VARCHAR(255),
            valor NUMERIC(14,2) NOT NULL DEFAULT 0,
            criado_por VARCHAR(150),
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS lucro_real_saldos (
            periodo VARCHAR(7) PRIMARY KEY,
            prejuizo_fiscal NUMERIC(14,2) DEFAULT 0,
            base_negativa_csll NUMERIC(14,2) DEFAULT 0,
            compensado_irpj NUMERIC(14,2) DEFAULT 0,
            compensado_csll NUMERIC(14,2) DEFAULT 0,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute("ALTER TABLE lucro_real_saldos ADD COLUMN IF NOT EXISTS fechado BOOLEAN DEFAULT FALSE")
    cursor.execute("ALTER TABLE lucro_real_saldos ADD COLUMN IF NOT EXISTS fechado_por VARCHAR(150)")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS lucro_real_fechamento_log (
            id SERIAL PRIMARY KEY,
            periodo VARCHAR(7) NOT NULL,
            acao VARCHAR(10) NOT NULL,
            usuario_nome VARCHAR(150),
            motivo TEXT,
            em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    garantir_tributos_snapshot(cursor)


def garantir_tributos_snapshot(cursor, schema=None):
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {tabela(schema, 'tributos_snapshot')} (
            competencia VARCHAR(7),
            unidade_id INT,
            regime VARCHAR(20),
            dados JSONB,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (competencia, unidade_id)
        )
        """
    )


def ler_tributos_snapshot(cursor, unidades, competencias):
    """{(unidade_id, competencia): dados} dos meses congelados de cada unidade. `unidades`: [(id, schema)].
    Uma consulta para a rede toda; unidade sem a tabela fica sem snapshot."""
    unidades = [(uid, s) for uid, s in unidades if uid is not None and schema_valido(s)]
    if not unidades or not competencias:
        return {}
    comps = list(competencias)

    def _ler(lista):
        partes = [
            f"SELECT unidade_id, competencia, dados FROM {tabela(s, 'tributos_snapshot')} "
            "WHERE unidade_id = %s AND competencia = ANY(%s)"
            for _uid, s in lista
        ]
        params = [p for uid, _s in lista for p in (uid, comps)]
        cursor.execute(" UNION ALL ".join(partes), params)
        return _linhas(cursor)

    try:
        linhas = _savepoint(cursor, "carga_trib_snap", lambda: _ler(unidades))
    except Exception:
        linhas = []
        for item in unidades:
            try:
                linhas += _savepoint(cursor, "carga_trib_snap", lambda item=item: _ler([item]))
            except Exception:
                pass
    saida = {}
    for linha in linhas:
        dados = linha.get("dados")
        if isinstance(dados, str):
            try:
                dados = json.loads(dados)
            except ValueError:
                dados = None
        if isinstance(dados, dict):
            saida[(linha.get("unidade_id"), linha.get("competencia"))] = dados
    return saida


def gravar_tributos_snapshot(cursor, schema, competencia, unidade_id, regime, dados):
    garantir_tributos_snapshot(cursor, schema)
    cursor.execute(
        f"""
        INSERT INTO {tabela(schema, 'tributos_snapshot')} (competencia, unidade_id, regime, dados)
        VALUES (%s, %s, %s, %s::jsonb)
        ON CONFLICT (competencia, unidade_id) DO UPDATE SET
            regime = EXCLUDED.regime, dados = EXCLUDED.dados, criado_em = CURRENT_TIMESTAMP
        """,
        (competencia, unidade_id, regime, json.dumps(dados, default=str)),
    )


def apagar_tributos_snapshot(cursor, schema, competencias=None, desde=None):
    """Apaga o snapshot das competências pedidas ou de `desde` em diante."""
    def _apagar():
        if desde:
            cursor.execute(f"DELETE FROM {tabela(schema, 'tributos_snapshot')} WHERE competencia >= %s", (desde,))
        else:
            cursor.execute(
                f"DELETE FROM {tabela(schema, 'tributos_snapshot')} WHERE competencia = ANY(%s)",
                (list(competencias or []),),
            )

    try:
        _savepoint(cursor, "apaga_trib_snap", _apagar)
    except Exception:
        pass


# ---------------------------------------------------------------- custos e LAIR

CATEGORIAS_RESCISAO = ("rescisao", "rescisão", "rescisoes", "rescisões")


def efeito_caixa_custo(custo):
    valor = _f(custo.get("valor"))
    tipo = (custo.get("tipo") or "avista").lower()
    extra = 0.0
    if tipo == "servico":
        federais = _f(custo.get("irrf")) + _f(custo.get("pis")) + _f(custo.get("cofins")) + _f(custo.get("csll"))
        if not custo.get("federal_na_nota"):
            extra += federais
        if not custo.get("iss_na_nota"):
            extra += _f(custo.get("iss"))
    return valor + extra, tipo


def resumir_custos(custos):
    compras = servicos = rescisoes = 0.0
    for item in custos or []:
        efeito, tipo = efeito_caixa_custo(item)
        categoria = (item.get("categoria") or "").strip().lower()
        if categoria in CATEGORIAS_RESCISAO:
            rescisoes += efeito
        elif tipo == "servico":
            servicos += efeito
        else:
            compras += efeito
    return {
        "compras": round(compras, 2),
        "servicos": round(servicos, 2),
        "rescisoes": round(rescisoes, 2),
        "custos": round(compras + servicos + rescisoes, 2),
    }


def _comp_data(valor):
    if not valor:
        return None
    if hasattr(valor, "strftime"):
        return valor.strftime("%Y-%m")
    texto = str(valor)
    return texto[:7] if re.match(r"^\d{4}-\d{2}", texto) else None


def meses_do_custo(custo, competencias):
    """Meses de `competencias` em que o custo entra (mesma regra de `listar_custos_do_mes`)."""
    tipo = (custo.get("tipo") or "avista").lower()
    if tipo == "recorrente":
        inicio = _comp_data(custo.get("data_inicio") or custo.get("data_custo"))
        fim = _comp_data(custo.get("data_fim"))
        return [c for c in competencias if inicio and inicio <= c and (not fim or fim >= c)]
    if tipo in ("avista", "servico", "parcelado"):
        comp = _comp_data(custo.get("data_custo"))
        return [comp] if comp in competencias else []
    return []


def custos_por_mes(linhas, competencias):
    """{comp: {"custos": resumo, "creditos_pis": soma dos custos que geram crédito de PIS/COFINS}}."""
    por_mes = {c: [] for c in competencias}
    for custo in linhas or []:
        if custo.get("ativo") is False:
            continue
        for comp in meses_do_custo(custo, competencias):
            por_mes[comp].append(custo)
    return {
        c: {
            "custos": resumir_custos(itens),
            "creditos_pis": round(sum(_f(i.get("valor")) for i in itens if i.get("gera_credito_pis_cofins")), 2),
        }
        for c, itens in por_mes.items()
    }


def carregar_custos_meses(cursor, schema, competencias):
    """Custos de vários meses numa consulta."""
    if not competencias:
        return {}
    inicio, fim = min(competencias), max(competencias)

    def _ler():
        cursor.execute(
            f"""
            SELECT * FROM {tabela(schema, 'financeiro_custos')}
            WHERE COALESCE(ativo, TRUE) = TRUE
              AND (
                (COALESCE(tipo, 'avista') IN ('avista', 'servico', 'parcelado')
                    AND TO_CHAR(data_custo, 'YYYY-MM') >= %s AND TO_CHAR(data_custo, 'YYYY-MM') <= %s)
                OR (tipo = 'recorrente'
                    AND TO_CHAR(COALESCE(data_inicio, data_custo), 'YYYY-MM') <= %s
                    AND (data_fim IS NULL OR TO_CHAR(data_fim, 'YYYY-MM') >= %s))
              )
            """,
            (inicio, fim, fim, inicio),
        )
        return _linhas(cursor)

    return custos_por_mes(_savepoint(cursor, "carga_custos", _ler), list(competencias))


def lair_do_mes(dados, comp, cfg, folha_custo, custos_mes):
    """LAIR da unidade no mês, com as linhas da DRE: receita por competência − PIS/COFINS − ISS − folha
    − rescisões − compras − serviços + juros e multa recebidos."""
    from tributos_rede import apurar_pis_cofins_real, arred

    receita = receita_regime(dados, comp, "competencia")
    mora = mora_do_mes(dados, comp)["total"]
    modo = cfg.get("pis_cofins_lucro_real") or "cumulativo_ensino"
    custos_mes = custos_mes or {}
    creditos = _f(custos_mes.get("creditos_pis")) if modo == "nao_cumulativo" else 0.0
    pis_cofins = apurar_pis_cofins_real(receita, 0, mora, creditos, modo, bool(cfg.get("pis_cofins_incluir_mora", True)))
    iss = arred(receita * _f(cfg.get("iss_aliquota_pct")) / 100)
    custos = custos_mes.get("custos") or {}
    lair = arred(
        receita - pis_cofins["total"] - iss - _f(folha_custo)
        - _f(custos.get("rescisoes")) - _f(custos.get("compras")) - _f(custos.get("servicos"))
        + mora
    )
    return {
        "lair": lair, "receita": receita, "mora": mora, "pis_cofins": pis_cofins["total"], "iss": iss,
        "folha": round(_f(folha_custo), 2), "custos": _f(custos.get("custos")),
    }


def ajustes_lucro_real(cursor, schema, competencias):
    """{competencia: {"adicoes_irpj", "exclusoes_irpj", "adicoes_csll", "exclusoes_csll", "itens": [...]}}."""
    saida = {c: {"adicoes_irpj": 0.0, "exclusoes_irpj": 0.0, "adicoes_csll": 0.0, "exclusoes_csll": 0.0, "itens": []}
             for c in competencias}
    if not competencias:
        return saida

    def _ler():
        cursor.execute(
            f"SELECT id, competencia, tipo, tributo, descricao, valor FROM {tabela(schema, 'lucro_real_ajustes')} "
            "WHERE competencia = ANY(%s) ORDER BY competencia, id",
            (list(competencias),),
        )
        return _linhas(cursor)

    try:
        linhas = _savepoint(cursor, "carga_ajustes", _ler)
    except Exception:
        return saida
    for linha in linhas:
        alvo = saida.get(linha["competencia"])
        if alvo is None:
            continue
        valor = _f(linha["valor"])
        sufixo = "adicoes" if linha["tipo"] == "adicao" else "exclusoes"
        if linha["tributo"] in ("irpj", "ambos"):
            alvo[f"{sufixo}_irpj"] += valor
        if linha["tributo"] in ("csll", "ambos"):
            alvo[f"{sufixo}_csll"] += valor
        alvo["itens"].append(dict(linha))
    return saida


def saldo_prejuizo_anterior(cursor, schema, periodo):
    """Saldo de prejuízo fiscal e base negativa gravado no último período antes de `periodo` (ou o inicial)."""
    def _ler():
        cursor.execute(
            f"SELECT periodo, prejuizo_fiscal, base_negativa_csll FROM {tabela(schema, 'lucro_real_saldos')} "
            "WHERE periodo < %s ORDER BY periodo DESC LIMIT 1",
            (periodo,),
        )
        return _linha(cursor)

    try:
        linha = _savepoint(cursor, "carga_saldo", _ler) or {}
    except Exception:
        linha = {}
    return {
        "periodo": linha.get("periodo"),
        "prejuizo_fiscal": _f(linha.get("prejuizo_fiscal")),
        "base_negativa_csll": _f(linha.get("base_negativa_csll")),
    }


def ler_saldos_lucro_real(cursor, schema):
    """{periodo: {"prejuizo_fiscal", "base_negativa_csll", "fechado"}} de todos os saldos gravados. Uma consulta."""
    def _ler(com_fechado):
        coluna = ", COALESCE(fechado, FALSE) AS fechado" if com_fechado else ""
        cursor.execute(
            f"SELECT periodo, prejuizo_fiscal, base_negativa_csll{coluna} FROM {tabela(schema, 'lucro_real_saldos')}"
        )
        return _linhas(cursor)

    try:
        linhas = _savepoint(cursor, "carga_saldos", lambda: _ler(True))
    except Exception:
        try:
            linhas = _savepoint(cursor, "carga_saldos", lambda: _ler(False))
        except Exception:
            linhas = []
    return {
        l["periodo"]: {
            "prejuizo_fiscal": _f(l.get("prejuizo_fiscal")),
            "base_negativa_csll": _f(l.get("base_negativa_csll")),
            "fechado": bool(l.get("fechado")) and l["periodo"] != SALDO_INICIAL,
        }
        for l in linhas if l.get("periodo")
    }


def gravar_saldo_periodo(cursor, schema, periodo, apuracao, fechado_por=None):
    """Grava o saldo do período no fechamento explícito (nunca num GET)."""
    cursor.execute(
        f"""
        INSERT INTO {tabela(schema, 'lucro_real_saldos')}
            (periodo, prejuizo_fiscal, base_negativa_csll, compensado_irpj, compensado_csll, fechado, fechado_por, atualizado_em)
        VALUES (%s, %s, %s, %s, %s, TRUE, %s, NOW())
        ON CONFLICT (periodo) DO UPDATE SET
            prejuizo_fiscal = EXCLUDED.prejuizo_fiscal,
            base_negativa_csll = EXCLUDED.base_negativa_csll,
            compensado_irpj = EXCLUDED.compensado_irpj,
            compensado_csll = EXCLUDED.compensado_csll,
            fechado = TRUE,
            fechado_por = EXCLUDED.fechado_por,
            atualizado_em = NOW()
        """,
        (
            periodo,
            apuracao.get("novo_prejuizo") or 0,
            apuracao.get("nova_base_negativa") or 0,
            apuracao.get("compensacao_irpj") or 0,
            apuracao.get("compensacao_csll") or 0,
            (fechado_por or "")[:150] or None,
        ),
    )


def apagar_saldos_desde(cursor, schema, periodo):
    """Reabrir: apaga o saldo do período e dos seguintes (o saldo inicial fica)."""
    cursor.execute(
        f"DELETE FROM {tabela(schema, 'lucro_real_saldos')} WHERE periodo >= %s AND periodo <> %s",
        (periodo, SALDO_INICIAL),
    )


def registrar_fechamento_lucro_real(cursor, schema, periodo, acao, usuario_nome=None, motivo=None):
    cursor.execute(
        f"INSERT INTO {tabela(schema, 'lucro_real_fechamento_log')} (periodo, acao, usuario_nome, motivo) "
        "VALUES (%s, %s, %s, %s)",
        (periodo, acao, (usuario_nome or "")[:150] or None, (motivo or "")[:1000] or None),
    )


def historico_fechamento_lucro_real(cursor, schema, limite=10):
    def _ler():
        cursor.execute(
            f"SELECT periodo, acao, usuario_nome, motivo, em FROM {tabela(schema, 'lucro_real_fechamento_log')} "
            "ORDER BY em DESC, id DESC LIMIT %s",
            (limite,),
        )
        return _linhas(cursor)

    try:
        return _savepoint(cursor, "carga_log_real", _ler)
    except Exception:
        return []


# ---------------------------------------------------------------- montagem (pura)

def mora_do_mes(dados, comp):
    juros = dados["juros"].get(comp, 0.0)
    multa = dados["multa"].get(comp, 0.0)
    return {"juros": juros, "multa": multa, "total": round(juros + multa, 2), "qtd": dados["qtd_mora"].get(comp, 0)}


def receita_prevista_resto_trimestre(dados):
    """Parcelas já geradas que vencem nos meses seguintes do trimestre (depois do mês apurado)."""
    return round(sum((dados.get("venc_futuro") or {}).values()), 2)


def receita_regime(dados, comp, regime):
    return dados["pago" if normalizar_regime_apuracao(regime) == "caixa" else "venc"].get(comp, 0.0)


def primeira_competencia(dados, regime):
    """Mesma regra de simples_nacional.primeira_competencia_sistema."""
    gravadas = [
        c for c, g in dados["gravados"].items()
        if _f(g.get("receita_bruta")) > 0 or (g.get("origem") or "") in _ORIGENS_CONGELADAS
    ]
    if gravadas:
        return min(gravadas)
    return dados["primeira_pago"] if normalizar_regime_apuracao(regime) == "caixa" else dados["primeira_venc"]


def quadro_da_unidade(dados, mes_apuracao, regime_apuracao="competencia", regime_rbt12=None):
    """Mesmo resultado de simples_nacional.montar_quadro_simples, a partir dos dados já carregados."""
    regime = normalizar_regime_apuracao(regime_apuracao)
    regime_janela = normalizar_regime_apuracao(regime_rbt12 or regime)
    janela = janela_competencias(mes_apuracao)
    primeira = primeira_competencia(dados, regime_janela)
    gravados = dados["gravados"]
    linhas = []
    rbt12 = fs12 = 0.0
    meses_validos = 0
    for comp in janela:
        gravado = gravados.get(comp) or {}
        rec = receita_para_apuracao(gravado, regime_janela, receita_regime(dados, comp, regime_janela), comp, mes_apuracao)
        folha = _f(gravado.get("folha_encargos")) if gravado else dados["folha"].get(comp, 0.0)
        entra = not (primeira and comp < primeira)
        if entra:
            rbt12 += rec
            fs12 += folha
            meses_validos += 1
        linhas.append({
            "competencia": comp,
            "receita_bruta": rec,
            "folha_encargos": folha,
            "origem": gravado.get("origem") or ("sistema" if rec or folha else ""),
            "observacao": gravado.get("observacao") or "",
            "entra_rbt12": entra,
            "rotulo": _rotulo_comp(comp),
        })
    gravado_mes = gravados.get(mes_apuracao) or {}
    receita_mes = receita_para_apuracao(gravado_mes, regime, receita_regime(dados, mes_apuracao, regime), mes_apuracao, mes_apuracao)
    folha_mes = _f(gravado_mes.get("folha_encargos")) or dados["folha"].get(mes_apuracao, 0.0)
    origem_mes = gravado_mes.get("origem") or ("sistema" if receita_mes or folha_mes else "")
    if regime == "competencia":
        origem_mes = "sistema"
    return {
        "janela": janela,
        "linhas": linhas,
        "linha_apuracao": {
            "competencia": mes_apuracao,
            "receita_bruta": receita_mes,
            "folha_encargos": folha_mes,
            "origem": origem_mes,
            "observacao": gravado_mes.get("observacao") or "",
            "entra_rbt12": False,
            "rotulo": _rotulo_comp(mes_apuracao),
        },
        "rbt12": rbt12,
        "fs12": fs12,
        "meses_validos": meses_validos or 1,
        "primeira": primeira,
        "receita_mes": receita_mes,
        "folha_mes": folha_mes,
        "mes_apuracao": mes_apuracao,
        "regime_apuracao": regime,
    }


def config_efetiva(cfg_unidade, cfg_matriz=None, eh_filial=False):
    """Campos tributários usados nos cálculos. Filial herda da matriz; o ISS é sempre da própria unidade."""
    cfg_unidade = cfg_unidade or {}
    origem = (cfg_matriz or {}) if eh_filial else cfg_unidade
    efetiva = {}
    for campo in CAMPOS_HERDADOS:
        valor = origem.get(campo)
        efetiva[campo] = PADROES_TRIBUTARIOS.get(campo) if valor is None or valor == "" else valor
    iss = cfg_unidade.get("iss_aliquota_pct")
    efetiva["iss_aliquota_pct"] = PADROES_TRIBUTARIOS["iss_aliquota_pct"] if iss is None else _f(iss)
    efetiva["data_abertura"] = origem.get("data_abertura")
    efetiva["regime_tributario"] = (origem.get("regime_tributario") or "").strip() or None
    divergentes = []
    if eh_filial and cfg_matriz:
        for campo in CAMPOS_HERDADOS:
            proprio = cfg_unidade.get(campo)
            if proprio in (None, ""):
                continue
            if str(proprio).strip().lower() != str(efetiva.get(campo) or "").strip().lower():
                try:
                    if float(proprio) == float(efetiva.get(campo)):
                        continue
                except (TypeError, ValueError):
                    pass
                divergentes.append(ROTULOS_HERDADOS.get(campo, campo))
    efetiva["divergentes"] = divergentes
    efetiva["herdado"] = bool(eh_filial and cfg_matriz)
    return efetiva


def receitas_do_ano(dados, mes_apuracao, regime):
    """Receita, juros e multa de cada mês do ano até o mês de apuração (Presumido/Real)."""
    ano = mes_apuracao[:4]
    comps = [c for c in (competencia_add(mes_apuracao, -i) for i in range(11, -1, -1)) if c[:4] == ano]
    return {c: {"receita": receita_regime(dados, c, regime), "mora": mora_do_mes(dados, c)["total"]} for c in comps}
