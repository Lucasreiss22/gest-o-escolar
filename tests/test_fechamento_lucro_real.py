"""Fechar e reabrir o período do Lucro Real (matriz, admin, depois da DARF) e o snapshot dos tributos."""

import unittest
from unittest import mock

import database
try:
    from test_lucro_real_rede import _CursorLucroReal
except ImportError:
    from tests.test_lucro_real_rede import _CursorLucroReal


class _CursorFechamento(_CursorLucroReal):
    def __init__(self, saldos=None, folha_fechada=None, **kw):
        super().__init__(funcionarios=(0, 0), **kw)
        self.saldos = saldos or []
        self.folha_fechada = folha_fechada or {}
        self.escritas = []

    def execute(self, sql, params=None):
        texto = " ".join(sql.split())
        if texto.upper().startswith(("INSERT", "DELETE", "UPDATE")):
            self.escritas.append((texto, params))
            self._resultado = []
            return
        super().execute(sql, params)
        if "lucro_real_saldos" in texto and texto.upper().startswith("SELECT"):
            self._resultado = [dict(s) for s in self.saldos]
        elif "folha_snapshot" in texto:
            schema = self._schema(texto)
            self._resultado = [{"origem": "f", "competencia": c, "total": v} for c, v in self.folha_fechada.get(schema, {}).items()]

    def escritas_em(self, nome, acao):
        return [(t, p) for t, p in self.escritas if nome in t and t.upper().startswith(acao)]


class _Conexao:
    def __init__(self, cur):
        self.cur = cur
        self.commits = 0

    def cursor(self, cursor_factory=None):
        return self.cur

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass


class FechamentoLucroRealTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app as app_mod

        cls.app = app_mod

    def setUp(self):
        import carga_tributos

        carga_tributos._CACHE.clear()

    def _post(self, view, cur, dados, schema="esc_matriz", papel="admin"):
        conexao = _Conexao(cur)
        token = database.definir_banco_escola(schema)
        try:
            with mock.patch.multiple(self.app, garantir_tabelas_folha=mock.DEFAULT, _garantir_ponto=mock.DEFAULT,
                                     _garantir_folha_ajustes=mock.DEFAULT), \
                    mock.patch.object(self.app, "obter_conexao", return_value=conexao), \
                    mock.patch.object(self.app, "flash") as flash, \
                    self.app.app.test_request_context("/", method="POST", data=dados):
                self.app.session.update(usuario_id=1, usuario_papel=papel, usuario_nome="Admin Teste")
                view()
        finally:
            database.limpar_banco_escola(token)
        return conexao, [c.args[0] for c in flash.call_args_list]

    def _fechar(self, cur, mes="2026-06", **kw):
        return self._post(self.app.lucro_real_fechar_periodo, cur, {"mes": mes}, **kw)

    def _reabrir(self, cur, motivo, mes="2026-06", **kw):
        return self._post(self.app.lucro_real_reabrir_periodo, cur, {"mes": mes, "motivo": motivo}, **kw)

    def test_fecha_trimestre_vencido_grava_saldo_snapshot_e_log(self):
        meses = ["2026-04", "2026-05", "2026-06"]
        cur = _CursorFechamento(meses=meses, folha_fechada={"esc_matriz": {"2026-04": 0}, "esc_filial": {"2026-05": 0}})
        conexao, mensagens = self._fechar(cur)
        self.assertEqual(conexao.commits, 1, mensagens)
        saldo = cur.escritas_em("lucro_real_saldos", "INSERT")
        self.assertEqual(len(saldo), 1)
        self.assertEqual(saldo[0][1][0], "2026-06")
        snap = cur.escritas_em("tributos_snapshot", "INSERT")
        self.assertEqual(sorted((p[1], p[0]) for _t, p in snap), [(1, "2026-04"), (2, "2026-05")])
        self.assertIn('"esc_filial".tributos_snapshot', next(t for t, p in snap if p[1] == 2))
        self.assertEqual(len(cur.escritas_em("lucro_real_fechamento_log", "INSERT")), 1)

    def test_nao_fecha_antes_da_darf(self):
        cur = _CursorFechamento(meses=["2026-07", "2026-08", "2026-09"])
        with mock.patch.object(self.app, "date") as data_falsa:
            from datetime import date

            data_falsa.today.return_value = date(2026, 10, 4)
            conexao, mensagens = self._fechar(cur, mes="2026-09")
        self.assertEqual(conexao.commits, 0)
        self.assertFalse(cur.escritas)
        self.assertIn("vencimento da DARF", mensagens[0])

    def test_filial_e_nao_admin_nao_fecham(self):
        cur = _CursorFechamento()
        _c, mensagens = self._fechar(cur, schema="esc_filial")
        self.assertIn("matriz", mensagens[0])
        cur = _CursorFechamento()
        _c, mensagens = self._fechar(cur, papel="financeiro")
        self.assertIn("administrador", mensagens[0])
        self.assertFalse(cur.escritas)

    def test_reabrir_exige_motivo_de_15_caracteres(self):
        cur = _CursorFechamento(saldos=[{"periodo": "2026-06", "prejuizo_fiscal": 0, "base_negativa_csll": 0, "fechado": True}])
        conexao, mensagens = self._reabrir(cur, "curto demais")
        self.assertEqual(conexao.commits, 0)
        self.assertIn("15", mensagens[0])

    def test_reabrir_apaga_este_periodo_e_os_seguintes(self):
        cur = _CursorFechamento(saldos=[{"periodo": "2026-06", "prejuizo_fiscal": 0, "base_negativa_csll": 0, "fechado": True}])
        conexao, mensagens = self._reabrir(cur, "Ajuste de custo lançado depois")
        self.assertEqual(conexao.commits, 1, mensagens)
        apagou = cur.escritas_em("lucro_real_saldos", "DELETE")
        self.assertEqual(apagou[0][1], ("2026-06", "0000-00"))
        snaps = cur.escritas_em("tributos_snapshot", "DELETE")
        self.assertEqual(len(snaps), 2)
        self.assertTrue(all(p == ("2026-04",) for _t, p in snaps))
        log = cur.escritas_em("lucro_real_fechamento_log", "INSERT")
        self.assertEqual(log[0][1][1], "reabrir")

    def test_reabrir_folha_apaga_o_snapshot_dos_tributos_do_mes(self):
        cur = _CursorFechamento()
        with mock.patch.object(self.app, "reabrir_competencia", return_value={}):
            conexao, mensagens = self._post(
                self.app.reabrir_competencia_folha, cur, {"mes": "2026-09", "motivo": "Correção de horas extras"}
            )
        self.assertEqual(conexao.commits, 1, mensagens)
        snaps = cur.escritas_em("tributos_snapshot", "DELETE")
        self.assertEqual(snaps[0][1], (["2026-09"],))


if __name__ == "__main__":
    unittest.main()
