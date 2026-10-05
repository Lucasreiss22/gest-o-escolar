"""Apuração da empresa (raiz de CNPJ): Simples, Lucro Presumido e Lucro Real, com rateio entre unidades.

Funções puras: recebem números e devolvem números. Quem lê o banco é carga_tributos.py.
Calcula com precisão total e arredonda só o valor final de cada tributo (ROUND_HALF_UP).
"""

from decimal import ROUND_HALF_UP, Decimal

from simples_nacional import competencia_add, janela_competencias
from tributacao import ATIVIDADE_ENSINO, LIMITE_SIMPLES, apurar_simples

SUBLIMITE_SIMPLES = 3_600_000.00

IRPJ_ALIQUOTA = Decimal("0.15")
IRPJ_ADICIONAL_ALIQUOTA = Decimal("0.10")
IRPJ_ADICIONAL_LIMITE_MES = Decimal("20000")
CSLL_ALIQUOTA = Decimal("0.09")
PIS_CUMULATIVO = Decimal("0.0065")
COFINS_CUMULATIVO = Decimal("0.03")
PIS_NAO_CUMULATIVO = Decimal("0.0165")
COFINS_NAO_CUMULATIVO = Decimal("0.076")
# Receitas financeiras no regime não cumulativo (Decreto 8.426/2015).
PIS_RECEITA_FINANCEIRA = Decimal("0.0065")
COFINS_RECEITA_FINANCEIRA = Decimal("0.04")
# Compensação de prejuízo fiscal e base negativa (Lei 9.065/1995, arts. 15 e 16).
LIMITE_COMPENSACAO = Decimal("0.30")

PRESUNCAO_PADRAO_PCT = 32.0
ISS_PADRAO_PCT = 5.0
ISS_MINIMO_PCT = 2.0

# LC 224/2025: +10% nos percentuais de presunção sobre a receita bruta anual acima de R$ 5 milhões,
# com limite proporcional por mês e ajuste nos períodos seguintes do mesmo ano.
LC224_LIMITE_ANUAL = Decimal("5000000")
LC224_ACRESCIMO = Decimal("0.10")
LC224_INICIO_IRPJ = "2026-01"
LC224_INICIO_CSLL = "2026-04"

MODO_PIS_CUMULATIVO_ENSINO = "cumulativo_ensino"
MODO_PIS_NAO_CUMULATIVO = "nao_cumulativo"
PERIODO_TRIMESTRAL = "trimestral"
PERIODO_ANUAL_ESTIMATIVA = "anual_estimativa"
ESTIMATIVA_BALANCETE = "balancete"
ESTIMATIVA_RECEITA = "receita"

_CENTAVO = Decimal("0.01")


def _d(valor):
    if isinstance(valor, Decimal):
        return valor
    try:
        return Decimal(str(valor if valor is not None else 0))
    except Exception:
        return Decimal("0")


def _q(valor):
    return _d(valor).quantize(_CENTAVO, rounding=ROUND_HALF_UP)


def arred(valor):
    return float(_q(valor))


def _pct(valor, padrao):
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return _d(padrao) / 100
    return _d(numero) / 100


def ratear(valor_total, partes):
    """`partes`: [(chave, peso)], a primeira é a matriz. Cada parte arredondada; a sobra de centavos fica na matriz."""
    partes = list(partes or [])
    if not partes:
        return []
    total = _q(valor_total)
    pesos = [max(_d(peso), Decimal("0")) for _chave, peso in partes]
    soma = sum(pesos)
    if soma <= 0:
        return [(partes[0][0], float(total))] + [(chave, 0.0) for chave, _p in partes[1:]]
    valores = [_q(total * peso / soma) for peso in pesos]
    valores[0] += total - sum(valores)
    return [(chave, float(valor)) for (chave, _p), valor in zip(partes, valores)]


def validar_percentual(valor, minimo=0.0, maximo=100.0):
    try:
        numero = float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return None
    if numero != numero or numero < minimo or numero > maximo:
        return None
    return numero


# ---------------------------------------------------------------- Simples Nacional

def mes_inicio_empresa(data_abertura, receitas_por_unidade=None, primeiras=None):
    """Abertura da matriz (Dados da empresa) ou a 1ª competência com receita de qualquer unidade.
    Receita anterior à data de abertura cadastrada puxa o início para trás (a data estaria errada).
    `primeiras`: 1ª competência de cada unidade, quando já calculada sobre o histórico inteiro."""
    comps = [
        comp for meses in (receitas_por_unidade or {}).values()
        for comp, valor in (meses or {}).items() if float(valor or 0) > 0
    ] + [comp for comp in (primeiras or []) if comp]
    primeira = min(comps) if comps else None
    abertura = None
    if data_abertura:
        abertura = data_abertura.strftime("%Y-%m") if hasattr(data_abertura, "strftime") else str(data_abertura)[:7]
    if abertura and primeira:
        return min(abertura, primeira)
    return abertura or primeira


def apurar_simples_empresa(
    receitas_por_unidade_por_mes,
    mes_apuracao,
    inicio_empresa,
    atividade=ATIVIDADE_ENSINO,
    folha_por_mes=None,
    receitas_mes=None,
    ordem=None,
):
    """Um DAS para a empresa: RBT12 com a receita de todas as unidades e anualização pelo início da empresa.

    `receitas_por_unidade_por_mes`: {unidade: {"AAAA-MM": receita}}; `folha_por_mes`: idem, para o Fator R.
    `receitas_mes`: {unidade: receita do mês} quando a base do mês difere da usada na RBT12.
    `ordem`: unidades na ordem de exibição, matriz primeiro (recebe a sobra de centavos do rateio).
    """
    receitas = receitas_por_unidade_por_mes or {}
    folhas = folha_por_mes or {}
    unidades = list(ordem or receitas.keys())
    janela = janela_competencias(mes_apuracao)
    validos = [comp for comp in janela if not inicio_empresa or comp >= inicio_empresa]
    rbt_acumulado = sum(float((receitas.get(u) or {}).get(c) or 0) for u in unidades for c in validos)
    fs_acumulado = sum(float((folhas.get(u) or {}).get(c) or 0) for u in unidades for c in validos)
    if receitas_mes is None:
        receitas_mes = {u: float((receitas.get(u) or {}).get(mes_apuracao) or 0) for u in unidades}
    receita_mes = sum(float(receitas_mes.get(u) or 0) for u in unidades)
    folha_mes = sum(float((folhas.get(u) or {}).get(mes_apuracao) or 0) for u in unidades)
    apuracao = apurar_simples(
        rbt_acumulado, fs_acumulado, len(validos), receita_mes,
        atividade=atividade, folha_mes=folha_mes,
    )
    apuracao["meses_atividade"] = len(validos)
    apuracao["inicio_empresa"] = inicio_empresa
    apuracao["receita_mes_empresa"] = receita_mes
    apuracao["das_total"] = arred(_d(receita_mes) * _d(apuracao["aliquota_efetiva"]))
    apuracao["das"] = apuracao["das_total"]
    partes = ratear(apuracao["das_total"], [(u, receitas_mes.get(u) or 0) for u in unidades])
    apuracao["rateio"] = [
        {"unidade_id": u, "receita_mes": float(receitas_mes.get(u) or 0), "das": das}
        for u, das in partes
    ]
    apuracao["linhas_empresa"] = [
        {
            "competencia": comp,
            "receita_bruta": sum(float((receitas.get(u) or {}).get(comp) or 0) for u in unidades),
            "folha_encargos": sum(float((folhas.get(u) or {}).get(comp) or 0) for u in unidades),
            "entra_rbt12": comp in validos,
        }
        for comp in janela
    ]
    apuracao["acima_sublimite"] = apuracao["rbt12"] > SUBLIMITE_SIMPLES
    apuracao["extrapolou_limite"] = apuracao["rbt12"] > LIMITE_SIMPLES
    return apuracao


def avisos_limites_simples(rbt12_competencia):
    """Sublimite e limite do Simples pela receita auferida (competência), mesmo para quem está no caixa."""
    avisos = []
    if rbt12_competencia > LIMITE_SIMPLES:
        avisos.append(
            "A receita dos últimos 12 meses pelo faturamento passou de R$ 4,8 milhões, limite do Simples "
            "(LC 123/2006, art. 3º). Confirme com o contador a exclusão."
        )
    elif rbt12_competencia > SUBLIMITE_SIMPLES:
        avisos.append(
            "A receita dos últimos 12 meses pelo faturamento passou do sublimite de R$ 3,6 milhões: "
            "ISS e ICMS saem do DAS (LC 123/2006, art. 19). Confirme com o contador."
        )
    return avisos


# ---------------------------------------------------------------- Lucro Presumido

def _meses_entre(inicio, fim):
    if fim < inicio:
        return []
    meses, comp = [], inicio
    while comp <= fim:
        meses.append(comp)
        comp = competencia_add(comp, 1)
    return meses


def excedente_lc224(receitas_por_comp, ate_comp, inicio_vigencia):
    """Receita do ano (desde a vigência) acima do limite proporcional acumulado até `ate_comp`."""
    if not ate_comp:
        return Decimal("0")
    inicio = max(f"{ate_comp[:4]}-01", inicio_vigencia)
    meses = _meses_entre(inicio, ate_comp)
    if not meses:
        return Decimal("0")
    receita = sum(_d((receitas_por_comp or {}).get(c)) for c in meses)
    limite = LC224_LIMITE_ANUAL * len(meses) / 12
    return max(receita - limite, Decimal("0"))


def _excedente_no_periodo(receitas_ano, competencias, inicio_vigencia):
    if not competencias:
        return Decimal("0")
    antes = competencia_add(competencias[0], -1)
    ate = excedente_lc224(receitas_ano, competencias[-1], inicio_vigencia)
    if antes[:4] != competencias[-1][:4]:
        return ate
    return max(ate - excedente_lc224(receitas_ano, antes, inicio_vigencia), Decimal("0"))


def _presumido_acumulado(receitas, demais, competencias, p_irpj, p_csll, aplicar_lc224, receitas_ano):
    receita = sum(_d(v) for v in receitas)
    outras = sum(_d(v) for v in demais)
    exc_irpj = exc_csll = Decimal("0")
    if aplicar_lc224 and competencias:
        ano = dict(receitas_ano or {})
        for comp, valor in zip(competencias, receitas):
            ano[comp] = valor
        exc_irpj = _excedente_no_periodo(ano, competencias, LC224_INICIO_IRPJ)
        exc_csll = _excedente_no_periodo(ano, competencias, LC224_INICIO_CSLL)
    base_irpj = receita * p_irpj + exc_irpj * p_irpj * LC224_ACRESCIMO + outras
    base_csll = receita * p_csll + exc_csll * p_csll * LC224_ACRESCIMO + outras
    meses = len(receitas)
    adicional = max(base_irpj - IRPJ_ADICIONAL_LIMITE_MES * meses, Decimal("0")) * IRPJ_ADICIONAL_ALIQUOTA
    return {
        "receita": receita,
        "demais": outras,
        "excedente_lc224_irpj": exc_irpj,
        "excedente_lc224_csll": exc_csll,
        "base_irpj": base_irpj,
        "base_csll": base_csll,
        "irpj": _q(base_irpj * IRPJ_ALIQUOTA),
        "adicional": _q(adicional),
        "csll": _q(base_csll * CSLL_ALIQUOTA),
    }


def apurar_presumido_periodo(
    receitas_mes,
    demais_receitas_mes=None,
    presuncao_irpj=PRESUNCAO_PADRAO_PCT,
    presuncao_csll=PRESUNCAO_PADRAO_PCT,
    iss_pct=ISS_PADRAO_PCT,
    incluir_mora=True,
    lc224=None,
    receita_acumulada_ano_antes=None,
    competencias=None,
):
    """Trimestre do Lucro Presumido até o mês de apuração (1 a 3 meses em `receitas_mes`).

    IRPJ/CSLL: provisão do mês = acumulado do trimestre até o mês − acumulado até o mês anterior,
    então as provisões somam exatamente o devido no trimestre. PIS/COFINS/ISS são mensais.
    `lc224`: True/False; `receita_acumulada_ano_antes`: {"AAAA-MM": receita} dos meses do ano antes do trimestre.
    """
    receitas = [_d(v) for v in (receitas_mes or [])]
    demais = [_d(v) for v in (demais_receitas_mes or [])] + [Decimal("0")] * len(receitas)
    demais = demais[:len(receitas)]
    p_irpj = _pct(presuncao_irpj, PRESUNCAO_PADRAO_PCT)
    p_csll = _pct(presuncao_csll, PRESUNCAO_PADRAO_PCT)
    iss = _pct(iss_pct, ISS_PADRAO_PCT)
    comps = list(competencias or [])
    aplicar = bool(lc224) and len(comps) == len(receitas)
    receitas_ano = receita_acumulada_ano_antes if isinstance(receita_acumulada_ano_antes, dict) else {}

    meses = []
    anterior = {"irpj": Decimal("0"), "adicional": Decimal("0"), "csll": Decimal("0")}
    acumulado = None
    for i in range(len(receitas)):
        acumulado = _presumido_acumulado(
            receitas[:i + 1], demais[:i + 1], comps[:i + 1] if aplicar else None,
            p_irpj, p_csll, aplicar, receitas_ano,
        )
        base_pis = receitas[i] + (demais[i] if incluir_mora else Decimal("0"))
        meses.append({
            "competencia": comps[i] if i < len(comps) else None,
            "receita": float(receitas[i]),
            "demais": float(demais[i]),
            "pis": arred(base_pis * PIS_CUMULATIVO),
            "cofins": arred(base_pis * COFINS_CUMULATIVO),
            "iss": arred(receitas[i] * iss),
            "irpj": float(acumulado["irpj"] - anterior["irpj"]),
            "adicional": float(acumulado["adicional"] - anterior["adicional"]),
            "csll": float(acumulado["csll"] - anterior["csll"]),
        })
        anterior = {k: acumulado[k] for k in anterior}

    if acumulado is None:
        acumulado = _presumido_acumulado([], [], None, p_irpj, p_csll, False, {})
    base_pis_tri = acumulado["receita"] + (acumulado["demais"] if incluir_mora else Decimal("0"))
    trimestre = {
        "receita": float(acumulado["receita"]),
        "demais": float(acumulado["demais"]),
        "base_irpj": arred(acumulado["base_irpj"]),
        "base_csll": arred(acumulado["base_csll"]),
        "excedente_lc224_irpj": arred(acumulado["excedente_lc224_irpj"]),
        "excedente_lc224_csll": arred(acumulado["excedente_lc224_csll"]),
        "irpj": float(acumulado["irpj"]),
        "adicional": float(acumulado["adicional"]),
        "csll": float(acumulado["csll"]),
        "pis": arred(base_pis_tri * PIS_CUMULATIVO),
        "cofins": arred(base_pis_tri * COFINS_CUMULATIVO),
        "iss": arred(acumulado["receita"] * iss),
    }
    mes = meses[-1] if meses else {k: 0.0 for k in ("receita", "demais", "pis", "cofins", "iss", "irpj", "adicional", "csll")}
    return {
        "meses": meses,
        "mes": mes,
        "trimestre": trimestre,
        "presuncao_irpj_pct": float(p_irpj * 100),
        "presuncao_csll_pct": float(p_csll * 100),
        "iss_pct": float(iss * 100),
        "incluir_mora": bool(incluir_mora),
        "lc224": aplicar,
    }


# ---------------------------------------------------------------- Lucro Real

def apurar_lucro_real_periodo(
    lair,
    adicoes_irpj=0,
    exclusoes_irpj=0,
    adicoes_csll=0,
    exclusoes_csll=0,
    prejuizo_acumulado=0,
    base_negativa_acumulada=0,
    meses_periodo=3,
):
    """IRPJ/CSLL sobre o lucro real, com compensação limitada a 30% e saldos separados por tributo."""
    lair_d = _d(lair)
    prejuizo = max(_d(prejuizo_acumulado), Decimal("0"))
    base_negativa = max(_d(base_negativa_acumulada), Decimal("0"))

    def _base(ajustado, saldo):
        if ajustado > 0:
            compensa = min(saldo, ajustado * LIMITE_COMPENSACAO)
            return ajustado, compensa, ajustado - compensa, saldo - compensa
        return ajustado, Decimal("0"), Decimal("0"), saldo - ajustado

    aj_irpj, comp_irpj, base_irpj, novo_prejuizo = _base(lair_d + _d(adicoes_irpj) - _d(exclusoes_irpj), prejuizo)
    aj_csll, comp_csll, base_csll, nova_base_neg = _base(lair_d + _d(adicoes_csll) - _d(exclusoes_csll), base_negativa)
    meses = max(int(meses_periodo or 1), 1)
    adicional = max(base_irpj - IRPJ_ADICIONAL_LIMITE_MES * meses, Decimal("0")) * IRPJ_ADICIONAL_ALIQUOTA
    irpj = _q(base_irpj * IRPJ_ALIQUOTA)
    adicional = _q(adicional)
    csll = _q(base_csll * CSLL_ALIQUOTA)
    return {
        "lair": arred(lair_d),
        "lucro_ajustado_irpj": arred(aj_irpj),
        "compensacao_irpj": arred(comp_irpj),
        "base_irpj": arred(base_irpj),
        "irpj": float(irpj),
        "adicional": float(adicional),
        "lucro_ajustado_csll": arred(aj_csll),
        "compensacao_csll": arred(comp_csll),
        "base_csll": arred(base_csll),
        "csll": float(csll),
        "total": float(irpj + adicional + csll),
        "novo_prejuizo": arred(novo_prejuizo),
        "nova_base_negativa": arred(nova_base_neg),
        "prejuizo": aj_irpj <= 0,
        "meses_periodo": meses,
    }


def provisao_lucro_real(lairs_mes, ajustes=None, prejuizo_acumulado=0, base_negativa_acumulada=0, modo="trimestral"):
    """Provisão mensal do Lucro Real a partir do LAIR de cada mês do período (trimestre ou ano).

    Trimestral: devido acumulado até o mês − devido até o mês anterior (as provisões fecham com o trimestre).
    Balancete (anual por estimativa): devido acumulado − já pago, nunca negativo.
    `ajustes`: [{"adicoes_irpj", "exclusoes_irpj", "adicoes_csll", "exclusoes_csll"}] por mês.
    """
    ajustes = list(ajustes or [])
    pago = {"irpj": Decimal("0"), "adicional": Decimal("0"), "csll": Decimal("0")}
    meses = []
    acumulado = None
    soma = {"lair": Decimal("0"), "ai": Decimal("0"), "ei": Decimal("0"), "ac": Decimal("0"), "ec": Decimal("0")}
    for i, lair in enumerate(lairs_mes or []):
        aj = ajustes[i] if i < len(ajustes) else {}
        soma["lair"] += _d(lair)
        soma["ai"] += _d(aj.get("adicoes_irpj"))
        soma["ei"] += _d(aj.get("exclusoes_irpj"))
        soma["ac"] += _d(aj.get("adicoes_csll"))
        soma["ec"] += _d(aj.get("exclusoes_csll"))
        acumulado = apurar_lucro_real_periodo(
            soma["lair"], soma["ai"], soma["ei"], soma["ac"], soma["ec"],
            prejuizo_acumulado, base_negativa_acumulada, i + 1,
        )
        mes = {}
        for chave in pago:
            devido = _d(acumulado[chave])
            if modo == ESTIMATIVA_BALANCETE:
                valor = max(devido - pago[chave], Decimal("0"))
            else:
                valor = devido - pago[chave]
            mes[chave] = float(valor)
            pago[chave] += valor
        mes["lair"] = arred(lair)
        mes["total"] = arred(sum(_d(mes[k]) for k in ("irpj", "adicional", "csll")))
        meses.append(mes)
    if acumulado is None:
        acumulado = apurar_lucro_real_periodo(0, prejuizo_acumulado=prejuizo_acumulado,
                                              base_negativa_acumulada=base_negativa_acumulada, meses_periodo=1)
    return {"meses": meses, "mes": meses[-1] if meses else {"irpj": 0.0, "adicional": 0.0, "csll": 0.0, "total": 0.0, "lair": 0.0},
            "periodo": acumulado}


def apurar_pis_cofins_real(
    receita_ensino,
    receita_outras=0,
    receitas_financeiras=0,
    creditos_base=0,
    modo=MODO_PIS_CUMULATIVO_ENSINO,
    incluir_mora=True,
):
    """PIS/COFINS no Lucro Real.

    Ensino regular (infantil, fundamental, médio e superior) fica no cumulativo mesmo no Lucro Real
    (Lei 10.833/2003, art. 10, XIV, e art. 15, V). Outras receitas seguem o não cumulativo, com créditos.
    A folha nunca gera crédito.
    """
    ensino = _d(receita_ensino)
    outras = _d(receita_outras)
    financeiras = max(_d(receitas_financeiras), Decimal("0"))
    creditos = max(_d(creditos_base), Decimal("0"))
    if modo == MODO_PIS_NAO_CUMULATIVO:
        base_nc = ensino + outras
        base_cum = Decimal("0")
        fin_pis, fin_cofins = financeiras * PIS_RECEITA_FINANCEIRA, financeiras * COFINS_RECEITA_FINANCEIRA
    else:
        base_nc = outras
        base_cum = ensino + (financeiras if incluir_mora else Decimal("0"))
        fin_pis = fin_cofins = Decimal("0")
    credito_pis = creditos * PIS_NAO_CUMULATIVO if base_nc > 0 else Decimal("0")
    credito_cofins = creditos * COFINS_NAO_CUMULATIVO if base_nc > 0 else Decimal("0")
    pis = max(base_cum * PIS_CUMULATIVO + base_nc * PIS_NAO_CUMULATIVO - credito_pis, Decimal("0")) + fin_pis
    cofins = max(base_cum * COFINS_CUMULATIVO + base_nc * COFINS_NAO_CUMULATIVO - credito_cofins, Decimal("0")) + fin_cofins
    return {
        "modo": modo,
        "base_cumulativa": arred(base_cum),
        "base_nao_cumulativa": arred(base_nc),
        "credito_pis": arred(credito_pis),
        "credito_cofins": arred(credito_cofins),
        "pis": arred(pis),
        "cofins": arred(cofins),
        "total": arred(_q(pis) + _q(cofins)),
    }


AVISO_REAL_CAIXA = "Lucro Real exige regime de competência; o regime de caixa foi ignorado nos tributos."


def regime_apuracao_efetivo(regime_tributario, regime_apuracao):
    """(regime usado nos tributos, aviso). O Lucro Real é sempre por competência (regime contábil)."""
    apuracao = "caixa" if str(regime_apuracao or "").strip().lower() in ("caixa", "regime_de_caixa") else "competencia"
    if regime_tributario == "lucro_real" and apuracao == "caixa":
        return "competencia", AVISO_REAL_CAIXA
    return apuracao, None


def ratear_por_lucro(valor_total, lairs, ordem):
    """IRPJ/CSLL da empresa no Lucro Real: proporcional ao LAIR positivo; unidade com prejuízo recebe 0."""
    return ratear(valor_total, [(u, max(float(lairs.get(u) or 0), 0.0)) for u in ordem])
