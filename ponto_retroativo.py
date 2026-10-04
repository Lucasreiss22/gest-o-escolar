"""Regras do ponto retroativo e da correção de batidas.

O pedido não grava em ponto_registros. Só a aprovação aplica o dia,
e é essa tabela que a folha usa para horas extras.
"""

from __future__ import annotations

import re
from datetime import date, datetime

MARCAS = ("entrada", "cafe_ida", "cafe_volta", "almoco", "almoco_volta", "saida")

ROTULOS = {
    "entrada": "Entrada",
    "cafe_ida": "Café (ida)",
    "cafe_volta": "Café (volta)",
    "almoco": "Almoço (ida)",
    "almoco_volta": "Almoço (volta)",
    "saida": "Saída",
}

STATUS_ROTULO = {
    "pendente": "Pendente",
    "aprovado": "Aprovado",
    "rejeitado": "Rejeitado",
    "cancelado": "Cancelado",
}

TIPO_ROTULO = {
    "retroativo": "Retroativo",
    "correcao": "Correção",
}

_PARES = (
    ("cafe_ida", "cafe_volta", "a ida do café", "a volta do café"),
    ("almoco", "almoco_volta", "a ida do almoço", "a volta do almoço"),
)


def fmt_hora(valor):
    if valor is None:
        return ""
    if isinstance(valor, datetime):
        return valor.strftime("%H:%M")
    if hasattr(valor, "hour") and hasattr(valor, "minute") and not hasattr(valor, "year"):
        return f"{int(valor.hour):02d}:{int(valor.minute):02d}"
    if hasattr(valor, "strftime") and not hasattr(valor, "year"):
        return valor.strftime("%H:%M")
    texto = str(valor).strip()
    if not texto or texto.lower() in {"none", "null"}:
        return ""
    if " " in texto:
        texto = texto.split(" ")[-1]
    if "T" in texto:
        texto = texto.split("T")[-1]
    return texto[:5]


def normalizar_hora(valor):
    """Devolve HH:MM ou None se vazio. Horário impossível gera erro."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.strftime("%H:%M")
    if hasattr(valor, "hour") and hasattr(valor, "minute") and not hasattr(valor, "year"):
        hora = int(valor.hour)
        minuto = int(valor.minute)
        if hora > 23 or minuto > 59:
            raise ValueError(f"Horário inválido: {hora:02d}:{minuto:02d}.")
        return f"{hora:02d}:{minuto:02d}"
    texto = str(valor).strip()
    if not texto:
        return None
    if " " in texto:
        texto = texto.split(" ")[-1]
    if "T" in texto:
        texto = texto.split("T")[-1]
    texto = texto[:5]
    if not re.fullmatch(r"\d{1,2}:\d{2}", texto):
        raise ValueError("Horário inválido. Use o formato HH:MM.")
    hora, minuto = (int(parte) for parte in texto.split(":"))
    if hora > 23 or minuto > 59:
        raise ValueError(f"Horário inválido: {texto}.")
    return f"{hora:02d}:{minuto:02d}"


def _minutos(hhmm):
    hora, minuto = (int(parte) for parte in hhmm.split(":"))
    return hora * 60 + minuto


def parse_data(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor or "").strip()[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", texto):
        raise ValueError("Informe uma data válida.")
    ano, mes, dia = (int(parte) for parte in texto.split("-"))
    try:
        return date(ano, mes, dia)
    except ValueError as erro:
        raise ValueError("Informe uma data válida.") from erro


def validar_justificativa(texto):
    texto = (texto or "").strip()
    if len(texto) < 3:
        raise ValueError("A justificativa é obrigatória.")
    if len(texto) > 2000:
        raise ValueError("A justificativa deve ter no máximo 2000 caracteres.")
    return texto


def validar_data(data_ref, hoje, permitir_hoje=False):
    data_ref = parse_data(data_ref)
    hoje = parse_data(hoje)
    if data_ref.year < 2000:
        raise ValueError("Data inválida.")
    if data_ref > hoje:
        raise ValueError("Não é possível lançar ponto em data futura.")
    if data_ref == hoje and not permitir_hoje:
        raise ValueError(
            "Para o dia de hoje use as batidas normais do ponto. "
            "O pedido retroativo é para dias anteriores."
        )
    return data_ref


def validar_competencia_aberta(data_ref, competencias_fechadas=()):
    """Bloqueia o mês se a folha da competência (YYYY-MM) já estiver fechada."""
    data_ref = parse_data(data_ref)
    competencia = f"{data_ref.year:04d}-{data_ref.month:02d}"
    fechadas = {str(item)[:7] for item in (competencias_fechadas or ()) if item}
    if competencia in fechadas:
        raise ValueError(
            f"A folha de {competencia[5:7]}/{competencia[0:4]} já está fechada. "
            "Não é possível lançar ou corrigir ponto nesse mês."
        )
    return competencia


def pedidas_do_mapa(mapa):
    pedidas = {}
    origem = mapa or {}
    for marca in MARCAS:
        hora = normalizar_hora(origem.get(marca))
        if hora:
            pedidas[marca] = hora
    if not pedidas:
        raise ValueError("Informe ao menos um horário (entrada, café, almoço ou saída).")
    return pedidas


def mesclar(atuais, pedidas):
    resultado = {}
    for marca in MARCAS:
        resultado[marca] = fmt_hora((atuais or {}).get(marca))
    for marca, hora in (pedidas or {}).items():
        if marca in resultado and hora:
            resultado[marca] = hora
    return resultado


def validar_ordem(marcas):
    """Ordem do dia e pares de intervalo no resultado já mesclado."""
    presentes = {}
    for marca in MARCAS:
        hora = fmt_hora((marcas or {}).get(marca))
        if hora:
            presentes[marca] = normalizar_hora(hora)
    if not presentes:
        raise ValueError("Informe ao menos um horário (entrada, café, almoço ou saída).")
    for ida, volta, rotulo_ida, rotulo_volta in _PARES:
        if ida in presentes and volta not in presentes:
            raise ValueError(f"Informe também {rotulo_volta}.")
        if volta in presentes and ida not in presentes:
            raise ValueError(f"Informe também {rotulo_ida}.")
    if any(marca != "entrada" for marca in presentes) and "entrada" not in presentes:
        raise ValueError("Informe a entrada. Os outros horários dependem dela.")
    anterior = None
    anterior_rotulo = None
    anterior_hora = None
    for marca in MARCAS:
        if marca not in presentes:
            continue
        minutos = _minutos(presentes[marca])
        if anterior is not None and minutos <= anterior:
            raise ValueError(
                "Os horários precisam seguir a ordem do dia. "
                f"{ROTULOS[marca]} ({presentes[marca]}) não pode ser igual ou anterior a "
                f"{anterior_rotulo} ({anterior_hora})."
            )
        anterior = minutos
        anterior_rotulo = ROTULOS[marca]
        anterior_hora = presentes[marca]
    return presentes


def houve_mudanca(atuais, pedidas):
    for marca, hora in (pedidas or {}).items():
        if fmt_hora((atuais or {}).get(marca)) != hora:
            return True
    return False


def validar_pedido(
    atuais,
    pedidas,
    data_ref,
    hoje,
    modo="retroativo",
    competencias_fechadas=(),
    exigir_mudanca=True,
):
    """Valida o pedido e devolve tipo, marcas pedidas e o dia resultante.

    modo retroativo: só dia anterior.
    modo correcao: dia atual só se já existir alguma batida; dias anteriores também.
    """
    modo = (modo or "retroativo").strip().lower()
    if modo not in {"retroativo", "correcao"}:
        raise ValueError("Tipo de lançamento inválido.")
    data_ok = validar_data(data_ref, hoje, permitir_hoje=(modo == "correcao"))
    validar_competencia_aberta(data_ok, competencias_fechadas)
    atuais_fmt = {marca: fmt_hora((atuais or {}).get(marca)) for marca in MARCAS}
    pedidas_ok = pedidas_do_mapa(pedidas)
    if modo == "correcao" and data_ok == parse_data(hoje):
        if not any(atuais_fmt.values()):
            raise ValueError(
                "Para corrigir o dia de hoje já precisa existir uma batida. "
                "O ponto de hoje continua pelas batidas normais."
            )
    resultado = mesclar(atuais_fmt, pedidas_ok)
    validar_ordem(resultado)
    if exigir_mudanca and not houve_mudanca(atuais_fmt, pedidas_ok):
        raise ValueError("Nenhum horário diferente do que já está registrado nesse dia.")
    tipo = "retroativo"
    if modo == "correcao" and data_ok == parse_data(hoje):
        tipo = "correcao"
    for marca, hora in pedidas_ok.items():
        atual = atuais_fmt.get(marca) or ""
        if atual and atual != hora:
            tipo = "correcao"
            break
    return {
        "tipo": tipo,
        "data_ref": data_ok,
        "pedidas": pedidas_ok,
        "atuais": atuais_fmt,
        "resultado": resultado,
    }


def pedidas_da_linha(row):
    row = row or {}
    pedidas = {}
    for marca in MARCAS:
        if not row.get(f"altera_{marca}"):
            continue
        hora = normalizar_hora(row.get(marca))
        if not hora:
            raise ValueError(f"A solicitação não tem horário de {ROTULOS[marca]}.")
        pedidas[marca] = hora
    if not pedidas:
        raise ValueError("A solicitação não tem horários para lançar.")
    return pedidas


def linhas_comparacao(pedidas, origens):
    linhas = []
    for marca in MARCAS:
        if marca not in (pedidas or {}):
            continue
        antes = fmt_hora((origens or {}).get(marca)) or "—"
        depois = fmt_hora(pedidas.get(marca)) or "—"
        linhas.append(
            {
                "campo": marca,
                "rotulo": ROTULOS[marca],
                "antes": antes,
                "depois": depois,
            }
        )
    return linhas
