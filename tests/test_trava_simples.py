import os
import sys
import unittest
from datetime import date
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database  # noqa: E402
from tributacao import competencia_do_titulo  # noqa: E402

HOJE = date(2026, 10, 4)
MSG_SIMPLES = "o PGDAS-D desse mês já venceu"
MSG_TRIMESTRE = "o trimestre encerrou e a DARF venceu"


class _CursorTrava:
    """Banco falso: rede matriz + filial, configuração por unidade, competências congeladas e parcelas."""

    ESCOLAS = [
        {"id": 1, "nome": "Matriz", "db_nome": "esc_matriz", "tipo_unidade": "matriz", "matriz_id": None, "cnpj": "11222333000181"},
        {"id": 2, "nome": "Filial", "db_nome": "esc_filial", "tipo_unidade": "filial", "matriz_id": 1, "cnpj": "11222333000262"},
    ]

    def __init__(self, configs, parcelas, congeladas=None, rede=True):
        self.configs = configs
        self.parcelas = {p["id"]: dict(p) for p in parcelas}
        self.congeladas = congeladas or {}
        self.rede = rede
        self.escritas = []
        self._resultado = []
        self.rowcount = 0
        self.description = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def _schema(self, sql):
        for escola in self.ESCOLAS:
            if f'"{escola["db_nome"]}".' in sql:
                return escola["db_nome"]
        return database._nome_banco_atual()

    def execute(self, sql, params=None):
        texto = " ".join(sql.split())
        upper = texto.upper()
        self._resultado = []
        if upper.startswith(("SAVEPOINT", "RELEASE", "ROLLBACK")):
            return
        schema = self._schema(sql)
        if upper.startswith(("UPDATE FINANCEIRO_MENSALIDADES", "DELETE FROM FINANCEIRO_MENSALIDADES")):
            self.escritas.append((texto, params))
            self.rowcount = 1
            if upper.startswith("UPDATE") and "SET STATUS = 'PAGO'" in upper:
                ids = params[-1] if isinstance(params[-1], list) else [int(params[-1])]
                for i in ids:
                    self.parcelas[int(i)].update(status="Pago", data_pagamento=params[1])
            return
        if "plataforma_escolas" in texto:
            self._resultado = [dict(e) for e in self.ESCOLAS] if self.rede else []
        elif "simples_competencias" in texto:
            self._resultado = [{"competencia": c} for c in self.congeladas.get(schema, [])]
        elif "configuracoes" in texto:
            self._resultado = [dict(self.configs.get(schema) or {})]
        elif upper.startswith("SELECT") and "financeiro_mensalidades" in texto:
            self._resultado = [
                {
                    "data_vencimento": p["data_vencimento"], "data_pagamento": p.get("data_pagamento"),
                    "status": p["status"], "valor": p["valor"], "mora": p.get("mora", 0),
                }
                for i, p in self.parcelas.items() if i in [int(x) for x in params[0]]
            ]

    def fetchone(self):
        return self._resultado[0] if self._resultado else None

    def fetchall(self):
        return list(self._resultado)


class _ConexaoFalsa:
    def __init__(self, cursor):
        self.cur = cursor
        self.commits = 0
        self.rollbacks = 0

    def cursor(self, cursor_factory=None):
        return self.cur

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass


def _cfg(regime="simples_nacional", apuracao="caixa"):
    return {"id": 1, "nome_escola": "Escola", "regime_tributario": regime, "regime_apuracao": apuracao}


def _parcela(venc, pag=None, valor=1000.0, status=None, mora=0):
    return {
        "id": 1, "data_vencimento": venc, "data_pagamento": pag, "valor": valor,
        "status": status or ("Pago" if pag else "Pendente"), "mora": mora,
    }


class TravaSimplesRotasTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app as app_mod

        cls.app = app_mod

    def setUp(self):
        import carga_tributos

        carga_tributos._CACHE.clear()

    def _executar(self, chamada, cur, schema, hoje, form=None, path="/financeiro"):
        app = self.app
        conexao = _ConexaoFalsa(cur)
        original = app._travas_rede
        token = database.definir_banco_escola(schema)
        try:
            with mock.patch.object(app, "garantir_tabelas_folha"), \
                    mock.patch.object(app, "garantir_tabelas_pedagogicas"), \
                    mock.patch.object(app, "obter_conexao", return_value=conexao), \
                    mock.patch.object(app, "_travas_rede", side_effect=lambda c, h=None: original(c, hoje)):
                with app.app.test_request_context(path, method="POST", data=form or {}):
                    app.session["usuario_id"] = 1
                    chamada()
                    flashes = list(app.session.get("_flashes") or [])
        finally:
            database.limpar_banco_escola(token)
        return conexao, flashes

    def _baixa(self, cur, data_pag, hoje=HOJE, schema="esc_matriz", acao="dar_baixa"):
        form = {"acao": acao, "cobranca_id": "1", "data_pagamento": data_pag, "forma_pagamento": "Pix"}
        return self._executar(self.app.pagina_financeiro, cur, schema, hoje, form)

    def _bloqueou(self, flashes, trecho=MSG_SIMPLES):
        return any(cat == "danger" and trecho in msg for cat, msg in flashes)

    def _configs(self, matriz=None, filial=None):
        return {"esc_matriz": matriz or _cfg(), "esc_filial": filial or _cfg()}

    def test_s1_baixa_no_caixa_em_junho_bloqueia_e_das_continua_zero(self):
        cur = _CursorTrava(self._configs(), [_parcela(date(2027, 1, 10))])
        conexao, flashes = self._baixa(cur, "2026-06-15")
        self.assertTrue(self._bloqueou(flashes))
        self.assertTrue(any("Competência já apurada (06/2026)" in m for _c, m in flashes))
        self.assertEqual(cur.escritas, [])
        self.assertGreaterEqual(conexao.rollbacks, 1)
        receita_jun = sum(
            p["valor"] for p in cur.parcelas.values()
            if competencia_do_titulo(p["data_vencimento"], p["data_pagamento"], p["status"], "caixa") == "2026-06"
        )
        self.assertEqual(receita_jun, 0)

    def test_s2_baixa_em_setembro_permite(self):
        cur = _CursorTrava(self._configs(), [_parcela(date(2027, 1, 10))])
        _conexao, flashes = self._baixa(cur, "2026-09-15")
        self.assertFalse(self._bloqueou(flashes))
        self.assertEqual(len(cur.escritas), 1)

    def test_s3_depois_do_dia_20_setembro_trava(self):
        cur = _CursorTrava(self._configs(), [_parcela(date(2027, 1, 10))])
        _conexao, flashes = self._baixa(cur, "2026-09-15", hoje=date(2026, 10, 21))
        self.assertTrue(any("(09/2026)" in m for c, m in flashes if c == "danger"))
        self.assertEqual(cur.escritas, [])

    def test_s4_tirar_baixa_paga_em_agosto(self):
        cur = _CursorTrava(self._configs(), [_parcela(date(2026, 8, 10), pag=date(2026, 8, 10))])
        form = {"acao": "tirar_baixa", "cobranca_id": "1"}
        _conexao, flashes = self._executar(self.app.pagina_financeiro, cur, "esc_matriz", HOJE, form)
        self.assertTrue(any("(08/2026)" in m for c, m in flashes if c == "danger"))
        self.assertEqual(cur.escritas, [])

    def test_s5_alterar_pagamento_para_agosto(self):
        cur = _CursorTrava(self._configs(), [_parcela(date(2026, 10, 10), pag=date(2026, 10, 5))])
        form = {"acao": "alterar_data_pagamento", "cobranca_id": "1", "data_pagamento": "2026-08-30"}
        _conexao, flashes = self._executar(self.app.pagina_financeiro, cur, "esc_matriz", HOJE, form)
        self.assertTrue(any("(08/2026)" in m for c, m in flashes if c == "danger"))
        self.assertEqual(cur.escritas, [])

    def test_s6_competencia_baixa_em_junho_permite(self):
        configs = self._configs(_cfg(apuracao="competencia"), _cfg(apuracao="competencia"))
        cur = _CursorTrava(configs, [_parcela(date(2027, 1, 10))])
        _conexao, flashes = self._baixa(cur, "2026-06-15")
        self.assertFalse(self._bloqueou(flashes))
        self.assertEqual(len(cur.escritas), 1)

    def test_s7_competencia_excluir_parcela_de_junho(self):
        configs = self._configs(_cfg(apuracao="competencia"), _cfg(apuracao="competencia"))
        cur = _CursorTrava(configs, [_parcela(date(2026, 6, 10), valor=1100.0)])
        conexao, flashes = self._executar(
            lambda: self.app.excluir_financeiro(1), cur, "esc_matriz", HOJE, path="/financeiro/excluir/1"
        )
        self.assertTrue(any("(06/2026)" in m and MSG_SIMPLES in m for c, m in flashes if c == "danger"))
        self.assertEqual(cur.escritas, [])
        self.assertEqual(conexao.commits, 0)
        self.assertIn(1, cur.parcelas)

    def test_s8_competencia_alterar_vencimento_de_junho(self):
        configs = self._configs(_cfg(apuracao="competencia"), _cfg(apuracao="competencia"))
        cur = _CursorTrava(configs, [_parcela(date(2026, 6, 10))])
        form = {"acao": "alterar_data_vencimento", "cobranca_id": "1", "data_vencimento": "2026-11-10"}
        _conexao, flashes = self._executar(self.app.pagina_financeiro, cur, "esc_matriz", HOJE, form)
        self.assertTrue(any("(06/2026)" in m for c, m in flashes if c == "danger"))
        self.assertEqual(cur.escritas, [])

    def test_s9_filial_obedece_o_caixa_da_matriz(self):
        configs = self._configs(_cfg(apuracao="caixa"), _cfg(apuracao="competencia"))
        cur = _CursorTrava(configs, [_parcela(date(2027, 1, 10))])
        _conexao, flashes = self._baixa(cur, "2026-06-15", schema="esc_filial")
        self.assertTrue(self._bloqueou(flashes))
        self.assertEqual(cur.escritas, [])

    def test_s10_congelada_na_filial_trava_a_matriz(self):
        cur = _CursorTrava(self._configs(), [_parcela(date(2027, 1, 10))], congeladas={"esc_filial": ["2026-10"]})
        _conexao, flashes = self._baixa(cur, "2026-10-15")
        self.assertTrue(any("(10/2026)" in m for c, m in flashes if c == "danger"))
        self.assertEqual(cur.escritas, [])

    def test_s11_presumido_caixa_regressao(self):
        configs = self._configs(_cfg("lucro_presumido", "caixa"), _cfg("lucro_presumido", "caixa"))
        cur = _CursorTrava(configs, [_parcela(date(2027, 1, 10))])
        _conexao, flashes = self._baixa(cur, "2026-06-15")
        self.assertTrue(self._bloqueou(flashes, MSG_TRIMESTRE))
        self.assertEqual(cur.escritas, [])
        cur = _CursorTrava(configs, [_parcela(date(2027, 1, 10))])
        _conexao, flashes = self._baixa(cur, "2026-09-15")
        self.assertFalse(self._bloqueou(flashes, MSG_TRIMESTRE))
        self.assertEqual(len(cur.escritas), 1)

    def test_s12_regime_nao_informado_nao_bloqueia(self):
        configs = self._configs(_cfg(None, "caixa"), _cfg(None, "caixa"))
        cur = _CursorTrava(configs, [_parcela(date(2027, 1, 10))])
        _conexao, flashes = self._baixa(cur, "2026-06-15")
        self.assertFalse(any(c == "danger" for c, _m in flashes))
        self.assertEqual(len(cur.escritas), 1)

    def test_baixa_em_lote_e_tirar_baixa_em_lote(self):
        cur = _CursorTrava(self._configs(), [_parcela(date(2027, 1, 10))])
        _conexao, flashes = self._baixa(cur, "2026-06-15", acao="dar_baixa_lote")
        self.assertTrue(self._bloqueou(flashes))
        cur = _CursorTrava(self._configs(), [_parcela(date(2026, 8, 10), pag=date(2026, 8, 10))])
        form = {"acao": "tirar_baixa_lote", "cobranca_id": "1"}
        _conexao, flashes = self._executar(self.app.pagina_financeiro, cur, "esc_matriz", HOJE, form)
        self.assertTrue(self._bloqueou(flashes))
        self.assertEqual(cur.escritas, [])


if __name__ == "__main__":
    unittest.main()
