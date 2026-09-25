import unittest
from datetime import datetime

from nfse import (
    competencia_fiscal,
    interpretar_resposta,
    montar_payload,
    pode_emitir_mensalidade,
    substituicao_retroativa,
    texto_tarja,
    tp_ret_pis_cofins,
    valor_da_nota,
    valor_na_competencia,
)
from permissoes import pode_acao, pode_modulo


class NfseRegrasTeste(unittest.TestCase):
    def test_caixa_so_emite_mensalidade_paga(self):
        ok, _ = pode_emitir_mensalidade("caixa", "Pendente", None)
        self.assertFalse(ok)
        ok, _ = pode_emitir_mensalidade("caixa", "Pago", None)
        self.assertFalse(ok)
        ok, _ = pode_emitir_mensalidade("caixa", "Pago", datetime(2026, 9, 10))
        self.assertTrue(ok)

    def test_competencia_emite_sem_pagamento(self):
        ok, motivo = pode_emitir_mensalidade("competencia", "Pendente", None)
        self.assertTrue(ok, motivo)

    def test_substituicao_em_mes_posterior_e_retroativa(self):
        self.assertTrue(substituicao_retroativa(datetime(2026, 9, 2), datetime(2026, 10, 3)))
        self.assertFalse(substituicao_retroativa(datetime(2026, 9, 2), datetime(2026, 9, 20)))

    def test_tarja_cita_o_periodo_original(self):
        texto = texto_tarja(datetime(2026, 10, 3), "2026-09")
        self.assertIn("03/10/2026", texto)
        self.assertIn("setembro/2026", texto)
        self.assertIn("período original de emissão", texto)

    def test_valor_da_substituta_fica_no_mes_original(self):
        notas = [
            {
                "status": "SUBSTITUIDA",
                "valor": 450,
                "periodo_competencia_original": "2026-09",
                "data_emissao": datetime(2026, 9, 2),
            },
            {
                "status": "FATURADA",
                "valor": 450,
                "periodo_competencia_original": "2026-09",
                "data_emissao": datetime(2026, 10, 3),
            },
        ]
        self.assertEqual(valor_na_competencia(notas, "2026-09"), 450)
        self.assertEqual(valor_na_competencia(notas, "2026-10"), 0)
        self.assertEqual(competencia_fiscal(notas[0]), "")
        self.assertEqual(competencia_fiscal(notas[1]), "2026-09")

    def test_cancelada_nao_entra_no_faturamento(self):
        notas = [{"status": "CANCELADA", "valor": 450, "periodo_competencia_original": "2026-09"}]
        self.assertEqual(valor_na_competencia(notas, "2026-09"), 0)

    def test_retencao_unificada_marca_o_tipo(self):
        self.assertEqual(tp_ret_pis_cofins(0, 0, 0), 0)
        self.assertEqual(tp_ret_pis_cofins(1, 1, 0), 1)
        self.assertEqual(tp_ret_pis_cofins(1, 1, 1), 3)

    def test_caixa_soma_juros_e_multa(self):
        self.assertEqual(valor_da_nota("caixa", 450, 10, 5, "Pago"), 465)
        self.assertEqual(valor_da_nota("competencia", 450, 10, 5, "Pendente"), 450)

    def test_payload_leva_reforma_e_a_nota_substituida(self):
        payload = montar_payload(
            {"cnpj": "12.345.678/0001-90", "inscricao_municipal": "123", "codigo_opcao_simples_nacional": "3"},
            {
                "documento": "12345678901",
                "razao_social": "Responsável",
                "email": "a@b.com",
                "logradouro": "Rua A",
                "numero": "10",
                "bairro": "Centro",
                "codigo_municipio": "3305802",
                "uf": "rj",
                "cep": "25900-000",
            },
            {
                "valor_servicos": 450,
                "valor_pis": 1,
                "valor_cofins": 1,
                "valor_csll": 1,
                "valor_ir": 2,
                "cBeneficio": "EDU",
                "reforma_tributaria": {"vIBS": 0, "vCBS": 0, "pIBS": 0, "pCBS": 0},
            },
            substituida={"numero_nfse": "99", "codigo_verificacao": "ABC", "chave": "CH"},
            data_emissao=datetime(2026, 9, 25, 10, 0),
        )
        self.assertEqual(payload["prestador"]["cnpj"], "12345678000190")
        self.assertEqual(payload["tomador"]["cpf"], "12345678901")
        self.assertEqual(payload["tomador"]["endereco"]["uf"], "RJ")
        self.assertEqual(payload["servico"]["tpRetPISCOFINS"], 3)
        self.assertEqual(payload["servico"]["cBeneficio"], "EDU")
        self.assertIn("vIBS", payload["servico"]["reforma_tributaria"])
        self.assertEqual(payload["nfse_substituida"]["numero"], "99")
        self.assertEqual(payload["numero_nfse_substituida"], "99")
        self.assertEqual(payload["nfse_substituida"]["chave"], "CH")

    def test_resposta_guarda_xml_e_danfse(self):
        lido = interpretar_resposta(200, {
            "status": "autorizado",
            "numero": "15",
            "caminho_xml_nota_fiscal": "/arquivos/nota.xml",
            "caminho_danfe": "/arquivos/danfse.pdf",
            "url": "https://prefeitura.exemplo/nota",
        })
        self.assertEqual(lido["status"], "FATURADA")
        self.assertEqual(lido["xml_caminho"], "/arquivos/nota.xml")
        self.assertEqual(lido["url_pdf"], "/arquivos/danfse.pdf")


class NfsePermissaoTeste(unittest.TestCase):
    def test_financeiro_e_admin_emitam_professor_nao(self):
        self.assertTrue(pode_modulo("financeiro", "nfse"))
        self.assertTrue(pode_modulo("admin", "nfse"))
        self.assertFalse(pode_modulo("professor", "nfse"))
        self.assertFalse(pode_modulo("direcao", "nfse"))
        self.assertTrue(pode_acao("admin", "nfse", "alterar"))
        self.assertFalse(pode_acao("professor", "nfse", "acessar"))

    def test_professor_pode_receber_a_aba(self):
        salvo = {"nfse": {"acessar": True, "ver": True, "alterar": True, "excluir": False}}
        self.assertTrue(pode_acao("professor", "nfse", "alterar", salvo))
        self.assertFalse(pode_acao("professor", "nfse", "excluir", salvo))


if __name__ == "__main__":
    unittest.main()
