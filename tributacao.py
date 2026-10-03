"""Apuração tributária da escola: Simples Nacional (Fator R) e resumo para Lucro Real."""

from calendar import monthrange
from datetime import date, datetime


def _avancar_meses(dia, meses):
    total = dia.year * 12 + (dia.month - 1) + meses
    return date(total // 12, total % 12 + 1, 1)


# Lei Complementar 123/2006 — tabelas vigentes do Simples Nacional
ANEXO_III = [
    {"faixa": 1, "limite": 180_000.00, "aliquota": 0.06, "deduzir": 0.00},
    {"faixa": 2, "limite": 360_000.00, "aliquota": 0.112, "deduzir": 9_360.00},
    {"faixa": 3, "limite": 720_000.00, "aliquota": 0.135, "deduzir": 17_640.00},
    {"faixa": 4, "limite": 1_800_000.00, "aliquota": 0.16, "deduzir": 35_640.00},
    {"faixa": 5, "limite": 3_600_000.00, "aliquota": 0.21, "deduzir": 125_640.00},
    {"faixa": 6, "limite": 4_800_000.00, "aliquota": 0.33, "deduzir": 648_000.00},
]

ANEXO_V = [
    {"faixa": 1, "limite": 180_000.00, "aliquota": 0.155, "deduzir": 0.00},
    {"faixa": 2, "limite": 360_000.00, "aliquota": 0.18, "deduzir": 4_500.00},
    {"faixa": 3, "limite": 720_000.00, "aliquota": 0.195, "deduzir": 9_900.00},
    {"faixa": 4, "limite": 1_800_000.00, "aliquota": 0.205, "deduzir": 17_100.00},
    {"faixa": 5, "limite": 3_600_000.00, "aliquota": 0.23, "deduzir": 62_100.00},
    {"faixa": 6, "limite": 4_800_000.00, "aliquota": 0.305, "deduzir": 540_000.00},
]

LIMITE_SIMPLES = 4_800_000.00
FATOR_R_MINIMO = 0.28

# Creche, pré-escola, ensino fundamental e médio, escolas técnicas, de línguas, de artes,
# preparatórios e escolas livres: Anexo III direto, sem Fator R (LC 123/2006, art. 18, § 5º-B, I).
ATIVIDADE_ENSINO = "ensino"
ATIVIDADE_FATOR_R = "fator_r"


def normalizar_atividade_simples(valor):
    return ATIVIDADE_FATOR_R if str(valor or "").strip().lower() == ATIVIDADE_FATOR_R else ATIVIDADE_ENSINO


def normalizar_regime_apuracao(valor):
    texto = str(valor or "").strip().lower()
    if texto in ("caixa", "regime_de_caixa"):
        return "caixa"
    return "competencia"


def competencia_do_titulo(data_vencimento, data_pagamento, status, regime_apuracao):
    """Mês em que o título entra na base do imposto. No caixa, só o mês do pagamento."""
    regime = normalizar_regime_apuracao(regime_apuracao)
    situacao = str(status or "").strip().lower()
    if situacao in ("cancelado", "cancelada"):
        return None
    if regime == "caixa":
        if situacao != "pago" or not data_pagamento:
            return None
        if isinstance(data_pagamento, datetime):
            data_pagamento = data_pagamento.date()
        return f"{data_pagamento.year:04d}-{data_pagamento.month:02d}"
    if not data_vencimento:
        return None
    if isinstance(data_vencimento, datetime):
        data_vencimento = data_vencimento.date()
    return f"{data_vencimento.year:04d}-{data_vencimento.month:02d}"


def base_do_mes(titulos, mes, regime_apuracao):
    total = 0.0
    for titulo in titulos or []:
        if competencia_do_titulo(
            titulo.get("data_vencimento"),
            titulo.get("data_pagamento"),
            titulo.get("status"),
            regime_apuracao,
        ) == mes:
            total += float(titulo.get("valor") or 0)
    return total


def meses_do_trimestre(mes_str):
    ano, mes = parse_mes(mes_str)
    inicio = ((mes - 1) // 3) * 3 + 1
    return [f"{ano}-{numero:02d}" for numero in range(inicio, inicio + 3)]


def parse_mes(mes_str):
    ano, mes = mes_str.split("-")
    return int(ano), int(mes)


def primeiro_dia(ano, mes):
    return date(ano, mes, 1)


def ultimo_dia(ano, mes):
    return date(ano, mes, monthrange(ano, mes)[1])


def janela_12_meses_anteriores(ano, mes):
    """Doze meses anteriores ao período de apuração (não inclui o mês vigente)."""
    inicio_apuracao = primeiro_dia(ano, mes)
    inicio_janela = _avancar_meses(inicio_apuracao, -12)
    return inicio_janela, inicio_apuracao


def meses_de_atividade(data_inicio, inicio_janela, fim_janela):
    if not data_inicio:
        return 12, inicio_janela
    if isinstance(data_inicio, datetime):
        data_inicio = data_inicio.date()
    inicio_real = max(data_inicio.replace(day=1), inicio_janela)
    if inicio_real >= fim_janela:
        return 0, inicio_real
    n = 0
    cursor = inicio_real
    while cursor < fim_janela:
        n += 1
        cursor = _avancar_meses(cursor, 1)
    return n, inicio_real


def annualizar(valor_acumulado, meses):
    if meses <= 0:
        return 0.0, False
    if meses >= 12:
        return float(valor_acumulado), False
    return (float(valor_acumulado) / meses) * 12.0, True


def localizar_faixa(rbt12, tabela):
    if rbt12 <= 0:
        return tabela[0]
    for faixa in tabela:
        if rbt12 <= faixa["limite"]:
            return faixa
    return tabela[-1]


def aliquota_efetiva(rbt12, faixa):
    if rbt12 <= 0:
        return 0.0
    return ((rbt12 * faixa["aliquota"]) - faixa["deduzir"]) / rbt12


def folha_mensal_fator_r(salario_base):
    """
    Massa salarial mensal para o Fator R:
    salários + 13º + férias (1/3) + encargos trabalhistas/previdenciários.
    """
    salario = float(salario_base or 0.0)
    fgts = salario * 0.08
    provisao_13 = salario / 12.0
    ferias_terco = (salario + (salario / 3.0)) / 12.0
    reflexos_fgts = (provisao_13 + ferias_terco) * 0.08
    inss_patronal = salario * 0.20
    rat = salario * 0.01
    sistema_s = salario * 0.058
    encargos = fgts + provisao_13 + ferias_terco + reflexos_fgts + inss_patronal + rat + sistema_s
    return {
        "salario": salario,
        "fgts": fgts,
        "provisao_13": provisao_13,
        "ferias_terco": ferias_terco,
        "reflexos_fgts": reflexos_fgts,
        "inss_patronal": inss_patronal,
        "rat": rat,
        "sistema_s": sistema_s,
        "encargos": encargos,
        "total": salario + encargos,
    }


def apurar_simples(
    rbt_acumulado,
    fs_acumulado,
    meses_atividade,
    receita_mes,
    annualizado=False,
    acrescimos_mora=0.0,
    atividade=ATIVIDADE_ENSINO,
    folha_mes=0.0,
):
    """DAS sobre a receita bruta. `acrescimos_mora` só é informado na tela:
    juros/multa por atraso não compõem a receita bruta (Res. CGSN 140/2018, art. 2º, § 5º, II).

    Primeiro mês de atividade (sem receita nos meses anteriores): a receita do próprio mês
    vezes 12 define a faixa (LC 123/2006, art. 18, § 2º)."""
    atividade = normalizar_atividade_simples(atividade)
    rbt12, rbt_annualizada = annualizar(rbt_acumulado, meses_atividade)
    fs12, fs_annualizada = annualizar(fs_acumulado, meses_atividade)
    annualizado = annualizado or rbt_annualizada or fs_annualizada
    inicio_atividade = False
    if rbt12 <= 0 and float(receita_mes or 0) > 0:
        rbt12 = float(receita_mes) * 12.0
        fs12 = float(folha_mes or 0) * 12.0
        annualizado = True
        inicio_atividade = True

    fator_r = (fs12 / rbt12) if rbt12 > 0 else 0.0
    fator_r_aplicavel = atividade == ATIVIDADE_FATOR_R
    usa_anexo_iii = (not fator_r_aplicavel) or fator_r >= FATOR_R_MINIMO
    anexo = "III" if usa_anexo_iii else "V"
    tabela = ANEXO_III if usa_anexo_iii else ANEXO_V
    faixa = localizar_faixa(rbt12, tabela)
    aliq = aliquota_efetiva(rbt12, faixa)
    das = float(receita_mes) * aliq
    extrapolou = rbt12 > LIMITE_SIMPLES

    return {
        "rbt_acumulado": float(rbt_acumulado or 0.0),
        "fs_acumulado": float(fs_acumulado or 0.0),
        "meses_atividade": meses_atividade,
        "annualizado": annualizado,
        "rbt12": rbt12,
        "fs12": fs12,
        "fator_r": fator_r,
        "fator_r_pct": min(fator_r * 100.0, 100.0),
        "fator_r_acima_100": fator_r > 1.0,
        "fator_r_aplicavel": fator_r_aplicavel,
        "atividade": atividade,
        "inicio_atividade": inicio_atividade,
        "anexo": anexo,
        "usa_anexo_iii": usa_anexo_iii,
        "faixa": faixa["faixa"],
        "aliquota_nominal": faixa["aliquota"],
        "parcela_deduzir": faixa["deduzir"],
        "aliquota_efetiva": aliq,
        "aliquota_efetiva_pct": aliq * 100.0,
        "receita_mes": float(receita_mes or 0.0),
        "acrescimos_mora": float(acrescimos_mora or 0.0),
        "das": das,
        "extrapolou_limite": extrapolou,
    }


def nome_regime(codigo):
    mapa = {
        "simples_nacional": "Simples Nacional",
        "lucro_presumido": "Lucro Presumido",
        "lucro_real": "Lucro Real",
    }
    return mapa.get(codigo, codigo or "Não informado")


def br_money(valor):
    numero = f"{float(valor or 0):,.2f}"
    return "R$ " + numero.replace(",", "X").replace(".", ",").replace("X", ".")


# Lucro Presumido cumulativo: PIS 0,65% e COFINS 3% sobre a receita bruta.
# Lucro Real não-cumulativo: PIS 1,65% e COFINS 7,6% (com créditos).
PIS_PRESUMIDO = 0.0065
COFINS_PRESUMIDO = 0.03
PIS_LUCRO_REAL = 0.0165
COFINS_LUCRO_REAL = 0.076


def apurar_pis_cofins(receita_mes, regime, acrescimos_mora=0.0):
    receita = float(receita_mes or 0.0)
    mora = max(0.0, float(acrescimos_mora or 0.0))
    base = receita + mora
    if regime == "lucro_real":
        pis_aliq, cofins_aliq = PIS_LUCRO_REAL, COFINS_LUCRO_REAL
        regime_pis = "não-cumulativo"
    else:
        pis_aliq, cofins_aliq = PIS_PRESUMIDO, COFINS_PRESUMIDO
        regime_pis = "cumulativo"
    pis = base * pis_aliq
    cofins = base * cofins_aliq
    return {
        "receita_mes": receita,
        "acrescimos_mora": mora,
        "base": base,
        "pis_aliquota": pis_aliq,
        "cofins_aliquota": cofins_aliq,
        "pis": pis,
        "cofins": cofins,
        "total": pis + cofins,
        "regime_pis": regime_pis,
    }


# Serviços educacionais no Lucro Presumido (demonstrativo da escola)
PRESUNCAO_SERVICOS = 0.32
ISS_ESTIMADO = 0.05
CSLL_ALIQUOTA = 0.09
IRPJ_ALIQUOTA = 0.15
IRPJ_ADICIONAL_ALIQUOTA = 0.10
IRPJ_ADICIONAL_LIMITE_TRIMESTRE = 60_000.00


def acrescimos_recebimento(valor, juros_percentual, multa_valor):
    """Juros são percentuais sobre a mensalidade. A multa é um valor fixo."""
    principal = round(float(valor or 0), 2)
    try:
        percentual = float(juros_percentual or 0)
    except (TypeError, ValueError):
        percentual = 0.0
    try:
        multa = float(multa_valor or 0)
    except (TypeError, ValueError):
        multa = 0.0
    if percentual < 0:
        percentual = 0.0
    if multa < 0:
        multa = 0.0
    juros_valor = round(principal * percentual / 100.0, 2)
    multa = round(multa, 2)
    return {
        "juros_percentual": round(percentual, 4),
        "juros_valor": juros_valor,
        "multa_valor": multa,
        "total": round(principal + juros_valor + multa, 2),
    }


def apurar_lucro_presumido(
    receita_mes,
    itens_folha,
    receita_trimestre=None,
    acrescimos_mora=0.0,
    acrescimos_trimestre=None,
):
    """
    Tributos sobre o faturamento + encargos cheios da folha CLT.
    Base de IRPJ/CSLL: 32% da receita bruta (serviços educacionais)
    + 100% dos juros/multa de mora recebidos (Lei 9.430/96, art. 25, II).
    PIS/COFINS cumulativos também alcançam juros/multa (STJ, Tema 1.237).
    ISS estimado em 5% só sobre o preço do serviço.
    Adicional de IRPJ (10%) só se a base trimestral superar R$ 60.000,00.
    """
    receita = float(receita_mes or 0.0)
    mora = max(0.0, float(acrescimos_mora or 0.0))
    pis = (receita + mora) * PIS_PRESUMIDO
    cofins = (receita + mora) * COFINS_PRESUMIDO
    iss = receita * ISS_ESTIMADO
    base_servicos = receita * PRESUNCAO_SERVICOS
    base_presumida = base_servicos + mora
    csll = base_presumida * CSLL_ALIQUOTA
    irpj = base_presumida * IRPJ_ALIQUOTA
    receita_tri = float(receita * 3.0 if receita_trimestre is None else receita_trimestre)
    mora_tri = float(mora * 3.0 if acrescimos_trimestre is None else acrescimos_trimestre)
    base_trimestral = receita_tri * PRESUNCAO_SERVICOS + mora_tri
    irpj_adicional_trimestre = 0.0
    if base_trimestral > IRPJ_ADICIONAL_LIMITE_TRIMESTRE:
        irpj_adicional_trimestre = (base_trimestral - IRPJ_ADICIONAL_LIMITE_TRIMESTRE) * IRPJ_ADICIONAL_ALIQUOTA
    irpj_adicional = irpj_adicional_trimestre / 3.0

    tributos = pis + cofins + iss + csll + irpj + irpj_adicional
    folha = [dict(item) for item in (itens_folha or [])]
    folha_total = sum(float(item.get("total") or 0) for item in folha)
    salario_bruto = sum(float(item.get("salario") or 0) for item in folha)
    entradas = receita + mora
    caixa = entradas - tributos - folha_total
    carga_pct = ((tributos + folha_total) / entradas * 100.0) if entradas else 0.0

    return {
        "receita_mes": receita,
        "acrescimos_mora": mora,
        "acrescimos_trimestre": mora_tri,
        "base_pis_cofins": receita + mora,
        "pis": pis,
        "cofins": cofins,
        "iss": iss,
        "base_servicos": base_servicos,
        "base_presumida": base_presumida,
        "csll": csll,
        "irpj": irpj,
        "receita_trimestre": receita_tri,
        "base_presumida_trimestre": base_trimestral,
        "irpj_adicional": irpj_adicional,
        "irpj_adicional_trimestre": irpj_adicional_trimestre,
        "aplica_adicional_irpj": irpj_adicional_trimestre > 0,
        "tributos": tributos,
        "folha": folha,
        "salario_bruto": salario_bruto,
        "folha_total": folha_total,
        "caixa_restante": caixa,
        "carga_pct": carga_pct,
    }
