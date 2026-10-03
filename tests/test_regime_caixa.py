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
        anterior = receita_para_apuracao(gravado, "competencia", 40000, "2026-08", "2026-09")
        self.assertEqual(anterior, 40000)
        sem_titulo = receita_para_apuracao(gravado, "competencia", 0, "2025-01", "2026-09")
        self.assertEqual(sem_titulo, 35750)
        apuracao = apurar_simples(337_500, 43_925.08, 12, base, atividade="fator_r")
        self.assertEqual(apuracao["anexo"], "V")
        self.assertEqual(apuracao["faixa"], 2)
        self.assertAlmostEqual(apuracao["fator_r_pct"], 13.01, places=2)
        self.assertAlmostEqual(apuracao["das"], 9783.33, places=2)


class SimplesEscolaTeste(unittest.TestCase):
    def test_ensino_vai_direto_ao_anexo_iii_sem_fator_r(self):
        apuracao = apurar_simples(112_250, 0, 1, 112_250)
        self.assertEqual(apuracao["anexo"], "III")
        self.assertFalse(apuracao["fator_r_aplicavel"])
        self.assertAlmostEqual(apuracao["aliquota_efetiva_pct"], 13.354, places=3)
        self.assertAlmostEqual(apuracao["das"], 14_990.00, delta=1.0)

    def test_mesma_receita_com_fator_r_baixo_cai_no_anexo_v(self):
        apuracao = apurar_simples(112_250, 0, 1, 112_250, atividade="fator_r")
        self.assertEqual(apuracao["anexo"], "V")
        self.assertAlmostEqual(apuracao["aliquota_efetiva_pct"], 19.2305, places=3)

    def test_primeiro_mes_sem_receita_anterior_usa_receita_do_mes_vezes_12(self):
        apuracao = apurar_simples(0, 0, 1, 5_350)
        self.assertTrue(apuracao["inicio_atividade"])
        self.assertAlmostEqual(apuracao["rbt12"], 64_200)
        self.assertAlmostEqual(apuracao["das"], 321.00, places=2)

    def test_sem_receita_no_mes_das_continua_zero(self):
        apuracao = apurar_simples(0, 0, 1, 0)
        self.assertFalse(apuracao["inicio_atividade"])
        self.assertEqual(apuracao["das"], 0)

    def test_fator_r_exibido_limitado_a_100(self):
        apuracao = apurar_simples(5_350, 807_133.98, 1, 2_200, atividade="fator_r")
        self.assertEqual(apuracao["fator_r_pct"], 100.0)
        self.assertTrue(apuracao["fator_r_acima_100"])
        self.assertEqual(apuracao["anexo"], "III")


if __name__ == "__main__":
    unittest.main()
