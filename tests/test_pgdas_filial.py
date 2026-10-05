import os
import re
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from relatorios_pdf import RelatorioPDF, pdf_extrato_pgdas, pdf_simples_nacional  # noqa: E402

MOEDA = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}")


def _apuracao(papel):
    unidades = [
        {"nome": "Escola Semente", "cnpj": "11.222.333/0001-81", "receita_mes": 114_870.0, "das": 15_359.78},
        {"nome": "Semente 2 Filial", "cnpj": "11.222.333/0002-62", "receita_mes": 51_000.0, "das": 6_819.44},
    ]
    eh_filial = papel == "filial"
    return {
        "anexo": "III", "faixa": 4, "aliquota_nominal": 0.16, "aliquota_efetiva_pct": 13.3714,
        "parcela_deduzir": 35_640.0, "rbt12": 1_355_880.0, "fs12": 0.0,
        "receita_mes": 165_870.0, "das": 22_179.22, "das_total": 22_179.22,
        "receita_unidade": 51_000.0 if eh_filial else 114_870.0,
        "das_unidade": 6_819.44 if eh_filial else 15_359.78,
        "rede": {
            "papel": papel, "matriz_nome": "Escola Semente", "matriz_cnpj": "11.222.333/0001-81", "n_filiais": 1,
        },
        "unidades": unidades,
        "quadro": {"linhas": []},
    }


def _texto(gerar):
    """Linhas e parágrafos escritos no PDF, na ordem."""
    escritos = []
    linha_original, paragrafo_original = RelatorioPDF.linha, RelatorioPDF.paragrafo

    def linha(self, rotulo, valor, *args, **kwargs):
        escritos.append(f"{rotulo}: {valor}")
        return linha_original(self, rotulo, valor, *args, **kwargs)

    def paragrafo(self, texto, *args, **kwargs):
        escritos.append(str(texto))
        return paragrafo_original(self, texto, *args, **kwargs)

    with mock.patch.object(RelatorioPDF, "linha", linha), mock.patch.object(RelatorioPDF, "paragrafo", paragrafo):
        buffer = gerar()
    assert buffer.getvalue().startswith(b"%PDF")
    return escritos


def _primeiro_valor(escritos):
    for texto in escritos:
        achado = MOEDA.search(texto)
        if achado and "R$" in texto:
            return achado.group(0)
    return None


class ExtratoPgdasFilialTest(unittest.TestCase):
    def test_filial_destaca_a_parte_da_unidade(self):
        escritos = _texto(lambda: pdf_extrato_pgdas("Semente 2 Filial", "Outubro/2026", _apuracao("filial")))
        self.assertEqual(_primeiro_valor(escritos), "6.819,44")
        self.assertTrue(any(t.startswith("Parte desta unidade no DAS da empresa") for t in escritos))
        com_total = [t for t in escritos if "22.179,22" in t]
        self.assertTrue(com_total)
        for texto in com_total:
            self.assertIn("empresa", texto)
        self.assertFalse(any(t.startswith("DAS a pagar neste mês") for t in escritos))
        self.assertTrue(any("Esta unidade não entrega PGDAS-D" in t and "CNPJ 11.222.333/0001-81" in t for t in escritos))
        receita = [t for t in escritos if t.startswith("Receita desta unidade")]
        self.assertTrue(receita and "51.000,00" in receita[0])
        self.assertTrue(any(t.startswith("Receita da empresa") and "165.870,00" in t for t in escritos))
        self.assertTrue(escritos[-1].startswith("Parte desta unidade:"))
        self.assertIn("6.819,44", escritos[-1])

    def test_matriz_continua_com_o_das_da_empresa(self):
        escritos = _texto(lambda: pdf_extrato_pgdas("Escola Semente", "Outubro/2026", _apuracao("matriz")))
        self.assertTrue(any(t.startswith("DAS a pagar neste mês") and "22.179,22" in t for t in escritos))
        destaque = next(t for t in escritos if t.startswith("DAS a pagar neste mês"))
        self.assertIn("22.179,22", destaque)
        self.assertFalse(any(t.startswith("Parte desta unidade no DAS") for t in escritos))

    def test_memoria_da_filial(self):
        escritos = _texto(lambda: pdf_simples_nacional(
            "Semente 2 Filial", "Outubro/2026", "simples_nacional", _apuracao("filial"), [], []
        ))
        self.assertEqual(_primeiro_valor(escritos), "6.819,44")
        for texto in escritos:
            if "22.179,22" in texto:
                self.assertIn("empresa", texto)
        self.assertTrue(any(t.startswith("Parte desta unidade:") and "6.819,44" in t for t in escritos))


if __name__ == "__main__":
    unittest.main()
