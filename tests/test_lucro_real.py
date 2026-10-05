import unittest

from tributos_rede import (
    AVISO_REAL_CAIXA,
    apurar_lucro_real_periodo,
    apurar_pis_cofins_real,
    encadear_saldos,
    provisao_lucro_real,
    ratear_por_lucro,
    regime_apuracao_efetivo,
    saldo_antes_do_periodo,
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


class SaldoEncadeadoTest(unittest.TestCase):
    def test_l1_prejuizo_do_3o_tri_compensado_no_4o(self):
        cadeia = encadear_saldos({}, [
            {"periodo": "2026-09", "lair": -30_000},
            {"periodo": "2026-12", "lair": 100_000},
        ])
        self.assertEqual(cadeia["2026-09"]["prejuizo_depois"], 30_000.00)
        q4 = cadeia["2026-12"]
        self.assertEqual(q4["prejuizo_antes"], 30_000.00)
        self.assertEqual(q4["compensacao_irpj"], 30_000.00)
        self.assertEqual(q4["base_irpj"], 70_000.00)
        self.assertEqual((q4["irpj"], q4["adicional"], q4["csll"]), (10_500.00, 1_000.00, 6_300.00))
        self.assertEqual((q4["prejuizo_depois"], q4["base_negativa_depois"]), (0.0, 0.0))

    def test_l3_saldo_inicial_com_adicoes_e_exclusoes(self):
        ajustes = {"adicoes_irpj": 10_000, "exclusoes_irpj": 5_000, "adicoes_csll": 10_000, "exclusoes_csll": 5_000}
        cadeia = encadear_saldos(
            {"prejuizo_fiscal": 100_000, "base_negativa_csll": 100_000},
            [{"periodo": "2026-03", "lair": 200_000, "ajustes": ajustes}],
        )
        p = cadeia["2026-03"]
        self.assertEqual(p["compensacao_irpj"], 61_500.00)
        self.assertEqual(p["base_irpj"], 143_500.00)
        self.assertEqual((p["irpj"], p["adicional"], p["csll"]), (21_525.00, 8_350.00, 12_915.00))
        self.assertEqual(p["prejuizo_depois"], 38_500.00)

    def test_periodo_fechado_vale_o_saldo_gravado(self):
        cadeia = encadear_saldos({}, [
            {"periodo": "2026-06", "lair": -50_000, "fechado": {"prejuizo_fiscal": 40_000, "base_negativa_csll": 40_000}},
            {"periodo": "2026-09", "lair": 0},
        ])
        self.assertTrue(cadeia["2026-06"]["fechado"])
        self.assertEqual(cadeia["2026-09"]["prejuizo_antes"], 40_000.00)

    def test_saldo_antes_parte_do_ultimo_gravado_antes_da_cadeia(self):
        gravados = {
            "0000-00": {"prejuizo_fiscal": 5_000, "base_negativa_csll": 5_000, "fechado": False},
            "2025-12": {"prejuizo_fiscal": 12_000, "base_negativa_csll": 11_000, "fechado": True},
            "2026-06": {"prejuizo_fiscal": 999_999, "base_negativa_csll": 999_999, "fechado": False},
        }
        anteriores = [
            {"periodo": "2026-03", "inicio": "2026-01", "lair": -1_000},
            {"periodo": "2026-06", "inicio": "2026-04", "lair": 0},
            {"periodo": "2026-09", "inicio": "2026-07", "lair": 0},
        ]
        saldo = saldo_antes_do_periodo(gravados, anteriores, "2026-10")
        self.assertEqual(saldo["periodo"], "2025-12")
        self.assertEqual(saldo["prejuizo_fiscal"], 13_000.00)
        self.assertEqual(saldo["base_negativa_csll"], 12_000.00)

    def test_sem_periodos_anteriores_vale_o_saldo_inicial(self):
        saldo = saldo_antes_do_periodo({"0000-00": {"prejuizo_fiscal": 7_000, "base_negativa_csll": 6_000}}, [], "2026-01")
        self.assertEqual((saldo["prejuizo_fiscal"], saldo["base_negativa_csll"]), (7_000.00, 6_000.00))


if __name__ == "__main__":
    unittest.main()
