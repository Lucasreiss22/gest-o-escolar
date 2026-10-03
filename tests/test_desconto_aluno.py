import os
import unittest

os.environ.setdefault("DATABASE_URL", "postgresql://x:y@127.0.0.1:1/z")

from alunos import normalizar_desconto, valor_mensalidade_liquido  # noqa: E402
import app as sistema  # noqa: E402


class DescontoAlunoTeste(unittest.TestCase):
    def test_percentual(self):
        self.assertEqual(valor_mensalidade_liquido(1100, "percentual", 10), 990.0)

    def test_valor_fixo_nao_fica_negativo(self):
        self.assertEqual(valor_mensalidade_liquido(1100, "valor_fixo", 150), 950.0)
        self.assertEqual(valor_mensalidade_liquido(100, "valor_fixo", 150), 0.0)

    def test_bolsa_e_sem_desconto(self):
        self.assertEqual(valor_mensalidade_liquido(1100, "bolsa", 0), 0.0)
        self.assertEqual(valor_mensalidade_liquido(1100, "nenhum", 10), 1100.0)
        self.assertEqual(valor_mensalidade_liquido(1100, None, None), 1100.0)

    def test_percentual_limitado_a_100(self):
        self.assertEqual(valor_mensalidade_liquido(1100, "percentual", 150), 0.0)

    def test_nomes_antigos_do_formulario(self):
        self.assertEqual(normalizar_desconto("porcentagem"), "percentual")
        self.assertEqual(normalizar_desconto("fixo"), "valor_fixo")
        self.assertEqual(normalizar_desconto("qualquer"), "nenhum")

    def test_abertas_divergentes(self):
        mensalidades = [
            {"id": 1, "valor": 1100, "status": "Pendente", "parcela_contrato": 1},
            {"id": 2, "valor": 1100, "status": "Atrasado", "parcela_contrato": 2},
            {"id": 3, "valor": 1100, "status": "Pago", "parcela_contrato": 3},
            {"id": 4, "valor": 990, "status": "Pendente", "parcela_contrato": 4},
            {"id": 5, "valor": 350, "status": "Pendente", "parcela_contrato": None},
        ]
        ids = [m["id"] for m in sistema._mensalidades_abertas_divergentes(mensalidades, 990.0)]
        self.assertEqual(ids, [1, 2])
        self.assertEqual(sistema._mensalidades_abertas_divergentes(mensalidades, 0.0), [])


if __name__ == "__main__":
    unittest.main()
