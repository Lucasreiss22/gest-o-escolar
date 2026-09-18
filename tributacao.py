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
):
    rbt12, rbt_annualizada = annualizar(rbt_acumulado, meses_atividade)
    fs12, fs_annualizada = annualizar(fs_acumulado, meses_atividade)
    annualizado = annualizado or rbt_annualizada or fs_annualizada

    fator_r = (fs12 / rbt12) if rbt12 > 0 else 0.0
    usa_anexo_iii = fator_r >= FATOR_R_MINIMO
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
        "fator_r_pct": fator_r * 100.0,
        "anexo": anexo,
        "usa_anexo_iii": usa_anexo_iii,
        "faixa": faixa["faixa"],
        "aliquota_nominal": faixa["aliquota"],
        "parcela_deduzir": faixa["deduzir"],
        "aliquota_efetiva": aliq,
        "aliquota_efetiva_pct": aliq * 100.0,
        "receita_mes": float(receita_mes or 0.0),
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


def apurar_pis_cofins(receita_mes, regime):
    receita = float(receita_mes or 0.0)
    if regime == "lucro_real":
        pis_aliq, cofins_aliq = PIS_LUCRO_REAL, COFINS_LUCRO_REAL
        regime_pis = "não-cumulativo"
    else:
        pis_aliq, cofins_aliq = PIS_PRESUMIDO, COFINS_PRESUMIDO
        regime_pis = "cumulativo"
    pis = receita * pis_aliq
    cofins = receita * cofins_aliq
    return {
        "receita_mes": receita,
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


def apurar_lucro_presumido(receita_mes, itens_folha):
    """
    Tributos sobre o faturamento + encargos cheios da folha CLT.
    Base de IRPJ/CSLL: 32% da receita bruta (serviços educacionais).
    ISS estimado em 5%. Adicional de IRPJ (10%) só se o lucro presumido
    trimestral superar R$ 60.000,00.
    """
    receita = float(receita_mes or 0.0)
    pis = receita * PIS_PRESUMIDO
    cofins = receita * COFINS_PRESUMIDO
    iss = receita * ISS_ESTIMADO
    base_presumida = receita * PRESUNCAO_SERVICOS
    csll = base_presumida * CSLL_ALIQUOTA
    irpj = base_presumida * IRPJ_ALIQUOTA
    base_trimestral = base_presumida * 3.0
    irpj_adicional = 0.0
    if base_trimestral > IRPJ_ADICIONAL_LIMITE_TRIMESTRE:
        irpj_adicional = ((base_trimestral - IRPJ_ADICIONAL_LIMITE_TRIMESTRE) * IRPJ_ADICIONAL_ALIQUOTA) / 3.0

    tributos = pis + cofins + iss + csll + irpj + irpj_adicional
    folha = [dict(item) for item in (itens_folha or [])]
    folha_total = sum(float(item.get("total") or 0) for item in folha)
    salario_bruto = sum(float(item.get("salario") or 0) for item in folha)
    caixa = receita - tributos - folha_total
    carga_pct = ((tributos + folha_total) / receita * 100.0) if receita else 0.0

    return {
        "receita_mes": receita,
        "pis": pis,
        "cofins": cofins,
        "iss": iss,
        "base_presumida": base_presumida,
        "csll": csll,
        "irpj": irpj,
        "irpj_adicional": irpj_adicional,
        "aplica_adicional_irpj": irpj_adicional > 0,
        "tributos": tributos,
        "folha": folha,
        "salario_bruto": salario_bruto,
        "folha_total": folha_total,
        "caixa_restante": caixa,
        "carga_pct": carga_pct,
    }
