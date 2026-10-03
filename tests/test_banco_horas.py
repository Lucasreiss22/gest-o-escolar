import os
import unittest
from datetime import date, datetime

os.environ.setdefault("DATABASE_URL", "postgresql://x:y@127.0.0.1:1/z")

import app as sistema  # noqa: E402

AGORA = datetime(2026, 10, 1, 23, 0)
DIA = {"entrada": "08:00", "almoco": "12:00", "almoco_volta": "13:00", "saida": "17:00"}


def _totais():
    return {"positivo": 0, "negativo": 0, "descanso": 0}


class BancoHorasRegraFolhaTeste(unittest.TestCase):
    def test_domingo_sem_jornada_esperada_vira_100(self):
        domingo = date(2026, 9, 13)
        descanso = sistema._dia_descanso_ponto(domingo, set())
        self.assertTrue(descanso)
        calc = sistema._saldo_dia_ponto(
            {"entrada": "08:00", "saida": "12:00"}, 480, domingo, AGORA, descanso=descanso
        )
        self.assertEqual(calc["esperado_min"], 0)
        self.assertEqual(calc["saldo_min"], 240)
        totais = _totais()
        self.assertEqual(sistema._somar_banco_dia(totais, calc), "descanso")
        self.assertEqual(totais, {"positivo": 0, "negativo": 0, "descanso": 240})

    def test_feriado_em_dia_util(self):
        feriado = date(2026, 10, 12)
        self.assertTrue(sistema._dia_descanso_ponto(feriado, {feriado}))
        self.assertFalse(sistema._dia_descanso_ponto(date(2026, 10, 13), {feriado}))

    def test_dia_util_dentro_da_tolerancia_nao_conta(self):
        calc = sistema._saldo_dia_ponto(
            dict(DIA, saida="17:08"), 480, date(2026, 10, 1), AGORA
        )
        self.assertEqual(calc["saldo_min"], 8)
        totais = _totais()
        self.assertEqual(sistema._somar_banco_dia(totais, calc), "tolerancia")
        self.assertEqual(totais["positivo"], 0)

    def test_dia_util_acima_da_tolerancia_conta(self):
        calc = sistema._saldo_dia_ponto(
            dict(DIA, saida="20:30"), 480, date(2026, 10, 1), AGORA
        )
        totais = _totais()
        sistema._somar_banco_dia(totais, calc)
        self.assertEqual(totais["positivo"], 210)

    def test_falta_conta_jornada_negativa(self):
        calc = sistema._saldo_dia_ponto(
            {}, 480, date(2026, 10, 2), AGORA, {"status": "confirmada"}
        )
        totais = _totais()
        sistema._somar_banco_dia(totais, calc)
        self.assertEqual(totais["negativo"], 480)

    def test_feriados_periodo_virada_de_ano(self):
        chamadas = []
        original = sistema._feriados_do_mes
        try:
            sistema._feriados_do_mes = lambda cursor, ano, mes: chamadas.append((ano, mes)) or set()
            sistema._feriados_periodo(None, date(2026, 12, 28), date(2027, 1, 3))
        finally:
            sistema._feriados_do_mes = original
        self.assertEqual(chamadas, [(2026, 12), (2027, 1)])


if __name__ == "__main__":
    unittest.main()
