"""DRE do mês: individual por unidade e consolidada (matriz + filiais).

Simples Nacional da rede: matriz e filiais são a mesma empresa (mesma raiz de CNPJ) e declaram um único PGDAS-D.
A faixa e a alíquota saem da RBT12 somada de todos os estabelecimentos (LC 123/2006, art. 3º e art. 18),
e cada unidade paga essa alíquota sobre a própria receita.
"""

from tributacao import ATIVIDADE_ENSINO, apurar_simples

LINHAS_DRE = (
    ("receita_bruta", "Receita bruta (mensalidades)", "receita"),
    ("deducoes", "(−) Tributos sobre a receita", "deducao"),
    ("receita_liquida", "= Receita líquida", "total"),
    ("folha", "(−) Folha e encargos", "custo"),
    ("rescisoes", "(−) Rescisões", "custo"),
    ("compras", "(−) Compras", "custo"),
    ("servicos", "(−) Serviços de terceiros", "custo"),
    ("resultado_operacional", "= Resultado operacional", "total"),
    ("receitas_financeiras", "(+) Juros e multa recebidos", "receita"),
    ("irpj_csll", "(−) IRPJ e CSLL", "deducao"),
    ("resultado_liquido", "= Resultado líquido do mês", "total"),
)
CAMPOS_BASE = ("receita_bruta", "deducoes", "folha", "rescisoes", "compras", "servicos", "receitas_financeiras", "irpj_csll")


def _n(valor):
    try:
        return round(float(valor or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def calcular_dre(base):
    """Fecha os subtotais da DRE a partir das linhas de base (valores positivos; o sinal vem da linha)."""
    dre = {campo: _n(base.get(campo)) for campo in CAMPOS_BASE}
    dre["receita_liquida"] = round(dre["receita_bruta"] - dre["deducoes"], 2)
    custos = dre["folha"] + dre["rescisoes"] + dre["compras"] + dre["servicos"]
    dre["resultado_operacional"] = round(dre["receita_liquida"] - custos, 2)
    dre["resultado_liquido"] = round(dre["resultado_operacional"] + dre["receitas_financeiras"] - dre["irpj_csll"], 2)
    dre["margem_pct"] = round(dre["resultado_liquido"] / dre["receita_bruta"] * 100, 2) if dre["receita_bruta"] else 0.0
    return dre


def consolidar_dre(dres):
    """Soma linha a linha as DREs das unidades e recalcula a margem."""
    soma = {campo: sum(_n((d or {}).get(campo)) for d in dres or []) for campo in CAMPOS_BASE}
    return calcular_dre(soma)


def aliquota_simples_rede(unidades, atividade=ATIVIDADE_ENSINO):
    """Apuração com a RBT12 e a folha (FS12) somadas da rede. `unidades`: [{"rbt12", "fs12"}] já anualizadas."""
    rbt12 = sum(_n(u.get("rbt12")) for u in unidades or [])
    fs12 = sum(_n(u.get("fs12")) for u in unidades or [])
    receita_mes = sum(_n(u.get("receita_mes")) for u in unidades or [])
    return apurar_simples(rbt12, fs12, 12, receita_mes, atividade=atividade)


def das_pela_rede(receita_mes, apuracao_rede):
    return round(_n(receita_mes) * float((apuracao_rede or {}).get("aliquota_efetiva") or 0), 2)


def linhas_para_tela(colunas, consolidado=None):
    """[(rotulo, tipo, [valores por coluna], valor consolidado)] na ordem da DRE."""
    linhas = []
    for campo, rotulo, tipo in LINHAS_DRE:
        valores = [_n((c.get("dre") or {}).get(campo)) for c in colunas]
        linhas.append({
            "campo": campo,
            "rotulo": rotulo,
            "tipo": tipo,
            "valores": valores,
            "consolidado": _n((consolidado or {}).get(campo)) if consolidado else None,
        })
    return linhas
