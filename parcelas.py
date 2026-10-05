"""Quais parcelas de um contrato podem ser geradas agora.

Padrão: do mês atual em diante. Meses passados só com confirmação de quem cadastra.
Competência já apurada nunca recebe parcela nova: mudaria receita e tributos já declarados.
Simples: PGDAS-D vencido (dia 20 do mês seguinte). Presumido/Real: trimestre com DARF vencida
(último dia útil do mês seguinte ao trimestre).
"""

import calendar
import re
from datetime import date, datetime, timedelta

from feriados import feriados_nacionais
from simples_nacional import _ORIGENS_CONGELADAS

DIA_LIMITE_PGDAS = 20
REGIMES_TRIMESTRAIS = ("lucro_presumido", "lucro_real")
_SCHEMA_OK = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def add_meses(data_ref, meses):
    if isinstance(data_ref, str):
        data_ref = datetime.strptime(data_ref[:10], "%Y-%m-%d").date()
    elif isinstance(data_ref, datetime):
        data_ref = data_ref.date()
    total = data_ref.year * 12 + (data_ref.month - 1) + int(meses)
    ano, mes = divmod(total, 12)
    dia = min(data_ref.day, calendar.monthrange(ano, mes + 1)[1])
    return date(ano, mes + 1, dia)


def _comp_menos(hoje, meses):
    total = hoje.year * 12 + (hoje.month - 1) - meses
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def _ultimo_dia_util(ano, mes, feriados=None):
    """Último dia do mês que não é sábado, domingo nem feriado nacional (Carnaval e Corpus Christi são
    ponto facultativo e não contam). `feriados`: conjunto de datas para testes."""
    if feriados is None:
        feriados = set(feriados_nacionais(ano))
    dia = date(ano, mes, calendar.monthrange(ano, mes)[1])
    while dia.weekday() >= 5 or dia in feriados:
        dia -= timedelta(days=1)
    return dia


def vencimento_trimestre(comp, feriados=None):
    """DARF trimestral de IRPJ/CSLL da competência: último dia útil do mês seguinte ao fim do trimestre."""
    ano, mes = int(comp[:4]), int(comp[5:7])
    fim = ((mes - 1) // 3 + 1) * 3
    ano_v, mes_v = (ano + 1, 1) if fim == 12 else (ano, fim + 1)
    return _ultimo_dia_util(ano_v, mes_v, feriados)


def limite_apurado(hoje, regime_tributario):
    """Última competência já apurada e vencida. None sem regime informado."""
    regime = regime_tributario or ""
    if regime == "simples_nacional":
        return _comp_menos(hoje, 1 if hoje.day > DIA_LIMITE_PGDAS else 2)
    if regime in REGIMES_TRIMESTRAIS:
        fim_tri = _comp_menos(hoje, (hoje.month - 1) % 3 + 1)
        if hoje > vencimento_trimestre(fim_tri):
            return fim_tri
        return _comp_menos(hoje, (hoje.month - 1) % 3 + 4)
    return None


OPERACOES_BAIXA = ("dar_baixa", "dar_baixa_lote")
OPERACOES_TIRAR_BAIXA = ("tirar_baixa", "tirar_baixa_lote")
OPERACOES_COM_VENCIMENTO = ("editar_cobranca", "alterar_data_vencimento", "excluir_financeiro")


def _comp_de(valor):
    if not valor:
        return None
    if hasattr(valor, "strftime"):
        return valor.strftime("%Y-%m")
    texto = str(valor)
    return texto[:7] if re.match(r"^\d{4}-\d{2}", texto) else None


def _valor(estado):
    try:
        return round(float(estado.get("valor") or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _entra_na_receita(status):
    return not str(status or "").strip().lower().startswith("cancel")


def _pago(estado):
    return str(estado.get("status") or "").strip().lower() == "pago" or bool(estado.get("pag"))


def competencias_afetadas(regime_tributario, regime_apuracao, operacao, antes, depois=None):
    """Competências ("AAAA-MM") cuja receita a operação na parcela altera.

    `antes`/`depois`: {venc, pag, status, valor, mora}; `depois` só com o que muda (None em exclusão).
    `regime_apuracao`: o efetivo da empresa (na rede, o da matriz)."""
    antes = dict(antes or {})
    novo = None if depois is None else {**antes, **depois}
    caixa = str(regime_apuracao or "").strip().lower() == "caixa"
    pag_antes = _comp_de(antes.get("pag")) if _pago(antes) else None
    pag_depois = _comp_de(novo.get("pag")) if novo is not None and _pago(novo) else None
    venc_antes = _comp_de(antes.get("venc"))
    venc_depois = _comp_de(novo.get("venc")) if novo is not None else None
    comps = set()

    if regime_tributario == "simples_nacional":
        if caixa:
            if operacao in OPERACOES_BAIXA or operacao == "alterar_data_pagamento":
                comps = {pag_antes, pag_depois}
            elif operacao in OPERACOES_TIRAR_BAIXA or operacao == "excluir_financeiro":
                comps = {pag_antes}
            elif operacao == "editar_cobranca":
                mudou = pag_antes != pag_depois or (pag_antes and _valor(antes) != _valor(novo))
                comps = {pag_antes, pag_depois} if mudou else set()
        else:
            if operacao == "alterar_data_vencimento":
                comps = {venc_antes, venc_depois} if venc_antes != venc_depois else set()
            elif operacao == "editar_cobranca":
                mudou = (
                    venc_antes != venc_depois
                    or _valor(antes) != _valor(novo)
                    or _entra_na_receita(antes.get("status")) != _entra_na_receita(novo.get("status"))
                )
                comps = {venc_antes, venc_depois} if mudou else set()
            elif operacao == "excluir_financeiro" and _entra_na_receita(antes.get("status")):
                comps = {venc_antes}
        comps.discard(None)
        return comps

    if regime_tributario not in REGIMES_TRIMESTRAIS:
        return set()
    comps = {pag_antes, pag_depois}
    if not caixa:
        comps = {venc_antes, venc_depois} if operacao in OPERACOES_COM_VENCIMENTO else set()
        mora_antes = float(antes.get("mora") or 0) > 0
        if mora_antes:
            comps.add(pag_antes)
        if mora_antes or (novo is not None and float(novo.get("mora") or 0) > 0):
            comps.add(pag_depois)
    comps.discard(None)
    return comps


def mensagem_competencia_apurada(regime_tributario, competencias):
    rotulos = ", ".join(f"{c[5:7]}/{c[:4]}" for c in sorted(competencias))
    if regime_tributario == "simples_nacional":
        return (f"Competência já apurada ({rotulos}): o PGDAS-D desse mês já venceu. "
                "A parcela não pode ser baixada, alterada, ter a baixa removida nem ser excluída nesse período: "
                "mudaria a receita e o DAS já declarados.")
    return (f"Competência já apurada ({rotulos}): o trimestre encerrou e a DARF venceu. "
            "A parcela não pode ser criada, alterada, baixada nem excluída nesse período: "
            "mudaria a receita e os tributos já declarados.")


class TravaCompetencias:
    def __init__(self, limite=None, congeladas=()):
        self.limite = limite
        self.congeladas = set(congeladas or ())

    def __contains__(self, comp):
        return bool((self.limite and comp <= self.limite) or comp in self.congeladas)

    def __bool__(self):
        return bool(self.limite or self.congeladas)


def travas_da_escola(cursor, hoje=None, regime=None, schemas=None):
    """Travas da empresa. `regime`: regime da empresa (a filial usa o da matriz); None lê a própria configuração.
    `schemas`: unidades da rede; competência congelada em qualquer uma trava a empresa toda."""
    hoje = hoje or date.today()
    if regime is None:
        cursor.execute("SELECT regime_tributario FROM configuracoes WHERE id = 1")
        linha = cursor.fetchone() or {}
        regime = linha.get("regime_tributario") if isinstance(linha, dict) else (linha[0] if linha else None)
    congeladas = set()
    if regime == "simples_nacional":
        tabelas = [f'"{s}".simples_competencias' for s in (schemas or []) if _SCHEMA_OK.match(s or "")]
        cursor.execute("SAVEPOINT travas_simples")
        try:
            for tabela in tabelas or ["simples_competencias"]:
                cursor.execute(
                    f"SELECT competencia FROM {tabela} WHERE origem = ANY(%s)",
                    (sorted(_ORIGENS_CONGELADAS),),
                )
                congeladas |= {
                    (l["competencia"] if isinstance(l, dict) else l[0]) for l in cursor.fetchall() or []
                }
            cursor.execute("RELEASE SAVEPOINT travas_simples")
        except Exception:
            cursor.execute("ROLLBACK TO SAVEPOINT travas_simples")
    return TravaCompetencias(limite_apurado(hoje, regime), congeladas)


def plano_parcelas(inicio, meses, hoje=None, gerar_passadas=False, travas=None):
    hoje = hoje or date.today()
    atual = hoje.strftime("%Y-%m")
    plano = {"gerar": [], "passadas": [], "travadas": []}
    for i in range(max(int(meses or 1), 1)):
        venc = add_meses(inicio, i)
        comp = venc.strftime("%Y-%m")
        if travas is not None and comp in travas:
            plano["travadas"].append(comp)
        elif comp < atual and not gerar_passadas:
            plano["passadas"].append(comp)
        else:
            plano["gerar"].append((i + 1, venc))
    return plano


def _faixa(comps):
    rot = [f"{c[5:7]}/{c[:4]}" for c in sorted(comps)]
    if len(rot) == 1:
        return rot[0]
    return f"{rot[0]} a {rot[-1]}"


def texto_puladas(plano):
    partes = []
    if plano.get("passadas"):
        partes.append(
            f"Parcelas de meses passados ({_faixa(plano['passadas'])}) não foram geradas. "
            "Para cobrar esses meses, gere de novo confirmando os meses passados."
        )
    if plano.get("travadas"):
        partes.append(
            f"Parcelas em competências já apuradas ({_faixa(plano['travadas'])}) foram bloqueadas: "
            "mudariam a receita e os tributos já declarados."
        )
    return " ".join(partes)


def juntar_planos(planos):
    total = {"gerar": [], "passadas": [], "travadas": []}
    for plano in planos:
        for chave in total:
            total[chave].extend(plano.get(chave) or [])
    total["passadas"] = sorted(set(total["passadas"]))
    total["travadas"] = sorted(set(total["travadas"]))
    return total
