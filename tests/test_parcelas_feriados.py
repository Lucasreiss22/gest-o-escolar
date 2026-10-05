import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from feriados import feriados_nacionais, feriados_nacionais_mes, pascoa
from parcelas import TravaCompetencias, limite_apurado, plano_parcelas, texto_puladas, travas_da_escola

HOJE = date(2026, 10, 4)


class TestFeriadosNacionais(unittest.TestCase):
    def test_pascoa(self):
        self.assertEqual(pascoa(2024), date(2024, 3, 31))
        self.assertEqual(pascoa(2025), date(2025, 4, 20))
        self.assertEqual(pascoa(2026), date(2026, 4, 5))

    def test_fixos_e_sexta_santa(self):
        f = feriados_nacionais(2026)
        self.assertIn(date(2026, 9, 7), f)
        self.assertIn(date(2026, 11, 20), f)
        self.assertEqual(f[date(2026, 4, 3)], "Sexta-feira Santa")
        self.assertEqual(len(f), 10)

    def test_facultativos_so_quando_marcados(self):
        self.assertNotIn(date(2026, 2, 16), feriados_nacionais(2026))
        f = feriados_nacionais(2026, carnaval=True, corpus_christi=True)
        self.assertIn(date(2026, 2, 16), f)
        self.assertIn(date(2026, 2, 17), f)
        self.assertIn(date(2026, 6, 4), f)

    def test_consciencia_negra_desde_2024(self):
        self.assertNotIn(date(2023, 11, 20), feriados_nacionais(2023))
        self.assertIn(date(2024, 11, 20), feriados_nacionais(2024))

    def test_mes(self):
        self.assertEqual(list(feriados_nacionais_mes(2026, 9)), [date(2026, 9, 7)])
        self.assertEqual(feriados_nacionais_mes(2026, 8), {})


class TestPlanoParcelas(unittest.TestCase):
    def test_limite_apurado_simples(self):
        self.assertEqual(limite_apurado(HOJE, "simples_nacional"), "2026-08")
        self.assertEqual(limite_apurado(date(2026, 10, 21), "simples_nacional"), "2026-09")
        self.assertEqual(limite_apurado(date(2026, 1, 5), "simples_nacional"), "2025-11")
        self.assertIsNone(limite_apurado(HOJE, None))
        self.assertIsNone(limite_apurado(HOJE, ""))

    def test_limite_apurado_trimestral(self):
        self.assertEqual(limite_apurado(HOJE, "lucro_presumido"), "2026-06")
        self.assertEqual(limite_apurado(date(2026, 10, 30), "lucro_presumido"), "2026-06")
        self.assertEqual(limite_apurado(date(2026, 10, 31), "lucro_presumido"), "2026-09")
        self.assertEqual(limite_apurado(date(2026, 11, 2), "lucro_real"), "2026-09")
        self.assertEqual(limite_apurado(date(2026, 1, 5), "lucro_presumido"), "2025-09")
        self.assertEqual(limite_apurado(date(2026, 2, 2), "lucro_presumido"), "2025-12")

    def test_travas_da_rede_juntam_unidades(self):
        class Cur:
            def __init__(self):
                self.sqls = []

            def execute(self, sql, params=None):
                self.sqls.append(sql)

            def fetchall(self):
                return [{"competencia": "2026-09"}] if '"esc_filial"' in self.sqls[-1] else []

        cur = Cur()
        travas = travas_da_escola(cur, hoje=HOJE, regime="simples_nacional", schemas=["esc_matriz", "esc_filial"])
        self.assertIn("2026-09", travas)
        self.assertFalse(any("configuracoes" in s for s in cur.sqls))

    def test_padrao_comeca_no_mes_atual(self):
        plano = plano_parcelas("2026-02-10", 12, hoje=HOJE)
        self.assertEqual([n for n, _v in plano["gerar"]], [9, 10, 11, 12])
        self.assertEqual(plano["gerar"][0][1], date(2026, 10, 10))
        self.assertEqual(len(plano["passadas"]), 8)
        self.assertEqual(plano["travadas"], [])

    def test_confirmado_gera_passadas_mas_respeita_apurado(self):
        travas = TravaCompetencias("2026-08", {"2026-11"})
        plano = plano_parcelas("2026-02-10", 12, hoje=HOJE, gerar_passadas=True, travas=travas)
        comps = [v.strftime("%Y-%m") for _n, v in plano["gerar"]]
        self.assertEqual(comps, ["2026-09", "2026-10", "2026-12", "2027-01"])
        self.assertEqual(plano["travadas"][0], "2026-02")
        self.assertIn("2026-11", plano["travadas"])
        self.assertEqual(plano["passadas"], [])

    def test_contrato_futuro_inteiro(self):
        plano = plano_parcelas("2026-11-05", 3, hoje=HOJE)
        self.assertEqual(len(plano["gerar"]), 3)

    def test_texto(self):
        plano = plano_parcelas("2026-02-10", 12, hoje=HOJE, travas=TravaCompetencias("2026-08"))
        texto = texto_puladas(plano)
        self.assertIn("09/2026", texto)
        self.assertIn("02/2026 a 08/2026", texto)
        self.assertEqual(texto_puladas(plano_parcelas("2026-10-01", 2, hoje=HOJE)), "")

    def test_travas_da_escola(self):
        class Cur:
            def __init__(self):
                self.ultimo = ""

            def execute(self, sql, params=None):
                self.ultimo = sql

            def fetchone(self):
                return {"regime_tributario": "simples_nacional"}

            def fetchall(self):
                return [{"competencia": "2026-09"}] if "simples_competencias" in self.ultimo else []

        travas = travas_da_escola(Cur(), hoje=HOJE)
        self.assertIn("2026-08", travas)
        self.assertIn("2026-09", travas)
        self.assertNotIn("2026-10", travas)


class TestAppParcelasFeriados(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app as app_mod

        cls.app = app_mod

    def test_divergentes_so_do_mes_atual(self):
        mens = [
            {"id": 1, "parcela_contrato": 1, "status": "Pendente", "valor": 1100, "data_vencimento": date(2026, 9, 10)},
            {"id": 2, "parcela_contrato": 2, "status": "Pendente", "valor": 1100, "data_vencimento": date(2026, 10, 10)},
        ]
        ids = [m["id"] for m in self.app._mensalidades_abertas_divergentes(mens, 990.0, a_partir="2026-10")]
        self.assertEqual(ids, [2])

    def test_eventos_virtuais_sem_duplicar(self):
        dias = {date(2026, 9, d) for d in range(1, 31)} | {date(2026, 10, d) for d in range(1, 4)}
        cfg = {"auto": True, "carnaval": False, "corpus_christi": False}
        virtuais = self.app._eventos_feriados_nacionais([], dias, cfg)
        self.assertEqual([v["data_evento"] for v in virtuais], [date(2026, 9, 7)])
        cadastrado = [{"tipo": "feriado", "data_evento": date(2026, 9, 7), "turma_id": None, "aluno_id": None}]
        self.assertEqual(self.app._eventos_feriados_nacionais(cadastrado, dias, cfg), [])
        self.assertEqual(self.app._eventos_feriados_nacionais([], dias, dict(cfg, auto=False)), [])

    def _bloqueio(self, regime_apuracao, linhas, **kwargs):
        from unittest import mock

        class Cur:
            def execute(self, sql, params=None):
                pass

            def fetchall(self):
                return linhas

        ctx = {"efetiva": {"regime_tributario": "lucro_presumido", "regime_apuracao": regime_apuracao}}
        with mock.patch.object(self.app, "_contexto_tributario", return_value=ctx), \
                mock.patch.object(self.app, "_travas_rede", return_value=TravaCompetencias("2026-06")):
            return self.app._bloqueio_parcelas(Cur(), **kwargs)

    def test_baixa_no_caixa_em_trimestre_travado(self):
        aberta = [{"data_vencimento": date(2026, 5, 10), "data_pagamento": None, "mora": 0}]
        self.assertIsNotNone(self._bloqueio("caixa", aberta, ids=[1], pagamentos=[date(2026, 6, 15)], vencimento_dos_ids=False))
        self.assertIsNone(self._bloqueio("caixa", aberta, ids=[1], pagamentos=[date(2026, 10, 4)], vencimento_dos_ids=False))

    def test_tirar_baixa_paga_em_trimestre_travado(self):
        paga = [{"data_vencimento": date(2026, 9, 10), "data_pagamento": date(2026, 6, 20), "mora": 0}]
        self.assertIsNotNone(self._bloqueio("caixa", paga, ids=[1], vencimento_dos_ids=False))
        self.assertIsNone(self._bloqueio("competencia", paga, ids=[1], vencimento_dos_ids=False))

    def test_baixa_na_competencia_so_trava_com_juros(self):
        aberta = [{"data_vencimento": date(2026, 5, 10), "data_pagamento": None, "mora": 0}]
        kwargs = {"ids": [1], "pagamentos": [date(2026, 6, 15)], "vencimento_dos_ids": False}
        self.assertIsNone(self._bloqueio("competencia", aberta, **kwargs))
        self.assertIsNotNone(self._bloqueio("competencia", aberta, mora_nova=True, **kwargs))

    def test_feriados_do_mes_junta_nacionais(self):
        class Cur:
            def execute(self, sql, params=None):
                self.sql = sql

            def fetchone(self):
                return {"feriados_nacionais_auto": True, "feriado_carnaval": False, "feriado_corpus_christi": False}

            def fetchall(self):
                return [{"data_evento": date(2026, 9, 20)}] if "calendario_eventos" in self.sql else []

        with self.app.app.test_request_context("/"):
            datas = self.app._feriados_do_mes(Cur(), 2026, 9)
        self.assertEqual(datas, {date(2026, 9, 7), date(2026, 9, 20)})


if __name__ == "__main__":
    unittest.main()
