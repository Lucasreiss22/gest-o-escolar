import unittest
from datetime import date

from permissoes import classificar_requisicao, pode_requisicao, pode_subacao
from ponto_retroativo import validar_pedido


HOJE = date(2026, 10, 3)
ONTEM = date(2026, 10, 2)


def _pedido(atuais, pedidas, dia=ONTEM, modo="retroativo", fechadas=(), exigir_mudanca=True):
    return validar_pedido(
        atuais,
        pedidas,
        dia,
        HOJE,
        modo=modo,
        competencias_fechadas=fechadas,
        exigir_mudanca=exigir_mudanca,
    )


class PontoRetroativoRegrasTeste(unittest.TestCase):
    def test_dia_completo_no_passado(self):
        pedido = _pedido(
            {},
            {
                "entrada": "08:00",
                "cafe_ida": "10:00",
                "cafe_volta": "10:15",
                "almoco": "12:00",
                "almoco_volta": "13:00",
                "saida": "17:00",
            },
        )
        self.assertEqual(pedido["tipo"], "retroativo")
        self.assertEqual(pedido["resultado"]["saida"], "17:00")

    def test_marca_avulsa_completa_o_dia_existente(self):
        pedido = _pedido({"entrada": "08:00"}, {"saida": "17:30"})
        self.assertEqual(pedido["resultado"]["entrada"], "08:00")
        self.assertEqual(pedido["resultado"]["saida"], "17:30")
        self.assertEqual(pedido["tipo"], "retroativo")

    def test_troca_de_horario_e_correcao(self):
        pedido = _pedido({"entrada": "08:00", "saida": "17:00"}, {"saida": "18:10"})
        self.assertEqual(pedido["tipo"], "correcao")
        self.assertEqual(pedido["resultado"]["saida"], "18:10")

    def test_rejeita_data_futura(self):
        with self.assertRaises(ValueError) as ctx:
            _pedido({}, {"entrada": "08:00"}, dia=date(2026, 10, 4))
        self.assertIn("futura", str(ctx.exception))

    def test_colaborador_nao_lanca_o_dia_de_hoje(self):
        with self.assertRaises(ValueError) as ctx:
            _pedido({}, {"entrada": "08:00"}, dia=HOJE, modo="retroativo")
        self.assertIn("batidas normais", str(ctx.exception))

    def test_correcao_de_hoje_exige_batida_existente(self):
        with self.assertRaises(ValueError) as ctx:
            _pedido({}, {"entrada": "08:00", "saida": "17:00"}, dia=HOJE, modo="correcao")
        self.assertIn("já precisa existir", str(ctx.exception))
        pedido = _pedido({"entrada": "08:00"}, {"saida": "17:00"}, dia=HOJE, modo="correcao")
        self.assertEqual(pedido["tipo"], "correcao")
        self.assertEqual(pedido["resultado"]["saida"], "17:00")

    def test_ordem_e_pares_de_intervalo(self):
        with self.assertRaises(ValueError) as ctx:
            _pedido({}, {"entrada": "18:00", "saida": "08:00"})
        self.assertIn("ordem", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            _pedido({}, {"entrada": "08:00", "cafe_ida": "10:00", "saida": "17:00"})
        self.assertIn("volta do café", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            _pedido({}, {"cafe_volta": "10:15", "entrada": "08:00"})
        self.assertIn("ida do café", str(ctx.exception))

    def test_justificativa_e_horario_obrigatorios_na_validacao_de_entrada(self):
        with self.assertRaises(ValueError):
            _pedido({"entrada": "08:00"}, {})
        with self.assertRaises(ValueError) as ctx:
            _pedido({"entrada": "08:00", "saida": "17:00"}, {"saida": "17:00"})
        self.assertIn("Nenhum horário diferente", str(ctx.exception))

    def test_competencia_fechada_bloqueia_pedido_e_aprovacao(self):
        with self.assertRaises(ValueError) as ctx:
            _pedido({}, {"entrada": "08:00"}, fechadas={"2026-10"})
        self.assertIn("fechada", str(ctx.exception))
        with self.assertRaises(ValueError):
            _pedido(
                {"entrada": "08:00"},
                {"saida": "17:00"},
                fechadas=["2026-10"],
                exigir_mudanca=False,
            )

    def test_hora_invalida(self):
        with self.assertRaises(ValueError):
            _pedido({}, {"entrada": "25:00"})


class PontoRetroativoPermissaoTeste(unittest.TestCase):
    def test_batida_normal_continua_sendo_alterar(self):
        self.assertEqual(
            classificar_requisicao("ponto", "POST", "bater_ponto"),
            ("alterar", "ponto"),
        )

    def test_aprovacao_e_correcao_usam_a_subacao(self):
        self.assertEqual(
            classificar_requisicao("ponto", "POST", "aprovar_ponto_retroativo"),
            ("aprovar_retroativo", "ponto"),
        )
        self.assertEqual(
            classificar_requisicao("ponto", "POST", "rejeitar_ponto_retroativo"),
            ("aprovar_retroativo", "ponto"),
        )
        self.assertEqual(
            classificar_requisicao("ponto", "POST", "solicitar_correcao_ponto"),
            ("aprovar_retroativo", "ponto"),
        )
        self.assertEqual(
            classificar_requisicao("ponto", "POST", "solicitar_ponto_retroativo"),
            ("alterar", "ponto"),
        )

    def test_padrao_secretaria_e_admin_aprovam_professor_nao(self):
        self.assertTrue(pode_subacao("admin", "ponto", "aprovar_retroativo"))
        self.assertTrue(pode_subacao("secretaria", "ponto", "aprovar_retroativo"))
        self.assertFalse(pode_subacao("professor", "ponto", "aprovar_retroativo"))
        self.assertFalse(pode_subacao("funcionario", "ponto", "aprovar_retroativo"))
        self.assertFalse(pode_subacao("financeiro", "ponto", "aprovar_retroativo"))
        self.assertFalse(pode_subacao("direcao", "ponto", "aprovar_retroativo"))

    def test_permissao_atribuida_libera_a_aprovacao(self):
        salvo = {
            "ponto": {
                "acessar": True,
                "ver": True,
                "alterar": False,
                "excluir": False,
                "aprovar_retroativo": True,
            }
        }
        self.assertTrue(pode_subacao("professor", "ponto", "aprovar_retroativo", salvo))
        self.assertTrue(
            pode_requisicao("professor", "ponto", "POST", salvo, "aprovar_ponto_retroativo")
        )
        self.assertFalse(
            pode_requisicao("professor", "ponto", "POST", None, "aprovar_ponto_retroativo")
        )
        self.assertTrue(
            pode_requisicao("secretaria", "ponto", "POST", None, "rejeitar_ponto_retroativo")
        )
        self.assertTrue(
            pode_requisicao("funcionario", "ponto", "POST", None, "solicitar_ponto_retroativo")
        )
        self.assertFalse(
            pode_requisicao("funcionario", "ponto", "POST", None, "solicitar_correcao_ponto")
        )


if __name__ == "__main__":
    unittest.main()
