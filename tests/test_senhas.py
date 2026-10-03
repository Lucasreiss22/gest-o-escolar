import os
import unittest
from unittest import mock

os.environ.setdefault("DATABASE_URL", "postgresql://x:y@127.0.0.1:1/z")

import plataforma  # noqa: E402
from senhas import conferir_senha, eh_hash, gerar_hash  # noqa: E402


class SenhaTeste(unittest.TestCase):
    def test_hash_confere_e_nao_guarda_texto(self):
        h = gerar_hash("minhaSenha1")
        self.assertTrue(eh_hash(h))
        self.assertNotIn("minhaSenha1", h)
        self.assertEqual(conferir_senha(h, "minhaSenha1"), (True, False))
        self.assertEqual(conferir_senha(h, "outra"), (False, False))

    def test_senha_antiga_em_texto_entra_e_pede_regravacao(self):
        self.assertEqual(conferir_senha("abc123", "abc123"), (True, True))
        self.assertEqual(conferir_senha("abc123 ", "abc123"), (True, True))
        self.assertEqual(conferir_senha("abc123", "abc124"), (False, False))

    def test_acentos_e_vazios(self):
        self.assertEqual(conferir_senha("ção123", "ção123"), (True, True))
        self.assertEqual(conferir_senha(gerar_hash("ção123"), "ção123"), (True, False))
        self.assertEqual(conferir_senha(None, "x"), (False, False))
        self.assertEqual(conferir_senha("x", ""), (False, False))

    def test_hash_cabe_na_coluna(self):
        self.assertLessEqual(len(gerar_hash("s" * 64)), 255)


class CursorLogin:
    def __init__(self, usuario):
        self.usuario = usuario
        self.updates = []

    def execute(self, sql, params=None):
        if sql.strip().upper().startswith("UPDATE"):
            self.updates.append(params)

    def fetchone(self):
        return self.usuario

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class LoginEscolaTeste(unittest.TestCase):
    def _login(self, usuario, senha):
        cursor = CursorLogin(usuario)
        conexao = mock.MagicMock()
        conexao.cursor.return_value = cursor
        escola = {"db_nome": "escola_teste", "senha_definida": True, "ativo": True}
        with mock.patch.object(plataforma, "definir_banco_escola", return_value="tk"), \
                mock.patch.object(plataforma, "limpar_banco_escola"), \
                mock.patch.object(plataforma, "obter_conexao", return_value=conexao):
            resultado, _escola = plataforma.usuario_da_escola("a@b.com", senha, escola)
        return resultado, cursor

    def test_texto_puro_entra_e_vira_hash(self):
        resultado, cursor = self._login({"id": 3, "senha": "antiga1"}, "antiga1")
        self.assertIsNotNone(resultado)
        self.assertEqual(len(cursor.updates), 1)
        novo_hash, uid = cursor.updates[0]
        self.assertEqual(uid, 3)
        self.assertTrue(conferir_senha(novo_hash, "antiga1")[0])

    def test_hash_entra_sem_regravar(self):
        resultado, cursor = self._login({"id": 3, "senha": gerar_hash("nova123")}, "nova123")
        self.assertIsNotNone(resultado)
        self.assertEqual(cursor.updates, [])

    def test_senha_errada(self):
        resultado, cursor = self._login({"id": 3, "senha": gerar_hash("nova123")}, "errada")
        self.assertIsNone(resultado)
        self.assertEqual(cursor.updates, [])


if __name__ == "__main__":
    unittest.main()
