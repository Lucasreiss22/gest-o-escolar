"""Rescisão contratual CLT: vínculos, cálculo e recontratação.

Fundamentos principais:
- Art. 477 CLT / Art. 7º, X CF — saldo de salário e quitação
- Lei 12.506/2011 e Arts. 487–491 CLT — aviso prévio proporcional
- Lei 4.090/1962 — 13º (avos; fração ≥ 15 dias)
- Arts. 130, 137, 146–147 CLT + Art. 7º, XVII CF — férias + 1/3
- Lei 8.036/1990 — FGTS e multa (40% / 20% no acordo 484-A)
- Art. 477 §6º CLT (Reforma) — pagamento em até 10 dias do término
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal
import json

from folha import (
    ALIQUOTA_FGTS,
    ALIQUOTA_FGTS_APRENDIZ,
    _eh_aprendiz,
    _num,
    hora_normal_clt,
    inss_empregado,
    irrf_progressivo,
)

TIPOS_RESCISAO = (
    ("sem_justa_causa", "Demissão sem justa causa (empregador)"),
    ("pedido_demissao", "Pedido de demissão (empregado)"),
    ("justa_causa", "Demissão por justa causa"),
    ("acordo_mutuo", "Acordo mútuo (Art. 484-A CLT)"),
    ("culpa_reciproca", "Culpa recíproca"),
    ("termino_prazo", "Término de contrato a prazo determinado"),
)

AVISO_MODALIDADES = (
    ("indenizado", "Indenizado (pago em dinheiro)"),
    ("trabalhado", "Trabalhado (cumprido)"),
    ("dispensado", "Dispensado pelo empregador (sem desconto)"),
    ("nao_cumprido", "Não cumprido pelo empregado (desconto)"),
)

# Dados da pessoa física que podem ser reaproveitados na recontratação
# (mesmo CPF / PIS — vínculo novo; matrícula eSocial e admissão são novos).
DADOS_REAPROVEITAVEIS = (
    "nome_completo",
    "cpf",
    "rg",
    "pis_nit",
    "data_nascimento",
    "telefone",
    "email",
    "foto_url",
    "cep",
    "rua",
    "numero",
    "bairro",
    "cidade",
    "estado",
    "banco",
    "agencia",
    "conta",
    "tipo_conta",
    "pix",
    "formacao",
    "especialidade",
)


def _as_date(valor):
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor)[:10])
    except (TypeError, ValueError):
        return None


def _money(valor):
    return round(_num(valor), 2)


def anos_completos_servico(admissao, desligamento):
    ini = _as_date(admissao)
    fim = _as_date(desligamento)
    if not ini or not fim or fim < ini:
        return 0
    anos = fim.year - ini.year
    if (fim.month, fim.day) < (ini.month, ini.day):
        anos -= 1
    return max(anos, 0)


def dias_aviso_proporcional(admissao, desligamento):
    """Lei 12.506/2011: 30 dias + 3 por ano completo, teto 90."""
    anos = anos_completos_servico(admissao, desligamento)
    return min(30 + 3 * anos, 90)


def avos_periodo(inicio, fim, projetar_dias=0):
    """Conta avos (1/12) com regra dos 15 dias; inclui projeção do aviso indenizado."""
    ini = _as_date(inicio)
    fim = _as_date(fim)
    if not ini or not fim or fim < ini:
        return 0
    fim_proj = fim + timedelta(days=max(int(projetar_dias or 0), 0))
    avos = 0
    y, m = ini.year, ini.month
    while (y, m) <= (fim_proj.year, fim_proj.month):
        primeiro = date(y, m, 1)
        ultimo = date(y, m, monthrange(y, m)[1])
        trecho_ini = max(ini, primeiro)
        trecho_fim = min(fim_proj, ultimo)
        if trecho_fim >= trecho_ini:
            dias = (trecho_fim - trecho_ini).days + 1
            if dias >= 15:
                avos += 1
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
    return min(avos, 12)


def avos_13_ano_civil(admissao, desligamento, projetar_dias=0):
    """Avos de 13º no ano civil do desligamento (máx. 12)."""
    fim = _as_date(desligamento)
    ini = _as_date(admissao)
    if not fim or not ini:
        return 0
    inicio_ano = date(fim.year, 1, 1)
    inicio = max(ini, inicio_ano)
    return min(avos_periodo(inicio, fim, projetar_dias), 12)


def salario_base_diario(func):
    """Salário / 30 para saldo e aviso (CLT). Horista: hora × jornada média / 30."""
    tipo = (func.get("tipo_contrato") or "clt_mensalista").strip().lower()
    salario = _num(func.get("salario"))
    if tipo in ("clt_horista", "horista"):
        vh = _num(func.get("valor_hora")) or hora_normal_clt(func)
        horas = _num(func.get("horas_mes")) or 220.0
        salario = vh * horas if vh > 0 else salario
    if salario <= 0:
        return 0.0
    return round(salario / 30.0, 4)


def salario_mensal_referencia(func):
    tipo = (func.get("tipo_contrato") or "clt_mensalista").strip().lower()
    salario = _num(func.get("salario"))
    if tipo in ("clt_horista", "horista"):
        vh = _num(func.get("valor_hora")) or hora_normal_clt(func)
        horas = _num(func.get("horas_mes")) or 220.0
        if vh > 0:
            return round(vh * horas, 2)
    return _money(salario)


def aliquota_fgts_contrato(tipo_contrato):
    return ALIQUOTA_FGTS_APRENDIZ if _eh_aprendiz(tipo_contrato) else ALIQUOTA_FGTS


def multa_fgts_aliquota(tipo_rescisao):
    if tipo_rescisao == "sem_justa_causa":
        return 0.40
    if tipo_rescisao in ("acordo_mutuo", "culpa_reciproca"):
        return 0.20
    return 0.0


def direitos_por_tipo(tipo_rescisao):
    """Flags de verbas conforme o tipo de rescisão."""
    t = tipo_rescisao or "sem_justa_causa"
    return {
        "saldo_salario": True,
        "aviso_indenizado": t in ("sem_justa_causa", "acordo_mutuo", "culpa_reciproca", "termino_prazo"),
        "aviso_desconto_pedido": t == "pedido_demissao",
        "decimo_terceiro": True,  # Lei 4.090 — inclusive justa causa (avos do ano)
        "ferias_vencidas": True,
        "ferias_proporcionais": t != "justa_causa",
        "multa_fgts": multa_fgts_aliquota(t) > 0,
        "aviso_metade": t in ("acordo_mutuo", "culpa_reciproca"),
        "saque_fgts": t in ("sem_justa_causa", "acordo_mutuo", "culpa_reciproca", "termino_prazo"),
    }


def projetar_aviso_dias(tipo_rescisao, aviso_modalidade, dias_aviso):
    """Dias que projetam tempo de serviço (só aviso indenizado pelo empregador)."""
    direitos = direitos_por_tipo(tipo_rescisao)
    if aviso_modalidade != "indenizado":
        return 0
    if not direitos["aviso_indenizado"]:
        return 0
    dias = max(int(dias_aviso or 0), 0)
    if direitos["aviso_metade"]:
        dias = (dias + 1) // 2  # Art. 484-A: metade do aviso
    return dias


def data_limite_pagamento(data_termino):
    """Art. 477 §6º CLT (após Lei 13.467/2017): até 10 dias do término do contrato."""
    fim = _as_date(data_termino)
    if not fim:
        return None
    return fim + timedelta(days=10)


def pagamento_em_atraso(data_termino, data_pagamento):
    limite = data_limite_pagamento(data_termino)
    pag = _as_date(data_pagamento) or date.today()
    if not limite:
        return False, None
    return pag > limite, limite


def calcular_rescisao(func, params):
    """Calcula verbas rescisórias. Campos de params são ajustáveis pela tela.

    params:
      tipo_rescisao, aviso_modalidade, data_desligamento, dias_trabalhados_mes,
      dias_aviso (opcional), ferias_vencidas_simples, ferias_vencidas_dobro,
      avos_ferias_proporcionais (opcional override), avos_13 (opcional),
      saldo_fgts_depositos, outros_proventos, outros_descontos,
      decimo_ja_pago, ind_aviso_manual (override valor aviso)
    """
    tipo = (params.get("tipo_rescisao") or "sem_justa_causa").strip()
    aviso_mod = (params.get("aviso_modalidade") or "indenizado").strip()
    deslig = _as_date(params.get("data_desligamento")) or date.today()
    admissao = (
        _as_date(func.get("data_inicio_contrato"))
        or _as_date(func.get("data_contratacao"))
        or deslig
    )
    direitos = direitos_por_tipo(tipo)
    salario_mes = salario_mensal_referencia(func)
    diario = salario_base_diario(func)

    dias_mes = int(params.get("dias_trabalhados_mes") or deslig.day)
    dias_mes = max(0, min(dias_mes, 31))
    saldo_salario = _money(diario * dias_mes) if direitos["saldo_salario"] else 0.0

    dias_aviso = params.get("dias_aviso")
    if dias_aviso is None or dias_aviso == "":
        dias_aviso = dias_aviso_proporcional(admissao, deslig)
    else:
        dias_aviso = max(0, int(dias_aviso))

    proj_dias = projetar_aviso_dias(tipo, aviso_mod, dias_aviso)

    aviso_valor = 0.0
    aviso_desconto = 0.0
    if params.get("ind_aviso_manual") not in (None, ""):
        aviso_valor = _money(params.get("ind_aviso_manual"))
    elif direitos["aviso_indenizado"] and aviso_mod == "indenizado":
        base_dias = dias_aviso
        if direitos["aviso_metade"]:
            base_dias = (dias_aviso + 1) // 2
        aviso_valor = _money(diario * base_dias)
    elif direitos["aviso_desconto_pedido"] and aviso_mod == "nao_cumprido":
        # Pedido sem cumprir: desconto de 30 dias (Art. 487 §2º), não o proporcional extra
        aviso_desconto = _money(diario * 30)

    # 13º proporcional
    avos_13 = params.get("avos_13")
    if avos_13 in (None, ""):
        avos_13 = avos_13_ano_civil(admissao, deslig, proj_dias if aviso_mod == "indenizado" else 0)
    else:
        avos_13 = max(0, min(int(avos_13), 12))
    decimo = 0.0
    if direitos["decimo_terceiro"]:
        decimo = _money(salario_mes * (avos_13 / 12.0))
        decimo = _money(max(decimo - _num(params.get("decimo_ja_pago")), 0))

    # Férias
    ferias_simples = max(int(params.get("ferias_vencidas_simples") or 0), 0)
    ferias_dobro = max(int(params.get("ferias_vencidas_dobro") or 0), 0)
    ferias_venc_valor = _money(salario_mes * ferias_simples + salario_mes * 2 * ferias_dobro)
    terco_venc = _money(ferias_venc_valor / 3.0) if direitos["ferias_vencidas"] else 0.0
    if not direitos["ferias_vencidas"]:
        ferias_venc_valor = 0.0

    avos_fer = params.get("avos_ferias_proporcionais")
    if avos_fer in (None, ""):
        # Período aquisitivo corrente: a partir do último aniversário de admissão
        anos = anos_completos_servico(admissao, deslig)
        try:
            inicio_aquisitivo = date(admissao.year + anos, admissao.month, admissao.day)
        except ValueError:
            inicio_aquisitivo = date(admissao.year + anos, admissao.month, 28)
        avos_fer = avos_periodo(
            inicio_aquisitivo,
            deslig,
            proj_dias if aviso_mod == "indenizado" else 0,
        )
        avos_fer = min(avos_fer, 12)
    else:
        avos_fer = max(0, min(int(avos_fer), 12))

    ferias_prop = 0.0
    terco_prop = 0.0
    if direitos["ferias_proporcionais"] and avos_fer > 0:
        ferias_prop = _money(salario_mes * (avos_fer / 12.0))
        terco_prop = _money(ferias_prop / 3.0)

    # FGTS do mês + multa
    aliq = aliquota_fgts_contrato(func.get("tipo_contrato"))
    base_fgts_mes = saldo_salario + decimo + (aviso_valor if aviso_mod == "indenizado" else 0.0)
    fgts_mes = _money(base_fgts_mes * aliq)
    saldo_depositos = _money(params.get("saldo_fgts_depositos"))
    # Inclui depósito do mês da rescisão na base da multa se informado
    base_multa = _money(saldo_depositos + fgts_mes)
    aliq_multa = multa_fgts_aliquota(tipo)
    multa_fgts = _money(base_multa * aliq_multa) if direitos["multa_fgts"] else 0.0

    outros_prov = _money(params.get("outros_proventos"))
    outros_desc = _money(params.get("outros_descontos"))

    proventos = _money(
        saldo_salario
        + aviso_valor
        + decimo
        + ferias_venc_valor
        + terco_venc
        + ferias_prop
        + terco_prop
        + outros_prov
    )
    descontos = _money(aviso_desconto + outros_desc)

    # INSS/IRRF aproximados sobre verbas tributáveis (saldo + 13º + aviso indenizado)
    base_inss = saldo_salario + decimo + aviso_valor
    inss = inss_empregado(base_inss)
    irrf = irrf_progressivo(max(base_inss - inss, 0))
    descontos = _money(descontos + inss + irrf)

    total_liquido = _money(proventos - descontos)

    atrasado, limite_pag = pagamento_em_atraso(deslig, params.get("data_pagamento"))

    return {
        "tipo_rescisao": tipo,
        "aviso_modalidade": aviso_mod,
        "data_admissao": admissao.isoformat(),
        "data_desligamento": deslig.isoformat(),
        "dias_trabalhados_mes": dias_mes,
        "dias_aviso": dias_aviso,
        "dias_aviso_projecao": proj_dias,
        "salario_mensal": salario_mes,
        "salario_diario": _money(diario),
        "saldo_salario": saldo_salario,
        "aviso_indenizado": aviso_valor,
        "aviso_desconto": aviso_desconto,
        "avos_13": avos_13,
        "decimo_terceiro": decimo,
        "ferias_vencidas_simples": ferias_simples,
        "ferias_vencidas_dobro": ferias_dobro,
        "ferias_vencidas": ferias_venc_valor,
        "terco_ferias_vencidas": terco_venc,
        "avos_ferias_proporcionais": avos_fer,
        "ferias_proporcionais": ferias_prop,
        "terco_ferias_proporcionais": terco_prop,
        "fgts_mes": fgts_mes,
        "aliquota_fgts": aliq,
        "saldo_fgts_depositos": saldo_depositos,
        "aliquota_multa_fgts": aliq_multa,
        "multa_fgts": multa_fgts,
        "outros_proventos": outros_prov,
        "outros_descontos": outros_desc,
        "inss": inss,
        "irrf": irrf,
        "proventos": proventos,
        "descontos": descontos,
        "total_liquido": total_liquido,
        "data_limite_pagamento": limite_pag.isoformat() if limite_pag else None,
        "pagamento_atrasado": atrasado,
        "direitos": direitos,
        "rotulo_tipo": dict(TIPOS_RESCISAO).get(tipo, tipo),
        "rotulo_aviso": dict(AVISO_MODALIDADES).get(aviso_mod, aviso_mod),
    }


def garantir_tabelas_rescisao(cursor):
    """Cria vínculos/rescisões e faz backfill a partir de funcionarios."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS funcionario_vinculos (
            id SERIAL PRIMARY KEY,
            funcionario_id INT NOT NULL REFERENCES funcionarios(id) ON DELETE CASCADE,
            matricula_esocial VARCHAR(40),
            data_inicio DATE NOT NULL,
            data_fim DATE,
            tipo_contrato VARCHAR(30) DEFAULT 'clt_mensalista',
            cargo VARCHAR(150),
            salario NUMERIC(12,2) DEFAULT 0,
            valor_hora NUMERIC(12,2) DEFAULT 0,
            horas_mes NUMERIC(10,2) DEFAULT 0,
            situacao VARCHAR(30) DEFAULT 'ativo',
            motivo_encerramento VARCHAR(40),
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_vinculo_aberto
        ON funcionario_vinculos (funcionario_id)
        WHERE data_fim IS NULL AND situacao = 'ativo'
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS rescisoes (
            id SERIAL PRIMARY KEY,
            vinculo_id INT NOT NULL UNIQUE REFERENCES funcionario_vinculos(id) ON DELETE CASCADE,
            funcionario_id INT NOT NULL REFERENCES funcionarios(id) ON DELETE CASCADE,
            data_aviso DATE,
            data_desligamento DATE NOT NULL,
            data_pagamento DATE,
            tipo VARCHAR(40) NOT NULL,
            aviso_modalidade VARCHAR(20),
            saldo_salario NUMERIC(12,2) DEFAULT 0,
            aviso_indenizado NUMERIC(12,2) DEFAULT 0,
            aviso_desconto NUMERIC(12,2) DEFAULT 0,
            decimo_terceiro NUMERIC(12,2) DEFAULT 0,
            ferias_vencidas NUMERIC(12,2) DEFAULT 0,
            ferias_proporcionais NUMERIC(12,2) DEFAULT 0,
            terco_ferias NUMERIC(12,2) DEFAULT 0,
            fgts_mes NUMERIC(12,2) DEFAULT 0,
            multa_fgts NUMERIC(12,2) DEFAULT 0,
            inss NUMERIC(12,2) DEFAULT 0,
            irrf NUMERIC(12,2) DEFAULT 0,
            outros_proventos NUMERIC(12,2) DEFAULT 0,
            outros_descontos NUMERIC(12,2) DEFAULT 0,
            total_proventos NUMERIC(12,2) DEFAULT 0,
            total_descontos NUMERIC(12,2) DEFAULT 0,
            total_liquido NUMERIC(12,2) DEFAULT 0,
            remover_usuario BOOLEAN DEFAULT FALSE,
            detalhes JSONB,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            criado_por INT
        )
        """
    )
    # Colunas de apoio no cadastro da pessoa
    for col, spec in (
        ("situacao", "VARCHAR(30) DEFAULT 'ativo'"),
        ("matricula_esocial", "VARCHAR(40)"),
    ):
        try:
            cursor.execute(f"ALTER TABLE funcionarios ADD COLUMN IF NOT EXISTS {col} {spec}")
        except Exception:
            pass

    # Backfill: um vínculo por funcionário que ainda não tenha histórico
    cursor.execute(
        """
        INSERT INTO funcionario_vinculos (
            funcionario_id, matricula_esocial, data_inicio, data_fim, tipo_contrato, cargo,
            salario, valor_hora, horas_mes, situacao, motivo_encerramento
        )
        SELECT f.id,
               f.matricula_esocial,
               COALESCE(f.data_inicio_contrato, f.data_contratacao, CURRENT_DATE),
               CASE WHEN COALESCE(f.ativo, TRUE) = FALSE OR f.data_fim_contrato IS NOT NULL
                    THEN COALESCE(f.data_fim_contrato, CURRENT_DATE) ELSE NULL END,
               COALESCE(NULLIF(f.tipo_contrato, ''), 'clt_mensalista'),
               f.cargo,
               COALESCE(f.salario, 0),
               COALESCE(f.valor_hora, 0),
               COALESCE(f.horas_mes, 0),
               CASE WHEN COALESCE(f.ativo, TRUE) = FALSE OR LOWER(COALESCE(f.situacao, '')) = 'rescindido'
                    THEN 'rescindido' ELSE 'ativo' END,
               NULL
        FROM funcionarios f
        WHERE NOT EXISTS (
            SELECT 1 FROM funcionario_vinculos v WHERE v.funcionario_id = f.id
        )
        """
    )
    cursor.execute(
        """
        UPDATE funcionarios
        SET situacao = CASE
            WHEN COALESCE(ativo, TRUE) = FALSE THEN 'rescindido'
            ELSE COALESCE(NULLIF(situacao, ''), 'ativo')
        END
        WHERE situacao IS NULL OR TRIM(situacao) = ''
        """
    )


def vinculo_aberto(cursor, funcionario_id):
    cursor.execute(
        """
        SELECT * FROM funcionario_vinculos
        WHERE funcionario_id = %s AND data_fim IS NULL AND situacao = 'ativo'
        ORDER BY id DESC LIMIT 1
        """,
        (funcionario_id,),
    )
    return cursor.fetchone()


def sincronizar_vinculo_do_funcionario(cursor, funcionario_id, dados):
    """Mantém o vínculo aberto alinhado ao cache em funcionarios (folha atual)."""
    aberto = vinculo_aberto(cursor, funcionario_id)
    inicio = (
        _as_date(dados.get("data_inicio_contrato"))
        or _as_date(dados.get("data_contratacao"))
        or date.today()
    )
    fim = _as_date(dados.get("data_fim_contrato"))
    situacao = "rescindido" if (dados.get("ativo") is False or fim) else "ativo"
    if situacao == "rescindido" and not fim:
        fim = date.today()
    vals = (
        dados.get("matricula_esocial"),
        inicio,
        fim if situacao == "rescindido" else None,
        dados.get("tipo_contrato") or "clt_mensalista",
        dados.get("cargo"),
        _num(dados.get("salario")),
        _num(dados.get("valor_hora")),
        _num(dados.get("horas_mes")),
        situacao,
        funcionario_id,
    )
    if aberto:
        cursor.execute(
            """
            UPDATE funcionario_vinculos SET
                matricula_esocial = COALESCE(%s, matricula_esocial),
                data_inicio = %s,
                data_fim = %s,
                tipo_contrato = %s,
                cargo = %s,
                salario = %s,
                valor_hora = %s,
                horas_mes = %s,
                situacao = %s
            WHERE id = %s
            """,
            vals[:-1] + (aberto["id"],),
        )
        return aberto["id"]
    cursor.execute(
        """
        INSERT INTO funcionario_vinculos (
            funcionario_id, matricula_esocial, data_inicio, data_fim, tipo_contrato, cargo,
            salario, valor_hora, horas_mes, situacao
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (funcionario_id,) + vals[:-1],
    )
    row = cursor.fetchone()
    return row["id"] if row else None


def encerrar_vinculo_e_salvar_rescisao(cursor, funcionario_id, calculo, params, usuario_id=None):
    """Fecha vínculo, grava rescisão, marca pessoa como rescindida e opcionalmente remove login."""
    aberto = vinculo_aberto(cursor, funcionario_id)
    deslig = _as_date(calculo["data_desligamento"])
    if not aberto:
        # Garante vínculo a partir do cadastro atual
        cursor.execute("SELECT * FROM funcionarios WHERE id = %s", (funcionario_id,))
        func = cursor.fetchone() or {}
        sincronizar_vinculo_do_funcionario(
            cursor,
            funcionario_id,
            {
                **dict(func),
                "ativo": True,
                "data_fim_contrato": None,
            },
        )
        aberto = vinculo_aberto(cursor, funcionario_id)
    if not aberto:
        raise ValueError("Não há vínculo ativo para rescindir.")

    cursor.execute(
        """
        UPDATE funcionario_vinculos
        SET data_fim = %s, situacao = 'rescindido', motivo_encerramento = %s
        WHERE id = %s
        """,
        (deslig, calculo["tipo_rescisao"], aberto["id"]),
    )

    terco = _money(
        _num(calculo.get("terco_ferias_vencidas")) + _num(calculo.get("terco_ferias_proporcionais"))
    )
    detalhes = json.dumps(calculo, ensure_ascii=False, default=str)
    cursor.execute(
        """
        INSERT INTO rescisoes (
            vinculo_id, funcionario_id, data_aviso, data_desligamento, data_pagamento,
            tipo, aviso_modalidade, saldo_salario, aviso_indenizado, aviso_desconto,
            decimo_terceiro, ferias_vencidas, ferias_proporcionais, terco_ferias,
            fgts_mes, multa_fgts, inss, irrf, outros_proventos, outros_descontos,
            total_proventos, total_descontos, total_liquido, remover_usuario, detalhes, criado_por
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s::jsonb, %s
        )
        RETURNING id
        """,
        (
            aberto["id"],
            funcionario_id,
            _as_date(params.get("data_aviso")),
            deslig,
            _as_date(params.get("data_pagamento")),
            calculo["tipo_rescisao"],
            calculo["aviso_modalidade"],
            calculo["saldo_salario"],
            calculo["aviso_indenizado"],
            calculo["aviso_desconto"],
            calculo["decimo_terceiro"],
            calculo["ferias_vencidas"],
            calculo["ferias_proporcionais"],
            terco,
            calculo["fgts_mes"],
            calculo["multa_fgts"],
            calculo["inss"],
            calculo["irrf"],
            calculo["outros_proventos"],
            calculo["outros_descontos"],
            calculo["proventos"],
            calculo["descontos"],
            calculo["total_liquido"],
            bool(params.get("remover_usuario")),
            detalhes,
            usuario_id,
        ),
    )
    rescisao_id = cursor.fetchone()["id"]

    cursor.execute(
        """
        UPDATE funcionarios SET
            ativo = FALSE,
            situacao = 'rescindido',
            data_fim_contrato = %s,
            enviar_contracheque = FALSE
        WHERE id = %s
        """,
        (deslig, funcionario_id),
    )

    removido_login = False
    if params.get("remover_usuario"):
        cursor.execute("SELECT usuario_id FROM funcionarios WHERE id = %s", (funcionario_id,))
        row = cursor.fetchone() or {}
        uid = row.get("usuario_id")
        if uid:
            cursor.execute("UPDATE funcionarios SET usuario_id = NULL WHERE id = %s", (funcionario_id,))
            cursor.execute("DELETE FROM usuarios WHERE id = %s", (uid,))
            removido_login = True

    return rescisao_id, removido_login


def recontratar_funcionario(cursor, funcionario_id, novo_contrato):
    """Abre novo vínculo reaproveitando dados cadastrais da pessoa.

    novo_contrato: data_inicio, cargo, tipo_contrato, salario, valor_hora, horas_mes,
                   matricula_esocial, dia_pagamento
    """
    cursor.execute("SELECT * FROM funcionarios WHERE id = %s", (funcionario_id,))
    pessoa = cursor.fetchone()
    if not pessoa:
        raise ValueError("Funcionário não encontrado.")
    aberto = vinculo_aberto(cursor, funcionario_id)
    if aberto:
        raise ValueError("Já existe um vínculo ativo. Encerre a rescisão antes de recontratar.")

    inicio = _as_date(novo_contrato.get("data_inicio")) or date.today()
    tipo = novo_contrato.get("tipo_contrato") or "clt_mensalista"
    cargo = (novo_contrato.get("cargo") or pessoa.get("cargo") or "Funcionário").strip()
    salario = _num(novo_contrato.get("salario"))
    valor_hora = _num(novo_contrato.get("valor_hora"))
    horas_mes = _num(novo_contrato.get("horas_mes"))
    matricula = (novo_contrato.get("matricula_esocial") or "").strip() or None

    cursor.execute(
        """
        INSERT INTO funcionario_vinculos (
            funcionario_id, matricula_esocial, data_inicio, data_fim, tipo_contrato, cargo,
            salario, valor_hora, horas_mes, situacao
        ) VALUES (%s, %s, %s, NULL, %s, %s, %s, %s, %s, 'ativo')
        RETURNING id
        """,
        (funcionario_id, matricula, inicio, tipo, cargo, salario, valor_hora, horas_mes),
    )
    vid = cursor.fetchone()["id"]

    cursor.execute(
        """
        UPDATE funcionarios SET
            ativo = TRUE,
            situacao = 'ativo',
            data_contratacao = %s,
            data_inicio_contrato = %s,
            data_fim_contrato = NULL,
            cargo = %s,
            tipo_contrato = %s,
            salario = %s,
            valor_hora = %s,
            horas_mes = %s,
            matricula_esocial = %s,
            dia_pagamento = COALESCE(%s, dia_pagamento, 5),
            enviar_contracheque = TRUE
        WHERE id = %s
        """,
        (
            inicio,
            inicio,
            cargo,
            tipo,
            salario,
            valor_hora,
            horas_mes,
            matricula,
            novo_contrato.get("dia_pagamento"),
            funcionario_id,
        ),
    )
    return vid


def listar_historico_vinculos(cursor, funcionario_id):
    cursor.execute(
        """
        SELECT v.*, r.id AS rescisao_id, r.tipo AS rescisao_tipo, r.total_liquido, r.data_desligamento AS rescisao_data
        FROM funcionario_vinculos v
        LEFT JOIN rescisoes r ON r.vinculo_id = v.id
        WHERE v.funcionario_id = %s
        ORDER BY v.data_inicio DESC, v.id DESC
        """,
        (funcionario_id,),
    )
    return list(cursor.fetchall() or [])


def decimal_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError
