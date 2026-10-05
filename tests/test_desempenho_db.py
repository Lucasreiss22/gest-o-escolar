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


class _CursorRede:
    """Banco falso de uma rede (matriz + filial) só com o necessário para a apuração."""

    ESCOLAS = [
        {"id": 1, "nome": "Matriz", "db_nome": "esc_matriz", "tipo_unidade": "matriz", "matriz_id": None, "cnpj": "11222333000181"},
        {"id": 2, "nome": "Filial", "db_nome": "esc_filial", "tipo_unidade": "filial", "matriz_id": 1, "cnpj": "11222333000262"},
    ]

    def __init__(self, regime="simples_nacional"):
        self.regime = regime
        self.consultas = []
        self._resultado = []
        matriz = [{"tipo": "v", "comp": f"2026-{m:02d}", "receita": 112_990.0} for m in range(2, 10)]
        matriz.append({"tipo": "v", "comp": "2026-10", "receita": 113_870.0})
        matriz.append({"tipo": "iv", "comp": "2026-02", "receita": 0})
        filial = [{"tipo": "v", "comp": "2026-10", "receita": 51_000.0}, {"tipo": "iv", "comp": "2026-10", "receita": 0}]
        self.mensalidades = {"esc_matriz": matriz, "esc_filial": filial}

    def _schema(self, sql):
        for escola in self.ESCOLAS:
            if f'"{escola["db_nome"]}".' in sql:
                return escola["db_nome"]
        return database._nome_banco_atual()

    def execute(self, sql, params=None):
        texto = sql.strip().upper()
        if texto.startswith(("SAVEPOINT", "RELEASE", "ROLLBACK")):
            return
        self.consultas.append(sql)
        schema = self._schema(sql)
        if "plataforma_escolas" in sql:
            self._resultado = [dict(e) for e in self.ESCOLAS]
        elif "configuracoes" in sql:
            self._resultado = [{"nome_escola": schema, "regime_tributario": self.regime, "regime_apuracao": "competencia"}]
        elif "financeiro_mensalidades" in sql:
            self._resultado = [dict({"juros": 0, "multa": 0, "qtd": 0}, **l) for l in self.mensalidades[schema]]
        else:
            self._resultado = []

    def fetchone(self):
        return self._resultado[0] if self._resultado else None

    def fetchall(self):
        return list(self._resultado)


class ConsultasDaApuracaoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app as app_mod

        cls.app = app_mod

    def setUp(self):
        import carga_tributos

        carga_tributos._CACHE.clear()

    def _apurar(self, schema, regime="simples_nacional"):
        cur = _CursorRede(regime)
        token = database.definir_banco_escola(schema)
        try:
            with self.app.app.test_request_context("/"):
                tributos = self.app._tributos_do_mes(cur, "2026-10")
        finally:
            database.limpar_banco_escola(token)
        return tributos, cur.consultas

    def test_carregador_faz_tres_consultas_por_unidade(self):
        from carga_tributos import carregar_unidade

        cur = _CursorRede()
        carregar_unidade(cur, "esc_filial", "2026-10")
        self.assertEqual(len(cur.consultas), 3)

    def test_simples_da_rede_na_matriz(self):
        tributos, consultas = self._apurar("esc_matriz")
        self.assertLessEqual(len(consultas), 20)
        self.assertEqual(tributos["simples"]["das_total"], 22_045.51)
        self.assertEqual(tributos["tributos"], 15_226.07)

    def test_simples_da_rede_na_filial(self):
        tributos, consultas = self._apurar("esc_filial")
        self.assertLessEqual(len(consultas), 20)
        self.assertEqual(tributos["tributos"], 6_819.44)
        self.assertEqual(tributos["simples"]["rede"]["papel"], "filial")

    def test_presumido_da_rede(self):
        tributos, consultas = self._apurar("esc_matriz", "lucro_presumido")
        self.assertLessEqual(len(consultas), 20)
        self.assertGreater(tributos["tributos"], 0)
        self.assertEqual(tributos["irpj_csll"], tributos["presumido"]["irpj_csll"])

    def test_regime_vazio_nao_calcula(self):
        tributos, _consultas = self._apurar("esc_matriz", None)
        self.assertEqual(tributos["regime"], "nao_informado")
        self.assertEqual(tributos["tributos"], 0)


class _CursorFolha:
    """Banco falso da folha do mês: N funcionários CLT com ponto, faltas e um feriado no calendário.
    DDL `IF NOT EXISTS` não conta (em produção o memo do cursor não reenvia)."""

    def __init__(self, n_funcionarios):
        from datetime import date, time

        self.consultas = []
        self._resultado = []
        self.description = None
        self.funcionarios = [
            {
                "id": i, "nome_completo": f"Pessoa {i:02d}", "tipo_contrato": "clt_mensalista", "salario": 3000 + i,
                "data_inicio_contrato": date(2025, 1, 1), "data_contratacao": date(2025, 1, 1), "ativo": True,
                "data_fim_contrato": None, "email": None, "ponto_jornada_minutos": None,
            }
            for i in range(1, n_funcionarios + 1)
        ]
        self.ponto = [
            {"funcionario_id": f["id"], "data_ref": date(2026, 10, d), "entrada": time(8, 0), "cafe_ida": None,
             "cafe_volta": None, "almoco": time(12, 0), "almoco_volta": time(13, 0), "cafe": None, "saida": time(18, 0)}
            for f in self.funcionarios for d in (5, 6, 7)
        ]
        self.faltas = [{"funcionario_id": 1, "data_ref": date(2026, 10, 8)}]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        texto = " ".join(sql.split())
        if database._ddl_memorizavel(texto):
            return
        self.consultas.append(texto)
        if texto.startswith("SELECT * FROM funcionarios WHERE id"):
            self._resultado = [dict(f) for f in self.funcionarios if f["id"] == params[0]]
        elif "FROM funcionarios" in texto:
            self._resultado = [dict(f) for f in self.funcionarios]
        elif "FROM configuracoes" in texto:
            self._resultado = [{"nome_escola": "Escola", "regime_tributario": "simples_nacional", "ponto_he_folha": True}]
        elif "FROM ponto_registros" in texto:
            ids = params[2]
            self._resultado = [dict(r, fonte="p") for r in self.ponto if r["funcionario_id"] in ids]
            if "FROM ponto_faltas" in texto:
                self._resultado += [dict(r, fonte="f") for r in self.faltas if r["funcionario_id"] in ids]
        else:
            self._resultado = []

    def fetchone(self):
        return self._resultado[0] if self._resultado else None

    def fetchall(self):
        return list(self._resultado)


class ConsultasDaFolhaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app as app_mod

        cls.app = app_mod

    def setUp(self):
        import carga_tributos

        carga_tributos._CACHE.clear()

    def _patches(self):
        from unittest import mock

        return mock.patch.multiple(self.app, garantir_tabelas_folha=mock.DEFAULT, _garantir_ponto=mock.DEFAULT)

    def _folha(self, n):
        cur = _CursorFolha(n)
        token = database.definir_banco_escola("esc_matriz")
        try:
            with self._patches(), self.app.app.test_request_context("/"):
                itens, totais = self.app.montar_folha_contratos(cur, "simples_nacional", "2026-10")
        finally:
            database.limpar_banco_escola(token)
        return itens, totais, cur.consultas

    def test_p1_folha_nao_cresce_com_funcionarios(self):
        contagens = {}
        for n in (1, 11, 50):
            itens, _totais, consultas = self._folha(n)
            self.assertEqual(len(itens), n)
            self.assertLessEqual(len(consultas), 8, consultas)
            contagens[n] = len(consultas)
        self.assertEqual(len(set(contagens.values())), 1, contagens)

    def test_p1_ponto_e_faltas_continuam_na_folha(self):
        itens, _totais, _consultas = self._folha(2)
        pessoa1 = next(i for i in itens if i["id"] == 1)
        self.assertGreater(pessoa1.get("desconto_faltas") or 0, 0)
        self.assertAlmostEqual(pessoa1.get("horas_extras_ponto") or 0, 3.0)

    def test_folha_repetida_na_requisicao_sai_do_cache(self):
        cur = _CursorFolha(11)
        token = database.definir_banco_escola("esc_matriz")
        try:
            with self._patches(), self.app.app.test_request_context("/"):
                self.app._folha_competencia(cur, "simples_nacional", "2026-10")
                antes = len(cur.consultas)
                self.app._folha_competencia(cur, "simples_nacional", "2026-10")
        finally:
            database.limpar_banco_escola(token)
        self.assertEqual(len(cur.consultas), antes)

    def test_p2_contracheque_do_mes(self):
        from datetime import date
        from unittest import mock

        cur = _CursorFolha(11)

        class _Conexao:
            def cursor(self, cursor_factory=None):
                return cur

            def close(self):
                pass

        token = database.definir_banco_escola("esc_matriz")
        self.app._contracheque_auto_dia["esc_matriz"] = date.today()
        try:
            with self._patches(), mock.patch.object(self.app, "obter_conexao", return_value=_Conexao()), \
                    mock.patch.object(self.app, "render_template", return_value="ok") as render:
                with self.app.app.test_request_context("/contracheque?mes=2026-10&funcionario_id=3"):
                    self.app.session.update(usuario_id=1, usuario_papel="admin", escola_db="esc_matriz", funcionario_id=3)
                    self.app.contracheque()
        finally:
            database.limpar_banco_escola(token)
            self.app._contracheque_auto_dia.pop("esc_matriz", None)
        self.assertLessEqual(len(cur.consultas), 20, cur.consultas)
        contexto = render.call_args.kwargs
        self.assertEqual(len(contexto["itens"]), 11)
        self.assertEqual(contexto["item"]["id"], 3)


if __name__ == "__main__":
    unittest.main()
