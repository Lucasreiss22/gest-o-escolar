import unittest

import database


class _ConexaoFalsa:
    def __init__(self, objetos_existentes):
        self.notices = []
        self.existentes = objetos_existentes
        self.enviadas = []


class _CursorFalso:
    def __init__(self, conexao):
        self.connection = conexao

    def execute(self, query, vars=None):
        self.connection.enviadas.append(query)
        texto = query if isinstance(query, str) else ""
        for nome in self.connection.existentes:
            if nome in texto and "IF NOT EXISTS" in texto.upper():
                self.connection.notices.append(f'NOTICE:  relation "{nome}" already exists, skipping\n')


class CursorMemoTest(unittest.TestCase):
    def setUp(self):
        database._DDL_JA_EXISTE.clear()
        self.classe = database._classe_cursor_memo(_CursorFalso)

    def _cursor(self, conexao, schema="escola_a"):
        cur = self.classe(conexao)
        cur._schema_memo = schema
        return cur

    def test_ddl_ja_existente_nao_e_reenviado(self):
        conexao = _ConexaoFalsa({"alunos"})
        sql = "CREATE TABLE IF NOT EXISTS alunos (id SERIAL PRIMARY KEY)"
        self._cursor(conexao).execute(sql)
        self._cursor(conexao).execute(sql)
        self.assertEqual(conexao.enviadas, [sql])

    def test_ddl_que_criou_objeto_nao_e_memorizado(self):
        conexao = _ConexaoFalsa(set())
        sql = "ALTER TABLE alunos ADD COLUMN IF NOT EXISTS apelido TEXT"
        self._cursor(conexao).execute(sql)
        self._cursor(conexao).execute(sql)
        self.assertEqual(len(conexao.enviadas), 2)

    def test_memo_e_separado_por_schema(self):
        conexao = _ConexaoFalsa({"alunos"})
        sql = "CREATE TABLE IF NOT EXISTS alunos (id SERIAL PRIMARY KEY)"
        self._cursor(conexao, "escola_a").execute(sql)
        self._cursor(conexao, "escola_b").execute(sql)
        self.assertEqual(len(conexao.enviadas), 2)

    def test_alter_com_varias_colunas_exige_todas_existentes(self):
        conexao = _ConexaoFalsa({"apelido"})
        sql = "ALTER TABLE alunos ADD COLUMN IF NOT EXISTS apelido TEXT, ADD COLUMN IF NOT EXISTS cpf TEXT"
        self._cursor(conexao).execute(sql)
        self._cursor(conexao).execute(sql)
        self.assertEqual(len(conexao.enviadas), 2)

    def test_consultas_com_parametros_ou_alteracoes_nao_entram_no_memo(self):
        self.assertFalse(database._ddl_memorizavel("SELECT 1"))
        self.assertFalse(database._ddl_memorizavel("ALTER TABLE a DROP COLUMN IF EXISTS b"))
        self.assertFalse(database._ddl_memorizavel("ALTER TABLE a ALTER COLUMN b TYPE TEXT"))
        self.assertFalse(database._ddl_memorizavel(
            "CREATE TABLE IF NOT EXISTS a (id INT); CREATE TABLE IF NOT EXISTS b (id INT)"
        ))
        self.assertTrue(database._ddl_memorizavel("CREATE UNIQUE INDEX IF NOT EXISTS ix ON a (b);"))
        conexao = _ConexaoFalsa({"alunos"})
        sql = "CREATE TABLE IF NOT EXISTS alunos (id INT)"
        self._cursor(conexao).execute(sql, ())
        self._cursor(conexao).execute(sql, ())
        self.assertEqual(len(conexao.enviadas), 2)

    def test_esquecer_schema_libera_nova_conferencia(self):
        conexao = _ConexaoFalsa({"alunos"})
        sql = "CREATE TABLE IF NOT EXISTS alunos (id SERIAL PRIMARY KEY)"
        self._cursor(conexao).execute(sql)
        database.esquecer_schema("escola_a")
        self._cursor(conexao).execute(sql)
        self.assertEqual(len(conexao.enviadas), 2)

    def test_contagem_de_consultas(self):
        database.iniciar_contagem_consultas()
        conexao = _ConexaoFalsa({"alunos"})
        sql = "CREATE TABLE IF NOT EXISTS alunos (id INT)"
        cur = self._cursor(conexao)
        cur.execute("SELECT 1")
        cur.execute(sql)
        cur.execute(sql)
        self.assertEqual(database.contagem_consultas(), 2)


if __name__ == "__main__":
    unittest.main()
