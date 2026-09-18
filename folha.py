"""Cálculos de folha: CLT mensalista, horista, PJ e RPA."""

from calendar import monthrange
from datetime import date

# Portaria Interministerial MPS/MF — tabela 2025/2026 (progressiva)
TETO_INSS = 8157.41
FAIXAS_INSS = [
    (1518.00, 0.075),
    (2793.88, 0.09),
    (4190.83, 0.12),
    (TETO_INSS, 0.14),
]

FAIXAS_IRRF = [
    (2259.20, 0.0, 0.0),
    (2826.65, 0.075, 169.44),
    (3751.05, 0.15, 381.44),
    (4664.68, 0.225, 662.77),
    (10**12, 0.275, 896.00),
]

ALIQUOTA_INSS_AUTONOMO = 0.11
ALIQUOTA_INSS_PATRONAL = 0.20
ALIQUOTA_FGTS = 0.08
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


def inss_empregado(bruto):
    base = min(max(_num(bruto), 0.0), TETO_INSS)
    if base <= 0:
        return 0.0
    anterior = 0.0
    total = 0.0
    for limite, aliquota in FAIXAS_INSS:
        faixa = min(base, limite) - anterior
        if faixa > 0:
            total += faixa * aliquota
        anterior = limite
        if base <= limite:
            break
    return round(total, 2)


def irrf_progressivo(base):
    valor = max(_num(base), 0.0)
    if valor <= 0:
        return 0.0
    for limite, aliquota, deducao in FAIXAS_IRRF:
        if valor <= limite:
            if aliquota == 0:
                return 0.0
            return round(max(valor * aliquota - deducao, 0.0), 2)
    return 0.0


def inss_autonomo(bruto):
    base = min(max(_num(bruto), 0.0), TETO_INSS)
    return round(base * ALIQUOTA_INSS_AUTONOMO, 2)


def dsr_horista(valor_horas, ano=None, mes=None):
    """DSR habitual de 1/6 sobre as horas-aula. Se ano/mês forem informados, usa dias úteis/domingos."""
    horas = _num(valor_horas)
    if ano and mes:
        dias = monthrange(int(ano), int(mes))[1]
        domingos = sum(1 for d in range(1, dias + 1) if date(int(ano), int(mes), d).weekday() == 6)
        uteis = max(dias - domingos, 1)
        return round(horas * (domingos / uteis), 2)
    return round(horas / 6.0, 2)


def encargos_clt(base, regime):
    salario = _num(base)
    fgts = round(salario * ALIQUOTA_FGTS, 2)
    provisao_13 = round(salario / 12.0, 2)
    ferias_terco = round((salario + salario / 3.0) / 12.0, 2)
    reflexos_fgts = round((provisao_13 + ferias_terco) * ALIQUOTA_FGTS, 2)
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
    }


def calcular_folha_pessoa(func, regime, ano=None, mes=None):
    tipo = (func.get("tipo_contrato") or "clt_mensalista").strip().lower()
    nome = func.get("nome_completo") or "-"
    cargo = func.get("cargo") or "-"
    resultado = {
        "id": func.get("id"),
        "nome_completo": nome,
        "cargo": cargo,
        "tipo_contrato": tipo,
        "salario": 0.0,
        "dsr": 0.0,
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
    }

    if tipo in ("pj", "pessoa_juridica"):
        bruto = _num(func.get("salario") or func.get("valor_servico"))
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
                "salario": bruto,
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
                "observacao": "PJ / NFS-e: sem FGTS, férias, 13º ou INSS de folha. Pagamento contra nota. Retenções só se parametrizadas.",
            }
        )
        return resultado

    if tipo in ("rpa", "autonomo", "extra_pf"):
        bruto = _num(func.get("salario") or func.get("valor_servico"))
        inss_f = inss_autonomo(bruto)
        irrf = irrf_progressivo(bruto - inss_f)
        descontos = inss_f + irrf
        inss_p = round(bruto * ALIQUOTA_INSS_PATRONAL, 2)
        rat = round(bruto * ALIQUOTA_RAT, 2)
        encargos = inss_p + rat
        resultado.update(
            {
                "salario": bruto,
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
                "observacao": "RPA: INSS do autônomo + IRRF. Escola recolhe INSS patronal 20% e RAT.",
            }
        )
        return resultado

    if tipo in ("clt_horista", "horista"):
        valor_hora = _num(func.get("valor_hora"))
        horas = _num(func.get("horas_mes"))
        valor_horas = round(valor_hora * horas, 2)
        dsr = dsr_horista(valor_horas, ano, mes)
        bruto = round(valor_horas + dsr, 2)
        resultado["observacao"] = f"Horista: {horas:g} h × R$ {valor_hora:.2f} + DSR de R$ {dsr:.2f}."
    else:
        bruto = _num(func.get("salario"))
        dsr = 0.0
        resultado["observacao"] = "CLT mensalista: salário fixo. INSS progressivo e IRRF sobre o bruto."

    inss_f = inss_empregado(bruto)
    irrf = irrf_progressivo(bruto - inss_f)
    descontos = inss_f + irrf
    patronal = encargos_clt(bruto, regime)
    simples = (regime or "").lower() in ("simples_nacional", "simples")
    if simples:
        resultado["observacao"] += " Simples Nacional: INSS patronal e RAT zerados; permanecem FGTS e provisões."
    else:
        resultado["observacao"] += " Lucro Presumido/Real: FGTS, 13º, férias+1/3, INSS 20%, RAT e Sistema S."
    resultado.update(patronal)
    resultado.update(
        {
            "salario": bruto - dsr if tipo in ("clt_horista", "horista") else bruto,
            "dsr": dsr,
            "bruto": bruto,
            "inss_funcionario": inss_f,
            "irrf": irrf,
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
        "pj": "PJ / NFS-e",
        "pessoa_juridica": "PJ / NFS-e",
        "rpa": "RPA / Autônomo",
        "autonomo": "RPA / Autônomo",
        "extra_pf": "RPA / Autônomo",
    }
    return mapa.get((tipo or "").lower(), "CLT mensalista")
