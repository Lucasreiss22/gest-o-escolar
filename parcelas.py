"""Quais parcelas de um contrato podem ser geradas agora.

Padrão: do mês atual em diante. Meses passados só com confirmação de quem cadastra.
Competência já apurada no Simples nunca recebe parcela nova: mudaria receita, RBT12 e DAS já declarados.
"""

import calendar
from datetime import date, datetime

from simples_nacional import _ORIGENS_CONGELADAS

DIA_LIMITE_PGDAS = 20


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


def limite_apurado(hoje, regime_tributario):
    """Última competência com PGDAS-D vencido (dia 20 do mês seguinte). None fora do Simples."""
    if (regime_tributario or "") != "simples_nacional":
        return None
    return _comp_menos(hoje, 1 if hoje.day > DIA_LIMITE_PGDAS else 2)


class TravaCompetencias:
    def __init__(self, limite=None, congeladas=()):
        self.limite = limite
        self.congeladas = set(congeladas or ())

    def __contains__(self, comp):
        return bool((self.limite and comp <= self.limite) or comp in self.congeladas)

    def __bool__(self):
        return bool(self.limite or self.congeladas)


def travas_da_escola(cursor, hoje=None):
    hoje = hoje or date.today()
    cursor.execute("SELECT regime_tributario FROM configuracoes WHERE id = 1")
    linha = cursor.fetchone() or {}
    regime = linha.get("regime_tributario") if isinstance(linha, dict) else (linha[0] if linha else None)
    congeladas = set()
    if regime == "simples_nacional":
        cursor.execute("SAVEPOINT travas_simples")
        try:
            cursor.execute(
                "SELECT competencia FROM simples_competencias WHERE origem = ANY(%s)",
                (sorted(_ORIGENS_CONGELADAS),),
            )
            congeladas = {
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
            f"Parcelas em competências já apuradas no Simples ({_faixa(plano['travadas'])}) foram bloqueadas: "
            "mudariam receita, RBT12 e DAS já declarados."
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
