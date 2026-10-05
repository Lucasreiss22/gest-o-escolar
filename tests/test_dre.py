import unittest

from dre import (
    CAMPOS_BASE,
    LINHAS_DRE,
    calcular_dre,
    consolidar_dre,
    linhas_para_tela,
)
from relatorios_pdf import pdf_dre
from tributos_rede import apurar_simples_empresa
from unidades import unidades_da_rede


class CalcularDreTest(unittest.TestCase):
    def test_subtotais(self):
        dre = calcular_dre({
            "receita_bruta": 10000, "deducoes": 600, "folha": 4000, "rescisoes": 500,
            "compras": 800, "servicos": 300, "receitas_financeiras": 50, "irpj_csll": 200,
        })
        self.assertEqual(dre["receita_liquida"], 9400)
        self.assertEqual(dre["resultado_operacional"], 3800)
        self.assertEqual(dre["resultado_liquido"], 3650)
        self.assertEqual(dre["margem_pct"], 36.5)

    def test_base_vazia_sem_divisao_por_zero(self):
        dre = calcular_dre({})
        self.assertEqual(dre["resultado_liquido"], 0)
        self.assertEqual(dre["margem_pct"], 0)

    def test_valores_invalidos_viram_zero(self):
        dre = calcular_dre({"receita_bruta": "abc", "folha": None})
        self.assertEqual(dre["receita_bruta"], 0)
        self.assertEqual(dre["folha"], 0)


class ConsolidarDreTest(unittest.TestCase):
    def test_soma_linha_a_linha_e_recalcula_margem(self):
        a = calcular_dre({"receita_bruta": 10000, "deducoes": 1000, "folha": 5000})
        b = calcular_dre({"receita_bruta": 5000, "deducoes": 500, "folha": 1000, "receitas_financeiras": 100})
        total = consolidar_dre([a, b])
        for campo in CAMPOS_BASE:
            self.assertAlmostEqual(total[campo], a[campo] + b[campo], places=2)
        self.assertEqual(total["resultado_liquido"], a["resultado_liquido"] + b["resultado_liquido"])
        self.assertAlmostEqual(total["margem_pct"], round(total["resultado_liquido"] / 15000 * 100, 2))

    def test_lista_vazia(self):
        self.assertEqual(consolidar_dre([])["resultado_liquido"], 0)


class SimplesDaRedeTest(unittest.TestCase):
    def setUp(self):
        matriz = {f"2026-{m:02d}": 112_990.0 for m in range(2, 10)}
        matriz["2026-10"] = 113_870.0
        receitas = {"matriz": matriz, "filial": {"2026-10": 51_000.0}}
        self.ap = apurar_simples_empresa(receitas, "2026-10", "2026-02", ordem=["matriz", "filial"])
        self.colunas = [
            {"dre": calcular_dre({"receita_bruta": r["receita_mes"], "deducoes": r["das"]})}
            for r in self.ap["rateio"]
        ]

    def test_consolidada_igual_ao_das_da_empresa(self):
        total = consolidar_dre([c["dre"] for c in self.colunas])
        self.assertEqual(total["deducoes"], 22_045.51)
        self.assertEqual([c["dre"]["deducoes"] for c in self.colunas], [15_226.07, 6_819.44])

    def test_filial_individual_mostra_a_sua_parte(self):
        self.assertEqual(self.colunas[1]["dre"]["deducoes"], 6_819.44)
        self.assertEqual(self.colunas[1]["dre"]["irpj_csll"], 0)


class LinhasParaTelaTest(unittest.TestCase):
    def test_ordem_e_colunas(self):
        colunas = [
            {"dre": calcular_dre({"receita_bruta": 100})},
            {"dre": calcular_dre({"receita_bruta": 50})},
        ]
        consolidado = consolidar_dre([c["dre"] for c in colunas])
        linhas = linhas_para_tela(colunas, consolidado)
        self.assertEqual([l["campo"] for l in linhas], [campo for campo, _r, _t in LINHAS_DRE])
        self.assertEqual(linhas[0]["valores"], [100, 50])
        self.assertEqual(linhas[0]["consolidado"], 150)

    def test_sem_consolidado(self):
        linhas = linhas_para_tela([{"dre": calcular_dre({"receita_bruta": 100})}])
        self.assertIsNone(linhas[0]["consolidado"])


class UnidadesDaRedeTest(unittest.TestCase):
    ESCOLAS = [
        {"id": 1, "nome": "Matriz", "tipo_unidade": "matriz", "matriz_id": None},
        {"id": 3, "nome": "Filial B", "tipo_unidade": "filial", "matriz_id": 1},
        {"id": 2, "nome": "Filial A", "tipo_unidade": "filial", "matriz_id": 1},
        {"id": 4, "nome": "Outra", "tipo_unidade": "independente", "matriz_id": None},
    ]

    def test_matriz_primeiro_filiais_por_nome(self):
        rede = unidades_da_rede(self.ESCOLAS[0], self.ESCOLAS)
        self.assertEqual([e["id"] for e in rede], [1, 2, 3])

    def test_filial_enxerga_a_mesma_rede(self):
        rede = unidades_da_rede(self.ESCOLAS[1], self.ESCOLAS)
        self.assertEqual([e["id"] for e in rede], [1, 2, 3])

    def test_independente_sozinha(self):
        self.assertEqual([e["id"] for e in unidades_da_rede(self.ESCOLAS[3], self.ESCOLAS)], [4])

    def test_filial_com_matriz_invalida_fica_sozinha(self):
        orfa = {"id": 9, "nome": "Órfã", "tipo_unidade": "filial", "matriz_id": 99}
        self.assertEqual([e["id"] for e in unidades_da_rede(orfa, self.ESCOLAS + [orfa])], [9])


class PdfDreTest(unittest.TestCase):
    def test_consolidada_gera_pdf(self):
        colunas = [{"dre": calcular_dre({"receita_bruta": 1000, "folha": 300})},
                   {"dre": calcular_dre({"receita_bruta": 500})}]
        consolidado = consolidar_dre([c["dre"] for c in colunas])
        linhas = [
            {"rotulo": l["rotulo"], "valores": l["valores"] + [l["consolidado"]]}
            for l in linhas_para_tela(colunas, consolidado)
        ]
        buffer = pdf_dre("Escola Teste", "outubro de 2026", ["Matriz", "Filial A", "Consolidado"],
                         linhas, ["Nota de teste."], consolidada=True)
        self.assertTrue(buffer.getvalue().startswith(b"%PDF"))

    def test_individual_gera_pdf(self):
        linhas = [{"rotulo": l["rotulo"], "valores": l["valores"]}
                  for l in linhas_para_tela([{"dre": calcular_dre({"receita_bruta": 1000})}])]
        buffer = pdf_dre("Escola Teste", "outubro de 2026", ["Escola Teste"], linhas)
        self.assertTrue(buffer.getvalue().startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
