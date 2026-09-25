import unittest
from datetime import date

from simples_nacional import receita_para_apuracao
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

    def test_competencia_soma_pago_pendente_e_atrasado(self):
        titulos = [
            {"data_vencimento": date(2026, 9, 10), "data_pagamento": date(2026, 9, 8), "status": "Pago", "valor": 43250},
            {"data_vencimento": date(2026, 9, 30), "data_pagamento": None, "status": "Pendente", "valor": 950},
            {"data_vencimento": date(2026, 9, 5), "data_pagamento": None, "status": "Atrasado", "valor": 14500},
        ]
        self.assertEqual(base_do_mes(titulos, "2026-09", "competencia"), 58700)
        self.assertEqual(base_do_mes(titulos, "2026-09", "caixa"), 43250)

    def test_mes_de_apuracao_ignora_receita_gravada_no_caixa(self):
        gravado = {"origem": "pgdas", "receita_bruta": 35750}
        base = receita_para_apuracao(gravado, "competencia", 58700, "2026-09", "2026-09")
        self.assertEqual(base, 58700)
        anterior = receita_para_apuracao(gravado, "competencia", 58700, "2026-08", "2026-09")
        self.assertEqual(anterior, 35750)
        apuracao = apurar_simples(337_500, 43_925.08, 12, base)
        self.assertEqual(apuracao["anexo"], "V")
        self.assertEqual(apuracao["faixa"], 2)
        self.assertAlmostEqual(apuracao["fator_r_pct"], 13.01, places=2)
        self.assertAlmostEqual(apuracao["das"], 9783.33, places=2)


if __name__ == "__main__":
    unittest.main()
