"""Cálculos de folha: CLT mensalista, horista, PJ e RPA."""

from calendar import monthrange
from datetime import date, datetime

from tributacao import br_money

# Tabelas por vigência: a competência da folha escolhe a tabela (a mais recente com início <= competência).
# INSS do empregado — Portarias Interministeriais MPS/MF de 2025 e 2026 (progressiva).
TABELAS_INSS = (
    (date(2025, 1, 1), ((1518.00, 0.075), (2793.88, 0.09), (4190.83, 0.12), (8157.41, 0.14))),
    (date(2026, 1, 1), ((1621.00, 0.075), (2902.84, 0.09), (4354.27, 0.12), (8475.55, 0.14))),
)

# IRRF mensal: (faixas (limite, alíquota, dedução), desconto simplificado mensal).
# Fev/2024: Lei 14.848/2024. Mai/2025: Lei 15.191/2025.
TABELAS_IRRF = (
    (
        date(2024, 2, 1),
        (
            (2259.20, 0.0, 0.0),
            (2826.65, 0.075, 169.44),
            (3751.05, 0.15, 381.44),
            (4664.68, 0.225, 662.77),
            (10**12, 0.275, 896.00),
        ),
        564.80,
    ),
    (
        date(2025, 5, 1),
        (
            (2428.80, 0.0, 0.0),
            (2826.65, 0.075, 182.16),
            (3751.05, 0.15, 394.16),
            (4664.68, 0.225, 675.49),
            (10**12, 0.275, 908.73),
        ),
        607.20,
    ),
)

# Redução do IRRF mensal da Lei 15.270/2025, a partir de jan/2026, sobre os rendimentos tributáveis do mês:
# até 5.000 o imposto zera; de 5.000,01 a 7.350 reduz 978,62 − 0,133145 × rendimentos.
REDUTOR_IRRF_INICIO = date(2026, 1, 1)
REDUTOR_IRRF_ISENCAO = 5000.00
REDUTOR_IRRF_LIMITE = 7350.00
REDUTOR_IRRF_CONSTANTE = 978.62
REDUTOR_IRRF_FATOR = 0.133145

ALIQUOTA_INSS_AUTONOMO = 0.11
ALIQUOTA_INSS_PATRONAL = 0.20
ALIQUOTA_FGTS = 0.08
ALIQUOTA_FGTS_APRENDIZ = 0.02  # Lei 10.097/2000 + art. 15 Lei 8.036/1990
ALIQUOTA_RAT = 0.01
ALIQUOTA_SISTEMA_S = 0.058
RETENCAO_IRRF_PJ = 0.015
RETENCAO_PIS = 0.0065
RETENCAO_COFINS = 0.03
RETENCAO_CSLL = 0.01


def _num(valor):
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return 0.0


def _referencia(ano=None, mes=None):
    try:
        if ano and mes:
            return date(int(ano), int(mes), 1)
    except (TypeError, ValueError):
        pass
    hoje = date.today()
    return date(hoje.year, hoje.month, 1)


def _vigente(tabelas, ano=None, mes=None):
    ref = _referencia(ano, mes)
    escolhida = tabelas[0]
    for item in tabelas:
        if item[0] <= ref:
            escolhida = item
    return escolhida


def faixas_inss(ano=None, mes=None):
    return _vigente(TABELAS_INSS, ano, mes)[1]


def teto_inss(ano=None, mes=None):
    return faixas_inss(ano, mes)[-1][0]


TETO_INSS = teto_inss()


def inss_empregado(bruto, ano=None, mes=None):
    faixas = faixas_inss(ano, mes)
    base = min(max(_num(bruto), 0.0), faixas[-1][0])
    if base <= 0:
        return 0.0
    anterior = 0.0
    total = 0.0
    for limite, aliquota in faixas:
        faixa = min(base, limite) - anterior
        if faixa > 0:
            total += faixa * aliquota
        anterior = limite
        if base <= limite:
            break
    return round(total, 2)


def irrf_progressivo(base, ano=None, mes=None):
    """Imposto pela tabela progressiva vigente, sem desconto simplificado nem redutor."""
    valor = max(_num(base), 0.0)
    if valor <= 0:
        return 0.0
    for limite, aliquota, deducao in _vigente(TABELAS_IRRF, ano, mes)[1]:
        if valor <= limite:
            if aliquota == 0:
                return 0.0
            return round(max(valor * aliquota - deducao, 0.0), 2)
    return 0.0


def desconto_simplificado_irrf(ano=None, mes=None):
    return _vigente(TABELAS_IRRF, ano, mes)[2]


def redutor_irrf(rendimentos, imposto, ano=None, mes=None):
    """Redução da Lei 15.270/2025, limitada ao imposto calculado."""
    imposto = max(_num(imposto), 0.0)
    rendimentos = max(_num(rendimentos), 0.0)
    if imposto <= 0 or _referencia(ano, mes) < REDUTOR_IRRF_INICIO:
        return 0.0
    if rendimentos <= REDUTOR_IRRF_ISENCAO:
        return round(imposto, 2)
    if rendimentos <= REDUTOR_IRRF_LIMITE:
        reducao = REDUTOR_IRRF_CONSTANTE - REDUTOR_IRRF_FATOR * rendimentos
        return round(min(max(reducao, 0.0), imposto), 2)
    return 0.0


def irrf_mensal(rendimentos, inss, ano=None, mes=None):
    """IRRF do salário: usa o que for melhor entre deduzir o INSS ou o desconto simplificado, depois o redutor."""
    rendimentos = max(_num(rendimentos), 0.0)
    simplificado = desconto_simplificado_irrf(ano, mes)
    deducao_legal = max(_num(inss), 0.0)
    usa_simplificado = simplificado > deducao_legal
    deducao = simplificado if usa_simplificado else deducao_legal
    base = round(max(rendimentos - deducao, 0.0), 2)
    imposto = irrf_progressivo(base, ano, mes)
    reducao = redutor_irrf(rendimentos, imposto, ano, mes)
    return {
        "base": base,
        "deducao": round(deducao, 2),
        "desconto_simplificado": usa_simplificado,
        "imposto_tabela": imposto,
        "redutor": reducao,
        "irrf": round(max(imposto - reducao, 0.0), 2),
    }


def inss_autonomo(bruto, ano=None, mes=None):
    base = min(max(_num(bruto), 0.0), teto_inss(ano, mes))
    return round(base * ALIQUOTA_INSS_AUTONOMO, 2)


def dsr_horista(valor_horas, ano=None, mes=None, feriados=()):
    """DSR das horas-aula: valor × (domingos + feriados) ÷ dias úteis do mês. Sem mês, 1/6 habitual."""
    horas = _num(valor_horas)
    if ano and mes:
        ano, mes = int(ano), int(mes)
        dias = monthrange(ano, mes)[1]
        feriados_mes = set()
        for item in feriados or ():
            if isinstance(item, datetime):
                item = item.date()
            elif isinstance(item, str):
                try:
                    item = date.fromisoformat(item[:10])
                except ValueError:
                    continue
            if isinstance(item, date) and item.year == ano and item.month == mes:
                feriados_mes.add(item)
        descansos = sum(
            1 for d in range(1, dias + 1)
            if date(ano, mes, d).weekday() == 6 or date(ano, mes, d) in feriados_mes
        )
        uteis = max(dias - descansos, 1)
        return round(horas * (descansos / uteis), 2)
    return round(horas / 6.0, 2)


def _data(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str) and valor:
        try:
            return date.fromisoformat(valor[:10])
        except ValueError:
            return None
    return None


def dias_proporcionais_admissao(func, ano=None, mes=None):
    """Dias a pagar no mês de admissão/readmissão (salário ÷ 30 × dias). None se o mês é cheio."""
    if not ano or not mes:
        return None
    inicio = _data(func.get("data_inicio_contrato") or func.get("data_contratacao"))
    if not inicio or inicio.year != int(ano) or inicio.month != int(mes) or inicio.day == 1:
        return None
    ultimo = monthrange(int(ano), int(mes))[1]
    return max(0, min(ultimo - inicio.day + 1, 30))


def _eh_aprendiz(tipo_contrato):
    return (tipo_contrato or "").strip().lower() in ("jovem_aprendiz", "aprendiz")


def encargos_clt(base, regime, tipo_contrato=None):
    """Encargos patronais CLT. Aprendiz: FGTS 2% (Lei 10.097/2000); INSS patronal segue o regime
    (zerado no Simples; integral no Presumido/Real — STJ Tema 1342/2025)."""
    salario = _num(base)
    aprendiz = _eh_aprendiz(tipo_contrato)
    aliq_fgts = ALIQUOTA_FGTS_APRENDIZ if aprendiz else ALIQUOTA_FGTS
    fgts = round(salario * aliq_fgts, 2)
    fgts_cheio = round(salario * ALIQUOTA_FGTS, 2)
    provisao_13 = round(salario / 12.0, 2)
    ferias_terco = round((salario + salario / 3.0) / 12.0, 2)
    reflexos_fgts = round((provisao_13 + ferias_terco) * aliq_fgts, 2)
    reflexos_fgts_cheio = round((provisao_13 + ferias_terco) * ALIQUOTA_FGTS, 2)
    reducao_fgts = round(max((fgts_cheio + reflexos_fgts_cheio) - (fgts + reflexos_fgts), 0.0), 2)
    simples = (regime or "").lower() in ("simples_nacional", "simples")
    if simples:
        inss_patronal = 0.0
        rat = 0.0
        sistema_s = 0.0
    else:
        inss_patronal = round(salario * ALIQUOTA_INSS_PATRONAL, 2)
        rat = round(salario * ALIQUOTA_RAT, 2)
        sistema_s = round(salario * ALIQUOTA_SISTEMA_S, 2)
    encargos = fgts + provisao_13 + ferias_terco + reflexos_fgts + inss_patronal + rat + sistema_s
    return {
        "fgts": fgts,
        "provisao_13": provisao_13,
        "ferias_terco": ferias_terco,
        "reflexos_fgts": reflexos_fgts,
        "inss_patronal": inss_patronal,
        "rat": rat,
        "sistema_s": sistema_s,
        "encargos": round(encargos, 2),
        "custo_escola": round(salario + encargos, 2),
        "aliquota_fgts": aliq_fgts,
        "fgts_cheio": fgts_cheio,
        "reducao_fgts_aprendiz": reducao_fgts if aprendiz else 0.0,
        "jovem_aprendiz": aprendiz,
    }


def contrato_vigente(func, ano=None, mes=None):
    if not ano or not mes:
        return True
    inicio = func.get("data_inicio_contrato") or func.get("data_contratacao")
    fim = func.get("data_fim_contrato")
    try:
        primeiro = date(int(ano), int(mes), 1)
        ultimo = date(int(ano), int(mes), monthrange(int(ano), int(mes))[1])
    except (TypeError, ValueError):
        return True
    if isinstance(inicio, datetime):
        inicio = inicio.date()
    if isinstance(fim, datetime):
        fim = fim.date()
    if isinstance(inicio, str) and inicio:
        try:
            inicio = date.fromisoformat(inicio[:10])
        except ValueError:
            inicio = None
    if isinstance(fim, str) and fim:
        try:
            fim = date.fromisoformat(fim[:10])
        except ValueError:
            fim = None
    if inicio and inicio > ultimo:
        return False
    if fim and fim < primeiro:
        return False
    return True


def situacao_folha_mes(func, ano=None, mes=None):
    """'folha' (entra na folha), 'rescisao' (mês do desligamento: o saldo de salário sai na rescisão) ou 'fora'."""
    ativo = func.get("ativo") is not False
    fim = _data(func.get("data_fim_contrato"))
    if not ano or not mes:
        return "folha" if ativo else "fora"
    if not contrato_vigente(func, ano, mes):
        return "fora"
    if ativo:
        return "folha"
    if not fim:
        return "fora"
    if (fim.year, fim.month) == (int(ano), int(mes)):
        return "rescisao"
    return "folha"


def dia_pagamento_valido(valor, padrao=5):
    try:
        dia = int(valor or padrao)
    except (TypeError, ValueError):
        dia = padrao
    return max(1, min(28, dia))


DIVISOR_CLT = 220.0
ADICIONAL_HE_50 = 1.5
ADICIONAL_HE_100 = 2.0


def hora_normal_clt(func):
    """Hora normal: horista usa valor_hora; mensalista usa salário ÷ 220 (CLT, jornada de 44h)."""
    tipo = (func.get("tipo_contrato") or "clt_mensalista").strip().lower()
    if tipo in ("clt_horista", "horista") and _num(func.get("valor_hora")) > 0:
        return round(_num(func.get("valor_hora")), 4)
    salario = _num(func.get("salario") or func.get("valor_servico"))
    if salario > 0:
        return round(salario / DIVISOR_CLT, 4)
    if _num(func.get("valor_hora")) > 0:
        return round(_num(func.get("valor_hora")), 4)
    return 0.0


def _contrato_clt(tipo):
    return (tipo or "clt_mensalista").strip().lower() in (
        "clt_mensalista",
        "clt_horista",
        "horista",
        "jovem_aprendiz",
        "aprendiz",
        "",
    )


def detalhe_horas_extras(func):
    """HE 50% (dia útil) e 100% (domingo/feriado), com DSR de 1/6 nas extras habituais (Súmula 172 TST)."""
    hora_n = hora_normal_clt(func)
    horas_50 = max(_num(func.get("horas_extras")), 0.0)
    horas_100 = max(_num(func.get("horas_extras_100")), 0.0)
    informado = _num(func.get("valor_hora_extra"))
    tipo = (func.get("tipo_contrato") or "clt_mensalista").strip().lower()
    minimo_50 = hora_n * ADICIONAL_HE_50
    if informado > 0:
        valor_50 = max(informado, minimo_50) if _contrato_clt(tipo) else informado
    else:
        valor_50 = minimo_50
    valor_50 = round(valor_50, 4)
    valor_100 = round(max(hora_n * ADICIONAL_HE_100, valor_50), 4)
    adicional_50 = round(horas_50 * valor_50, 2)
    adicional_100 = round(horas_100 * valor_100, 2)
    adicional = round(adicional_50 + adicional_100, 2)
    dsr_he = round(adicional / 6.0, 2) if adicional > 0 and _contrato_clt(tipo) else 0.0
    return {
        "hora_normal": hora_n,
        "horas_extras": horas_50,
        "horas_extras_100": horas_100,
        "valor_hora_extra": valor_50,
        "valor_hora_extra_100": valor_100,
        "adicional_he_50": adicional_50,
        "adicional_he_100": adicional_100,
        "adicional_he": adicional,
        "dsr_he": dsr_he,
    }


def adicional_horas_extras(func):
    d = detalhe_horas_extras(func)
    return d["horas_extras"], d["valor_hora_extra"], d["adicional_he"]


def aplicar_ajuste_competencia(func, ajuste):
    if not ajuste:
        return func
    dados = dict(func)
    for chave in ("horas_extras", "horas_extras_100", "valor_hora_extra"):
        if ajuste.get(chave) is not None:
            dados[chave] = ajuste.get(chave)
    return dados


def calcular_folha_pessoa(func, regime, ano=None, mes=None):
    tipo = (func.get("tipo_contrato") or "clt_mensalista").strip().lower()
    nome = func.get("nome_completo") or "-"
    cargo = func.get("cargo") or "-"
    he = detalhe_horas_extras(func)
    horas_ex = he["horas_extras"]
    valor_he = he["valor_hora_extra"]
    adicional_he = he["adicional_he"]
    dsr_he = he["dsr_he"]
    resultado = {
        "id": func.get("id"),
        "nome_completo": nome,
        "cargo": cargo,
        "tipo_contrato": tipo,
        "salario": 0.0,
        "dsr": 0.0,
        "dsr_he": dsr_he,
        "bruto": 0.0,
        "inss_funcionario": 0.0,
        "irrf": 0.0,
        "pis": 0.0,
        "cofins": 0.0,
        "csll": 0.0,
        "iss": 0.0,
        "descontos": 0.0,
        "liquido": 0.0,
        "fgts": 0.0,
        "provisao_13": 0.0,
        "ferias_terco": 0.0,
        "reflexos_fgts": 0.0,
        "inss_patronal": 0.0,
        "rat": 0.0,
        "sistema_s": 0.0,
        "encargos": 0.0,
        "custo_escola": 0.0,
        "total": 0.0,
        "observacao": "",
        "valor_hora": _num(func.get("valor_hora")),
        "horas_mes": _num(func.get("horas_mes")),
        "hora_normal": he["hora_normal"],
        "horas_extras": horas_ex,
        "horas_extras_100": he["horas_extras_100"],
        "valor_hora_extra": valor_he,
        "valor_hora_extra_100": he["valor_hora_extra_100"],
        "adicional_he_50": he["adicional_he_50"],
        "adicional_he_100": he["adicional_he_100"],
        "adicional_he": adicional_he,
        "horas_extras_ponto": _num(func.get("horas_extras_ponto")),
        "horas_extras_100_ponto": _num(func.get("horas_extras_100_ponto")),
        "horas_extras_manual": _num(func.get("horas_extras_manual", func.get("horas_extras"))),
        "horas_extras_100_manual": _num(func.get("horas_extras_100_manual", func.get("horas_extras_100"))),
        "dia_pagamento": dia_pagamento_valido(func.get("dia_pagamento")),
        "aliquota_fgts": ALIQUOTA_FGTS,
        "fgts_cheio": 0.0,
        "reducao_fgts_aprendiz": 0.0,
        "jovem_aprendiz": False,
    }

    if tipo in ("pj", "pessoa_juridica"):
        bruto = _num(func.get("salario") or func.get("valor_servico")) + adicional_he
        reter_fed = str(func.get("reter_federal") or "").lower() in ("t", "true", "1", "sim")
        reter_iss = str(func.get("reter_iss") or "").lower() in ("t", "true", "1", "sim")
        aliq_iss = _num(func.get("aliquota_iss") or 0)
        irrf = round(bruto * RETENCAO_IRRF_PJ, 2) if reter_fed else 0.0
        pis = round(bruto * RETENCAO_PIS, 2) if reter_fed else 0.0
        cofins = round(bruto * RETENCAO_COFINS, 2) if reter_fed else 0.0
        csll = round(bruto * RETENCAO_CSLL, 2) if reter_fed else 0.0
        iss = round(bruto * (aliq_iss / 100.0 if aliq_iss > 1 else aliq_iss), 2) if reter_iss else 0.0
        descontos = irrf + pis + cofins + csll + iss
        resultado.update(
            {
                "salario": _num(func.get("salario") or func.get("valor_servico")),
                "bruto": bruto,
                "irrf": irrf,
                "pis": pis,
                "cofins": cofins,
                "csll": csll,
                "iss": iss,
                "descontos": round(descontos, 2),
                "liquido": round(bruto - descontos, 2),
                "custo_escola": bruto,
                "total": bruto,
                "observacao": "PJ / NFS-e: sem FGTS, férias, 13º ou INSS de folha. Pagamento contra nota. Retenções só se parametrizadas."
                + (f" Inclui {horas_ex:g} h extras ({br_money(adicional_he)})." if adicional_he else ""),
            }
        )
        return resultado

    if tipo in ("rpa", "autonomo", "extra_pf"):
        bruto = _num(func.get("salario") or func.get("valor_servico")) + adicional_he
        inss_f = inss_autonomo(bruto, ano, mes)
        irrf = irrf_mensal(bruto, inss_f, ano, mes)["irrf"]
        descontos = inss_f + irrf
        inss_p = round(bruto * ALIQUOTA_INSS_PATRONAL, 2)
        rat = round(bruto * ALIQUOTA_RAT, 2)
        encargos = inss_p + rat
        resultado.update(
            {
                "salario": _num(func.get("salario") or func.get("valor_servico")),
                "bruto": bruto,
                "inss_funcionario": inss_f,
                "irrf": irrf,
                "descontos": round(descontos, 2),
                "liquido": round(bruto - descontos, 2),
                "inss_patronal": inss_p,
                "rat": rat,
                "encargos": round(encargos, 2),
                "custo_escola": round(bruto + encargos, 2),
                "total": round(bruto + encargos, 2),
                "observacao": "RPA: INSS do autônomo + IRRF. Escola recolhe INSS patronal 20% e RAT."
                + (f" Inclui {horas_ex:g} h extras ({br_money(adicional_he)})." if adicional_he else ""),
            }
        )
        return resultado

    aprendiz = _eh_aprendiz(tipo)
    if tipo in ("clt_horista", "horista"):
        valor_hora = _num(func.get("valor_hora"))
        horas = _num(func.get("horas_mes"))
        valor_horas = round(valor_hora * horas, 2)
        feriados = func.get("feriados_competencia") or ()
        dsr = dsr_horista(valor_horas, ano, mes, feriados)
        bruto = round(valor_horas + dsr + adicional_he + dsr_he, 2)
        resultado["observacao"] = (
            f"Horista: {horas:g} h × {br_money(valor_hora)} + DSR de {br_money(dsr)} "
            f"(domingos{' e feriados' if feriados else ''} do mês ÷ dias úteis)."
        )
        salario_mes = round(bruto - dsr - adicional_he - dsr_he, 2)
    else:
        salario_cheio = _num(func.get("salario"))
        dias_admissao = dias_proporcionais_admissao(func, ano, mes)
        salario_mes = round(salario_cheio / 30.0 * dias_admissao, 2) if dias_admissao is not None else salario_cheio
        bruto = round(salario_mes + adicional_he + dsr_he, 2)
        dsr = 0.0
        if aprendiz:
            resultado["observacao"] = (
                "Jovem aprendiz (CLT art. 428 / Lei 10.097/2000): salário do contrato. "
                "INSS e IRRF do empregado como CLT. FGTS patronal 2%."
            )
        else:
            resultado["observacao"] = "CLT mensalista: salário fixo. INSS progressivo e IRRF sobre o bruto."
        if dias_admissao is not None:
            resultado["observacao"] += (
                f" Mês de admissão: {br_money(salario_cheio)} ÷ 30 × {dias_admissao} dia(s) = {br_money(salario_mes)}."
            )
        resultado["dias_admissao"] = dias_admissao
    if adicional_he or dsr_he:
        partes = []
        if he["adicional_he_50"]:
            partes.append(f"{horas_ex:g} h a 50% × {br_money(valor_he)} = {br_money(he['adicional_he_50'])}")
        if he["adicional_he_100"]:
            partes.append(
                f"{he['horas_extras_100']:g} h a 100% × {br_money(he['valor_hora_extra_100'])} = {br_money(he['adicional_he_100'])}"
            )
        if dsr_he:
            partes.append(f"DSR sobre extras {br_money(dsr_he)} (1/6, Súmula 172 TST)")
        resultado["observacao"] += " Horas extras CLT: " + "; ".join(partes) + "."
        ponto_50 = resultado["horas_extras_ponto"]
        ponto_100 = resultado["horas_extras_100_ponto"]
        if ponto_50 or ponto_100:
            origem = []
            if ponto_50:
                origem.append(f"{ponto_50:g} h a 50%")
            if ponto_100:
                origem.append(f"{ponto_100:g} h a 100%")
            resultado["observacao"] += (
                f" Desse total, {' e '.join(origem)} vieram do ponto eletrônico do sistema"
                " (compensação no mês, art. 59 §6º CLT; tolerância de 10 min/dia, art. 58 §1º)."
            )

    desconto_faltas = _num(func.get("desconto_faltas"))
    desconto_dsr_faltas = _num(func.get("desconto_dsr_faltas"))
    dias_falta = int(func.get("dias_falta_desconto") or 0)
    semanas_dsr = int(func.get("semanas_dsr_falta") or 0)
    base_tributavel = round(max(bruto - desconto_faltas - desconto_dsr_faltas, 0.0), 2)
    inss_f = inss_empregado(base_tributavel, ano, mes)
    ir = irrf_mensal(base_tributavel, inss_f, ano, mes)
    irrf = ir["irrf"]
    descontos = inss_f + irrf + desconto_faltas + desconto_dsr_faltas
    if desconto_faltas or desconto_dsr_faltas:
        resultado["observacao"] += (
            f" Faltas não justificadas confirmadas: {dias_falta} dia(s) "
            f"({br_money(desconto_faltas)})"
            + (f" + DSR de {semanas_dsr} semana(s) ({br_money(desconto_dsr_faltas)})" if desconto_dsr_faltas else "")
            + f" — Lei 605/1949. INSS, IRRF e FGTS sobre {br_money(base_tributavel)}."
        )
    if ir["desconto_simplificado"] and ir["imposto_tabela"]:
        resultado["observacao"] += f" IRRF com desconto simplificado de {br_money(ir['deducao'])}."
    if ir["redutor"]:
        resultado["observacao"] += f" Redução do IRRF (Lei 15.270/2025): {br_money(ir['redutor'])}."
    patronal = encargos_clt(base_tributavel, regime, tipo)
    simples = (regime or "").lower() in ("simples_nacional", "simples")
    if aprendiz:
        resultado["observacao"] += (
            f" Redução de FGTS: {(ALIQUOTA_FGTS - ALIQUOTA_FGTS_APRENDIZ) * 100:.0f} p.p. "
            f"(economia R$ {br_money(patronal.get('reducao_fgts_aprendiz') or 0)} neste mês)."
        )
    if simples:
        resultado["observacao"] += " Simples Nacional: INSS patronal e RAT zerados (DAS); permanecem FGTS e provisões."
    else:
        resultado["observacao"] += (
            " Lucro Presumido/Real: FGTS, 13º, férias+1/3, INSS 20%, RAT e Sistema S"
            + (" — INSS patronal também sobre aprendiz (STJ Tema 1342)." if aprendiz else ".")
        )
    resultado.update(patronal)
    resultado.update(
        {
            "salario": salario_mes,
            "dsr": dsr,
            "dsr_he": dsr_he,
            "bruto": bruto,
            "base_inss": base_tributavel,
            "base_irrf": ir["base"],
            "base_fgts": base_tributavel,
            "irrf_redutor": ir["redutor"],
            "inss_funcionario": inss_f,
            "irrf": irrf,
            "desconto_faltas": round(desconto_faltas, 2),
            "desconto_dsr_faltas": round(desconto_dsr_faltas, 2),
            "dias_falta_desconto": dias_falta,
            "descontos": round(descontos, 2),
            "liquido": round(bruto - descontos, 2),
            "total": patronal["custo_escola"],
        }
    )
    return resultado


def _aliquota_percentual(valor, padrao):
    aliq = _num(valor)
    if aliq <= 0:
        aliq = _num(padrao)
    return aliq / 100.0


def impostos_nota(
    bruto,
    reter_federal=False,
    reter_iss=False,
    aliquota_iss=5,
    aliq_irrf=None,
    aliq_pis=None,
    aliq_cofins=None,
    aliq_csll=None,
):
    valor = _num(bruto)
    irrf = round(valor * _aliquota_percentual(aliq_irrf, RETENCAO_IRRF_PJ * 100), 2) if reter_federal else 0.0
    pis = round(valor * _aliquota_percentual(aliq_pis, RETENCAO_PIS * 100), 2) if reter_federal else 0.0
    cofins = round(valor * _aliquota_percentual(aliq_cofins, RETENCAO_COFINS * 100), 2) if reter_federal else 0.0
    csll = round(valor * _aliquota_percentual(aliq_csll, RETENCAO_CSLL * 100), 2) if reter_federal else 0.0
    iss = round(valor * _aliquota_percentual(aliquota_iss, 5), 2) if reter_iss else 0.0
    retido = irrf + pis + cofins + csll + iss
    return {
        "irrf": irrf,
        "pis": pis,
        "cofins": cofins,
        "csll": csll,
        "iss": iss,
        "retido": round(retido, 2),
        "liquido": round(valor - retido, 2),
    }


def rotulo_contrato(tipo):
    mapa = {
        "clt_mensalista": "CLT mensalista",
        "clt_horista": "CLT horista",
        "horista": "CLT horista",
        "jovem_aprendiz": "Jovem aprendiz",
        "aprendiz": "Jovem aprendiz",
        "pj": "PJ / NFS-e",
        "pessoa_juridica": "PJ / NFS-e",
        "rpa": "RPA / Autônomo",
        "autonomo": "RPA / Autônomo",
        "extra_pf": "RPA / Autônomo",
    }
    return mapa.get((tipo or "").lower(), "CLT mensalista")
