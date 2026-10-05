import unittest

from tributos_rede import (
    AVISO_REAL_CAIXA,
    apurar_lucro_real_periodo,
    apurar_pis_cofins_real,
    provisao_lucro_real,
    ratear_por_lucro,
    regime_apuracao_efetivo,
)


class LucroRealTest(unittest.TestCase):
    def test_d1_trimestre_com_compensacao(self):
        ap = apurar_lucro_real_periodo(200_000, 10_000, 5_000, 10_000, 5_000, 100_000, 100_000, 3)
        self.assertEqual(ap["lucro_ajustado_irpj"], 205_000.00)
        self.assertEqual(ap["compensacao_irpj"], 61_500.00)
        self.assertEqual(ap["base_irpj"], 143_500.00)
        self.assertEqual(ap["irpj"], 21_525.00)
        self.assertEqual(ap["adicional"], 8_350.00)
        self.assertEqual(ap["csll"], 12_915.00)
        self.assertEqual(ap["novo_prejuizo"], 38_500.00)
        self.assertEqual(ap["nova_base_negativa"], 38_500.00)

    def test_d2_prejuizo_sem_imposto(self):
        ap = apurar_lucro_real_periodo(-4_488.38, meses_periodo=1)
        self.assertEqual(ap["irpj"], 0)
        self.assertEqual(ap["csll"], 0)
        self.assertEqual(ap["novo_prejuizo"], 4_488.38)
        self.assertTrue(ap["prejuizo"])

    def test_d3_rede_soma_o_lair_antes_de_zerar_prejuizo(self):
        lairs = {"matriz": -4_488.38, "filial": 36_838.12}
        ap = apurar_lucro_real_periodo(sum(lairs.values()), meses_periodo=1)
        self.assertEqual(ap["lair"], 32_349.74)
        self.assertEqual(ap["irpj"], 4_852.46)
        self.assertEqual(ap["adicional"], 1_234.97)
        self.assertEqual(ap["csll"], 2_911.48)
        self.assertEqual(ap["total"], 8_998.91)
        separado = apurar_lucro_real_periodo(36_838.12, meses_periodo=1)["total"]
        self.assertEqual(separado, 10_524.96)
        self.assertNotEqual(ap["total"], separado)
        self.assertEqual(ratear_por_lucro(ap["total"], lairs, ["matriz", "filial"]),
                         [("matriz", 0.0), ("filial", 8_998.91)])

    def test_d3_balancete_primeiro_mes(self):
        prov = provisao_lucro_real([32_349.74], modo="balancete")
        self.assertEqual(prov["mes"]["total"], 8_998.91)

    def test_provisao_trimestral_fecha_com_o_trimestre(self):
        prov = provisao_lucro_real([50_000, 80_000, 40_000])
        tri = apurar_lucro_real_periodo(170_000, meses_periodo=3)
        for chave in ("irpj", "adicional", "csll"):
            self.assertEqual(round(sum(m[chave] for m in prov["meses"]), 2), tri[chave], chave)

    def test_balancete_nunca_negativo(self):
        prov = provisao_lucro_real([60_000, -50_000, 10_000], modo="balancete")
        self.assertTrue(all(m["total"] >= 0 for m in prov["meses"]))
        self.assertEqual(prov["meses"][1]["total"], 0)

    def test_d4_pis_cofins_cumulativo_do_ensino(self):
        ap = apurar_pis_cofins_real(164_870)
        self.assertEqual(ap["pis"], 1_071.66)
        self.assertEqual(ap["cofins"], 4_946.10)

    def test_d5_nao_cumulativo_com_creditos(self):
        ap = apurar_pis_cofins_real(100_000, creditos_base=20_000, modo="nao_cumulativo")
        self.assertEqual(ap["pis"], 1_320.00)
        self.assertEqual(ap["cofins"], 6_080.00)

    def test_d6_caixa_no_lucro_real_vira_competencia(self):
        self.assertEqual(regime_apuracao_efetivo("lucro_real", "caixa"), ("competencia", AVISO_REAL_CAIXA))
        self.assertEqual(regime_apuracao_efetivo("simples_nacional", "caixa"), ("caixa", None))
        self.assertEqual(regime_apuracao_efetivo("lucro_presumido", None), ("competencia", None))


if __name__ == "__main__":
    unittest.main()
