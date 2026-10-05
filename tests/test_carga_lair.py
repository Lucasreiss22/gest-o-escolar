import unittest
from datetime import date

from carga_tributos import (
    carregar_unidade,
    custos_por_mes,
    folha_por_competencia,
    lair_do_mes,
    meses_do_custo,
    resumir_custos,
)

COMPS = ["2026-10", "2026-11", "2026-12"]


def _dados(venc=None, juros=None):
    return {"venc": venc or {}, "pago": {}, "juros": juros or {}, "multa": {}, "qtd_mora": {}}


class CustosPorMesTest(unittest.TestCase):
    def test_avista_entra_so_no_mes_do_custo(self):
        custo = {"tipo": "avista", "data_custo": date(2026, 11, 3), "valor": 100}
        self.assertEqual(meses_do_custo(custo, COMPS), ["2026-11"])
        self.assertEqual(meses_do_custo({"tipo": "avista", "data_custo": date(2026, 9, 3)}, COMPS), [])

    def test_recorrente_entra_em_todos_os_meses_da_vigencia(self):
        custo = {"tipo": "recorrente", "data_inicio": date(2026, 1, 1), "data_fim": date(2026, 11, 30), "valor": 50}
        self.assertEqual(meses_do_custo(custo, COMPS), ["2026-10", "2026-11"])
        sem_fim = {"tipo": "recorrente", "data_inicio": "2026-11-01", "valor": 50}
        self.assertEqual(meses_do_custo(sem_fim, COMPS), ["2026-11", "2026-12"])

    def test_resumo_e_creditos_por_mes(self):
        linhas = [
            {"tipo": "avista", "data_custo": date(2026, 10, 2), "valor": 1000, "gera_credito_pis_cofins": True},
            {"tipo": "servico", "data_custo": date(2026, 10, 5), "valor": 500, "iss": 25, "iss_na_nota": False},
            {"tipo": "avista", "data_custo": date(2026, 10, 9), "valor": 300, "categoria": "Rescisão"},
            {"tipo": "recorrente", "data_inicio": date(2026, 10, 1), "valor": 200, "ativo": False},
        ]
        por_mes = custos_por_mes(linhas, COMPS)
        self.assertEqual(por_mes["2026-10"]["custos"], {"compras": 1000.0, "servicos": 525.0, "rescisoes": 300.0, "custos": 1825.0})
        self.assertEqual(por_mes["2026-10"]["creditos_pis"], 1000.0)
        self.assertEqual(por_mes["2026-11"]["custos"], resumir_custos([]))


class LairDoMesTest(unittest.TestCase):
    CFG = {"pis_cofins_lucro_real": "cumulativo_ensino", "iss_aliquota_pct": 5, "pis_cofins_incluir_mora": True}

    def test_lair_da_filial_do_reteste(self):
        custos = custos_por_mes([{"tipo": "avista", "data_custo": date(2026, 10, 1), "valor": 7188.09}], ["2026-10"])
        r = lair_do_mes(_dados({"2026-10": 50_000.0}), "2026-10", self.CFG, 0, custos["2026-10"])
        self.assertEqual(r["pis_cofins"], 1825.0)
        self.assertEqual(r["iss"], 2500.0)
        self.assertEqual(r["lair"], 38_486.91)

    def test_folha_e_mora_entram(self):
        r = lair_do_mes(_dados({"2026-10": 10_000.0}, {"2026-10": 100.0}), "2026-10", self.CFG, 4_000, {})
        self.assertEqual(r["mora"], 100.0)
        self.assertEqual(r["pis_cofins"], 368.65)
        self.assertEqual(r["lair"], round(10_000 - 368.65 - 500 - 4_000 + 100, 2))

    def test_matriz_so_com_custos_fica_negativa(self):
        custos = custos_por_mes([{"tipo": "avista", "data_custo": date(2026, 10, 1), "valor": 9901.68}], ["2026-10"])
        r = lair_do_mes(_dados(), "2026-10", self.CFG, 0, custos["2026-10"])
        self.assertEqual(r["lair"], -9901.68)


class _CursorFolhaUnidade:
    """Só responde a consulta da folha do carregador (snapshot dos meses fechados + folha_itens)."""

    def __init__(self):
        self.description = None
        self._resultado = []

    def execute(self, sql, params=None):
        if "folha_snapshot" in sql:
            self._resultado = [
                {"origem": "f", "competencia": "2026-09", "total": 9_000},
                {"origem": "i", "competencia": "2026-09", "total": 7_500},
                {"origem": "i", "competencia": "2026-10", "total": 8_000},
            ]
        else:
            self._resultado = []

    def fetchall(self):
        return list(self._resultado)

    def fetchone(self):
        return self._resultado[0] if self._resultado else None


class FolhaFechadaNoFs12Test(unittest.TestCase):
    """B10: mês fechado usa o snapshot da folha; aberto usa folha_itens."""

    def test_snapshot_vence_folha_itens(self):
        linhas = [
            {"origem": "i", "competencia": "2026-09", "total": 7_500},
            {"origem": "f", "competencia": "2026-09", "total": 9_000},
            {"origem": "i", "competencia": "2026-10", "total": 8_000},
        ]
        folha, fechada = folha_por_competencia(linhas)
        self.assertEqual(folha, {"2026-09": 9_000.0, "2026-10": 8_000.0})
        self.assertEqual(fechada, {"2026-09": 9_000.0})

    def test_carregador_da_unidade(self):
        dados = carregar_unidade(_CursorFolhaUnidade(), None, "2026-10")
        self.assertEqual(dados["folha"]["2026-09"], 9_000.0)
        self.assertEqual(dados["folha"]["2026-10"], 8_000.0)
        self.assertEqual(dados["folha_fechada"], {"2026-09": 9_000.0})


if __name__ == "__main__":
    unittest.main()
