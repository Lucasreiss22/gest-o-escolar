import unittest
from datetime import date

from folha import (
    calcular_folha_pessoa,
    dsr_horista,
    inss_empregado,
    irrf_mensal,
)
from rescisao import alerta_readmissao


def _clt(salario, **extra):
    dados = {"id": 1, "nome_completo": "Teste", "tipo_contrato": "clt_mensalista", "salario": salario}
    dados.update(extra)
    return dados


class TabelasPorVigenciaTeste(unittest.TestCase):
    def test_inss_2026(self):
        self.assertEqual(inss_empregado(4800, 2026, 10), 473.51)
        self.assertEqual(inss_empregado(2200, 2026, 10), 173.69)
        self.assertEqual(inss_empregado(9000, 2026, 10), 988.09)

    def test_inss_2025_continua_na_tabela_antiga(self):
        self.assertEqual(inss_empregado(4800, 2025, 10), 481.60)

    def test_irrf_ate_5000_zera_com_redutor(self):
        ir = irrf_mensal(4800, 473.51, 2026, 10)
        self.assertTrue(ir["desconto_simplificado"])
        self.assertEqual(ir["imposto_tabela"], 267.89)
        self.assertEqual(ir["irrf"], 0.0)

    def test_irrf_faixa_de_transicao(self):
        self.assertEqual(irrf_mensal(6500, 711.51, 2026, 10)["irrf"], 569.92)

    def test_irrf_acima_de_7350_sem_redutor(self):
        ir = irrf_mensal(9000, 988.09, 2026, 10)
        self.assertEqual(ir["redutor"], 0.0)
        self.assertEqual(ir["irrf"], 1294.55)

    def test_irrf_2025_sem_redutor(self):
        self.assertEqual(irrf_mensal(4800, 481.60, 2025, 10)["irrf"], 267.89)


class FolhaPessoaTeste(unittest.TestCase):
    def test_falta_reduz_bases(self):
        item = calcular_folha_pessoa(
            _clt(6500, desconto_faltas=216.67, desconto_dsr_faltas=216.67, dias_falta_desconto=1, semanas_dsr_falta=1),
            "simples_nacional", 2026, 10,
        )
        self.assertEqual(item["base_inss"], 6066.66)
        self.assertEqual(item["inss_funcionario"], 650.85)
        self.assertEqual(item["irrf"], 409.75)
        self.assertEqual(item["liquido"], 5006.06)
        self.assertEqual(item["fgts"], 485.33)

    def test_horista_com_feriado_no_dsr(self):
        self.assertEqual(dsr_horista(3600, 2026, 10, [date(2026, 10, 12)]), 692.31)
        self.assertEqual(dsr_horista(3600, 2026, 10), 533.33)
        item = calcular_folha_pessoa(
            {"id": 2, "tipo_contrato": "clt_horista", "valor_hora": 45, "horas_mes": 80,
             "feriados_competencia": [date(2026, 10, 12)]},
            "simples_nacional", 2026, 10,
        )
        self.assertEqual(item["dsr"], 692.31)
        self.assertEqual(item["bruto"], 4292.31)

    def test_admissao_no_meio_do_mes_paga_proporcional(self):
        item = calcular_folha_pessoa(
            _clt(2300, data_inicio_contrato=date(2026, 10, 5)), "simples_nacional", 2026, 10
        )
        self.assertEqual(item["salario"], 2070.0)
        self.assertEqual(item["bruto"], 2070.0)

    def test_mes_seguinte_a_admissao_e_cheio(self):
        item = calcular_folha_pessoa(
            _clt(2300, data_inicio_contrato=date(2026, 10, 5)), "simples_nacional", 2026, 11
        )
        self.assertEqual(item["bruto"], 2300.0)


class ReadmissaoTeste(unittest.TestCase):
    def test_alerta_so_para_sem_justa_causa(self):
        historico = [
            {"data_inicio": date(2026, 10, 5), "rescisao_data": None},
            {"data_inicio": date(2024, 8, 5), "rescisao_data": date(2026, 10, 2), "rescisao_tipo": "sem_justa_causa"},
        ]
        alerta = alerta_readmissao(historico)
        self.assertEqual(alerta["data_limite"], date(2026, 12, 31))
        historico[1]["rescisao_tipo"] = "pedido_demissao"
        self.assertIsNone(alerta_readmissao(historico))


if __name__ == "__main__":
    unittest.main()
