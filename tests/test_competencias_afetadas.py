import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parcelas import competencias_afetadas  # noqa: E402


class CompetenciasAfetadasTest(unittest.TestCase):
    def _antes(self, venc, pag=None, valor=1000, status=None, mora=0):
        return {"venc": venc, "pag": pag, "valor": valor, "status": status or ("Pago" if pag else "Pendente"), "mora": mora}

    def test_simples_caixa_baixa_conta_pagamento_antigo_e_novo(self):
        antes = self._antes(date(2027, 1, 10), pag=date(2026, 6, 1))
        comps = competencias_afetadas("simples_nacional", "caixa", "dar_baixa", antes, {"pag": date(2026, 9, 1), "status": "Pago"})
        self.assertEqual(comps, {"2026-06", "2026-09"})

    def test_simples_competencia_baixa_nao_afeta(self):
        antes = self._antes(date(2026, 6, 10))
        comps = competencias_afetadas("simples_nacional", "competencia", "dar_baixa", antes,
                                      {"pag": date(2026, 6, 15), "status": "Pago", "mora": 1})
        self.assertEqual(comps, set())

    def test_simples_caixa_vencimento_nao_afeta(self):
        antes = self._antes(date(2026, 6, 10), pag=date(2026, 6, 10))
        self.assertEqual(
            competencias_afetadas("simples_nacional", "caixa", "alterar_data_vencimento", antes, {"venc": date(2026, 11, 10)}),
            set(),
        )

    def test_simples_editar_so_descricao_nao_afeta(self):
        antes = self._antes(date(2026, 6, 10), pag=date(2026, 6, 10))
        mesmo = {"venc": date(2026, 6, 10), "pag": date(2026, 6, 10), "status": "Pago", "valor": 1000}
        self.assertEqual(competencias_afetadas("simples_nacional", "caixa", "editar_cobranca", antes, mesmo), set())
        self.assertEqual(competencias_afetadas("simples_nacional", "competencia", "editar_cobranca", antes, mesmo), set())
        self.assertEqual(
            competencias_afetadas("simples_nacional", "caixa", "editar_cobranca", antes, dict(mesmo, valor=900)),
            {"2026-06"},
        )
        self.assertEqual(
            competencias_afetadas("simples_nacional", "competencia", "editar_cobranca", antes, dict(mesmo, valor=900)),
            {"2026-06"},
        )

    def test_simples_excluir(self):
        aberta = self._antes(date(2026, 6, 10))
        self.assertEqual(competencias_afetadas("simples_nacional", "caixa", "excluir_financeiro", aberta), set())
        self.assertEqual(competencias_afetadas("simples_nacional", "competencia", "excluir_financeiro", aberta), {"2026-06"})
        cancelada = self._antes(date(2026, 6, 10), status="Cancelado")
        self.assertEqual(competencias_afetadas("simples_nacional", "competencia", "excluir_financeiro", cancelada), set())
        paga = self._antes(date(2026, 9, 10), pag=date(2026, 6, 20))
        self.assertEqual(competencias_afetadas("simples_nacional", "caixa", "excluir_financeiro", paga), {"2026-06"})

    def test_presumido_competencia_mora_no_mes_do_pagamento(self):
        antes = self._antes(date(2026, 5, 10))
        sem = competencias_afetadas("lucro_presumido", "competencia", "dar_baixa", antes, {"pag": date(2026, 6, 15), "status": "Pago", "mora": 0})
        com = competencias_afetadas("lucro_presumido", "competencia", "dar_baixa", antes, {"pag": date(2026, 6, 15), "status": "Pago", "mora": 1})
        self.assertEqual(sem, set())
        self.assertEqual(com, {"2026-06"})
        self.assertEqual(
            competencias_afetadas("lucro_presumido", "competencia", "excluir_financeiro", antes),
            {"2026-05"},
        )

    def test_regime_nao_informado(self):
        antes = self._antes(date(2026, 6, 10), pag=date(2026, 6, 10))
        self.assertEqual(competencias_afetadas(None, "caixa", "excluir_financeiro", antes), set())
        self.assertEqual(competencias_afetadas("", "competencia", "editar_cobranca", antes, {"valor": 1}), set())


if __name__ == "__main__":
    unittest.main()
