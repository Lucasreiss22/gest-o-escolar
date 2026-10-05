import unittest

from tributacao import apurar_lucro_presumido
from tributos_rede import apurar_presumido_periodo, validar_percentual

TRI_OUT = ["2026-10", "2026-11", "2026-12"]


class PresumidoEmpresaTest(unittest.TestCase):
    def test_c1_trimestre_da_empresa(self):
        ap = apurar_presumido_periodo([164_870.0] * 3, competencias=TRI_OUT, lc224=True)
        tri = ap["trimestre"]
        self.assertAlmostEqual(tri["receita"], 494_610.00, places=2)
        self.assertEqual(tri["base_irpj"], 158_275.20)
        self.assertEqual(tri["irpj"], 23_741.28)
        self.assertEqual(tri["adicional"], 9_827.52)
        self.assertEqual(tri["csll"], 14_244.77)
        self.assertEqual(tri["pis"], 3_214.97)
        self.assertEqual(tri["cofins"], 14_838.30)

    def test_c2_limite_unico_do_adicional(self):
        matriz = apurar_presumido_periodo([113_870.0] * 3)["trimestre"]["adicional"]
        filial = apurar_presumido_periodo([51_000.0] * 3)["trimestre"]["adicional"]
        self.assertEqual(matriz + filial, 4_931.52)
        empresa = apurar_presumido_periodo([164_870.0] * 3)["trimestre"]["adicional"]
        self.assertNotEqual(empresa, 4_931.52)
        self.assertEqual(empresa, 9_827.52)

    def test_c3_provisao_mensal_fecha_com_o_trimestre(self):
        outubro = apurar_presumido_periodo([164_870.0], competencias=TRI_OUT[:1])["mes"]
        self.assertEqual(outubro["irpj"], 7_913.76)
        self.assertEqual(outubro["adicional"], 3_275.84)
        self.assertEqual(outubro["csll"], 4_748.26)
        self.assertEqual(outubro["pis"], 1_071.66)
        self.assertEqual(outubro["cofins"], 4_946.10)
        ap = apurar_presumido_periodo([164_870.0] * 3, competencias=TRI_OUT)
        for tributo in ("irpj", "adicional", "csll"):
            soma = round(sum(m[tributo] for m in ap["meses"]), 2)
            self.assertEqual(soma, ap["trimestre"][tributo], tributo)

    def test_c4_percentuais_configuraveis(self):
        ap = apurar_presumido_periodo([164_870.0] * 3, presuncao_irpj=16, presuncao_csll=12)
        self.assertEqual(ap["trimestre"]["base_irpj"], 79_137.60)
        self.assertEqual(ap["trimestre"]["base_csll"], 59_353.20)
        self.assertEqual(ap["presuncao_irpj_pct"], 16.0)
        self.assertIsNone(validar_percentual("150"))
        self.assertIsNone(validar_percentual("-1"))
        self.assertIsNone(validar_percentual("abc"))
        self.assertEqual(validar_percentual("16,5"), 16.5)

    def test_c5_lc224(self):
        receitas = [700_000.0, 650_000.0, 650_000.0]
        comps = ["2026-01", "2026-02", "2026-03"]
        com = apurar_presumido_periodo(receitas, competencias=comps, lc224=True)["trimestre"]
        self.assertEqual(com["base_irpj"], 664_000.00)
        self.assertEqual(com["base_csll"], 640_000.00)
        sem = apurar_presumido_periodo(receitas, competencias=comps, lc224=False)["trimestre"]
        self.assertEqual(sem["base_irpj"], 640_000.00)

    def test_c5_lc224_csll_a_partir_de_abril(self):
        comps = ["2026-04", "2026-05", "2026-06"]
        ap = apurar_presumido_periodo([700_000.0, 650_000.0, 650_000.0], competencias=comps, lc224=True,
                                      receita_acumulada_ano_antes={"2026-01": 10.0})
        self.assertEqual(ap["trimestre"]["excedente_lc224_csll"], 750_000.00)

    def test_juros_fora_do_pis_quando_configurado(self):
        com = apurar_presumido_periodo([10_000.0], [1_000.0], incluir_mora=True)["mes"]
        sem = apurar_presumido_periodo([10_000.0], [1_000.0], incluir_mora=False)["mes"]
        self.assertEqual(com["pis"], 71.50)
        self.assertEqual(sem["pis"], 65.00)

    def test_iss_configuravel(self):
        self.assertEqual(apurar_presumido_periodo([10_000.0], iss_pct=2)["mes"]["iss"], 200.00)

    def test_c7_independente_com_padroes_igual_ao_atual(self):
        receitas = [40_000.0, 42_000.0]
        novo = apurar_presumido_periodo(receitas, [300.0, 500.0], competencias=TRI_OUT[:2])["mes"]
        antigo = apurar_lucro_presumido(42_000.0, [], 82_000.0, acrescimos_mora=500.0)
        for chave in ("pis", "cofins", "iss", "irpj", "csll"):
            self.assertAlmostEqual(novo[chave], antigo[chave], delta=0.011, msg=chave)


if __name__ == "__main__":
    unittest.main()
