import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _Cursor:
    def __init__(self):
        self.sql = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.sql.append(sql)

    def fetchone(self):
        return None

    def fetchall(self):
        return []


class _Conexao:
    def __init__(self):
        self.cur = _Cursor()
        self.commits = 0

    def cursor(self, cursor_factory=None):
        return self.cur

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass


class GuardasDaFilialTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app as app_mod

        cls.app = app_mod

    def _post(self, papel, view, path, form):
        app = self.app
        conexao = _Conexao()
        with mock.patch.object(app, "garantir_tabelas_folha"), \
                mock.patch.object(app, "garantir_tabelas_pedagogicas"), \
                mock.patch.object(app, "obter_conexao", return_value=conexao), \
                mock.patch.object(app, "_contexto_tributario", return_value={"papel": papel}), \
                mock.patch.object(app, "carregar_sistema", return_value=3) as carregar, \
                mock.patch.object(app, "enviar_email") as enviar:
            with app.app.test_request_context(path, method="POST", data=form):
                app.session["usuario_id"] = 1
                view()
                flashes = list(app.session.get("_flashes") or [])
        return flashes, carregar, enviar, conexao

    def test_filial_nao_carrega_nem_importa(self):
        for acao in ("simples_carregar_sistema", "simples_carregar_folha", "simples_importar"):
            flashes, carregar, _enviar, conexao = self._post(
                "filial", self.app.pagina_financeiro, "/financeiro", {"acao": acao, "mes": "2026-10"}
            )
            self.assertIn(("danger", self.app.MSG_PGDAS_DA_MATRIZ), flashes, acao)
            carregar.assert_not_called()
            self.assertEqual(conexao.commits, 0)

    def test_matriz_continua_carregando(self):
        flashes, carregar, _enviar, _conexao = self._post(
            "matriz", self.app.pagina_financeiro, "/financeiro", {"acao": "simples_carregar_sistema", "mes": "2026-10"}
        )
        carregar.assert_called_once()
        self.assertNotIn(("danger", self.app.MSG_PGDAS_DA_MATRIZ), flashes)

    def test_filial_nao_envia_memoria(self):
        flashes, _carregar, enviar, _conexao = self._post(
            "filial", self.app.enviar_memoria_simples, "/financeiro/simples/enviar",
            {"mes": "2026-10", "email": "contador@example.com"},
        )
        self.assertIn(("danger", self.app.MSG_PGDAS_DA_MATRIZ), flashes)
        enviar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
