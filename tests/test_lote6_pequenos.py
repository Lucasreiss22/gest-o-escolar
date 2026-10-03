import os
import unittest
from unittest import mock

os.environ.setdefault("DATABASE_URL", "postgresql://x:y@127.0.0.1:1/z")

import app as sistema  # noqa: E402
import plataforma  # noqa: E402
from folha import situacao_folha_mes  # noqa: E402
from permissoes import TELAS_PLANO  # noqa: E402
from rescisao import calcular_rescisao  # noqa: E402


class CursorFalso:
    """Devolve as respostas na ordem das consultas que retornam linhas."""

    def __init__(self, respostas=()):
        self.respostas = list(respostas)
        self.sql = []
        self._atual = None

    def execute(self, sql, params=None):
        self.sql.append((sql, params))
        texto = sql.strip().upper()
        if texto.startswith(("SAVEPOINT", "RELEASE", "ROLLBACK", "SELECT PG_ADVISORY")):
            self._atual = None
            return
        self._atual = self.respostas.pop(0) if self.respostas else None

    def fetchone(self):
        atual = self._atual
        if isinstance(atual, list):
            return atual[0] if atual else None
        return atual

    def fetchall(self):
        atual = self._atual
        if atual is None:
            return []
        return atual if isinstance(atual, list) else [atual]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TurmaDuplicadaTeste(unittest.TestCase):
    def test_bloqueia_mesmo_nome_e_ano(self):
        cursor = CursorFalso([{"?column?": 1}])
        with self.assertRaises(sistema.TurmaDuplicada):
            sistema._travar_turma_unica(cursor, "  1º Ano   A ", "2026")
        trava = cursor.sql[0]
        self.assertIn("pg_advisory_xact_lock", trava[0])
        self.assertEqual(trava[1], ("1º ano a:2026",))

    def test_turma_nova_passa_normalizada(self):
        cursor = CursorFalso([None])
        self.assertEqual(sistema._travar_turma_unica(cursor, " 7º  Ano A", "2026"), ("7º Ano A", 2026))

    def test_nome_vazio(self):
        with self.assertRaises(ValueError):
            sistema._travar_turma_unica(CursorFalso(), "  ", "2026")


class FolhaMesDaSaidaTeste(unittest.TestCase):
    base = {"data_inicio_contrato": "2024-02-01"}

    def test_ativo_entra(self):
        self.assertEqual(situacao_folha_mes({**self.base, "ativo": True}, 2026, 9), "folha")

    def test_mes_do_desligamento_fica_com_a_rescisao(self):
        func = {**self.base, "ativo": False, "data_fim_contrato": "2026-09-20"}
        self.assertEqual(situacao_folha_mes(func, 2026, 9), "rescisao")

    def test_mes_anterior_ao_desligamento_continua_na_folha(self):
        func = {**self.base, "ativo": False, "data_fim_contrato": "2026-09-20"}
        self.assertEqual(situacao_folha_mes(func, 2026, 8), "folha")

    def test_depois_do_desligamento_fica_fora(self):
        func = {**self.base, "ativo": False, "data_fim_contrato": "2026-09-20"}
        self.assertEqual(situacao_folha_mes(func, 2026, 10), "fora")

    def test_inativo_sem_data_fica_fora(self):
        self.assertEqual(situacao_folha_mes({**self.base, "ativo": False}, 2026, 9), "fora")

    def test_alerta_quando_ja_tem_contracheque_no_mes(self):
        cursor = CursorFalso([{"bruto": 3500, "liquido": 3100}, None])
        alerta = sistema._folha_do_mes_da_saida(cursor, 7, "2026-09-20")
        self.assertEqual(alerta["competencia"], "2026-09")
        self.assertEqual(alerta["bruto"], 3500.0)

    def test_sem_contracheque_sem_alerta(self):
        self.assertIsNone(sistema._folha_do_mes_da_saida(CursorFalso([None, None]), 7, "2026-09-20"))


class AvisoPedidoDemissaoTeste(unittest.TestCase):
    def test_pedido_usa_30_dias_e_preserva_o_proporcional_no_campo(self):
        func = {"salario": 3500, "tipo_contrato": "clt_mensalista", "data_inicio_contrato": "2023-03-01"}
        calc = calcular_rescisao(func, {
            "tipo_rescisao": "pedido_demissao",
            "aviso_modalidade": "nao_cumprido",
            "data_desligamento": "2026-09-30",
            "dias_aviso": "39",
        })
        self.assertEqual(calc["dias_aviso"], 30)
        self.assertEqual(calc["dias_aviso_informado"], 39)
        self.assertEqual(calc["aviso_desconto"], 3500.0)

    def test_sem_justa_causa_mantem_proporcional(self):
        func = {"salario": 2200, "tipo_contrato": "clt_mensalista", "data_inicio_contrato": "2024-01-10"}
        calc = calcular_rescisao(func, {
            "tipo_rescisao": "sem_justa_causa",
            "aviso_modalidade": "indenizado",
            "data_desligamento": "2026-09-30",
            "dias_aviso": "36",
        })
        self.assertEqual(calc["dias_aviso"], 36)
        self.assertEqual(calc["aviso_indenizado"], 2640.0)


class PacoteCompletoTeste(unittest.TestCase):
    def test_completo_sempre_lista_todas_as_telas(self):
        cursor = CursorFalso([[
            {"codigo": "completo", "nome": "Completo", "descricao": "", "valor": 800, "telas": '["alunos", "financeiro"]'},
            {"codigo": "financeiro", "nome": "Financeiro", "descricao": "", "valor": 300, "telas": '["financeiro"]'},
        ]])
        conexao = mock.MagicMock()
        conexao.cursor.return_value = cursor
        with mock.patch.object(plataforma, "garantir_plataforma"), \
                mock.patch.object(plataforma, "obter_conexao", return_value=conexao):
            pacotes = {p["codigo"]: p["telas"] for p in plataforma.listar_pacotes()}
        self.assertEqual(pacotes["completo"], [c for c, _r in TELAS_PLANO])
        self.assertEqual(pacotes["financeiro"], ["financeiro"])


class ProfessorTurmasTeste(unittest.TestCase):
    def test_turma_de_outro_professor_e_bloqueada(self):
        cursor = CursorFalso([[{"id": 1}, {"id": 2}]])
        with self.assertRaises(PermissionError):
            sistema._checar_turma_professor(cursor, 5, turma_id=9)

    def test_aluno_fora_das_turmas_e_bloqueado(self):
        cursor = CursorFalso([[{"id": 1}], None])
        with self.assertRaises(PermissionError):
            sistema._checar_turma_professor(cursor, 5, aluno_id=30)

    def test_turma_propria_passa(self):
        cursor = CursorFalso([[{"id": 1}, {"id": 2}], {"?column?": 1}])
        self.assertEqual(sistema._checar_turma_professor(cursor, 5, turma_id=2, aluno_id=30), {1, 2})

    def test_so_professor_e_restrito(self):
        with sistema.app.test_request_context():
            sistema.session["funcionario_id"] = 5
            self.assertIsNone(sistema._professor_restrito("admin"))
            self.assertIsNone(sistema._professor_restrito("direcao"))
            self.assertEqual(sistema._professor_restrito("professor"), 5)


if __name__ == "__main__":
    unittest.main()
