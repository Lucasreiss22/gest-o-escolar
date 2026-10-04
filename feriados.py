"""Feriados nacionais (Lei 662/1949, Lei 6.802/1980, Lei 14.759/2023) e pontos facultativos móveis."""

from datetime import date, timedelta

FIXOS = (
    (1, 1, "Confraternização Universal"),
    (4, 21, "Tiradentes"),
    (5, 1, "Dia do Trabalho"),
    (9, 7, "Independência do Brasil"),
    (10, 12, "Nossa Senhora Aparecida"),
    (11, 2, "Finados"),
    (11, 15, "Proclamação da República"),
    (11, 20, "Dia Nacional de Zumbi e da Consciência Negra"),
    (12, 25, "Natal"),
)
ANO_CONSCIENCIA_NEGRA = 2024


def pascoa(ano):
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher)."""
    a = ano % 19
    b, c = divmod(ano, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = (h + l - 7 * m + 114) % 31 + 1
    return date(ano, mes, dia)


def feriados_nacionais(ano, carnaval=False, corpus_christi=False):
    """{data: nome} do ano. Carnaval e Corpus Christi são ponto facultativo federal: entram só se a escola marcar."""
    datas = {}
    for mes, dia, nome in FIXOS:
        if (mes, dia) == (11, 20) and ano < ANO_CONSCIENCIA_NEGRA:
            continue
        datas[date(ano, mes, dia)] = nome
    p = pascoa(ano)
    datas[p - timedelta(days=2)] = "Sexta-feira Santa"
    if carnaval:
        datas[p - timedelta(days=48)] = "Carnaval (segunda-feira)"
        datas[p - timedelta(days=47)] = "Carnaval (terça-feira)"
    if corpus_christi:
        datas[p + timedelta(days=60)] = "Corpus Christi"
    return datas


def feriados_nacionais_mes(ano, mes, carnaval=False, corpus_christi=False):
    return {d: n for d, n in feriados_nacionais(ano, carnaval, corpus_christi).items() if d.month == mes}
