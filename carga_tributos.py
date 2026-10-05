"""Leitura agregada dos dados tributários de cada unidade (poucas consultas por unidade) e cache curto.

As unidades da rede ficam em schemas diferentes do mesmo banco. A conexão é uma só por worker, então
as outras unidades são lidas com o nome do schema na consulta, sem trocar o search_path do cursor aberto.
"""

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
    t_mens = tabela(schema, "financeiro_mensalidades")
    dados = {
        "schema": schema, "mes": mes_apuracao, "inicio": inicio,
        "venc": {}, "pago": {}, "juros": {}, "multa": {}, "qtd_mora": {},
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
            """,
            (f"{inicio}-01", f"{fim_exclusivo}-01", f"{inicio}-01", f"{fim_exclusivo}-01"),
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

    def _gravados():
        cursor.execute(
            f"SELECT competencia, receita_bruta, folha_encargos, origem, observacao FROM {tabela(schema, 'simples_competencias')}"
        )
        return _linhas(cursor)

    try:
        dados["gravados"] = {l["competencia"]: dict(l) for l in _savepoint(cursor, "carga_simples", _gravados)}
    except Exception:
        dados["gravados"] = {}

    def _folha():
        cursor.execute(
            f"""
            SELECT competencia, SUM(custo_escola::numeric) AS total
            FROM {tabela(schema, 'folha_itens')}
            WHERE competencia >= %s AND competencia <= %s
            GROUP BY competencia
            """,
            (inicio, mes_apuracao),
        )
        return _linhas(cursor)

    try:
        dados["folha"] = {l["competencia"]: _f(l["total"]) for l in _savepoint(cursor, "carga_folha", _folha)}
    except Exception:
        dados["folha"] = {}
    return dados


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


def gravar_saldo_periodo(cursor, schema, periodo, apuracao):
    cursor.execute(
        f"""
        INSERT INTO {tabela(schema, 'lucro_real_saldos')}
            (periodo, prejuizo_fiscal, base_negativa_csll, compensado_irpj, compensado_csll, atualizado_em)
        VALUES (%s, %s, %s, %s, %s, NOW())
        ON CONFLICT (periodo) DO UPDATE SET
            prejuizo_fiscal = EXCLUDED.prejuizo_fiscal,
            base_negativa_csll = EXCLUDED.base_negativa_csll,
            compensado_irpj = EXCLUDED.compensado_irpj,
            compensado_csll = EXCLUDED.compensado_csll,
            atualizado_em = NOW()
        """,
        (
            periodo,
            apuracao.get("novo_prejuizo") or 0,
            apuracao.get("nova_base_negativa") or 0,
            apuracao.get("compensacao_irpj") or 0,
            apuracao.get("compensacao_csll") or 0,
        ),
    )


# ---------------------------------------------------------------- montagem (pura)

def mora_do_mes(dados, comp):
    juros = dados["juros"].get(comp, 0.0)
    multa = dados["multa"].get(comp, 0.0)
    return {"juros": juros, "multa": multa, "total": round(juros + multa, 2), "qtd": dados["qtd_mora"].get(comp, 0)}


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
