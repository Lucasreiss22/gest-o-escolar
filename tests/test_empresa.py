import json
import unittest
from datetime import date, timedelta

from empresa import (
    COLUNAS_EMPRESA,
    campos_apagados,
    cnpj_valido,
    copia_para_plataforma,
    cpf_valido,
    dados_empresa_do_form,
    dados_empresa_tela,
    empresa_incompleta,
    formatar_cnpj,
    garantir_colunas_empresa,
    salvar_empresa,
    tem_dados_empresa,
)


class CursorFalso:
    def __init__(self):
        self.sqls = []

    def execute(self, sql, params=None):
        self.sqls.append((sql, params))


class TestValidadores(unittest.TestCase):
    def test_cnpj(self):
        self.assertTrue(cnpj_valido("11.222.333/0001-81"))
        self.assertTrue(cnpj_valido("11222333000181"))
        self.assertFalse(cnpj_valido("11.222.333/0001-82"))
        self.assertFalse(cnpj_valido("00000000000000"))
        self.assertFalse(cnpj_valido("123"))

    def test_cpf(self):
        self.assertTrue(cpf_valido("529.982.247-25"))
        self.assertFalse(cpf_valido("529.982.247-24"))
        self.assertFalse(cpf_valido("111.111.111-11"))

    def test_formatar(self):
        self.assertEqual(formatar_cnpj("11222333000181"), "11.222.333/0001-81")


class TestFormulario(unittest.TestCase):
    def form_ok(self, **extra):
        base = {
            "razao_social": "Colégio Exemplo Ltda",
            "cnpj": "11.222.333/0001-81",
            "inscricao_estadual": "isento",
            "inscricao_municipal": "12345",
            "cnae_principal": "8513-9/00",
            "codigo_inep": "33012345",
            "data_abertura": "2010-02-01",
            "porte": "me",
            "cep": "28000-000",
            "logradouro": "Rua A",
            "numero": "10",
            "bairro": "Centro",
            "cidade": "Campos",
            "estado": "rj",
            "codigo_municipio": "3301009",
            "responsavel_nome": "Maria",
            "responsavel_cpf": "529.982.247-25",
            "contador_email": "Contador@Escritorio.com.br",
        }
        base.update(extra)
        return base

    def test_normaliza(self):
        dados, erros = dados_empresa_do_form(self.form_ok())
        self.assertEqual(erros, [])
        self.assertEqual(dados["cnpj"], "11222333000181")
        self.assertEqual(dados["inscricao_estadual"], "ISENTO")
        self.assertEqual(dados["cnae_principal"], "8513900")
        self.assertEqual(dados["uf"], "RJ")
        self.assertEqual(dados["cep"], "28000000")
        self.assertEqual(dados["porte_empresa"], "me")
        self.assertEqual(dados["responsavel_cpf"], "52998224725")
        self.assertEqual(dados["contador_email"], "contador@escritorio.com.br")
        self.assertIsNone(dados["complemento"])

    def test_erros(self):
        futuro = (date.today() + timedelta(days=5)).isoformat()
        _dados, erros = dados_empresa_do_form(self.form_ok(
            cnpj="11.222.333/0001-00", inscricao_estadual="abc", cnae_principal="85",
            codigo_inep="1", data_abertura=futuro, cep="123", estado="XX",
            codigo_municipio="33", responsavel_cpf="123.456.789-00", contador_email="sem-arroba",
        ))
        texto = " ".join(erros)
        for trecho in ("CNPJ", "Inscrição estadual", "CNAE", "INEP", "futura", "CEP", "UF", "IBGE", "CPF", "E-mail"):
            self.assertIn(trecho, texto)

    def test_porte_desconhecido_vira_vazio(self):
        dados, _erros = dados_empresa_do_form(self.form_ok(porte="gigante"))
        self.assertIsNone(dados["porte_empresa"])

    def test_tem_dados(self):
        self.assertFalse(tem_dados_empresa({"nome": "X", "cnpj": "  "}))
        self.assertTrue(tem_dados_empresa({"cnpj": "11222333000181"}))


class TestPersistencia(unittest.TestCase):
    def test_garantir_um_alter(self):
        cur = CursorFalso()
        garantir_colunas_empresa(cur)
        self.assertEqual(len(cur.sqls), 1)
        sql = cur.sqls[0][0]
        self.assertIn("ADD COLUMN IF NOT EXISTS cnpj VARCHAR(20)", sql)
        self.assertIn("data_abertura DATE", sql)

    def test_salvar_so_os_preenchidos(self):
        dados, _ = dados_empresa_do_form({"cnpj": "11222333000181", "razao_social": "X"})
        cur = CursorFalso()
        alvo = salvar_empresa(cur, dados)
        sql, params = cur.sqls[-1]
        self.assertIn("ON CONFLICT (id) DO UPDATE", sql)
        self.assertEqual(sorted(alvo), ["cnpj", "razao_social"])
        self.assertEqual(params, ("X", "11222333000181"))
        self.assertNotIn("inscricao_municipal", sql)

    def test_limpar_vazios_grava_todas(self):
        dados, _ = dados_empresa_do_form({"razao_social": "X"})
        cur = CursorFalso()
        salvar_empresa(cur, dados, limpar_vazios=True)
        _sql, params = cur.sqls[-1]
        self.assertEqual(len(params), len(COLUNAS_EMPRESA))

    def test_form_vazio_nao_grava(self):
        dados, _ = dados_empresa_do_form({})
        cur = CursorFalso()
        self.assertEqual(salvar_empresa(cur, dados), [])
        self.assertEqual(len(cur.sqls), 1)

    def test_campos_apagados(self):
        atual = {"cnpj": "11222333000181", "inscricao_municipal": "123", "razao_social": "X"}
        dados, _ = dados_empresa_do_form({"razao_social": "X"})
        self.assertEqual(campos_apagados(atual, dados), ["CNPJ", "Inscrição municipal"])

    def test_tela_e_incompleta(self):
        cfg = {"cnpj": "11222333000181", "razao_social": "X", "data_abertura": date(2010, 2, 1), "uf": "RJ"}
        tela = dados_empresa_tela(cfg)
        self.assertEqual(tela["cnpj"], "11.222.333/0001-81")
        self.assertEqual(tela["data_abertura"], "2010-02-01")
        self.assertEqual(tela["estado"], "RJ")
        faltam = empresa_incompleta(cfg)
        self.assertIn("inscrição municipal", faltam)
        self.assertNotIn("CNPJ", faltam)

    def test_copia_plataforma(self):
        dados, _ = dados_empresa_do_form({"cnpj": "11222333000181", "logradouro": "Rua A", "estado": "SP", "cep": "01001000"})
        copia = copia_para_plataforma(dados)
        self.assertEqual(copia["cnpj"], "11222333000181")
        self.assertEqual(copia["nfse_uf"], "SP")
        self.assertEqual(json.loads(copia["dados_empresa"])["logradouro"], "Rua A")


MATRIZ = {"id": 1, "nome": "Colégio Centro", "cnpj": "11222333000181", "tipo_unidade": "matriz", "matriz_id": None, "db_nome": "esc_a"}
FILIAL = {"id": 2, "nome": "Colégio Bairro", "cnpj": "11222333000262", "tipo_unidade": "filial", "matriz_id": 1, "db_nome": "esc_b"}
NOVA = {"id": 3, "nome": "Colégio Norte", "cnpj": "11222333000343", "tipo_unidade": "independente", "matriz_id": None}
OUTRA = {"id": 4, "nome": "Outra Rede", "cnpj": "99888777000100", "tipo_unidade": "matriz", "matriz_id": None}
REDE = [MATRIZ, FILIAL, NOVA, OUTRA]


class TestUnidades(unittest.TestCase):
    def test_raiz(self):
        from unidades import raiz_cnpj
        self.assertEqual(raiz_cnpj("11.222.333/0002-62"), "11222333")
        self.assertEqual(raiz_cnpj("123"), "")

    def test_opcoes_so_com_mesma_raiz(self):
        from unidades import matrizes_possiveis
        self.assertEqual([m["id"] for m in matrizes_possiveis(NOVA, REDE)], [1])
        self.assertEqual(matrizes_possiveis({"id": 9, "cnpj": ""}, REDE), [])

    def test_filial_valida(self):
        from unidades import validar_unidade
        self.assertEqual(validar_unidade(NOVA, "filial", "1", REDE), ("filial", 1))

    def test_filial_de_outra_raiz(self):
        from unidades import validar_unidade
        with self.assertRaises(ValueError) as ctx:
            validar_unidade(NOVA, "filial", 4, REDE)
        self.assertIn("raiz de CNPJ", str(ctx.exception))

    def test_filial_de_quem_nao_e_matriz(self):
        from unidades import validar_unidade
        with self.assertRaises(ValueError):
            validar_unidade(NOVA, "filial", 2, REDE)
        with self.assertRaises(ValueError):
            validar_unidade(NOVA, "filial", None, REDE)
        with self.assertRaises(ValueError):
            validar_unidade(NOVA, "filial", 3, REDE)

    def test_matriz_com_filiais_nao_muda(self):
        from unidades import validar_unidade
        with self.assertRaises(ValueError) as ctx:
            validar_unidade(MATRIZ, "independente", None, REDE)
        self.assertIn("Colégio Bairro", str(ctx.exception))
        self.assertEqual(validar_unidade(MATRIZ, "matriz", 99, REDE), ("matriz", None))

    def test_sem_cnpj(self):
        from unidades import validar_unidade
        with self.assertRaises(ValueError):
            validar_unidade({"id": 5, "cnpj": None}, "matriz", None, REDE)
        self.assertEqual(validar_unidade({"id": 5, "cnpj": None}, "xyz", None, REDE), ("independente", None))

    def test_resumo(self):
        from unidades import resumo_unidade
        r = resumo_unidade(MATRIZ, REDE)
        self.assertEqual(r["filiais"], [{"id": 2, "nome": "Colégio Bairro"}])
        f = resumo_unidade(FILIAL, REDE)
        self.assertEqual((f["tipo"], f["matriz_nome"], f["db_nome"]), ("filial", "Colégio Centro", "esc_b"))


if __name__ == "__main__":
    unittest.main()
