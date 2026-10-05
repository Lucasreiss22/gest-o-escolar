"""Lucro Real da rede no mesmo cursor: contagem de consultas (P3–P5) e números do reteste (P7)."""

import unittest
from datetime import date
from unittest import mock

import database

ESCOLAS = [
    {"id": 1, "nome": "Matriz", "db_nome": "esc_matriz", "tipo_unidade": "matriz", "matriz_id": None, "cnpj": "11222333000181"},
    {"id": 2, "nome": "Filial", "db_nome": "esc_filial", "tipo_unidade": "filial", "matriz_id": 1, "cnpj": "11222333000262"},
]


def _funcionarios(n, base_id):
    return [
        {
            "id": base_id + i, "nome_completo": f"Pessoa {base_id + i}", "tipo_contrato": "clt_mensalista",
            "salario": 3000, "data_inicio_contrato": date(2025, 1, 1), "data_contratacao": date(2025, 1, 1),
            "ativo": True, "data_fim_contrato": None, "email": None, "ponto_jornada_minutos": None,
        }
        for i in range(n)
    ]


class _CursorLucroReal:
    """Banco falso da rede (matriz + filial) no Lucro Real. SAVEPOINT e DDL não contam."""

    def __init__(self, periodo="trimestral", meses=None, receitas=None, custos=None, funcionarios=(11, 2), snapshot=None):
        self.periodo = periodo
        self.consultas = []
        self.description = None
        self._resultado = []
        meses = meses or ["2026-10"]
        receitas = receitas or {"esc_matriz": 100_000.0, "esc_filial": 50_000.0}
        self.mensalidades = {}
        for s, valor in receitas.items():
            por_mes = valor if isinstance(valor, dict) else {m: valor for m in meses}
            self.mensalidades[s] = [{"tipo": "v", "comp": m, "receita": v} for m, v in sorted(por_mes.items())]
            self.mensalidades[s].append({"tipo": "iv", "comp": min(por_mes) if por_mes else None, "receita": 0})
        self.custos = custos or {"esc_matriz": [], "esc_filial": []}
        self.funcionarios = {"esc_matriz": _funcionarios(funcionarios[0], 100), "esc_filial": _funcionarios(funcionarios[1], 200)}
        self.snapshot = snapshot or []

    def _schema(self, sql):
        for escola in ESCOLAS:
            if f'"{escola["db_nome"]}".' in sql:
                return escola["db_nome"]
        return database._nome_banco_atual()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        texto = " ".join(sql.split())
        if texto.upper().startswith(("SAVEPOINT", "RELEASE", "ROLLBACK", "CREATE", "ALTER", "DO ")):
            return
        self.consultas.append(texto)
        schema = self._schema(texto)
        if "plataforma_escolas" in texto:
            self._resultado = [dict(e) for e in ESCOLAS]
        elif "tributos_snapshot" in texto:
            self._resultado = [dict(s) for s in self.snapshot]
        elif "FROM configuracoes" in texto or "configuracoes WHERE" in texto or ".configuracoes" in texto:
            self._resultado = [{
                "nome_escola": schema, "regime_tributario": "lucro_real", "regime_apuracao": "competencia",
                "lucro_real_periodo": self.periodo, "lucro_real_estimativa_modo": "balancete",
                "pis_cofins_lucro_real": "cumulativo_ensino", "iss_aliquota_pct": 5,
            }]
        elif "financeiro_mensalidades" in texto:
            self._resultado = [dict({"juros": 0, "multa": 0, "qtd": 0}, **l) for l in self.mensalidades[schema]]
        elif "financeiro_custos" in texto:
            self._resultado = [dict(c) for c in self.custos[schema]]
        elif "funcionarios" in texto and "ponto_registros" not in texto:
            self._resultado = [dict(f) for f in self.funcionarios[schema]]
        else:
            self._resultado = []

    def fetchone(self):
        return self._resultado[0] if self._resultado else None

    def fetchall(self):
        return list(self._resultado)


class LucroRealRedeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app as app_mod

        cls.app = app_mod

    def setUp(self):
        import carga_tributos

        carga_tributos._CACHE.clear()

    def _rede(self, cur, mes, schema="esc_matriz"):
        token = database.definir_banco_escola(schema)
        try:
            with mock.patch.multiple(self.app, garantir_tabelas_folha=mock.DEFAULT, _garantir_ponto=mock.DEFAULT,
                                     _garantir_folha_ajustes=mock.DEFAULT), \
                    mock.patch.object(self.app, "obter_conexao") as conexao, \
                    self.app.app.test_request_context("/"):
                resultado = self.app._lucro_real_rede(mes, cur)
        finally:
            database.limpar_banco_escola(token)
        return resultado, conexao.call_count

    def test_p3_trimestral_no_mesmo_cursor(self):
        cur = _CursorLucroReal()
        resultado, conexoes = self._rede(cur, "2026-10")
        self.assertEqual(conexoes, 0)
        self.assertLessEqual(len(cur.consultas), 25, cur.consultas)
        self.assertEqual(resultado["erros"], [])
        self.assertEqual([u["id"] for u in resultado["unidades"]], [1, 2])

    def test_p3_repetido_sai_do_cache(self):
        cur = _CursorLucroReal()
        self._rede(cur, "2026-10")
        antes = len(cur.consultas)
        self._rede(cur, "2026-10")
        self.assertEqual(len(cur.consultas), antes)

    def test_p4_anual_em_dezembro_sem_snapshot(self):
        meses = [f"2026-{m:02d}" for m in range(1, 13)]
        cur = _CursorLucroReal(periodo="anual_estimativa", meses=meses)
        resultado, conexoes = self._rede(cur, "2026-12")
        self.assertEqual(conexoes, 0)
        self.assertLessEqual(len(cur.consultas), 40, cur.consultas)
        self.assertEqual(len(resultado["lair_empresa"]), 12)

    def test_p5_anual_com_snapshot_jan_a_set(self):
        meses = [f"2026-{m:02d}" for m in range(1, 13)]
        snapshot = [
            {"unidade_id": uid, "competencia": f"2026-{m:02d}", "dados": {"lair": 1000.0 * uid}}
            for uid in (1, 2) for m in range(1, 10)
        ]
        cur = _CursorLucroReal(periodo="anual_estimativa", meses=meses, snapshot=snapshot)
        resultado, _conexoes = self._rede(cur, "2026-12")
        self.assertLessEqual(len(cur.consultas), 20, cur.consultas)
        self.assertEqual(resultado["meses_unidades"][2]["2026-01"]["lair"], 2000.0)
        self.assertTrue(resultado["meses_unidades"][2]["2026-01"]["congelado"])
        self.assertFalse(resultado["meses_unidades"][2]["2026-10"]["congelado"])
        custos_lidos = [c for c in cur.consultas if "financeiro_custos" in c]
        self.assertEqual(len(custos_lidos), 2)

    def test_p7_numeros_do_reteste(self):
        custos = {
            "esc_matriz": [{"tipo": "avista", "data_custo": date(2026, 10, 1), "valor": 9901.68}],
            "esc_filial": [{"tipo": "avista", "data_custo": date(2026, 10, 1), "valor": 7188.09}],
        }
        for schema in ("esc_matriz", "esc_filial"):
            import carga_tributos

            carga_tributos._CACHE.clear()
            cur = _CursorLucroReal(receitas={"esc_matriz": 0.0, "esc_filial": 50_000.0}, custos=custos, funcionarios=(0, 0))
            r, _conexoes = self._rede(cur, "2026-10", schema)
            self.assertEqual(r["lair_unidades"], {1: -9901.68, 2: 38_486.91})
            self.assertEqual(r["lair_empresa"], [28_585.23])
            mes = r["provisao"]["mes"]
            self.assertEqual((mes["irpj"], mes["adicional"], mes["csll"]), (4_287.78, 858.52, 2_572.67))
            self.assertEqual(r["rateio"][2]["total"], round(4_287.78 + 858.52 + 2_572.67, 2))
            self.assertEqual(r["rateio"].get(1, {}).get("total", 0.0), 0.0)

    def test_l2_terceiro_tri_nunca_aberto_entra_na_cadeia(self):
        custos = {
            "esc_matriz": [
                {"tipo": "avista", "data_custo": date(2026, 7, 10), "valor": 30_000},
                {"tipo": "avista", "data_custo": date(2026, 12, 10), "valor": 82_700},
            ],
            "esc_filial": [],
        }
        cur = _CursorLucroReal(receitas={"esc_matriz": {"2026-12": 200_000.0}, "esc_filial": {}}, custos=custos,
                               funcionarios=(0, 0))
        r, _conexoes = self._rede(cur, "2026-12")
        self.assertEqual(r["saldo_anterior"]["prejuizo_fiscal"], 30_000.00)
        per = r["provisao"]["periodo"]
        self.assertEqual(per["compensacao_irpj"], 30_000.00)
        self.assertEqual(per["base_irpj"], 70_000.00)
        self.assertEqual((per["irpj"], per["adicional"], per["csll"]), (10_500.00, 1_000.00, 6_300.00))
        self.assertEqual(per["novo_prejuizo"], 0.0)

    def test_l4_get_nao_grava_saldo(self):
        cur = _CursorLucroReal(meses=["2026-07", "2026-08", "2026-09"])
        token = database.definir_banco_escola("esc_matriz")
        try:
            with mock.patch.multiple(self.app, garantir_tabelas_folha=mock.DEFAULT, _garantir_ponto=mock.DEFAULT,
                                     _garantir_folha_ajustes=mock.DEFAULT), \
                    mock.patch.object(self.app, "obter_conexao"), self.app.app.test_request_context("/"):
                real = self.app._lucro_real_rede("2026-09", cur)
                self.app._tributos_do_mes(cur, "2026-09", real_rede=real)
        finally:
            database.limpar_banco_escola(token)
        self.assertFalse([c for c in cur.consultas if "lucro_real_saldos" in c and c.upper().startswith(("INSERT", "UPDATE"))])
        self.assertFalse([c for c in cur.consultas if "tributos_snapshot" in c and c.upper().startswith(("INSERT", "UPDATE", "DELETE"))])


if __name__ == "__main__":
    unittest.main()
