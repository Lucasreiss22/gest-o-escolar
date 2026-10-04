import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://x:y@127.0.0.1:1/z")

import app as sistema  # noqa: E402
from folha import calcular_folha_pessoa, detalhe_horas_extras, encargos_clt, fator_dsr  # noqa: E402

FABIO = {"id": 6, "tipo_contrato": "clt_mensalista", "salario": 1621, "horas_extras": 1}


class DsrHoraExtraTeste(unittest.TestCase):
    def test_sem_competencia_mantem_um_sexto(self):
        he = detalhe_horas_extras(dict(FABIO))
        self.assertEqual(he["adicional_he"], 11.05)
        self.assertEqual(he["dsr_he"], 1.84)

    def test_outubro_com_feriado_usa_5_descansos_por_26_uteis(self):
        dados = dict(FABIO, feriados_competencia=[date(2026, 10, 12)])
        he = detalhe_horas_extras(dados, 2026, 10)
        self.assertAlmostEqual(fator_dsr(2026, 10, [date(2026, 10, 12)]), 5 / 26)
        self.assertAlmostEqual(he["dsr_he"], 11.05 * 5 / 26, delta=0.006)

    def test_contracheque_usa_a_competencia(self):
        dados = dict(FABIO, feriados_competencia=[date(2026, 10, 12)])
        item = calcular_folha_pessoa(dados, "simples_nacional", 2026, 10)
        self.assertEqual(item["dsr_he"], 2.13)
        self.assertEqual(item["bruto"], round(1621 + 11.05 + 2.13, 2))
        self.assertIn("domingos e feriados", item["observacao"])

    def test_pj_nao_tem_dsr(self):
        he = detalhe_horas_extras({"tipo_contrato": "pj", "salario": 5000, "horas_extras": 2}, 2026, 10)
        self.assertEqual(he["dsr_he"], 0.0)


class ProvisoesTeste(unittest.TestCase):
    def test_provisao_sobre_salario_sem_falta(self):
        enc = encargos_clt(6066.66, "simples_nacional", "clt_mensalista", base_provisao=6500)
        self.assertEqual(enc["fgts"], 485.33)
        self.assertEqual(enc["provisao_13"], round(6500 / 12, 2))
        self.assertEqual(enc["ferias_terco"], round((6500 + 6500 / 3) / 12, 2))

    def test_falta_no_contracheque_nao_reduz_provisao(self):
        item = calcular_folha_pessoa(
            {"tipo_contrato": "clt_mensalista", "salario": 6500, "desconto_faltas": 216.67,
             "desconto_dsr_faltas": 216.67, "dias_falta_desconto": 1, "semanas_dsr_falta": 1},
            "simples_nacional", 2026, 10,
        )
        self.assertEqual(item["base_inss"], 6066.66)
        self.assertEqual(item["provisao_13"], round(6500 / 12, 2))


class AutoaprovacaoPontoTeste(unittest.TestCase):
    def test_proprio_ponto(self):
        self.assertTrue(sistema._autoaprovacao_ponto({"funcionario_id": 3, "solicitado_por": 9}, 1, 3))

    def test_pedido_lancado_pela_mesma_pessoa(self):
        self.assertTrue(sistema._autoaprovacao_ponto({"funcionario_id": 8, "solicitado_por": 1}, 1, 3))

    def test_pedido_de_outra_pessoa(self):
        self.assertFalse(sistema._autoaprovacao_ponto({"funcionario_id": 8, "solicitado_por": 9}, 1, 3))
        self.assertFalse(sistema._autoaprovacao_ponto({"funcionario_id": 8, "solicitado_por": None}, 1, None))


if __name__ == "__main__":
    unittest.main()
