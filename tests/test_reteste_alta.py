import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alunos import migrar_desconto_percentual_fracao, valor_mensalidade_liquido  # noqa: E402
from permissoes import normalizar_papel  # noqa: E402
from rescisao import calcular_rescisao, normalizar_redutor_13  # noqa: E402

GABRIELA = {"salario": 9000, "tipo_contrato": "clt_mensalista", "data_inicio_contrato": "2023-03-01"}


def _rescisao_gabriela(modo=None):
    params = {
        "tipo_rescisao": "pedido_demissao",
        "aviso_modalidade": "nao_cumprido",
        "data_desligamento": "2026-10-03",
        "dias_aviso": "36",
    }
    if modo is not None:
        params["irrf_13_redutor"] = modo
    return calcular_rescisao(dict(GABRIELA), params)


class RedutorDecimoTerceiroTeste(unittest.TestCase):
    def test_tabela_sem_redutor(self):
        calc = _rescisao_gabriela("nao")
        self.assertEqual(calc["decimo_terceiro"], 6750.0)
        self.assertEqual(calc["inss_13"], 746.51)
        self.assertEqual(calc["irrf_13_tabela"], 742.23)
        self.assertEqual(calc["irrf_13"], 742.23)
        self.assertEqual(calc["irrf_13_redutor"], 0.0)

    def test_padrao_e_redutor_sobre_o_bruto(self):
        calc = _rescisao_gabriela()
        self.assertEqual(calc["irrf_13_redutor_modo"], "bruto")
        self.assertEqual(calc["irrf_13_redutor"], 79.89)
        self.assertEqual(calc["irrf_13"], 662.34)

    def test_redutor_sobre_o_liquido_de_inss(self):
        calc = _rescisao_gabriela("liquido")
        self.assertAlmostEqual(calc["irrf_13"], 562.95, delta=0.011)

    def test_valor_invalido_cai_no_bruto(self):
        self.assertEqual(normalizar_redutor_13("qualquer"), "bruto")
        self.assertEqual(normalizar_redutor_13(None), "bruto")

    def test_irrf_total_soma_o_13_com_redutor(self):
        calc = _rescisao_gabriela("bruto")
        self.assertEqual(calc["irrf"], round(calc["irrf_mensal"] + 662.34, 2))


class PapelDesconhecidoTeste(unittest.TestCase):
    def test_vazio_ou_desconhecido_vira_funcionario(self):
        self.assertEqual(normalizar_papel(None), "funcionario")
        self.assertEqual(normalizar_papel(""), "funcionario")
        self.assertEqual(normalizar_papel("Coordenação"), "funcionario")

    def test_papeis_conhecidos_continuam(self):
        self.assertEqual(normalizar_papel("Administrador"), "admin")
        self.assertEqual(normalizar_papel("admin"), "admin")
        self.assertEqual(normalizar_papel("plataforma"), "admin")
        self.assertEqual(normalizar_papel("Direção"), "direcao")
        self.assertEqual(normalizar_papel("professor"), "professor")


class CursorMigracao:
    def __init__(self, primeira_vez=True, alunos=()):
        self.primeira_vez = primeira_vez
        self.alunos = list(alunos)
        self.sql = []
        self._resultado = None

    def execute(self, sql, params=None):
        self.sql.append((" ".join(sql.split()), params))
        if "INSERT INTO migracoes_sistema" in sql:
            self._resultado = [{"nome": "x"}] if self.primeira_vez else []
        elif sql.strip().startswith("UPDATE alunos"):
            self._resultado = self.alunos
        else:
            self._resultado = None

    def fetchone(self):
        return (self._resultado or [None])[0]

    def fetchall(self):
        return self._resultado or []


class MigracaoDescontoTeste(unittest.TestCase):
    def test_sofia_vira_10_por_cento_e_parcelas_990(self):
        sofia = {"id": 5, "valor_mensalidade": 1100, "desconto_tipo": "percentual", "desconto_valor": 10}
        cursor = CursorMigracao(alunos=[sofia])
        corrigidos = migrar_desconto_percentual_fracao(cursor)
        self.assertEqual(len(corrigidos), 1)
        update_parcelas = [p for s, p in cursor.sql if s.startswith("UPDATE financeiro_mensalidades")]
        self.assertEqual(len(update_parcelas), 1)
        self.assertEqual(update_parcelas[0][0], 990.0)
        self.assertEqual(update_parcelas[0][1], 5)
        self.assertEqual(valor_mensalidade_liquido(1100, "percentual", 10), 990.0)

    def test_migracao_roda_uma_vez(self):
        cursor = CursorMigracao(primeira_vez=False, alunos=[{"id": 1}])
        self.assertEqual(migrar_desconto_percentual_fracao(cursor), [])
        self.assertFalse(any(s.startswith("UPDATE alunos") for s, _ in cursor.sql))


if __name__ == "__main__":
    unittest.main()
