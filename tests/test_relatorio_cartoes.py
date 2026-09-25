import unittest
from datetime import date

from tributacao import acrescimos_recebimento
from relatorios_pdf import (
    pdf_caixa_restante,
    pdf_composicao_custos,
    pdf_composicao_mensalidades,
    pdf_folha_pagamento,
    pdf_lucro_presumido,
    pdf_lucro_real,
    pdf_regime_apuracao,
    pdf_regime_detalhado,
    pdf_simples_nacional,
)


def _pdf(buffer):
    dados = buffer.getvalue()
    if not dados.startswith(b"%PDF"):
        raise AssertionError("o arquivo não é um PDF")
    if len(dados) < 800:
        raise AssertionError("o PDF ficou curto demais para um relatório")
    return dados


class RelatoriosDosCartoes(unittest.TestCase):
    def test_juros_percentual_e_multa_fixa(self):
        conta = acrescimos_recebimento(1000, 1.5, 20)
        self.assertAlmostEqual(conta["juros_valor"], 15.0)
        self.assertAlmostEqual(conta["multa_valor"], 20.0)
        self.assertAlmostEqual(conta["total"], 1035.0)
        fino = acrescimos_recebimento(1000, 0.33, 0)
        self.assertAlmostEqual(fino["juros_valor"], 3.3)

    def test_relatorio_de_caixa_separa_pago_pendente_e_atraso(self):
        _pdf(pdf_regime_detalhado(
            "Escola",
            "Setembro/2026",
            "caixa",
            "lucro_presumido",
            [{
                "nome_completo": "Laura",
                "descricao": "Mensalidade",
                "parcela_contrato": 9,
                "valor": 1500,
                "juros_percentual": 1.5,
                "juros_valor": 22.5,
                "multa_valor": 10,
                "data_vencimento": date(2026, 3, 10),
                "data_pagamento": date(2026, 9, 4),
                "forma_pagamento": "Pix",
            }],
            [{
                "nome_completo": "Beatriz",
                "descricao": "Mensalidade",
                "parcela_contrato": 9,
                "valor": 750,
                "data_vencimento": date(2026, 9, 30),
            }],
            [{
                "nome_completo": "Valentina",
                "descricao": "Mensalidade",
                "parcela_contrato": 8,
                "valor": 950,
                "data_vencimento": date(2026, 8, 1),
            }],
        ))
    def test_mensalidades_lista_cada_baixa(self):
        _pdf(pdf_composicao_mensalidades(
            "Escola",
            "Maio/2026",
            "Pago no mês",
            "Entram as baixas de maio.",
            [{
                "nome_completo": "Laura",
                "descricao": "Mensalidade 03/2026",
                "valor": 1500,
                "data_vencimento": date(2026, 3, 10),
                "data_pagamento": date(2026, 5, 4),
                "forma_pagamento": "Pix",
            }],
            1500,
        ))

    def test_folha_explica_o_custo(self):
        _pdf(pdf_folha_pagamento(
            "Escola",
            "Setembro/2026",
            "lucro_presumido",
            [{
                "nome_completo": "Ana",
                "rotulo_contrato": "CLT mensalista",
                "observacao": "Salário fixo.",
                "salario": 3000,
                "bruto": 3000,
                "liquido": 2700,
                "encargos": 900,
                "custo_escola": 3900,
                "fgts": 240,
            }],
            {"custo_escola": 3900},
        ))

    def test_custos_e_caixa_e_regime(self):
        _pdf(pdf_composicao_custos(
            "Escola", "Setembro/2026", "Compras e custos fixos",
            "Aluguel do mês.",
            [{"descricao": "Aluguel", "porque": "Recorrente · 05/09/2026", "valor": 2000}],
            2000,
        ))
        _pdf(pdf_caixa_restante(
            "Escola", "Setembro/2026",
            [("(+) Recebido", 1000), ("(−) Folha", 400)],
            600,
            "caixa",
        ))
        _pdf(pdf_regime_apuracao("Escola", "Setembro/2026", "caixa", "simples_nacional"))

    def test_tributos_trazem_a_base_e_a_dre_continua_no_pdf(self):
        titulos = [{
            "nome_completo": "Laura",
            "descricao": "Mensalidade",
            "valor": 1500,
            "data_vencimento": date(2026, 3, 10),
            "data_pagamento": date(2026, 5, 4),
        }]
        ap = {
            "receita_mes": 1500, "das": 90, "rbt12": 100000, "fs12": 50000,
            "rbt_acumulado": 100000, "fs_acumulado": 50000, "meses_atividade": 12,
            "fator_r_pct": 50, "anexo": "III", "faixa": 1,
            "aliquota_nominal": 0.06, "parcela_deduzir": 0, "aliquota_efetiva_pct": 6,
            "quadro": {"linhas": []}, "regime_apuracao": "caixa",
        }
        _pdf(pdf_simples_nacional(
            "Escola", "Maio/2026", "simples_nacional", ap, [], [],
            dre={"receita": 1500, "das": 90, "folha": 0, "compras": 0, "servicos": 0},
            titulos=titulos, regime_apuracao="caixa",
        ))
        presumido = {
            "receita_mes": 1500, "pis": 9.75, "cofins": 45, "iss": 75,
            "base_presumida": 480, "csll": 43.2, "irpj": 72, "irpj_adicional": 0,
            "aplica_adicional_irpj": False, "tributos": 244.95,
        }
        _pdf(pdf_lucro_presumido(
            "Escola", "Maio/2026", "lucro_presumido", presumido,
            {"folha_pagamento": 0, "custos_compras": 0, "custos_servicos": 0},
            [], titulos=titulos, regime_apuracao="caixa",
        ))
        _pdf(pdf_lucro_real(
            "Escola", "Maio/2026", "lucro_real",
            {"recebido": 1500, "folha_pagamento": 0, "custos_compras": 0, "custos_servicos": 0},
            [], [], [], [],
            {"receita_mes": 1500, "pis": 24.75, "cofins": 114, "total": 138.75},
            titulos=titulos, regime_apuracao="caixa",
        ))


if __name__ == "__main__":
    unittest.main()
