"""Rescisão contratual CLT: vínculos, cálculo e recontratação.

Fundamentos principais:
- Art. 477 CLT / Art. 7º, X CF — saldo de salário e quitação
- Lei 12.506/2011 e Arts. 487–491 CLT — aviso prévio proporcional
- Lei 4.090/1962 — 13º (avos; fração ≥ 15 dias)
- Arts. 130, 137, 146–147 CLT + Art. 7º, XVII CF — férias + 1/3
- Lei 8.036/1990 — FGTS e multa (40% / 20% no acordo 484-A)
- Art. 477 §6º CLT (Reforma) — pagamento em até 10 dias do término
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal
import json

from folha import (
    ALIQUOTA_FGTS,
    ALIQUOTA_FGTS_APRENDIZ,
    ALIQUOTA_INSS_PATRONAL,
    ALIQUOTA_RAT,
    ALIQUOTA_SISTEMA_S,
    _eh_aprendiz,
    _num,
    hora_normal_clt,
    inss_empregado,
    irrf_mensal as calcular_irrf_mensal,
    irrf_progressivo,
    redutor_irrf,
)

# Redutor da Lei 15.270/2025 no IRRF do 13º: a base do redutor fica a critério da escola/contabilidade.
REDUTOR_13_OPCOES = (
    ("bruto", "Redutor sobre o 13º bruto"),
    ("liquido", "Redutor sobre o 13º menos o INSS"),
    ("nao", "Sem redutor no 13º"),
)


def normalizar_redutor_13(valor):
    valor = (valor or "").strip().lower()
    return valor if valor in dict(REDUTOR_13_OPCOES) else "bruto"


# Muda quando uma regra do cálculo muda; rescisões gravadas com outra versão ganham aviso e podem ser recalculadas.
VERSAO_REGRAS_RESCISAO = "2026-10-03"
DESCRICAO_REGRAS_RESCISAO = (
    "aviso do pedido de demissão limitado a 30 dias (Lei 12.506/2011) e redutor da Lei 15.270/2025 no IRRF do 13º"
)
CAMPOS_PARAMETROS_RESCISAO = (
    "tipo_rescisao", "aviso_modalidade", "data_desligamento", "data_aviso", "data_pagamento",
    "dias_trabalhados_mes", "dias_aviso", "ferias_vencidas_simples", "ferias_vencidas_dobro",
    "avos_ferias_proporcionais", "avos_13", "decimo_ja_pago", "saldo_fgts_depositos",
    "outros_proventos", "outros_descontos", "ind_aviso_manual",
)
# Verbas comparadas na tela de recálculo: (chave do cálculo, rótulo)
VERBAS_COMPARACAO = (
    ("dias_aviso", "Dias de aviso"),
    ("saldo_salario", "Saldo de salário"),
    ("aviso_indenizado", "Aviso prévio indenizado"),
    ("aviso_desconto", "Desconto do aviso"),
    ("decimo_terceiro", "13º proporcional"),
    ("ferias_vencidas", "Férias vencidas"),
    ("ferias_proporcionais", "Férias proporcionais"),
    ("inss", "INSS"),
    ("irrf_13", "IRRF do 13º"),
    ("irrf", "IRRF total"),
    ("fgts_mes", "FGTS do mês"),
    ("multa_fgts", "Multa do FGTS"),
    ("proventos", "Proventos"),
    ("descontos", "Descontos"),
    ("total_liquido", "Líquido ao trabalhador"),
    ("custo_empregador", "Custo da escola"),
)


def detalhes_rescisao_para_gravar(calculo, params):
    """Cálculo + versão das regras + parâmetros digitados (para recalcular depois sem adivinhar)."""
    dados = dict(calculo)
    dados["versao_regras"] = VERSAO_REGRAS_RESCISAO
    dados["parametros"] = {
        campo: params.get(campo) for campo in CAMPOS_PARAMETROS_RESCISAO if params.get(campo) not in (None, "")
    }
    return dados


def regras_desatualizadas(detalhes):
    return (detalhes or {}).get("versao_regras") != VERSAO_REGRAS_RESCISAO


def parametros_da_rescisao(row, detalhes):
    """Parâmetros usados na rescisão gravada. As antigas não guardavam: reconstrói pelo próprio cálculo."""
    d = detalhes or {}
    row = row or {}
    if d.get("parametros"):
        params = dict(d["parametros"])
    else:
        params = {
            "tipo_rescisao": d.get("tipo_rescisao") or row.get("tipo"),
            "aviso_modalidade": d.get("aviso_modalidade") or row.get("aviso_modalidade"),
            "data_desligamento": d.get("data_desligamento") or row.get("data_desligamento"),
            "dias_trabalhados_mes": d.get("dias_trabalhados_mes"),
            "dias_aviso": d.get("dias_aviso_informado", d.get("dias_aviso")),
            "ferias_vencidas_simples": d.get("ferias_vencidas_simples") or 0,
            "ferias_vencidas_dobro": d.get("ferias_vencidas_dobro") or 0,
            "avos_ferias_proporcionais": d.get("avos_ferias_proporcionais"),
            "avos_13": d.get("avos_13"),
            "saldo_fgts_depositos": d.get("saldo_fgts_depositos") or 0,
            "outros_proventos": d.get("outros_proventos") or 0,
            "outros_descontos": d.get("outros_descontos") or 0,
        }
        if (d.get("direitos") or {}).get("decimo_terceiro") and d.get("avos_13") not in (None, ""):
            bruto = _money(
                _num(d.get("salario_mensal")) * (int(d.get("avos_13")) / 12.0) * float(d.get("fator_proporcionais") or 1.0)
            )
            ja_pago = _money(bruto - _num(d.get("decimo_terceiro")))
            if ja_pago > 0.01:
                params["decimo_ja_pago"] = ja_pago
    for campo in ("data_aviso", "data_pagamento"):
        if params.get(campo) in (None, "") and row.get(campo):
            params[campo] = _as_date(row.get(campo)).isoformat()
    return {k: v for k, v in params.items() if v not in (None, "")}


def contrato_da_rescisao(vinculo, detalhes, funcionario=None):
    """Contrato da época: salário de referência gravado no cálculo e admissão do vínculo encerrado."""
    d = detalhes or {}
    base = dict(funcionario or {})
    base.update({k: v for k, v in dict(vinculo or {}).items() if k in ("tipo_contrato", "salario", "valor_hora", "horas_mes")})
    tipo = base.get("tipo_contrato") or "clt_mensalista"
    if _num(d.get("salario_mensal")) > 0:
        base["salario"] = _num(d.get("salario_mensal"))
        base["tipo_contrato"] = tipo if _eh_aprendiz(tipo) else "clt_mensalista"
    base["data_inicio_contrato"] = d.get("data_admissao") or (vinculo or {}).get("data_inicio") or base.get("data_inicio_contrato")
    return base


def comparar_rescisao(antigo, novo):
    linhas = []
    for chave, rotulo in VERBAS_COMPARACAO:
        a, n = _num((antigo or {}).get(chave)), _num((novo or {}).get(chave))
        linhas.append({"chave": chave, "rotulo": rotulo, "antes": a, "depois": n, "diferenca": round(n - a, 2)})
    return linhas


def aplicar_recalculo_rescisao(cursor, rescisao_id, calculo, params, usuario_id=None, anterior=None):
    """Regrava a rescisão com o cálculo novo, guardando os valores anteriores no histórico do registro."""
    detalhes = detalhes_rescisao_para_gravar(calculo, params)
    ant = anterior or {}
    historico = list(ant.get("recalculos") or [])
    historico.append({
        "em": datetime.now().isoformat(timespec="seconds"),
        "por": usuario_id,
        "versao_anterior": ant.get("versao_regras"),
        "valores_anteriores": {chave: ant.get(chave) for chave, _r in VERBAS_COMPARACAO},
    })
    detalhes["recalculos"] = historico
    terco = _money(_num(calculo.get("terco_ferias_vencidas")) + _num(calculo.get("terco_ferias_proporcionais")))
    cursor.execute(
        """
        UPDATE rescisoes SET
            aviso_modalidade = %s, saldo_salario = %s, aviso_indenizado = %s, aviso_desconto = %s,
            decimo_terceiro = %s, ferias_vencidas = %s, ferias_proporcionais = %s, terco_ferias = %s,
            fgts_mes = %s, multa_fgts = %s, inss = %s, irrf = %s, outros_proventos = %s, outros_descontos = %s,
            total_proventos = %s, total_descontos = %s, total_liquido = %s, detalhes = %s::jsonb
        WHERE id = %s
        """,
        (
            calculo["aviso_modalidade"], calculo["saldo_salario"], calculo["aviso_indenizado"], calculo["aviso_desconto"],
            calculo["decimo_terceiro"], calculo["ferias_vencidas"], calculo["ferias_proporcionais"], terco,
            calculo["fgts_mes"], calculo["multa_fgts"], calculo["inss"], calculo["irrf"],
            calculo["outros_proventos"], calculo["outros_descontos"],
            calculo["proventos"], calculo["descontos"], calculo["total_liquido"],
            json.dumps(detalhes, ensure_ascii=False, default=str),
            rescisao_id,
        ),
    )


TIPOS_RESCISAO = (
    ("sem_justa_causa", "Demissão sem justa causa (empregador)"),
    ("pedido_demissao", "Pedido de demissão (empregado)"),
    ("justa_causa", "Demissão por justa causa"),
    ("acordo_mutuo", "Acordo mútuo (Art. 484-A CLT)"),
    ("culpa_reciproca", "Culpa recíproca"),
    ("termino_prazo", "Término de contrato a prazo determinado"),
)

AVISO_MODALIDADES = (
    ("indenizado", "Indenizado (pago em dinheiro)"),
    ("trabalhado", "Trabalhado (cumprido)"),
    ("dispensado", "Dispensado pelo empregador (sem desconto)"),
    ("nao_cumprido", "Não cumprido pelo empregado (desconto)"),
)

# Dados da pessoa física que podem ser reaproveitados na recontratação
# (mesmo CPF / PIS — vínculo novo; matrícula eSocial e admissão são novos).
DADOS_REAPROVEITAVEIS = (
    "nome_completo",
    "cpf",
    "rg",
    "pis_nit",
    "data_nascimento",
    "telefone",
    "email",
    "foto_url",
    "cep",
    "rua",
    "numero",
    "bairro",
    "cidade",
    "estado",
    "banco",
    "agencia",
    "conta",
    "tipo_conta",
    "pix",
    "formacao",
    "especialidade",
)


def _as_date(valor):
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor)[:10])
    except (TypeError, ValueError):
        return None


def _money(valor):
    return round(_num(valor), 2)


def anos_completos_servico(admissao, desligamento):
    ini = _as_date(admissao)
    fim = _as_date(desligamento)
    if not ini or not fim or fim < ini:
        return 0
    anos = fim.year - ini.year
    if (fim.month, fim.day) < (ini.month, ini.day):
        anos -= 1
    return max(anos, 0)


def dias_aviso_proporcional(admissao, desligamento):
    """Lei 12.506/2011: 30 dias + 3 por ano completo, teto 90."""
    anos = anos_completos_servico(admissao, desligamento)
    return min(30 + 3 * anos, 90)


def avos_periodo(inicio, fim, projetar_dias=0):
    """Conta avos (1/12) com regra dos 15 dias; inclui projeção do aviso indenizado."""
    ini = _as_date(inicio)
    fim = _as_date(fim)
    if not ini or not fim or fim < ini:
        return 0
    fim_proj = fim + timedelta(days=max(int(projetar_dias or 0), 0))
    avos = 0
    y, m = ini.year, ini.month
    while (y, m) <= (fim_proj.year, fim_proj.month):
        primeiro = date(y, m, 1)
        ultimo = date(y, m, monthrange(y, m)[1])
        trecho_ini = max(ini, primeiro)
        trecho_fim = min(fim_proj, ultimo)
        if trecho_fim >= trecho_ini:
            dias = (trecho_fim - trecho_ini).days + 1
            if dias >= 15:
                avos += 1
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
    return min(avos, 12)


def avos_13_ano_civil(admissao, desligamento, projetar_dias=0):
    """Avos de 13º no ano civil do desligamento (máx. 12)."""
    fim = _as_date(desligamento)
    ini = _as_date(admissao)
    if not fim or not ini:
        return 0
    inicio_ano = date(fim.year, 1, 1)
    inicio = max(ini, inicio_ano)
    return min(avos_periodo(inicio, fim, projetar_dias), 12)


def salario_base_diario(func):
    """Salário / 30 para saldo e aviso (CLT). Horista: hora × jornada média / 30."""
    tipo = (func.get("tipo_contrato") or "clt_mensalista").strip().lower()
    salario = _num(func.get("salario"))
    if tipo in ("clt_horista", "horista"):
        vh = _num(func.get("valor_hora")) or hora_normal_clt(func)
        horas = _num(func.get("horas_mes")) or 220.0
        salario = vh * horas if vh > 0 else salario
    if salario <= 0:
        return 0.0
    return round(salario / 30.0, 4)


def salario_mensal_referencia(func):
    tipo = (func.get("tipo_contrato") or "clt_mensalista").strip().lower()
    salario = _num(func.get("salario"))
    if tipo in ("clt_horista", "horista"):
        vh = _num(func.get("valor_hora")) or hora_normal_clt(func)
        horas = _num(func.get("horas_mes")) or 220.0
        if vh > 0:
            return round(vh * horas, 2)
    return _money(salario)


def aliquota_fgts_contrato(tipo_contrato):
    return ALIQUOTA_FGTS_APRENDIZ if _eh_aprendiz(tipo_contrato) else ALIQUOTA_FGTS


def multa_fgts_aliquota(tipo_rescisao):
    if tipo_rescisao == "sem_justa_causa":
        return 0.40
    if tipo_rescisao in ("acordo_mutuo", "culpa_reciproca"):
        return 0.20
    return 0.0


def direitos_por_tipo(tipo_rescisao):
    """Flags de verbas conforme o tipo de rescisão.

    - Justa causa: só saldo e férias vencidas + 1/3 (sem 13º proporcional — Dec. 57.155/65, art. 7º).
    - Pedido de demissão: 13º e férias proporcionais (Súm. 261 TST); sem aviso indenizado, multa ou saque.
    - Acordo (Art. 484-A): metade do aviso indenizado, multa 20%, saque de 80% do FGTS, sem seguro-desemprego.
    - Culpa recíproca (Súm. 14 TST): 50% do aviso, do 13º e das férias proporcionais; multa 20%.
    - Término do prazo: sem aviso e sem multa; saque do FGTS (Lei 8.036, art. 20, IX).
    """
    t = tipo_rescisao or "sem_justa_causa"
    return {
        "saldo_salario": True,
        "aviso_indenizado": t in ("sem_justa_causa", "acordo_mutuo", "culpa_reciproca"),
        "aviso_desconto_pedido": t == "pedido_demissao",
        "decimo_terceiro": t != "justa_causa",
        "ferias_vencidas": True,
        "ferias_proporcionais": t != "justa_causa",
        "multa_fgts": multa_fgts_aliquota(t) > 0,
        "aviso_metade": t in ("acordo_mutuo", "culpa_reciproca"),
        "fator_proporcionais": 0.5 if t == "culpa_reciproca" else 1.0,
        "saque_fgts": t in ("sem_justa_causa", "acordo_mutuo", "culpa_reciproca", "termino_prazo"),
        "saque_fgts_percentual": 0.8 if t == "acordo_mutuo" else (
            1.0 if t in ("sem_justa_causa", "culpa_reciproca", "termino_prazo") else 0.0
        ),
        "seguro_desemprego": t == "sem_justa_causa",
    }


def obrigacoes_rescisao(data_desligamento, regime_tributario=None):
    """Prazos de pagamento e recolhimento após o desligamento."""
    fim = _as_date(data_desligamento) or date.today()
    if fim.month == 12:
        dia20 = date(fim.year + 1, 1, 20)
    else:
        dia20 = date(fim.year, fim.month + 1, 20)
    dez = fim + timedelta(days=10)
    itens = [
        ("Pagamento das verbas ao trabalhador", dez, "Art. 477, § 6º, CLT — atraso gera multa de 1 salário (§ 8º)."),
        ("FGTS rescisório (mês + multa) no FGTS Digital", dez, "Lei 8.036/90, art. 18 — guia rescisória até o 10º dia."),
        ("Evento S-2299 (desligamento) no eSocial", dez, "Até 10 dias do desligamento."),
        ("INSS retido do trabalhador (DCTFWeb)", dia20, "Lei 8.212/91, art. 30, I, b — até o dia 20 do mês seguinte."),
        ("IRRF retido (DCTFWeb/DARF)", dia20, "Até o dia 20 do mês seguinte."),
    ]
    if (regime_tributario or "") not in ("", "simples_nacional"):
        itens.append(
            ("INSS patronal + RAT + terceiros (DCTFWeb)", dia20, "Fora do Simples a cota patronal é recolhida à parte.")
        )
    return [{"item": a, "prazo": b.isoformat(), "base": c} for a, b, c in itens]


def projetar_aviso_dias(tipo_rescisao, aviso_modalidade, dias_aviso):
    """Dias que projetam tempo de serviço (só aviso indenizado pelo empregador)."""
    direitos = direitos_por_tipo(tipo_rescisao)
    if aviso_modalidade != "indenizado":
        return 0
    if not direitos["aviso_indenizado"]:
        return 0
    dias = max(int(dias_aviso or 0), 0)
    if direitos["aviso_metade"]:
        dias = (dias + 1) // 2  # Art. 484-A: metade do aviso
    return dias


def data_limite_pagamento(data_termino):
    """Art. 477 §6º CLT (após Lei 13.467/2017): até 10 dias do término do contrato."""
    fim = _as_date(data_termino)
    if not fim:
        return None
    return fim + timedelta(days=10)


def pagamento_em_atraso(data_termino, data_pagamento):
    limite = data_limite_pagamento(data_termino)
    pag = _as_date(data_pagamento) or date.today()
    if not limite:
        return False, None
    return pag > limite, limite


def calcular_rescisao(func, params):
    """Calcula verbas rescisórias. Campos de params são ajustáveis pela tela.

    params:
      tipo_rescisao, aviso_modalidade, data_desligamento, dias_trabalhados_mes,
      dias_aviso (opcional), ferias_vencidas_simples, ferias_vencidas_dobro,
      avos_ferias_proporcionais (opcional override), avos_13 (opcional),
      saldo_fgts_depositos, outros_proventos, outros_descontos,
      decimo_ja_pago, ind_aviso_manual (override valor aviso)
    """
    tipo = (params.get("tipo_rescisao") or "sem_justa_causa").strip()
    aviso_mod = (params.get("aviso_modalidade") or "indenizado").strip()
    deslig = _as_date(params.get("data_desligamento")) or date.today()
    admissao = (
        _as_date(func.get("data_inicio_contrato"))
        or _as_date(func.get("data_contratacao"))
        or deslig
    )
    direitos = direitos_por_tipo(tipo)
    salario_mes = salario_mensal_referencia(func)
    diario = salario_base_diario(func)

    dias_mes = int(params.get("dias_trabalhados_mes") or deslig.day)
    dias_mes = max(0, min(dias_mes, 31))
    saldo_salario = _money(diario * dias_mes) if direitos["saldo_salario"] else 0.0

    dias_aviso = params.get("dias_aviso")
    if dias_aviso is None or dias_aviso == "":
        dias_aviso = dias_aviso_proporcional(admissao, deslig)
    else:
        dias_aviso = max(0, int(dias_aviso))
    dias_aviso_informado = dias_aviso
    if direitos["aviso_desconto_pedido"]:
        # Lei 12.506/2011: a proporcionalidade só favorece o empregado; no pedido o aviso é de 30 dias
        dias_aviso = min(dias_aviso, 30)

    proj_dias = projetar_aviso_dias(tipo, aviso_mod, dias_aviso)

    aviso_valor = 0.0
    aviso_desconto = 0.0
    if params.get("ind_aviso_manual") not in (None, ""):
        aviso_valor = _money(params.get("ind_aviso_manual"))
    elif direitos["aviso_indenizado"] and aviso_mod == "indenizado":
        base_dias = dias_aviso
        if direitos["aviso_metade"]:
            base_dias = (dias_aviso + 1) // 2
        aviso_valor = _money(diario * base_dias)
    elif direitos["aviso_desconto_pedido"] and aviso_mod == "nao_cumprido":
        aviso_desconto = _money(diario * dias_aviso)

    fator = float(direitos.get("fator_proporcionais") or 1.0)

    # 13º proporcional (os avos ganhos só pela projeção do aviso indenizado são 13º indenizado)
    avos_sem_projecao = avos_13_ano_civil(admissao, deslig, 0)
    avos_13 = params.get("avos_13")
    if avos_13 in (None, ""):
        avos_13 = avos_13_ano_civil(admissao, deslig, proj_dias if aviso_mod == "indenizado" else 0)
    else:
        avos_13 = max(0, min(int(avos_13), 12))
    avos_13_indenizado = max(avos_13 - avos_sem_projecao, 0)
    decimo = 0.0
    decimo_indenizado = 0.0
    if direitos["decimo_terceiro"]:
        decimo_bruto = _money(salario_mes * (avos_13 / 12.0) * fator)
        decimo_indenizado = _money(salario_mes * (avos_13_indenizado / 12.0) * fator)
        decimo = _money(max(decimo_bruto - _num(params.get("decimo_ja_pago")), 0))
        decimo_indenizado = min(decimo_indenizado, decimo)
    decimo_trabalhado = _money(decimo - decimo_indenizado)

    # Férias
    ferias_simples = max(int(params.get("ferias_vencidas_simples") or 0), 0)
    ferias_dobro = max(int(params.get("ferias_vencidas_dobro") or 0), 0)
    ferias_venc_valor = _money(salario_mes * ferias_simples + salario_mes * 2 * ferias_dobro)
    terco_venc = _money(ferias_venc_valor / 3.0) if direitos["ferias_vencidas"] else 0.0
    if not direitos["ferias_vencidas"]:
        ferias_venc_valor = 0.0

    avos_fer = params.get("avos_ferias_proporcionais")
    if avos_fer in (None, ""):
        # Período aquisitivo corrente: a partir do último aniversário de admissão
        anos = anos_completos_servico(admissao, deslig)
        try:
            inicio_aquisitivo = date(admissao.year + anos, admissao.month, admissao.day)
        except ValueError:
            inicio_aquisitivo = date(admissao.year + anos, admissao.month, 28)
        avos_fer = avos_periodo(
            inicio_aquisitivo,
            deslig,
            proj_dias if aviso_mod == "indenizado" else 0,
        )
        avos_fer = min(avos_fer, 12)
    else:
        avos_fer = max(0, min(int(avos_fer), 12))

    ferias_prop = 0.0
    terco_prop = 0.0
    if direitos["ferias_proporcionais"] and avos_fer > 0:
        ferias_prop = _money(salario_mes * (avos_fer / 12.0) * fator)
        terco_prop = _money(ferias_prop / 3.0)

    outros_prov = _money(params.get("outros_proventos"))
    outros_desc = _money(params.get("outros_descontos"))

    # Incidência por verba:
    # - saldo de salário (e outros proventos salariais): INSS, IRRF e FGTS
    # - 13º: INSS e IRRF calculados à parte (tributação exclusiva); FGTS sim.
    #   A parcela indenizada (projeção do aviso) não tem INSS.
    # - aviso prévio indenizado: só FGTS (Súm. 305 TST); sem INSS (STJ Tema 478) e sem IRRF
    # - férias indenizadas + 1/3 (vencidas, em dobro e proporcionais): sem INSS, IRRF e FGTS
    #   (Lei 8.212/91, art. 28, § 9º, d; Súm. 125 e 386 STJ)
    base_mensal = _money(saldo_salario + outros_prov)
    ano_ref, mes_ref = deslig.year, deslig.month
    inss_mensal = inss_empregado(base_mensal, ano_ref, mes_ref)
    irrf_mensal = calcular_irrf_mensal(base_mensal, inss_mensal, ano_ref, mes_ref)["irrf"]
    inss_13 = inss_empregado(decimo_trabalhado, ano_ref, mes_ref)
    irrf_13_tabela = irrf_progressivo(max(decimo - inss_13, 0), ano_ref, mes_ref)
    modo_redutor_13 = normalizar_redutor_13(params.get("irrf_13_redutor"))
    irrf_13_redutor = 0.0
    if modo_redutor_13 != "nao":
        rendimento_redutor = decimo if modo_redutor_13 == "bruto" else max(decimo - inss_13, 0)
        irrf_13_redutor = redutor_irrf(rendimento_redutor, irrf_13_tabela, ano_ref, mes_ref)
    irrf_13 = _money(irrf_13_tabela - irrf_13_redutor)
    inss = _money(inss_mensal + inss_13)
    irrf = _money(irrf_mensal + irrf_13)

    # FGTS do mês + multa
    aliq = aliquota_fgts_contrato(func.get("tipo_contrato"))
    base_fgts_mes = _money(base_mensal + decimo + (aviso_valor if aviso_mod == "indenizado" else 0.0))
    fgts_mes = _money(base_fgts_mes * aliq)
    saldo_depositos = _money(params.get("saldo_fgts_depositos"))
    # Inclui depósito do mês da rescisão na base da multa se informado
    base_multa = _money(saldo_depositos + fgts_mes)
    aliq_multa = multa_fgts_aliquota(tipo)
    multa_fgts = _money(base_multa * aliq_multa) if direitos["multa_fgts"] else 0.0
    saque_pct = float(direitos.get("saque_fgts_percentual") or 0.0)
    saque_fgts_estimado = _money((saldo_depositos + fgts_mes) * saque_pct + multa_fgts) if saque_pct else 0.0

    atrasado, limite_pag = pagamento_em_atraso(deslig, params.get("data_pagamento"))
    # Art. 477, § 8º: atraso na quitação gera multa de um salário ao trabalhador (verba indenizatória)
    multa_art_477 = salario_mes if atrasado and params.get("data_pagamento") else 0.0

    proventos = _money(
        saldo_salario
        + aviso_valor
        + decimo
        + ferias_venc_valor
        + terco_venc
        + ferias_prop
        + terco_prop
        + outros_prov
        + multa_art_477
    )
    descontos = _money(aviso_desconto + outros_desc + inss + irrf)
    total_liquido = _money(proventos - descontos)

    # Cota patronal: no Simples (Anexos III e V) a CPP já está no DAS.
    regime = (params.get("regime_tributario") or "simples_nacional").strip().lower()
    base_patronal = _money(base_mensal + decimo_trabalhado)
    aliq_patronal = 0.0 if regime == "simples_nacional" else (ALIQUOTA_INSS_PATRONAL + ALIQUOTA_RAT + ALIQUOTA_SISTEMA_S)
    inss_patronal = _money(base_patronal * aliq_patronal)

    # Custo da escola: verbas ao trabalhador (líquido + retenções) + FGTS + multa + patronal
    custo_empregador = _money(total_liquido + inss + irrf + fgts_mes + multa_fgts + inss_patronal)

    return {
        "tipo_rescisao": tipo,
        "aviso_modalidade": aviso_mod,
        "data_admissao": admissao.isoformat(),
        "data_desligamento": deslig.isoformat(),
        "dias_trabalhados_mes": dias_mes,
        "dias_aviso": dias_aviso,
        "dias_aviso_informado": dias_aviso_informado,
        "dias_aviso_projecao": proj_dias,
        "salario_mensal": salario_mes,
        "salario_diario": _money(diario),
        "saldo_salario": saldo_salario,
        "aviso_indenizado": aviso_valor,
        "aviso_desconto": aviso_desconto,
        "avos_13": avos_13,
        "avos_13_indenizado": avos_13_indenizado,
        "decimo_terceiro": decimo,
        "decimo_indenizado": decimo_indenizado,
        "decimo_trabalhado": decimo_trabalhado,
        "fator_proporcionais": fator,
        "ferias_vencidas_simples": ferias_simples,
        "ferias_vencidas_dobro": ferias_dobro,
        "ferias_vencidas": ferias_venc_valor,
        "terco_ferias_vencidas": terco_venc,
        "avos_ferias_proporcionais": avos_fer,
        "ferias_proporcionais": ferias_prop,
        "terco_ferias_proporcionais": terco_prop,
        "fgts_mes": fgts_mes,
        "aliquota_fgts": aliq,
        "saldo_fgts_depositos": saldo_depositos,
        "aliquota_multa_fgts": aliq_multa,
        "multa_fgts": multa_fgts,
        "outros_proventos": outros_prov,
        "outros_descontos": outros_desc,
        "base_inss_mensal": base_mensal,
        "inss_mensal": inss_mensal,
        "irrf_mensal": irrf_mensal,
        "inss_13": inss_13,
        "irrf_13": irrf_13,
        "irrf_13_tabela": irrf_13_tabela,
        "irrf_13_redutor": irrf_13_redutor,
        "irrf_13_redutor_modo": modo_redutor_13,
        "rotulo_redutor_13": dict(REDUTOR_13_OPCOES)[modo_redutor_13],
        "inss": inss,
        "irrf": irrf,
        "base_fgts_mes": base_fgts_mes,
        "saque_fgts_percentual": saque_pct,
        "saque_fgts_estimado": saque_fgts_estimado,
        "multa_art_477": multa_art_477,
        "regime_tributario": regime,
        "base_patronal": base_patronal,
        "aliquota_patronal": aliq_patronal,
        "inss_patronal": inss_patronal,
        "proventos": proventos,
        "descontos": descontos,
        "total_liquido": total_liquido,
        "custo_empregador": custo_empregador,
        "data_limite_pagamento": limite_pag.isoformat() if limite_pag else None,
        "pagamento_atrasado": atrasado,
        "obrigacoes": obrigacoes_rescisao(deslig, regime),
        "seguro_desemprego": bool(direitos.get("seguro_desemprego")),
        "direitos": direitos,
        "rotulo_tipo": dict(TIPOS_RESCISAO).get(tipo, tipo),
        "rotulo_aviso": dict(AVISO_MODALIDADES).get(aviso_mod, aviso_mod),
    }


def garantir_tabelas_rescisao(cursor):
    """Cria vínculos/rescisões e faz backfill a partir de funcionarios."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS funcionario_vinculos (
            id SERIAL PRIMARY KEY,
            funcionario_id INT NOT NULL REFERENCES funcionarios(id) ON DELETE CASCADE,
            matricula_esocial VARCHAR(40),
            data_inicio DATE NOT NULL,
            data_fim DATE,
            tipo_contrato VARCHAR(30) DEFAULT 'clt_mensalista',
            cargo VARCHAR(150),
            salario NUMERIC(12,2) DEFAULT 0,
            valor_hora NUMERIC(12,2) DEFAULT 0,
            horas_mes NUMERIC(10,2) DEFAULT 0,
            situacao VARCHAR(30) DEFAULT 'ativo',
            motivo_encerramento VARCHAR(40),
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    try:
        cursor.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_vinculo_aberto
            ON funcionario_vinculos (funcionario_id)
            WHERE data_fim IS NULL AND situacao = 'ativo'
            """
        )
    except Exception:
        pass
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS rescisoes (
            id SERIAL PRIMARY KEY,
            vinculo_id INT NOT NULL UNIQUE REFERENCES funcionario_vinculos(id) ON DELETE CASCADE,
            funcionario_id INT NOT NULL REFERENCES funcionarios(id) ON DELETE CASCADE,
            data_aviso DATE,
            data_desligamento DATE NOT NULL,
            data_pagamento DATE,
            tipo VARCHAR(40) NOT NULL,
            aviso_modalidade VARCHAR(20),
            saldo_salario NUMERIC(12,2) DEFAULT 0,
            aviso_indenizado NUMERIC(12,2) DEFAULT 0,
            aviso_desconto NUMERIC(12,2) DEFAULT 0,
            decimo_terceiro NUMERIC(12,2) DEFAULT 0,
            ferias_vencidas NUMERIC(12,2) DEFAULT 0,
            ferias_proporcionais NUMERIC(12,2) DEFAULT 0,
            terco_ferias NUMERIC(12,2) DEFAULT 0,
            fgts_mes NUMERIC(12,2) DEFAULT 0,
            multa_fgts NUMERIC(12,2) DEFAULT 0,
            inss NUMERIC(12,2) DEFAULT 0,
            irrf NUMERIC(12,2) DEFAULT 0,
            outros_proventos NUMERIC(12,2) DEFAULT 0,
            outros_descontos NUMERIC(12,2) DEFAULT 0,
            total_proventos NUMERIC(12,2) DEFAULT 0,
            total_descontos NUMERIC(12,2) DEFAULT 0,
            total_liquido NUMERIC(12,2) DEFAULT 0,
            remover_usuario BOOLEAN DEFAULT FALSE,
            detalhes JSONB,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            criado_por INT
        )
        """
    )
    # Colunas de apoio no cadastro da pessoa
    for col, spec in (
        ("situacao", "VARCHAR(30) DEFAULT 'ativo'"),
        ("matricula_esocial", "VARCHAR(40)"),
    ):
        try:
            cursor.execute(f"ALTER TABLE funcionarios ADD COLUMN IF NOT EXISTS {col} {spec}")
        except Exception:
            pass

    # Backfill: um vínculo por funcionário que ainda não tenha histórico
    cursor.execute(
        """
        INSERT INTO funcionario_vinculos (
            funcionario_id, matricula_esocial, data_inicio, data_fim, tipo_contrato, cargo,
            salario, valor_hora, horas_mes, situacao, motivo_encerramento
        )
        SELECT f.id,
               f.matricula_esocial,
               COALESCE(f.data_inicio_contrato, f.data_contratacao, CURRENT_DATE),
               CASE WHEN COALESCE(f.ativo, TRUE) = FALSE OR f.data_fim_contrato IS NOT NULL
                    THEN COALESCE(f.data_fim_contrato, CURRENT_DATE) ELSE NULL END,
               COALESCE(NULLIF(f.tipo_contrato, ''), 'clt_mensalista'),
               f.cargo,
               COALESCE(f.salario, 0),
               COALESCE(f.valor_hora, 0),
               COALESCE(f.horas_mes, 0),
               CASE WHEN COALESCE(f.ativo, TRUE) = FALSE OR LOWER(COALESCE(f.situacao, '')) = 'rescindido'
                    THEN 'rescindido' ELSE 'ativo' END,
               NULL
        FROM funcionarios f
        WHERE NOT EXISTS (
            SELECT 1 FROM funcionario_vinculos v WHERE v.funcionario_id = f.id
        )
        """
    )
    cursor.execute(
        """
        UPDATE funcionarios
        SET situacao = CASE
            WHEN COALESCE(ativo, TRUE) = FALSE THEN 'rescindido'
            ELSE COALESCE(NULLIF(situacao, ''), 'ativo')
        END
        WHERE situacao IS NULL OR TRIM(situacao) = ''
        """
    )


def vinculo_aberto(cursor, funcionario_id):
    cursor.execute(
        """
        SELECT * FROM funcionario_vinculos
        WHERE funcionario_id = %s AND data_fim IS NULL AND situacao = 'ativo'
        ORDER BY id DESC LIMIT 1
        """,
        (funcionario_id,),
    )
    return cursor.fetchone()


def sincronizar_vinculo_do_funcionario(cursor, funcionario_id, dados):
    """Mantém o vínculo aberto alinhado ao cache em funcionarios (folha atual)."""
    aberto = vinculo_aberto(cursor, funcionario_id)
    inicio = (
        _as_date(dados.get("data_inicio_contrato"))
        or _as_date(dados.get("data_contratacao"))
        or date.today()
    )
    fim = _as_date(dados.get("data_fim_contrato"))
    situacao = "rescindido" if (dados.get("ativo") is False or fim) else "ativo"
    if situacao == "rescindido" and not fim:
        fim = date.today()
    vals = (
        dados.get("matricula_esocial"),
        inicio,
        fim if situacao == "rescindido" else None,
        dados.get("tipo_contrato") or "clt_mensalista",
        dados.get("cargo"),
        _num(dados.get("salario")),
        _num(dados.get("valor_hora")),
        _num(dados.get("horas_mes")),
        situacao,
        funcionario_id,
    )
    if aberto:
        cursor.execute(
            """
            UPDATE funcionario_vinculos SET
                matricula_esocial = COALESCE(%s, matricula_esocial),
                data_inicio = %s,
                data_fim = %s,
                tipo_contrato = %s,
                cargo = %s,
                salario = %s,
                valor_hora = %s,
                horas_mes = %s,
                situacao = %s
            WHERE id = %s
            """,
            vals[:-1] + (aberto["id"],),
        )
        return aberto["id"]
    cursor.execute(
        """
        INSERT INTO funcionario_vinculos (
            funcionario_id, matricula_esocial, data_inicio, data_fim, tipo_contrato, cargo,
            salario, valor_hora, horas_mes, situacao
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (funcionario_id,) + vals[:-1],
    )
    row = cursor.fetchone()
    return row["id"] if row else None


def encerrar_vinculo_e_salvar_rescisao(cursor, funcionario_id, calculo, params, usuario_id=None):
    """Fecha vínculo, grava rescisão, marca pessoa como rescindida e opcionalmente remove login."""
    aberto = vinculo_aberto(cursor, funcionario_id)
    deslig = _as_date(calculo["data_desligamento"])
    if not aberto:
        # Garante vínculo a partir do cadastro atual
        cursor.execute("SELECT * FROM funcionarios WHERE id = %s", (funcionario_id,))
        func = cursor.fetchone() or {}
        sincronizar_vinculo_do_funcionario(
            cursor,
            funcionario_id,
            {
                **dict(func),
                "ativo": True,
                "data_fim_contrato": None,
            },
        )
        aberto = vinculo_aberto(cursor, funcionario_id)
    if not aberto:
        raise ValueError("Não há vínculo ativo para rescindir.")

    cursor.execute(
        """
        UPDATE funcionario_vinculos
        SET data_fim = %s, situacao = 'rescindido', motivo_encerramento = %s
        WHERE id = %s
        """,
        (deslig, calculo["tipo_rescisao"], aberto["id"]),
    )

    terco = _money(
        _num(calculo.get("terco_ferias_vencidas")) + _num(calculo.get("terco_ferias_proporcionais"))
    )
    detalhes = json.dumps(detalhes_rescisao_para_gravar(calculo, params), ensure_ascii=False, default=str)
    cursor.execute(
        """
        INSERT INTO rescisoes (
            vinculo_id, funcionario_id, data_aviso, data_desligamento, data_pagamento,
            tipo, aviso_modalidade, saldo_salario, aviso_indenizado, aviso_desconto,
            decimo_terceiro, ferias_vencidas, ferias_proporcionais, terco_ferias,
            fgts_mes, multa_fgts, inss, irrf, outros_proventos, outros_descontos,
            total_proventos, total_descontos, total_liquido, remover_usuario, detalhes, criado_por
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s::jsonb, %s
        )
        RETURNING id
        """,
        (
            aberto["id"],
            funcionario_id,
            _as_date(params.get("data_aviso")),
            deslig,
            _as_date(params.get("data_pagamento")),
            calculo["tipo_rescisao"],
            calculo["aviso_modalidade"],
            calculo["saldo_salario"],
            calculo["aviso_indenizado"],
            calculo["aviso_desconto"],
            calculo["decimo_terceiro"],
            calculo["ferias_vencidas"],
            calculo["ferias_proporcionais"],
            terco,
            calculo["fgts_mes"],
            calculo["multa_fgts"],
            calculo["inss"],
            calculo["irrf"],
            calculo["outros_proventos"],
            calculo["outros_descontos"],
            calculo["proventos"],
            calculo["descontos"],
            calculo["total_liquido"],
            bool(params.get("remover_usuario")),
            detalhes,
            usuario_id,
        ),
    )
    rescisao_id = cursor.fetchone()["id"]

    cursor.execute(
        """
        UPDATE funcionarios SET
            ativo = FALSE,
            situacao = 'rescindido',
            data_fim_contrato = %s,
            enviar_contracheque = FALSE
        WHERE id = %s
        """,
        (deslig, funcionario_id),
    )

    removido_login = False
    if params.get("remover_usuario"):
        cursor.execute("SELECT usuario_id FROM funcionarios WHERE id = %s", (funcionario_id,))
        row = cursor.fetchone() or {}
        uid = row.get("usuario_id")
        if uid:
            cursor.execute("UPDATE funcionarios SET usuario_id = NULL WHERE id = %s", (funcionario_id,))
            cursor.execute("DELETE FROM usuarios WHERE id = %s", (uid,))
            removido_login = True

    return rescisao_id, removido_login


DIAS_READMISSAO_SUSPEITA = 90


def alerta_readmissao(historico):
    """Portaria MTb 384/1992: readmitir em até 90 dias após dispensa sem justa causa presume fraude ao FGTS."""
    ultimo = next((v for v in historico or [] if v.get("rescisao_data")), None)
    if not ultimo or (ultimo.get("rescisao_tipo") or "") != "sem_justa_causa":
        return None
    desligamento = _as_date(ultimo.get("rescisao_data"))
    if not desligamento:
        return None
    return {
        "data_desligamento": desligamento,
        "data_limite": desligamento + timedelta(days=DIAS_READMISSAO_SUSPEITA),
    }


def recontratar_funcionario(cursor, funcionario_id, novo_contrato):
    """Abre novo vínculo reaproveitando dados cadastrais da pessoa.

    novo_contrato: data_inicio, cargo, tipo_contrato, salario, valor_hora, horas_mes,
                   matricula_esocial, dia_pagamento, ciente_readmissao_90
    """
    cursor.execute("SELECT * FROM funcionarios WHERE id = %s", (funcionario_id,))
    pessoa = cursor.fetchone()
    if not pessoa:
        raise ValueError("Funcionário não encontrado.")
    aberto = vinculo_aberto(cursor, funcionario_id)
    if aberto:
        raise ValueError("Já existe um vínculo ativo. Encerre a rescisão antes de recontratar.")

    inicio = _as_date(novo_contrato.get("data_inicio")) or date.today()
    alerta = alerta_readmissao(listar_historico_vinculos(cursor, funcionario_id))
    if alerta and inicio < alerta["data_limite"] and not novo_contrato.get("ciente_readmissao_90"):
        raise ValueError(
            f"A dispensa sem justa causa foi em {alerta['data_desligamento'].strftime('%d/%m/%Y')}. "
            f"Readmitir antes de {alerta['data_limite'].strftime('%d/%m/%Y')} (90 dias) presume fraude "
            "(Portaria MTb 384/1992). Marque que está ciente para continuar."
        )
    tipo = novo_contrato.get("tipo_contrato") or "clt_mensalista"
    cargo = (novo_contrato.get("cargo") or pessoa.get("cargo") or "Funcionário").strip()
    salario = _num(novo_contrato.get("salario"))
    valor_hora = _num(novo_contrato.get("valor_hora"))
    horas_mes = _num(novo_contrato.get("horas_mes"))
    matricula = (novo_contrato.get("matricula_esocial") or "").strip() or None

    cursor.execute(
        """
        INSERT INTO funcionario_vinculos (
            funcionario_id, matricula_esocial, data_inicio, data_fim, tipo_contrato, cargo,
            salario, valor_hora, horas_mes, situacao
        ) VALUES (%s, %s, %s, NULL, %s, %s, %s, %s, %s, 'ativo')
        RETURNING id
        """,
        (funcionario_id, matricula, inicio, tipo, cargo, salario, valor_hora, horas_mes),
    )
    vid = cursor.fetchone()["id"]

    cursor.execute(
        """
        UPDATE funcionarios SET
            ativo = TRUE,
            situacao = 'ativo',
            data_contratacao = %s,
            data_inicio_contrato = %s,
            data_fim_contrato = NULL,
            cargo = %s,
            tipo_contrato = %s,
            salario = %s,
            valor_hora = %s,
            horas_mes = %s,
            matricula_esocial = %s,
            dia_pagamento = COALESCE(%s, dia_pagamento, 5),
            enviar_contracheque = TRUE
        WHERE id = %s
        """,
        (
            inicio,
            inicio,
            cargo,
            tipo,
            salario,
            valor_hora,
            horas_mes,
            matricula,
            novo_contrato.get("dia_pagamento"),
            funcionario_id,
        ),
    )
    return vid


def listar_historico_vinculos(cursor, funcionario_id):
    cursor.execute(
        """
        SELECT v.*, r.id AS rescisao_id, r.tipo AS rescisao_tipo, r.total_liquido, r.data_desligamento AS rescisao_data,
               r.detalhes->>'versao_regras' AS rescisao_versao_regras
        FROM funcionario_vinculos v
        LEFT JOIN rescisoes r ON r.vinculo_id = v.id
        WHERE v.funcionario_id = %s
        ORDER BY v.data_inicio DESC, v.id DESC
        """,
        (funcionario_id,),
    )
    return list(cursor.fetchall() or [])


def decimal_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError
