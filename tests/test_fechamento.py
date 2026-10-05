import json
import os
import sys
import unittest
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fechamento import (
    competencias_fechadas,
    fechar_competencia,
    folha_fechada,
    historico_fechamento,
    info_fechamento,
    item_fechado,
    reabrir_competencia,
    validar_competencia,
)
from ponto_retroativo import validar_competencia_aberta


class CursorFechamento:
    """Guarda as três tabelas do fechamento em memória, reconhecendo as consultas do módulo."""

    def __init__(self):
        self.fechadas = {}
        self.snapshot = {}
        self.log = []
        self._resultado = []

    def execute(self, sql, params=()):
        s = " ".join(sql.split())
        self._resultado = []
        if s.startswith("INSERT INTO competencias_fechadas"):
            comp, uid, nome, regime, pessoas, totais = params
            if comp in self.fechadas:
                return
            self.fechadas[comp] = {
                "competencia": comp, "fechada_em": None, "fechada_por": uid, "fechada_nome": nome,
                "regime": regime, "pessoas": pessoas, "totais": json.loads(totais),
            }
            self._resultado = [{"competencia": comp}]
        elif s.startswith("INSERT INTO folha_snapshot"):
            comp, fid, item = params
            self.snapshot[(comp, fid)] = json.loads(item)
        elif s.startswith("INSERT INTO competencias_fechamento_log"):
            if "'fechar'" in s:
                comp, uid, nome, totais = params
                self.log.append({"competencia": comp, "acao": "fechar", "usuario_nome": nome, "motivo": None, "em": None})
            else:
                comp, uid, nome, motivo, totais = params
                self.log.append({"competencia": comp, "acao": "reabrir", "usuario_nome": nome, "motivo": motivo, "em": None})
        elif s.startswith("DELETE FROM competencias_fechadas"):
            linha = self.fechadas.pop(params[0], None)
            if linha:
                self._resultado = [{"totais": linha["totais"]}]
        elif s.startswith("DELETE FROM folha_snapshot"):
            for chave in [k for k in self.snapshot if k[0] == params[0]]:
                del self.snapshot[chave]
        elif s.startswith("SELECT competencia, fechada_em"):
            linha = self.fechadas.get(params[0])
            self._resultado = [dict(linha)] if linha else []
        elif s.startswith("SELECT c.totais, s.item FROM competencias_fechadas"):
            linha = self.fechadas.get(params[0])
            if linha:
                itens = [v for (c, _f), v in self.snapshot.items() if c == params[0]] or [None]
                self._resultado = [{"totais": linha["totais"], "item": item} for item in itens]
        elif s.startswith("SELECT competencia FROM competencias_fechadas"):
            self._resultado = [{"competencia": c} for c in self.fechadas]
        elif s.startswith("SELECT item FROM folha_snapshot WHERE competencia = %s AND funcionario_id"):
            item = self.snapshot.get((params[0], params[1]))
            self._resultado = [{"item": item}] if item is not None else []
        elif s.startswith("SELECT item FROM folha_snapshot"):
            self._resultado = [{"item": v} for (c, _f), v in self.snapshot.items() if c == params[0]]
        elif s.startswith("SELECT acao, usuario_nome"):
            self._resultado = [dict(l) for l in reversed(self.log) if l["competencia"] == params[0]]
        else:
            raise AssertionError(f"SQL inesperado: {s}")

    def fetchone(self):
        return self._resultado[0] if self._resultado else None

    def fetchall(self):
        return list(self._resultado)


ITENS = [
    {"id": 2, "nome_completo": "Bruno", "bruto": 3000.0, "liquido": 2600.0, "aliquota_iss": Decimal("5.00")},
    {"id": 1, "nome_completo": "ana", "bruto": 2000.0, "liquido": 1800.0, "data_inicio": date(2025, 2, 1)},
]
TOTAIS = {"bruto": 5000.0, "liquido": 4400.0, "custo_escola": 6200.0}


class TestFechamentoCompetencia(unittest.TestCase):
    def setUp(self):
        self.cur = CursorFechamento()

    def fechar(self, comp="2026-09"):
        return fechar_competencia(
            self.cur, comp, ITENS, TOTAIS, "simples_nacional",
            usuario_id=7, usuario_nome="Diretora", hoje=date(2026, 10, 4),
        )

    def test_fechar_grava_snapshot_e_totais(self):
        self.assertEqual(self.fechar(), "2026-09")
        info = info_fechamento(self.cur, "2026-09")
        self.assertEqual(info["pessoas"], 2)
        self.assertEqual(info["fechada_nome"], "Diretora")
        itens, totais = folha_fechada(self.cur, "2026-09")
        self.assertEqual(totais, TOTAIS)
        self.assertEqual([i["nome_completo"] for i in itens], ["ana", "Bruno"])
        self.assertEqual(itens[1]["aliquota_iss"], 5.0)
        self.assertEqual(itens[0]["data_inicio"], "2025-02-01")

    def test_aberta_retorna_none(self):
        self.assertIsNone(folha_fechada(self.cur, "2026-09"))
        self.assertIsNone(item_fechado(self.cur, "2026-09", 1))

    def test_item_fechado_por_pessoa(self):
        self.fechar()
        self.assertEqual(item_fechado(self.cur, "2026-09", 2)["liquido"], 2600.0)
        self.assertIsNone(item_fechado(self.cur, "2026-09", 99))

    def test_nao_fecha_duas_vezes(self):
        self.fechar()
        with self.assertRaises(ValueError):
            self.fechar()

    def test_nao_fecha_futuro_nem_invalido(self):
        with self.assertRaises(ValueError):
            self.fechar("2026-11")
        with self.assertRaises(ValueError):
            self.fechar("2026-13")
        with self.assertRaises(ValueError):
            validar_competencia("abc")

    def test_reabrir_exige_motivo(self):
        self.fechar()
        with self.assertRaises(ValueError):
            reabrir_competencia(self.cur, "2026-09", "curto")
        self.assertIsNotNone(info_fechamento(self.cur, "2026-09"))

    def test_reabrir_apaga_snapshot_e_registra_log(self):
        self.fechar()
        totais = reabrir_competencia(self.cur, "2026-09", "Hora extra lançada errada", usuario_nome="Admin")
        self.assertEqual(totais, TOTAIS)
        self.assertIsNone(folha_fechada(self.cur, "2026-09"))
        self.assertEqual(self.cur.snapshot, {})
        hist = historico_fechamento(self.cur, "2026-09")
        self.assertEqual([h["acao"] for h in hist], ["reabrir", "fechar"])
        self.assertEqual(hist[0]["motivo"], "Hora extra lançada errada")
        self.fechar()
        self.assertIsNotNone(info_fechamento(self.cur, "2026-09"))

    def test_reabrir_aberta_falha(self):
        with self.assertRaises(ValueError):
            reabrir_competencia(self.cur, "2026-09", "motivo suficiente aqui")

    def test_ponto_retroativo_bloqueia_mes_fechado(self):
        self.fechar()
        fechadas = competencias_fechadas(self.cur)
        self.assertEqual(fechadas, {"2026-09"})
        with self.assertRaises(ValueError):
            validar_competencia_aberta(date(2026, 9, 15), fechadas)
        validar_competencia_aberta(date(2026, 10, 1), fechadas)


class TestFolhaCompetenciaApp(unittest.TestCase):
    """_folha_competencia usa o snapshot quando fechada e o cálculo quando aberta."""

    def test_wrapper(self):
        import app as app_mod

        cur = CursorFechamento()
        fechar_competencia(cur, "2026-09", ITENS, TOTAIS, "simples_nacional", hoje=date(2026, 10, 4))
        chamadas = []
        original_montar = app_mod.montar_folha_contratos
        original_garantir = app_mod.garantir_tabelas_folha
        app_mod.montar_folha_contratos = lambda c, r, m=None: (chamadas.append(m) or ([], {"bruto": 0}))
        app_mod.garantir_tabelas_folha = lambda: None
        try:
            itens, totais = app_mod._folha_competencia(cur, "simples_nacional", "2026-09")
            self.assertEqual(totais, TOTAIS)
            self.assertEqual(len(itens), 2)
            self.assertEqual(chamadas, [])
            _itens, totais_ab = app_mod._folha_competencia(cur, "simples_nacional", "2026-10")
            self.assertEqual(totais_ab, {"bruto": 0})
            self.assertEqual(chamadas, ["2026-10"])
        finally:
            app_mod.montar_folha_contratos = original_montar
            app_mod.garantir_tabelas_folha = original_garantir


if __name__ == "__main__":
    unittest.main()
