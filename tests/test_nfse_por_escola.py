import os
import unittest
from unittest import mock

os.environ.setdefault("DATABASE_URL", "postgresql://x:y@127.0.0.1:1/z")

import nfse  # noqa: E402


class CursorNfse:
    def __init__(self, escola, geral):
        self.escola = escola
        self.geral = geral
        self._ultimo = None

    def execute(self, sql, params=None):
        if "plataforma_escolas" in sql:
            self._ultimo = None if self.escola is None else {"nfse_habilitada": self.escola}
        elif "plataforma_nfse" in sql:
            self._ultimo = {"emissao_habilitada": self.geral}
        else:
            self._ultimo = None

    def fetchone(self):
        return self._ultimo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class NfsePorEscolaTeste(unittest.TestCase):
    def _ligada(self, escola, geral, escola_id=7):
        conexao = mock.MagicMock()
        conexao.cursor.return_value = CursorNfse(escola, geral)
        with mock.patch("database.obter_conexao", return_value=conexao):
            return nfse.emissao_nfse_ligada(escola_id)

    def test_segue_a_chave_geral(self):
        self.assertTrue(self._ligada(None, True))
        self.assertFalse(self._ligada(None, False))

    def test_escola_ligada_com_geral_desligada(self):
        self.assertTrue(self._ligada(True, False))

    def test_escola_desligada_com_geral_ligada(self):
        self.assertFalse(self._ligada(False, True))

    def test_plataforma_usa_so_a_geral(self):
        self.assertTrue(self._ligada(False, True, escola_id=None))


if __name__ == "__main__":
    unittest.main()
