import os
import unittest
from contextlib import contextmanager
from io import BytesIO
from unittest import mock

os.environ.setdefault("DATABASE_URL", "postgresql://x:y@127.0.0.1:1/z")

import relatorios_pdf as rp  # noqa: E402
from folha import calcular_folha_pessoa  # noqa: E402
import app as sistema  # noqa: E402


@contextmanager
def capturar_textos(classe=rp.RelatorioPDF):
    textos = []
    cell_original = classe.cell
    multi_original = classe.multi_cell

    def cell(self, *args, **kwargs):
        texto = kwargs.get("text", args[2] if len(args) > 2 else "")
        textos.append(str(texto or ""))
        return cell_original(self, *args, **kwargs)

    def multi_cell(self, *args, **kwargs):
        texto = kwargs.get("text", args[2] if len(args) > 2 else "")
        textos.append(str(texto or ""))
        return multi_original(self, *args, **kwargs)

    with mock.patch.object(classe, "cell", cell), mock.patch.object(classe, "multi_cell", multi_cell):
        yield textos


def _png():
    from PIL import Image

    saida = BytesIO()
    Image.new("RGB", (40, 20), (30, 58, 95)).save(saida, format="PNG")
    return saida.getvalue()


class IdentidadeCabecalhoTeste(unittest.TestCase):
    def tearDown(self):
        rp.registrar_identidade_escola(sistema._identidade_escola_pdf)

    def test_cabecalho_com_nome_cnpj_e_logo(self):
        rp.registrar_identidade_escola(
            lambda: {"nome": "Colégio Teste", "cnpj": "12.345.678/0001-90", "logo": (_png(), "image/png")}
        )
        with capturar_textos() as textos, mock.patch.object(rp.RelatorioPDF, "image", autospec=True) as imagem:
            rp.pdf_lista_alunos("Colégio Teste", [])
        self.assertIn("Colégio Teste", textos)
        self.assertIn("CNPJ 12.345.678/0001-90", textos)
        self.assertTrue(imagem.called)

    def test_provedor_com_erro_nao_quebra_pdf(self):
        def falha():
            raise RuntimeError("sem banco")

        rp.registrar_identidade_escola(falha)
        buffer = rp.pdf_lista_alunos("Escola", [])
        self.assertTrue(buffer.getvalue().startswith(b"%PDF"))

    def test_sem_sessao_nao_consulta_banco(self):
        with mock.patch("database.obter_conexao_nova") as nova:
            self.assertEqual(sistema._identidade_escola_pdf(), {})
        nova.assert_not_called()

    def test_formatar_cnpj(self):
        self.assertEqual(sistema._formatar_cnpj("12345678000190"), "12.345.678/0001-90")
        self.assertEqual(sistema._formatar_cnpj(None), "")


class ContrachequeTeste(unittest.TestCase):
    def test_pj_lista_retencoes_que_fecham_com_liquido(self):
        item = calcular_folha_pessoa(
            {"nome_completo": "Henrique", "cargo": "Consultor", "tipo_contrato": "pj",
             "salario": 5000, "reter_federal": True},
            "simples_nacional", 2026, 9,
        )
        with capturar_textos() as textos:
            rp.pdf_contracheque("Escola", "setembro de 2026", item)
        texto = "\n".join(textos)
        for rotulo in ("IRRF retido", "PIS retido", "COFINS retida", "CSLL retida", "ISS retido"):
            self.assertIn(rotulo, texto)
        self.assertEqual(item["liquido"], 4692.5)
        self.assertIn("R$ 4.692,50", texto)
        self.assertIn("Assinatura do(a) colaborador(a)", texto)

    def test_clt_mostra_bases_fgts_e_assinatura(self):
        item = calcular_folha_pessoa(
            {"nome_completo": "Diego", "cargo": "Professor", "tipo_contrato": "clt_mensalista", "salario": 6500},
            "simples_nacional", 2026, 9,
        )
        with capturar_textos() as textos:
            rp.pdf_contracheque("Escola", "setembro de 2026", item)
        texto = "\n".join(textos)
        self.assertIn("Base do INSS", texto)
        self.assertIn("Base do FGTS", texto)
        self.assertIn("FGTS do mês (8%", texto)
        self.assertIn("Responsável pela escola", texto)
        self.assertIn("Declaro ter recebido", texto)


class RescisaoBoletimProvaTeste(unittest.TestCase):
    def test_rescisao_tem_assinaturas(self):
        with capturar_textos() as textos:
            rp.pdf_rescisao(
                "Escola", {"nome_completo": "Ana", "cpf": "111.222.333-44"},
                {"total_liquido": 2070, "saldo_salario": 1000}, 7,
            )
        texto = "\n".join(textos)
        self.assertIn("Recebi as verbas rescisórias", texto)
        self.assertIn("CPF 111.222.333-44", texto)
        self.assertIn("Responsável pela escola", texto)

    def test_boletim_sem_nota_e_nota_zero(self):
        notas = [
            {"materia": "Matemática", "trimestre": 1, "nota": None},
            {"materia": "História", "trimestre": 1, "nota": 0},
            {"materia": "Ciências", "trimestre": 1, "nota": 8.5},
        ]
        with capturar_textos() as textos:
            rp.pdf_boletim("Escola", {"nome_completo": "Bia"}, notas, {})
        self.assertIn("Sem nota", textos)
        self.assertIn("0,0", textos)
        self.assertIn("8,5", textos)
        self.assertIn("Assinatura do(a) responsável", textos)

    def test_prova_imagem_depois_do_enunciado(self):
        ordem = []
        multi_original = rp._ProvaPDF.multi_cell

        def multi_cell(self, *args, **kwargs):
            texto = str(kwargs.get("text", args[2] if len(args) > 2 else "") or "")
            if "Quanto é" in texto and not kwargs.get("dry_run"):
                ordem.append("enunciado")
            return multi_original(self, *args, **kwargs)

        questoes = [{"enunciado": "Quanto é 2 + 2?", "tipo": "dissertativa", "fotos": [(_png(), "image/png")]}]
        with mock.patch.object(rp._ProvaPDF, "multi_cell", multi_cell), \
                mock.patch.object(rp, "_imagem_questao", side_effect=lambda *a: ordem.append("imagem")):
            rp.pdf_prova("Escola", "1º A", "Prova 1", "Matemática", questoes)
        self.assertIn("imagem", ordem)
        self.assertLess(ordem.index("enunciado"), ordem.index("imagem"))


if __name__ == "__main__":
    unittest.main()
