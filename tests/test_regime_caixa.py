import unittest
from datetime import date

from tributacao import apurar_simples, base_do_mes, competencia_do_titulo


TITULO = {
    "data_vencimento": date(2026, 3, 10),
    "data_pagamento": date(2026, 5, 4),
    "status": "Pago",
    "valor": 1500,
}


class RegimeCaixaTeste(unittest.TestCase):
    def test_titulo_de_marco_pago_em_maio_so_entra_em_maio_no_caixa(self):
        self.assertEqual(competencia_do_titulo(date(2026, 3, 10), date(2026, 5, 4), "Pago", "caixa"), "2026-05")
        self.assertEqual(base_do_mes([TITULO], "2026-03", "caixa"), 0)
        self.assertEqual(base_do_mes([TITULO], "2026-05", "caixa"), 1500)

    def test_o_mesmo_titulo_entra_em_marco_na_competencia(self):
        self.assertEqual(competencia_do_titulo(date(2026, 3, 10), date(2026, 5, 4), "Pago", "competencia"), "2026-03")
        self.assertEqual(base_do_mes([TITULO], "2026-03", "competencia"), 1500)
        self.assertEqual(base_do_mes([TITULO], "2026-05", "competencia"), 0)

    def test_titulo_em_aberto_nao_entra_no_caixa(self):
        aberto = dict(TITULO, data_pagamento=None, status="Pendente")
        self.assertIsNone(competencia_do_titulo(date(2026, 3, 10), None, "Pendente", "caixa"))
        self.assertEqual(base_do_mes([aberto], "2026-03", "caixa"), 0)
        self.assertEqual(base_do_mes([aberto], "2026-05", "caixa"), 0)

    def test_das_de_maio_usa_so_o_recebimento(self):
        apuracao = apurar_simples(100_000, 50_000, 12, base_do_mes([TITULO], "2026-05", "caixa"))
        self.assertEqual(apuracao["receita_mes"], 1500)
        self.assertAlmostEqual(apuracao["das"], 1500 * apuracao["aliquota_efetiva"])
        self.assertGreater(apuracao["das"], 0)
        marco = apurar_simples(100_000, 50_000, 12, base_do_mes([TITULO], "2026-03", "caixa"))
        self.assertEqual(marco["receita_mes"], 0)
        self.assertEqual(marco["das"], 0)


if __name__ == "__main__":
    unittest.main()
