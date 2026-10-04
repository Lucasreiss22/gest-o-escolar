import os
import sys
import unittest
from datetime import date, datetime
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://x:y@127.0.0.1:1/z")

import app as sistema  # noqa: E402
import database  # noqa: E402
from alunos import _turma_simples  # noqa: E402
from rescisao import (  # noqa: E402
    VERSAO_REGRAS_RESCISAO,
    calcular_rescisao,
    comparar_rescisao,
    contrato_da_rescisao,
    detalhes_rescisao_para_gravar,
    parametros_da_rescisao,
    regras_desatualizadas,
)

HOJE = datetime(2026, 10, 3, 10, 0)


class CursorPonto:
    """Banco falso: colaborador 5 existe, sem batida no dia e sem pedido pendente."""

    def __init__(self):
        self.sqls = []
        self._ultimo = ""

    def execute(self, sql, params=None):
        self._ultimo = " ".join(sql.split())
        self.sqls.append((self._ultimo, params))

    def fetchone(self):
        if self._ultimo.startswith("SELECT id FROM funcionarios"):
            return {"id": 5}
        return None

    def inseriu_pedido(self):
        return any(sql.startswith("INSERT INTO ponto_solicitacoes") for sql, _p in self.sqls)


class PontoRetroativoServidorTeste(unittest.TestCase):
    """POST direto na regra do servidor, sem passar pela validação do navegador."""

    def _enviar(self, **form):
        dados = {"acao": "solicitar_ponto_retroativo", "funcionario_id": "5", "entrada": "08:00", "saida": "17:00"}
        dados.update(form)
        cursor = CursorPonto()
        with sistema.app.test_request_context("/ponto", method="POST", data=dados):
            sistema.session.update({"usuario_id": 9, "usuario_nome": "Fábio", "usuario_papel": "funcionario"})
            with mock.patch.object(sistema, "_agora_ponto_br", return_value=HOJE):
                resultado = sistema._tratar_ponto_retroativo(cursor, dados["acao"], 5)
        return resultado, cursor

    def test_data_futura_bloqueada(self):
        with self.assertRaises(ValueError) as ctx:
            self._enviar(data_ref="2026-10-04", justificativa="Esqueci de bater")
        self.assertIn("futura", str(ctx.exception))

    def test_hoje_bloqueado_para_retroativo(self):
        with self.assertRaises(ValueError) as ctx:
            self._enviar(data_ref="2026-10-03", justificativa="Esqueci de bater")
        self.assertIn("batidas normais", str(ctx.exception))

    def test_justificativa_vazia_ou_curta(self):
        for texto in ("", "   ", "ok"):
            with self.assertRaises(ValueError) as ctx:
                self._enviar(data_ref="2026-10-02", justificativa=texto)
            self.assertIn("justificativa", str(ctx.exception).lower())

    def test_nada_e_gravado_quando_bloqueia(self):
        cursor = CursorPonto()
        dados = {"acao": "solicitar_ponto_retroativo", "funcionario_id": "5", "data_ref": "2026-10-09",
                 "entrada": "08:00", "justificativa": "Teste"}
        with sistema.app.test_request_context("/ponto", method="POST", data=dados):
            sistema.session.update({"usuario_id": 9, "usuario_papel": "funcionario"})
            with mock.patch.object(sistema, "_agora_ponto_br", return_value=HOJE):
                with self.assertRaises(ValueError):
                    sistema._tratar_ponto_retroativo(cursor, dados["acao"], 5)
        self.assertFalse(cursor.inseriu_pedido())

    def test_pedido_valido_fica_pendente(self):
        _painel, cursor = self._enviar(data_ref="2026-10-02", justificativa="Esqueci de bater a saída")
        self.assertTrue(cursor.inseriu_pedido())

    def test_colaborador_nao_lanca_para_outro(self):
        with self.assertRaises(ValueError) as ctx:
            self._enviar(funcionario_id="7", data_ref="2026-10-02", justificativa="Pedido de outra pessoa")
        self.assertIn("outro colaborador", str(ctx.exception))


BRUNO_ANTIGO = {
    "tipo_rescisao": "pedido_demissao",
    "aviso_modalidade": "nao_cumprido",
    "data_admissao": "2020-03-02",
    "data_desligamento": "2026-10-02",
    "dias_trabalhados_mes": 2,
    "dias_aviso": 36,
    "salario_mensal": 3000.0,
    "avos_13": 9,
    "fator_proporcionais": 1.0,
    "decimo_terceiro": 2250.0,
    "ferias_vencidas_simples": 0,
    "ferias_vencidas_dobro": 0,
    "avos_ferias_proporcionais": 7,
    "saldo_fgts_depositos": 0,
    "outros_proventos": 0,
    "outros_descontos": 0,
    "aviso_desconto": 3600.0,
    "total_liquido": 100.0,
    "direitos": {"decimo_terceiro": True},
    "regime_tributario": "simples_nacional",
}


class RecalculoRescisaoTeste(unittest.TestCase):
    def test_antiga_sem_versao_fica_desatualizada(self):
        self.assertTrue(regras_desatualizadas(BRUNO_ANTIGO))
        self.assertFalse(regras_desatualizadas({"versao_regras": VERSAO_REGRAS_RESCISAO}))

    def test_reconstroi_parametros_e_limita_aviso_do_pedido(self):
        row = {"tipo": "pedido_demissao", "data_aviso": date(2026, 10, 2), "data_pagamento": None}
        params = parametros_da_rescisao(row, BRUNO_ANTIGO)
        self.assertEqual(params["dias_aviso"], 36)
        self.assertEqual(params["data_aviso"], "2026-10-02")
        self.assertNotIn("decimo_ja_pago", params)
        func = contrato_da_rescisao({"tipo_contrato": "clt_horista", "valor_hora": 20, "horas_mes": 100}, BRUNO_ANTIGO)
        self.assertEqual(func["salario"], 3000.0)
        self.assertEqual(func["tipo_contrato"], "clt_mensalista")
        novo = calcular_rescisao(func, dict(params, irrf_13_redutor="bruto"))
        self.assertEqual(novo["dias_aviso"], 30)
        self.assertEqual(novo["aviso_desconto"], 3000.0)
        linhas = {linha["chave"]: linha for linha in comparar_rescisao(BRUNO_ANTIGO, novo)}
        self.assertEqual(linhas["dias_aviso"]["diferenca"], -6)
        self.assertEqual(linhas["aviso_desconto"]["diferenca"], -600.0)

    def test_decimo_ja_pago_e_recuperado(self):
        antigo = dict(BRUNO_ANTIGO, decimo_terceiro=750.0)
        params = parametros_da_rescisao({}, antigo)
        self.assertEqual(params["decimo_ja_pago"], 1500.0)

    def test_nova_rescisao_guarda_versao_e_parametros(self):
        detalhes = detalhes_rescisao_para_gravar(
            {"total_liquido": 10}, {"tipo_rescisao": "sem_justa_causa", "dias_aviso": "", "outros_proventos": "50"}
        )
        self.assertEqual(detalhes["versao_regras"], VERSAO_REGRAS_RESCISAO)
        self.assertEqual(detalhes["parametros"], {"tipo_rescisao": "sem_justa_causa", "outros_proventos": "50"})
        self.assertEqual(parametros_da_rescisao({}, detalhes)["outros_proventos"], "50")


class CursorTurmas:
    def __init__(self, repetidas):
        self.repetidas = repetidas
        self.sqls = []

    def execute(self, sql, params=None):
        self.sqls.append(" ".join(sql.split()))

    def fetchall(self):
        return self.repetidas

    def fetchone(self):
        return {"id": 77}


class TurmaUnicaTeste(unittest.TestCase):
    def test_cria_indice_sem_repetidas(self):
        cur = CursorTurmas([])
        database._garantir_turma_unica_idx(cur)
        self.assertTrue(any("CREATE UNIQUE INDEX IF NOT EXISTS turmas_nome_ano_uidx" in s for s in cur.sqls))
        self.assertIn("RELEASE SAVEPOINT sp_turmas_nome_idx", cur.sqls)

    def test_adia_indice_com_repetidas(self):
        cur = CursorTurmas([{"nome": "1º Ano A", "ano_letivo": 2026, "total": 2, "ids": [1, 4]}])
        database._garantir_turma_unica_idx(cur)
        self.assertFalse(any("CREATE UNIQUE INDEX" in s for s in cur.sqls))

    def test_importacao_reaproveita_turma_com_espacos_diferentes(self):
        mapa = {"1º ano a": 3}
        cur = CursorTurmas([])
        self.assertEqual(_turma_simples(cur, "  1º   Ano A ", mapa), 3)
        self.assertFalse(cur.sqls)
        self.assertEqual(_turma_simples(cur, "2º  Ano  B", mapa), 77)
        self.assertEqual(mapa["2º ano b"], 77)


class EditorProvaTeste(unittest.TestCase):
    def test_nova_pergunta_nao_herda_o_tipo(self):
        caminho = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates", "_editor_questoes.html")
        with open(caminho, encoding="utf-8") as arq:
            fonte = arq.read()
        trecho = fonte[fonte.index('getElementById("btnAddPergunta")'):]
        trecho = trecho[: trecho.index("addQuestao(base, true)")]
        self.assertNotIn("base.tipo", trecho)


if __name__ == "__main__":
    unittest.main()
