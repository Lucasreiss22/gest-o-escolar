"""DRE do mês: individual por unidade e consolidada (matriz + filiais).

Os tributos de cada unidade já chegam como a parte dela no imposto da empresa (tributos_rede),
então o consolidado é a soma das colunas.
"""

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


def juntar_avisos(colunas):
    """Avisos da DRE. O que aparece igual em todas as unidades é da empresa (uma vez, sem prefixo);
    o resto é da unidade e leva o nome dela."""
    listas = [
        (c.get("nome"), list(dict.fromkeys((c.get("info") or {}).get("avisos") or [])))
        for c in colunas if not c.get("erro")
    ]
    if len(listas) <= 1:
        return [aviso for _nome, lista in listas for aviso in lista]
    comuns = set(listas[0][1]).intersection(*(set(lista) for _nome, lista in listas[1:]))
    saida = []
    for nome, lista in listas:
        for aviso in lista:
            if aviso not in comuns:
                saida.append(f"{nome}: {aviso}")
            elif aviso not in saida:
                saida.append(aviso)
    return saida
