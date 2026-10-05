import unittest
from datetime import date

from tributos_rede import apurar_simples_empresa, avisos_limites_simples, mes_inicio_empresa, ratear


def _meses(inicio, fim, valor):
    ano, mes = map(int, inicio.split("-"))
    saida = {}
    while f"{ano:04d}-{mes:02d}" <= fim:
        saida[f"{ano:04d}-{mes:02d}"] = valor
        mes += 1
        if mes > 12:
            ano, mes = ano + 1, 1
    return saida


def _semente():
    matriz = _meses("2026-02", "2026-09", 112_990.0)
    matriz["2026-10"] = 113_870.0
    return {"matriz": matriz, "filial": {"2026-10": 51_000.0}}


ORDEM = ["matriz", "filial"]


class RatearTest(unittest.TestCase):
    def test_sobra_de_centavos_fica_na_matriz(self):
        partes = ratear(100, [("m", 1), ("a", 1), ("b", 1)])
        self.assertEqual(partes, [("m", 33.34), ("a", 33.33), ("b", 33.33)])

    def test_sem_peso_tudo_na_matriz(self):
        self.assertEqual(ratear(10, [("m", 0), ("f", 0)]), [("m", 10.0), ("f", 0.0)])

    def test_soma_igual_ao_total(self):
        partes = ratear(22045.51, [("m", 113870), ("f", 51000)])
        self.assertAlmostEqual(sum(v for _k, v in partes), 22045.51, places=2)


class SimplesEmpresaTest(unittest.TestCase):
    def _apurar(self, receitas, mes, inicio=None, abertura=None):
        inicio = inicio or mes_inicio_empresa(abertura, receitas)
        return apurar_simples_empresa(receitas, mes, inicio, ordem=ORDEM)

    def test_a1_outubro_competencia(self):
        ap = self._apurar(_semente(), "2026-10")
        self.assertAlmostEqual(ap["rbt12"], 1_355_880.00, places=2)
        self.assertEqual(ap["faixa"], 4)
        self.assertAlmostEqual(ap["aliquota_efetiva_pct"], 13.371449, places=5)
        self.assertAlmostEqual(ap["receita_mes_empresa"], 164_870.00, places=2)
        self.assertEqual(ap["das_total"], 22_045.51)
        self.assertEqual([r["das"] for r in ap["rateio"]], [15_226.07, 6_819.44])

    def test_a2_setembro_tudo_na_matriz(self):
        ap = self._apurar(_semente(), "2026-09")
        self.assertAlmostEqual(ap["rbt12"], 1_355_880.00, places=2)
        self.assertAlmostEqual(ap["receita_mes_empresa"], 112_990.00, places=2)
        self.assertEqual(ap["das_total"], 15_108.40)
        self.assertEqual([r["das"] for r in ap["rateio"]], [15_108.40, 0.0])

    def test_a3_novembro(self):
        receitas = _semente()
        receitas["matriz"]["2026-11"] = 113_870.0
        receitas["filial"]["2026-11"] = 51_000.0
        ap = self._apurar(receitas, "2026-11")
        self.assertAlmostEqual(ap["rbt12"], 1_425_053.33, places=2)
        self.assertAlmostEqual(ap["aliquota_efetiva_pct"], 13.4990, places=4)
        self.assertEqual(ap["das_total"], 22_255.87)
        self.assertEqual([r["das"] for r in ap["rateio"]], [15_371.36, 6_884.51])

    def test_a4_empresa_nova_anualiza_a_receita_da_empresa(self):
        receitas = {"matriz": {"2026-10": 113_870.0}, "filial": {"2026-10": 51_000.0}}
        ap = self._apurar(receitas, "2026-10")
        self.assertAlmostEqual(ap["rbt12"], 1_978_440.00, places=2)
        self.assertEqual(ap["faixa"], 5)
        self.assertAlmostEqual(ap["aliquota_efetiva_pct"], 14.6495, places=4)
        self.assertEqual(ap["das_total"], 24_152.70)

    def test_a5_caixa(self):
        receitas = {"matriz": _meses("2026-01", "2026-10", 100_000.0), "filial": {"2026-10": 30_000.0}}
        ap = self._apurar(receitas, "2026-10")
        self.assertAlmostEqual(ap["rbt12"], 1_200_000.00, places=2)
        self.assertAlmostEqual(ap["aliquota_efetiva_pct"], 13.03, places=4)
        self.assertEqual(ap["das_total"], 16_939.00)
        self.assertEqual([r["das"] for r in ap["rateio"]], [13_030.00, 3_909.00])

    def test_a8_inicio_pela_data_de_abertura(self):
        ap = self._apurar(_semente(), "2026-10", abertura=date(2025, 6, 15))
        self.assertEqual(ap["meses_atividade"], 12)
        self.assertFalse(ap["annualizado"])
        self.assertAlmostEqual(ap["rbt12"], 903_920.00, places=2)
        self.assertAlmostEqual(ap["aliquota_efetiva_pct"], 12.0572, places=4)
        self.assertEqual(ap["das_total"], 19_878.66)

    def test_filial_nova_nao_e_anualizada_sozinha(self):
        ap = self._apurar(_semente(), "2026-10")
        self.assertLess(ap["rbt12"], 1_967_880.00)

    def test_independente_igual_ao_calculo_atual(self):
        from tributacao import apurar_simples
        receitas = {"escola": _meses("2026-02", "2026-10", 50_000.0)}
        ap = apurar_simples_empresa(receitas, "2026-10", "2026-02")
        atual = apurar_simples(400_000.0, 0, 8, 50_000.0)
        self.assertAlmostEqual(ap["rbt12"], atual["rbt12"], places=2)
        self.assertAlmostEqual(ap["das_total"], round(atual["das"], 2), places=2)

    def test_inicio_empresa(self):
        self.assertEqual(mes_inicio_empresa(None, _semente()), "2026-02")
        self.assertEqual(mes_inicio_empresa(date(2025, 6, 15), _semente()), "2025-06")
        self.assertEqual(mes_inicio_empresa(date(2026, 5, 1), _semente()), "2026-02")
        self.assertIsNone(mes_inicio_empresa(None, {}))

    def test_avisos_de_limite(self):
        self.assertEqual(avisos_limites_simples(1_000_000), [])
        self.assertIn("3,6 milhões", avisos_limites_simples(3_700_000)[0])
        self.assertIn("4,8 milhões", avisos_limites_simples(5_000_000)[0])


if __name__ == "__main__":
    unittest.main()
