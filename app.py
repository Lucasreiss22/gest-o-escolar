import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from flask import Flask, flash, redirect, render_template, request, url_for, session, send_file
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename
from config import carregar_config, ambiente_producao
from email_envio import (
    email_valido,
    enviar_email,
    emails_contato_aluno,
    smtp_configurado,
    bytes_pdf,
    exigencia_email,
    enviar_via_gmail_api,
)
from psycopg2.extras import RealDictCursor
from alunos import cadastrar_aluno, listar_alunos, atualizar_responsavel, deletar_responsavel
from database import obter_conexao, garantir_tabelas_pedagogicas, garantir_tabelas_folha, definir_banco_escola, limpar_banco_escola, resetar_tenant, erro_conexao_atual
from tributacao import (
    apurar_simples,
    apurar_pis_cofins,
    apurar_lucro_presumido,
    folha_mensal_fator_r,
    janela_12_meses_anteriores,
    meses_de_atividade,
    parse_mes,
)
from relatorios_pdf import (
    pdf_boletim,
    pdf_contracheque,
    pdf_historico_periodo,
    pdf_folha_pagamento,
    pdf_lucro_presumido,
    pdf_lucro_real,
    pdf_simples_nacional,
    pdf_cobranca_mensalidade,
)
from folha import calcular_folha_pessoa, rotulo_contrato, impostos_nota
from permissoes import pode_endpoint, pode_modulo, normalizar_papel, rotulo_papel
from plataforma import (
    buscar_admin_plataforma,
    buscar_escola_por_email,
    buscar_escola_por_token,
    cadastrar_escola,
    atualizar_email_admin_escola,
    definir_status_escola,
    excluir_escola,
    regenerar_convite_escola,
    buscar_escola_por_id,
    eh_super_admin,
    email_super_admin,
    enviar_codigo,
    gerar_otp,
    garantir_plataforma,
    credenciais_google,
    listar_escolas,
    salvar_google_oauth,
    salvar_google_refresh,
    salvar_senha_plataforma,
    salvar_smtp_plataforma,
    localizar_escola_do_email,
    usuario_da_escola,
    validar_otp,
    ativar_escola as concluir_ativacao_escola,
)
import calendar as calendario_lib
from datetime import datetime, date, timedelta
import json
import hashlib
import secrets
import uuid

_CFG = carregar_config()
try:
    from urllib.parse import urlparse
    _dsn = (_CFG.get("DATABASE_URL") or "").replace("postgresql://", "http://").replace("postgres://", "http://")
    _host = urlparse(_dsn).hostname or "(sem host)"
    print(f"Postgres alvo: {_host}")
except Exception:
    pass
app = Flask(__name__)
app.secret_key = _CFG["SECRET_KEY"]
app.config["PREFERRED_URL_SCHEME"] = _CFG["PREFERRED_URL_SCHEME"]
if ambiente_producao():
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

oauth = None
try:
    from authlib.integrations.flask_client import OAuth as _OAuth
    oauth = _OAuth(app)
except ImportError:
    oauth = None


def _google_habilitado():
    cred = credenciais_google()
    cid = (cred.get("client_id") or "").strip()
    secret = (cred.get("client_secret") or "").strip()
    if "@" in cid or "googleusercontent.com" not in cid:
        return False
    return bool(oauth and cid and secret)


def _registrar_oauth():
    if not oauth:
        return False
    cred = credenciais_google()
    if not cred.get("client_id") or not cred.get("client_secret"):
        return False
    oauth.register(
        "google",
        overwrite=True,
        client_id=cred["client_id"],
        client_secret=cred["client_secret"],
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={
            "scope": "openid email profile https://www.googleapis.com/auth/gmail.send",
        },
    )
    return True


def _contar(row):
    if not row:
        return 0
    if isinstance(row, dict):
        return int(next(iter(row.values())) or 0)
    try:
        return int(row[0] or 0)
    except Exception:
        return 0


def _log(mensagem):
    try:
        print(str(mensagem).encode("ascii", "replace").decode("ascii"))
    except Exception:
        pass


def _float_form(nome, padrao=0.0):
    bruto = (request.form.get(nome) or "").strip().replace(",", ".")
    try:
        return float(bruto) if bruto else padrao
    except ValueError:
        return padrao


def _efeito_caixa_custo(custo):
    valor = float(custo.get("valor") or 0)
    tipo = (custo.get("tipo") or "avista").lower()
    extra = 0.0
    if tipo == "servico":
        federais = (
            float(custo.get("irrf") or 0)
            + float(custo.get("pis") or 0)
            + float(custo.get("cofins") or 0)
            + float(custo.get("csll") or 0)
        )
        if not custo.get("federal_na_nota"):
            extra += federais
        if not custo.get("iss_na_nota"):
            extra += float(custo.get("iss") or 0)
    return valor + extra, tipo


def resumir_custos_operacionais(custos):
    compras = 0.0
    servicos = 0.0
    for item in custos or []:
        efeito, tipo = _efeito_caixa_custo(item)
        if tipo == "servico":
            servicos += efeito
        else:
            compras += efeito
    return {
        "compras": round(compras, 2),
        "servicos": round(servicos, 2),
        "custos": round(compras + servicos, 2),
    }


def listar_custos_do_mes(cursor, mes_filtro):
    cursor.execute(
        """
        SELECT id, descricao, categoria, valor, data_custo, tipo, forma, parcelas, parcela_num,
               data_inicio, data_fim, valor_bruto, prestador, reter_federal, reter_iss,
               federal_na_nota, iss_na_nota, irrf, pis, cofins, csll, iss
        FROM financeiro_custos
        WHERE COALESCE(ativo, TRUE) = TRUE
          AND (
            (COALESCE(tipo, 'avista') IN ('avista', 'servico', 'parcelado')
                AND TO_CHAR(data_custo, 'YYYY-MM') = %s)
            OR (tipo = 'recorrente'
                AND TO_CHAR(COALESCE(data_inicio, data_custo), 'YYYY-MM') <= %s
                AND (data_fim IS NULL OR TO_CHAR(data_fim, 'YYYY-MM') >= %s))
          )
        ORDER BY COALESCE(data_custo, data_inicio) DESC
        """,
        (mes_filtro, mes_filtro, mes_filtro),
    )
    return cursor.fetchall()


def _cargo_do_papel(papel):
    mapa = {
        "admin": "Administrador",
        "supervisor": "Supervisor",
        "financeiro": "Financeiro",
        "direcao": "Direção",
        "secretaria": "Secretaria",
        "professor": "Professor",
        "funcionario": "Funcionário",
    }
    return mapa.get(normalizar_papel(papel), "Funcionário")


def _data_iso(valor):
    if not valor:
        return ""
    if hasattr(valor, "strftime"):
        return valor.strftime("%Y-%m-%d")
    return str(valor)[:10]


def _cpf_provisorio(chave):
    digest = hashlib.md5((chave or "x").encode("utf-8")).hexdigest()
    digits = "".join(ch for ch in digest if ch.isdigit()) + "00000000000"
    return digits[:11]


def _add_months(data_ref, meses):
    if not data_ref:
        data_ref = date.today()
    if isinstance(data_ref, str):
        data_ref = datetime.strptime(data_ref[:10], "%Y-%m-%d").date()
    elif isinstance(data_ref, datetime):
        data_ref = data_ref.date()
    total = data_ref.year * 12 + (data_ref.month - 1) + int(meses)
    ano, mes = divmod(total, 12)
    dia = min(data_ref.day, calendario_lib.monthrange(ano, mes + 1)[1])
    return date(ano, mes + 1, dia)


def _rotulo_turno_mensalidade(turnos):
    mapa = {
        "manha": "somente manhã",
        "tarde": "somente tarde",
        "noite": "somente noite",
        "integral": "manhã e tarde",
        "dois": "manhã e tarde",
    }
    return mapa.get((turnos or "manha").strip().lower(), "somente manhã")


def _gerar_mensalidades_contrato(cursor, aluno_id, valor, inicio, meses, turnos, descricao_base="Mensalidade"):
    if not aluno_id or not valor or valor <= 0:
        return 0
    meses = max(int(meses or 1), 1)
    turnos = turnos or "manha"
    geradas = 0
    for i in range(meses):
        venc = _add_months(inicio, i)
        competencia = venc.strftime("%Y-%m")
        cursor.execute(
            """
            SELECT 1 FROM financeiro_mensalidades
            WHERE aluno_id = %s AND TO_CHAR(data_vencimento, 'YYYY-MM') = %s
            LIMIT 1
            """,
            (aluno_id, competencia),
        )
        if cursor.fetchone():
            continue
        rotulo = _rotulo_turno_mensalidade(turnos)
        descricao = f"{descricao_base} {venc.strftime('%m/%Y')} ({i + 1}/{meses}) · {rotulo}"
        cursor.execute(
            """
            INSERT INTO financeiro_mensalidades
                (aluno_id, descricao, valor, data_vencimento, status, turno, parcela_contrato)
            VALUES (%s, %s, %s, %s, 'Pendente', %s, %s)
            """,
            (aluno_id, descricao, valor, venc, turnos, i + 1),
        )
        geradas += 1
    return geradas


@app.context_processor
def inject_acl():
    papel = normalizar_papel(session.get("usuario_papel"))
    return {
        "papel_atual": papel,
        "rotulo_papel": rotulo_papel(papel),
        "pode": lambda modulo: pode_modulo(papel, modulo),
        "smtp_ok": smtp_configurado(),
        "google_login": _google_habilitado(),
        "super_admin": bool(session.get("super_admin")),
        "escola_nome": session.get("escola_nome"),
        "origem_plataforma": bool(session.get("origem_plataforma")),
    }


@app.before_request
def isolar_banco_da_requisicao():
    resetar_tenant()
    if session.get("escola_db") and not session.get("super_admin"):
        definir_banco_escola(session.get("escola_db"))


@app.teardown_request
def encerrar_tenant(_erro):
    resetar_tenant()


@app.before_request
def proteger_rotas():
    endpoint = request.endpoint
    publicos = {
        None, "login", "logout", "static", "login_google", "login_google_callback",
        "login_codigo", "login_senha", "ativar_escola", "login_conectar_gmail", "login_esqueci_senha",
    }
    if endpoint in publicos:
        return None
    if session.get("super_admin"):
        if endpoint not in {"plataforma_escolas", "plataforma_autorizar_gmail", "logout", "plataforma_voltar"}:
            return redirect(url_for("plataforma_escolas"))
        return None
    if endpoint == "plataforma_voltar" and session.get("origem_plataforma"):
        return None
    if session.get("escola_id"):
        escola = buscar_escola_por_id(session.get("escola_id"))
        if not escola or not escola.get("ativo", True):
            session.clear()
            flash("Esta escola está pausada ou foi removida. O acesso ao sistema está bloqueado.", "danger")
            return redirect(url_for("login"))
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    if not session.get("escola_db"):
        session.clear()
        flash("Sessão sem banco da escola. Entre novamente.", "danger")
        return redirect(url_for("login"))
    if endpoint == "plataforma_escolas":
        flash("Apenas o administrador da plataforma pode cadastrar novas escolas.", "danger")
        return redirect(url_for("dashboard"))
    papel = session.get("usuario_papel")
    if endpoint == "pagina_pedagogico" and request.method == "POST":
        acao = request.form.get("acao") or ""
        if acao in ("criar_turma", "nova_turma", "vincular_aluno", "incluir_aluno") and not pode_modulo(papel, "pedagogico_cadastro"):
            flash("❌ Sem permissão para cadastrar turma ou matricular aluno (secretaria).", "danger")
            return redirect(url_for("pagina_pedagogico"))
    if not pode_endpoint(papel, endpoint):
        flash("❌ Sem permissão para acessar esta área.", "danger")
        return redirect(url_for("dashboard"))
    return None

PASTA_UPLOADS_PROVAS = "static/uploads/provas"
PASTA_UPLOADS_BOLETINS = "static/uploads/boletins"
os.makedirs(PASTA_UPLOADS_PROVAS, exist_ok=True)
os.makedirs(PASTA_UPLOADS_BOLETINS, exist_ok=True)


def limpar_campo(campo_nome, *args, **kwargs):
    valor = request.form.get(campo_nome)
    if valor is not None:
        valor = valor.strip()
        return valor if valor != "" else None
    return None


def _materias_da_turma(cursor, turma_id):
    if not turma_id:
        return []
    cursor.execute(
        """
        SELECT d.nome
        FROM turma_disciplinas td
        JOIN disciplinas d ON d.id = td.disciplina_id
        WHERE td.turma_id = %s
        ORDER BY d.nome
        """,
        (turma_id,),
    )
    nomes = []
    for row in cursor.fetchall():
        nomes.append(row["nome"] if isinstance(row, dict) else row[0])
    return nomes


def _upsert_frequencia(cursor, aluno_id, turma_id, data_aula, status, disciplina=""):
    disc = (disciplina or "").strip()
    cursor.execute(
        """
        INSERT INTO frequencia (aluno_id, turma_id, data_aula, status, disciplina)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (aluno_id, data_aula, disciplina)
        DO UPDATE SET status = EXCLUDED.status,
            turma_id = COALESCE(EXCLUDED.turma_id, frequencia.turma_id);
        """,
        (aluno_id, turma_id or None, data_aula, status, disc),
    )


def _lancar_frequencia_materias(cursor, aluno_id, turma_id, data_aula, status, disciplina):
    disc = (disciplina or "").strip()
    if disc in ("__todas__", "todas"):
        materias = _materias_da_turma(cursor, turma_id)
        if not materias:
            raise ValueError("Cadastre as matérias desta turma para lançar em todas.")
        for nome in materias:
            _upsert_frequencia(cursor, aluno_id, turma_id, data_aula, status, nome)
        return
    if not disc:
        _upsert_frequencia(cursor, aluno_id, turma_id, data_aula, status, "")
        return
    _upsert_frequencia(cursor, aluno_id, turma_id, data_aula, status, disc)


DIAS_SEMANA_OPCOES = [
    ("seg", "Seg"),
    ("ter", "Ter"),
    ("qua", "Qua"),
    ("qui", "Qui"),
    ("sex", "Sex"),
    ("sab", "Sáb"),
]


def _fmt_horas(valor):
    if valor is None:
        return "0h"
    numero = float(valor)
    if abs(numero - round(numero)) < 0.05:
        return f"{int(round(numero))}h"
    return f"{numero:.1f}".replace(".", ",") + "h"


def _parse_grade(valor):
    if not valor:
        return []
    if isinstance(valor, list):
        return valor
    try:
        dados = json.loads(valor)
        return dados if isinstance(dados, list) else []
    except Exception:
        return []


def _ler_grade_semanal():
    grade = []
    for dia, _rotulo in DIAS_SEMANA_OPCOES:
        qtds = request.form.getlist(f"grade_{dia}_qtd")
        mins = request.form.getlist(f"grade_{dia}_min")
        for qtd, minutos in zip(qtds, mins):
            try:
                qn = int(qtd or 0)
                mn = int(minutos or 60)
            except ValueError:
                continue
            if qn > 0:
                grade.append({"dia": dia, "quantidade": qn, "minutos": mn})
    return grade


def _ler_carga_materia():
    tipo = request.form.get("tipo_frequencia") or "semanal"
    vezes = int(request.form.get("vezes_mes") or 1)
    minutos_esp = int(request.form.get("minutos_aula") or 60)
    grade = _ler_grade_semanal()
    if tipo == "esporadica":
        carga = max(1, int(round(vezes * minutos_esp / 60.0)))
        aulas = 0
        dias = ""
        minutos = minutos_esp
    else:
        semana_min = sum(int(b["quantidade"]) * int(b["minutos"]) for b in grade)
        carga = max(1, int(round(semana_min / 60.0))) if semana_min else 1
        aulas = sum(int(b["quantidade"]) for b in grade)
        dias = ",".join(dict.fromkeys(b["dia"] for b in grade))
        minutos = int(grade[0]["minutos"]) if grade else 60
    return tipo, aulas, minutos, vezes, dias, carga, json.dumps(grade)


def _grade_efetiva(row):
    tipo = row.get("tipo_frequencia") or "semanal"
    grade = _parse_grade(row.get("grade_json"))
    if grade or tipo == "esporadica":
        return grade
    minutos = int(row.get("minutos_aula") or 60)
    dias = [p for p in (row.get("dias_semana") or "").split(",") if p]
    aulas = int(row.get("aulas_semana") or 0)
    if dias:
        return [{"dia": d, "quantidade": 1, "minutos": minutos} for d in dias]
    if aulas:
        return [{"dia": "seg", "quantidade": aulas, "minutos": minutos}]
    return []


def _quadro_materia(row):
    tipo = row.get("tipo_frequencia") or "semanal"
    if tipo == "esporadica":
        vezes = int(row.get("vezes_mes") or 1)
        minutos = int(row.get("minutos_aula") or 60)
        hora = minutos / 60.0
        mes = vezes * hora
        return {
            "nome": row.get("nome"),
            "tipo": "Esporádica",
            "dias": f"{vezes}x no mês · {_fmt_horas(hora)} cada",
            "hora_dia": _fmt_horas(hora),
            "hora_semana": "—",
            "hora_mes": _fmt_horas(mes),
            "resumo": f"esporádica · {vezes}x no mês · {_fmt_horas(hora)} cada · {_fmt_horas(mes)}/mês",
        }
    grade = _grade_efetiva(row)
    mapa = dict(DIAS_SEMANA_OPCOES)
    por_dia_min = {}
    semana_min = 0
    for bloco in grade:
        mins = int(bloco.get("quantidade") or 0) * int(bloco.get("minutos") or 0)
        dia = bloco.get("dia")
        por_dia_min[dia] = por_dia_min.get(dia, 0) + mins
        semana_min += mins
    partes = [f"{mapa.get(dia, dia)} {_fmt_horas(mins / 60.0)}" for dia, mins in por_dia_min.items() if mins]
    semana_h = semana_min / 60.0
    return {
        "nome": row.get("nome"),
        "tipo": "Semanal",
        "dias": ", ".join(partes) or "—",
        "hora_dia": ", ".join(partes) or "—",
        "hora_semana": _fmt_horas(semana_h),
        "hora_mes": _fmt_horas(semana_h * 4),
        "resumo": (
            f"{', '.join(partes)} · {_fmt_horas(semana_h)}/semana · {_fmt_horas(semana_h * 4)}/mês"
            if partes
            else f"{_fmt_horas(semana_h)}/semana"
        ),
    }


def calcular_encargos_professor(salario_base, regime_tributario="lucro_presumido"):
    """
    Calcula os encargos trabalhistas e provisões com base no salário bruto.
    regime_tributario: 'lucro_presumido', 'lucro_real' ou 'simples_nacional'
    """
    salario = float(salario_base or 0.0)
    
    fgts = salario * 0.08
    provisao_13 = salario / 12
    ferias_terco = (salario + (salario / 3)) / 12
    reflexos_fgts = (provisao_13 + ferias_terco) * 0.08
    
    if regime_tributario in ["lucro_presumido", "lucro_real"]:
        inss_patronal = salario * 0.20
        rat = salario * 0.01
        sistema_s = salario * 0.058
    else:  # Simples Nacional Anexo III (INSS patronal e RAT inclusos no DAS)
        inss_patronal = 0.0
        rat = 0.0
        sistema_s = 0.0
        
    total_encargos = fgts + provisao_13 + ferias_terco + reflexos_fgts + inss_patronal + rat + sistema_s
    custo_total = salario + total_encargos
    
    return {
        "salario_base": salario,
        "fgts": fgts,
        "provisao_13": provisao_13,
        "ferias_terco": ferias_terco,
        "reflexos_fgts": reflexos_fgts,
        "inss_patronal": inss_patronal,
        "rat": rat,
        "sistema_s": sistema_s,
        "total_encargos": total_encargos,
        "custo_total": custo_total
    }

# Disponibilizando a função globalmente para os templates HTML (Jinja2)
app.jinja_env.globals.update(calcular_encargos_professor=calcular_encargos_professor)


def _data_para_date(valor):
    if not valor:
        return None
    if hasattr(valor, "date") and not isinstance(valor, datetime):
        try:
            return valor
        except Exception:
            pass
    if isinstance(valor, datetime):
        return valor.date()
    return valor


def montar_folha_colaboradores(cursor):
    try:
        cursor.execute(
            """
            SELECT nome_completo,
                   COALESCE(salario, 0)::numeric AS salario,
                   data_contratacao
            FROM funcionarios
            WHERE ativo = TRUE
            ORDER BY nome_completo;
            """
        )
        rows = cursor.fetchall()
    except Exception:
        cursor.connection.rollback()
        cursor.execute(
            """
            SELECT nome_completo,
                   COALESCE(salario, 0)::numeric AS salario
            FROM funcionarios
            WHERE ativo = TRUE
            ORDER BY nome_completo;
            """
        )
        rows = cursor.fetchall()
        for row in rows:
            row["data_contratacao"] = None

    detalhe = []
    total_mes = 0.0
    for row in rows:
        calc = folha_mensal_fator_r(row["salario"])
        calc["nome_completo"] = row["nome_completo"]
        calc["data_contratacao"] = _data_para_date(row.get("data_contratacao"))
        detalhe.append(calc)
        total_mes += calc["total"]
    return detalhe, total_mes


def montar_folha_contratos(cursor, regime, mes_filtro=None):
    garantir_tabelas_folha()
    ano = mes = None
    if mes_filtro:
        try:
            ano, mes = parse_mes(mes_filtro)
        except Exception:
            ano = mes = None
    cursor.execute(
        """
        SELECT id, nome_completo, cargo, salario, tipo_contrato, valor_hora, horas_mes,
               reter_federal, reter_iss, aliquota_iss, usuario_id, email
        FROM funcionarios
        WHERE ativo = TRUE
        ORDER BY nome_completo
        """
    )
    itens = []
    totais = {
        "bruto": 0.0,
        "liquido": 0.0,
        "encargos": 0.0,
        "custo_escola": 0.0,
        "inss_patronal": 0.0,
        "fgts": 0.0,
    }
    for row in cursor.fetchall():
        calc = calcular_folha_pessoa(dict(row), regime, ano, mes)
        calc["rotulo_contrato"] = rotulo_contrato(calc["tipo_contrato"])
        calc["reter_federal"] = row.get("reter_federal")
        calc["reter_iss"] = row.get("reter_iss")
        calc["aliquota_iss"] = row.get("aliquota_iss") or 5
        calc["email"] = row.get("email")
        itens.append(calc)
        totais["bruto"] += calc["bruto"]
        totais["liquido"] += calc["liquido"]
        totais["encargos"] += calc["encargos"]
        totais["custo_escola"] += calc["custo_escola"]
        totais["inss_patronal"] += calc["inss_patronal"]
        totais["fgts"] += calc["fgts"]
    for chave in totais:
        totais[chave] = round(totais[chave], 2)
    return itens, totais


def data_inicio_atividade(cursor):
    cursor.execute("SELECT MIN(data_vencimento) AS inicio FROM financeiro_mensalidades;")
    row = cursor.fetchone()
    if row and row.get("inicio"):
        return _data_para_date(row["inicio"])
    cursor.execute("SELECT MIN(data_contratacao) AS inicio FROM funcionarios;")
    row = cursor.fetchone()
    if row and row.get("inicio"):
        return _data_para_date(row["inicio"])
    return None


def receita_por_periodo(cursor, inicio, fim_exclusivo):
    cursor.execute(
        """
        SELECT COALESCE(SUM(valor::numeric), 0) AS total
        FROM financeiro_mensalidades
        WHERE data_vencimento >= %s AND data_vencimento < %s;
        """,
        (inicio, fim_exclusivo),
    )
    return float(cursor.fetchone()["total"] or 0)


def receita_do_mes(cursor, mes_filtro):
    cursor.execute(
        """
        SELECT COALESCE(SUM(valor::numeric), 0) AS total
        FROM financeiro_mensalidades
        WHERE TO_CHAR(data_vencimento, 'YYYY-MM') = %s;
        """,
        (mes_filtro,),
    )
    return float(cursor.fetchone()["total"] or 0)


def listar_lancamentos_mes(cursor, mes_filtro, status=None):
    sql = """
        SELECT f.id, a.nome_completo, f.descricao, f.valor, f.data_vencimento,
               f.data_pagamento, f.status
        FROM financeiro_mensalidades f
        LEFT JOIN alunos a ON f.aluno_id = a.id
        WHERE TO_CHAR(f.data_vencimento, 'YYYY-MM') = %s
    """
    params = [mes_filtro]
    if status:
        sql += " AND f.status = %s"
        params.append(status)
    sql += " ORDER BY f.data_vencimento, a.nome_completo;"
    cursor.execute(sql, params)
    return cursor.fetchall()


def calcular_apuracao_simples(cursor, mes_filtro):
    ano, mes = parse_mes(mes_filtro)
    inicio_janela, fim_janela = janela_12_meses_anteriores(ano, mes)
    inicio_escola = data_inicio_atividade(cursor)
    n_meses, _inicio_real = meses_de_atividade(inicio_escola, inicio_janela, fim_janela)
    if n_meses == 0:
        n_meses = 1
    rbt_acumulado = receita_por_periodo(cursor, inicio_janela, fim_janela)
    colaboradores, folha_mes = montar_folha_colaboradores(cursor)
    fs_acumulado = 0.0
    for colab in colaboradores:
        n_colab, _ = meses_de_atividade(colab.get("data_contratacao") or inicio_escola, inicio_janela, fim_janela)
        fs_acumulado += colab["total"] * max(n_colab, 0)
    receita_mes = receita_do_mes(cursor, mes_filtro)
    apuracao = apurar_simples(rbt_acumulado, fs_acumulado, n_meses, receita_mes)
    apuracao["inicio_janela"] = inicio_janela
    apuracao["fim_janela"] = fim_janela
    apuracao["inicio_escola"] = inicio_escola
    return apuracao, colaboradores


def nome_mes_extenso(mes_filtro):
    meses = [
        "janeiro", "fevereiro", "março", "abril", "maio", "junho",
        "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
    ]
    ano, mes = parse_mes(mes_filtro)
    return f"{meses[mes - 1].capitalize()}/{ano}"


def _iniciar_sessao(usuario, email):
    session["usuario_id"] = usuario["id"]
    session["usuario_nome"] = usuario.get("nome") or usuario.get("nome_completo")
    session["usuario_papel"] = normalizar_papel(usuario.get("papel") or usuario.get("cargo") or "admin")
    garantir_tabelas_folha()
    garantir_tabelas_pedagogicas()
    conexao = obter_conexao()
    if conexao:
        try:
            with conexao.cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM funcionarios WHERE usuario_id = %s OR LOWER(email) = LOWER(%s) LIMIT 1",
                    (usuario["id"], email),
                )
                func = cursor.fetchone()
                if func:
                    session["funcionario_id"] = func["id"] if isinstance(func, dict) else func[0]
        finally:
            conexao.close()


def _entrar_plataforma(admin):
    session.clear()
    session["usuario_id"] = admin["id"]
    session["usuario_nome"] = admin.get("nome") or admin.get("email")
    session["usuario_email"] = admin.get("email")
    session["usuario_papel"] = "plataforma"
    session["super_admin"] = True


def _entrar_escola(usuario, email, escola, origem_plataforma=False, plataforma_email=None):
    session.clear()
    session["escola_db"] = escola["db_nome"]
    session["escola_id"] = escola["id"]
    session["escola_nome"] = escola["nome"]
    session["super_admin"] = False
    if origem_plataforma:
        session["origem_plataforma"] = True
        session["plataforma_email"] = plataforma_email or email_super_admin()
    _iniciar_sessao(usuario, email)
    session["usuario_email"] = email


def _usuario_admin_escola(escola):
    token = definir_banco_escola(escola["db_nome"])
    try:
        garantir_tabelas_pedagogicas()
        conexao = obter_conexao()
        if not conexao:
            raise RuntimeError("Não conectou no banco da escola.")
        try:
            with conexao.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM usuarios WHERE LOWER(email) = %s",
                    (escola["email_admin"],),
                )
                usuario = cursor.fetchone()
                if usuario:
                    return usuario
                cursor.execute(
                    "INSERT INTO usuarios (nome, email, senha, papel) VALUES (%s, %s, %s, 'admin') RETURNING *",
                    (escola["nome"], escola["email_admin"], secrets.token_urlsafe(12)),
                )
                usuario = cursor.fetchone()
            conexao.commit()
            return usuario
        finally:
            conexao.close()
    finally:
        limpar_banco_escola(token)


def _emails_admin_permitidos():
    bruto = (_CFG.get("ADMIN_EMAILS") or "").replace(";", ",")
    return {item.strip().lower() for item in bruto.split(",") if email_valido(item)}


def _voltar_ou(padrao):
    origem = (request.form.get("next") or request.args.get("next") or request.referrer or "").strip()
    if origem and origem.startswith("/"):
        return origem
    return padrao


def _enviar_codigo_plataforma(email, access_token=None):
    codigo = gerar_otp(email, "login_plataforma")
    corpo = (
        f"Seu código de confirmação da Gestão Escolar é: {codigo}\n\n"
        "Ele vale por 20 minutos. Se você não pediu este acesso, ignore o e-mail."
    )
    assunto = "Código de acesso da plataforma"
    session.pop("otp_local", None)
    try:
        if access_token:
            enviar_via_gmail_api(access_token, [email], assunto, corpo, remetente=email)
        else:
            ok, erro = enviar_codigo(email, codigo, assunto, corpo)
            if not ok:
                raise RuntimeError(erro)
    except Exception as e:
        texto = str(e)
        baixo = texto.lower()
        if any(x in texto or x in baixo for x in (
            "534", "535", "application-specific", "invalidsecondfactor", "username and password not accepted",
        )):
            texto = (
                "O Google bloqueou a senha normal da conta. No campo abaixo cole a senha de app "
                "(16 letras), não a senha com que você abre o Gmail."
            )
        flash(f"Não foi possível enviar o código para {email}: {texto}", "danger")
        return redirect(url_for("login_conectar_gmail"))
    flash(f"Código enviado para {email}. Abra o Gmail e digite os 6 dígitos.", "success")
    return redirect(url_for("login_codigo"))


@app.route("/login/esqueci-senha")
def login_esqueci_senha():
    garantir_plataforma()
    email = session.get("login_email")
    if not email:
        flash("Informe o e-mail na tela inicial.", "danger")
        return redirect(url_for("login"))
    if not eh_super_admin(email):
        flash("Redefinição por código está disponível para o administrador da plataforma. Escolas usam o convite enviado no cadastro.", "danger")
        return redirect(url_for("login_senha"))
    session["redefinir_senha"] = True
    return _enviar_codigo_plataforma(email)


@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    garantir_plataforma()
    if request.method == "POST":
        try:
            email = exigencia_email(request.form.get("email"), "E-mail")
        except ValueError as e:
            flash(str(e), "danger")
            return render_template("login.html")
        session["login_email"] = email
        if eh_super_admin(email):
            admin = buscar_admin_plataforma(email)
            if admin and admin.get("senha") and admin.get("email_confirmado"):
                return redirect(url_for("login_senha"))
            return redirect(url_for("login_conectar_gmail"))
        escola = buscar_escola_por_email(email) or localizar_escola_do_email(email)
        if escola:
            if not escola.get("ativo", True):
                flash("Esta escola está pausada. O acesso de todos os usuários dessa escola está bloqueado.", "danger")
                return render_template("login.html")
            if not escola.get("senha_definida"):
                flash("Esta escola ainda precisa ativar o acesso. Use o link e o código da tela de cadastro de escolas.", "danger")
                return redirect(url_for("ativar_escola", token=escola.get("convite_token")))
            return redirect(url_for("login_senha"))
        flash("Este e-mail não está cadastrado. Escolas entram com o e-mail convite. O admin da plataforma é o Gmail principal.", "danger")
    return render_template("login.html")


@app.route("/login/conectar-gmail", methods=["GET", "POST"])
def login_conectar_gmail():
    garantir_plataforma()
    email = session.get("login_email") or email_super_admin()
    try:
        from urllib.parse import urlparse
        dsn = (_CFG.get("DATABASE_URL") or "").replace("postgresql://", "http://").replace("postgres://", "http://")
        postgres_host = urlparse(dsn).hostname or "nao definido"
    except Exception:
        postgres_host = "nao definido"
    if request.method == "POST":
        try:
            email = exigencia_email(request.form.get("smtp_user") or email, "E-mail")
            senha = (request.form.get("smtp_password") or "").replace(" ", "").strip()
            if not senha:
                raise ValueError("Informe a senha de app (16 letras) para o sistema enviar o código.")
            session["login_email"] = email
            try:
                salvar_smtp_plataforma("smtp.gmail.com", 587, email, senha, email)
            except Exception as e:
                detalhe = erro_conexao_atual() or str(e)
                raise RuntimeError(
                    f"Postgres não conectou ({detalhe}). "
                    "O site está usando o host: {postgres_host}. "
                    "No Render use Save and deploy (não só Save only) depois de colar a URI do pooler."
                ) from e
        except Exception as e:
            flash(str(e), "danger")
            return render_template("login_conectar_gmail.html", email=email, postgres_host=postgres_host)
        return _enviar_codigo_plataforma(email)
    return render_template("login_conectar_gmail.html", email=email, postgres_host=postgres_host)


@app.route("/login/google")
def login_google():
    if not _registrar_oauth():
        flash("Conecte o Gmail pelo Google para receber o código. Não use senha de app.", "danger")
        return redirect(url_for("login_conectar_gmail"))
    redirect_uri = url_for("login_google_callback", _external=True)
    return oauth.google.authorize_redirect(
        redirect_uri,
        access_type="offline",
        prompt="consent",
    )


@app.route("/login/google/callback")
def login_google_callback():
    try:
        if not _registrar_oauth():
            flash("Login Google não está pronto.", "danger")
            return redirect(url_for("login_conectar_gmail"))
        token = oauth.google.authorize_access_token()
        info = token.get("userinfo") or {}
        email = (info.get("email") or "").strip().lower()
        access_token = token.get("access_token")
        salvar_google_refresh(token.get("refresh_token"))
        session["google_access_token"] = access_token
    except Exception as e:
        flash(f"Não foi possível concluir o login Google: {e}", "danger")
        return redirect(url_for("login"))
    if not email_valido(email):
        flash("A conta Google não retornou um e-mail válido.", "danger")
        return redirect(url_for("login"))
    garantir_plataforma()
    session["login_email"] = email
    if eh_super_admin(email):
        admin = buscar_admin_plataforma(email)
        if admin and admin.get("senha") and admin.get("email_confirmado"):
            _entrar_plataforma(admin)
            return redirect(url_for("plataforma_escolas"))
        return _enviar_codigo_plataforma(email, access_token=access_token)
    escola = buscar_escola_por_email(email)
    if escola:
        if not escola.get("ativo", True):
            flash("Esta escola está pausada. O acesso está bloqueado.", "danger")
            return redirect(url_for("login"))
        if not escola.get("senha_definida"):
            return redirect(url_for("ativar_escola", token=escola.get("convite_token")))
        session["login_tipo"] = "escola"
        return redirect(url_for("login_senha"))
    escola = localizar_escola_do_email(email)
    if escola:
        session["login_tipo"] = "escola"
        return redirect(url_for("login_senha"))
    flash("Este e-mail Google não está cadastrado como escola nem como admin da plataforma.", "danger")
    return redirect(url_for("login"))


@app.route("/login/codigo", methods=["GET", "POST"])
def login_codigo():
    email = session.get("login_email")
    if not email:
        return redirect(url_for("login"))
    if request.method == "POST":
        codigo = (request.form.get("codigo") or "").strip()
        if validar_otp(email, codigo, "login_plataforma"):
            session["otp_ok"] = True
            session["login_tipo"] = "plataforma"
            session["redefinir_senha"] = True
            session.pop("otp_local", None)
            flash("Código confirmado. Agora defina a senha de acesso da plataforma.", "success")
            return redirect(url_for("login_senha"))
        flash("Código inválido ou vencido. Use os 6 dígitos mostrados na tela, não 000000.", "danger")
    return render_template(
        "login_codigo.html",
        email=email,
        codigo_local=session.get("otp_local"),
    )


@app.route("/login/senha", methods=["GET", "POST"])
def login_senha():
    email = session.get("login_email")
    if not email:
        return redirect(url_for("login"))
    criar = False
    if eh_super_admin(email):
        admin = buscar_admin_plataforma(email)
        criar = (not (admin and admin.get("senha"))) or bool(session.get("redefinir_senha"))
        if criar and not session.get("otp_ok"):
            flash("Confirme o código enviado ao e-mail antes de criar ou redefinir a senha.", "danger")
            return redirect(url_for("login_conectar_gmail"))
    escola = None if eh_super_admin(email) else (buscar_escola_por_email(email) or localizar_escola_do_email(email))
    if request.method == "POST":
        senha = (request.form.get("senha") or "").strip()
        senha2 = (request.form.get("senha2") or "").strip()
        if criar:
            if senha != senha2:
                flash("As senhas não coincidem.", "danger")
                return render_template("login_senha.html", email=email, criar=True)
            if len(senha) < 6:
                flash("A senha deve ter pelo menos 6 caracteres.", "danger")
                return render_template("login_senha.html", email=email, criar=True)
            admin = salvar_senha_plataforma(email, senha)
            session.pop("otp_ok", None)
            session.pop("redefinir_senha", None)
            _entrar_plataforma(admin)
            return redirect(url_for("plataforma_escolas"))
        if eh_super_admin(email):
            admin = buscar_admin_plataforma(email)
            armazenada = (admin.get("senha") if admin else "") or ""
            if admin and armazenada.strip() == senha:
                _entrar_plataforma(admin)
                return redirect(url_for("plataforma_escolas"))
            flash("Senha incorreta. Use a senha que você criou neste sistema (não a do Gmail e não 123456, a menos que tenha escolhido essa).", "danger")
        elif escola:
            if not escola.get("ativo", True):
                flash("Esta escola está pausada. O acesso está bloqueado.", "danger")
                return redirect(url_for("login"))
            usuario, escola = usuario_da_escola(email, senha, escola)
            if usuario:
                _entrar_escola(usuario, email, escola)
                return redirect(url_for("dashboard"))
            flash("Senha incorreta.", "danger")
        else:
            flash("E-mail ou senha incorretos.", "danger")
    return render_template("login_senha.html", email=email, criar=criar)


def _enviar_convite_escola(escola):
    link = url_for("ativar_escola", token=escola["convite_token"], _external=True)
    codigo = escola.get("convite_codigo") or ""
    nome = escola["nome"]
    corpo = (
        f"Olá,\n\n"
        f"A escola {nome} foi cadastrada na Gestão Escolar.\n\n"
        f"Seu código é: {codigo}\n\n"
        f"Abra o link abaixo e digite só esse código:\n{link}\n\n"
        f"Na página você escolhe a senha de entrada. O sistema não gera senha.\n"
    )
    html = (
        f"<p>Olá,</p>"
        f"<p>A escola <strong>{nome}</strong> foi cadastrada na Gestão Escolar.</p>"
        f"<p>Seu código é:</p>"
        f"<p style='font-size:28px;letter-spacing:6px;font-weight:700'>{codigo}</p>"
        f"<p><a href='{link}'>Abrir página de ativação</a></p>"
        f"<p>Na página você escolhe a senha com que vai entrar. Nenhuma senha é gerada pelo sistema.</p>"
    )
    ok, erro = enviar_codigo(
        escola["email_admin"],
        codigo,
        f"Código de acesso da escola {nome}",
        corpo,
        html=html,
        access_token=session.get("google_access_token"),
    )
    return ok, erro, link


@app.route("/plataforma/autorizar-gmail")
def plataforma_autorizar_gmail():
    if not session.get("super_admin"):
        return redirect(url_for("login"))
    if not _registrar_oauth():
        flash("Para enviar e-mail pelo Google, o envio ainda precisa ser autorizado na conta da plataforma.", "danger")
        return redirect(url_for("plataforma_escolas"))
    redirect_uri = url_for("login_google_callback", _external=True)
    return oauth.google.authorize_redirect(
        redirect_uri,
        access_type="offline",
        prompt="consent",
    )


@app.route("/plataforma/escolas", methods=["GET", "POST"])
def plataforma_escolas():
    garantir_plataforma()
    if not session.get("super_admin"):
        return redirect(url_for("login"))
    if request.method == "POST":
        acao = request.form.get("acao")
        conexao = obter_conexao(master=True)
        if acao in {"salvar_smtp", "salvar_smtp_e_enviar"}:
            try:
                senha_app = (request.form.get("smtp_password") or "").strip()
                if acao == "salvar_smtp_e_enviar" and not senha_app:
                    raise ValueError("Cole a senha de app de 16 letras para o Gmail enviar o código.")
                salvar_smtp_plataforma(
                    "smtp.gmail.com",
                    request.form.get("smtp_port") or 587,
                    request.form.get("smtp_user"),
                    senha_app,
                    request.form.get("smtp_from") or request.form.get("smtp_user"),
                )
                if acao == "salvar_smtp_e_enviar":
                    enviados = []
                    falhas = []
                    for escola in listar_escolas():
                        if not escola.get("ativo", True) or escola.get("senha_definida") or not escola.get("convite_token"):
                            continue
                        ok, erro, _link = _enviar_convite_escola(escola)
                        if ok:
                            enviados.append(escola["email_admin"])
                        else:
                            falhas.append(f"{escola['email_admin']}: {erro}")
                    if enviados and not falhas:
                        flash(
                            "Código enviado para: " + ", ".join(enviados) + ". Abra essa caixa (e o Spam).",
                            "success",
                        )
                    elif enviados:
                        flash(
                            "Enviado para " + ", ".join(enviados) + ". Falhou: " + " | ".join(falhas),
                            "danger",
                        )
                    elif falhas:
                        flash("O Gmail não enviou: " + " | ".join(falhas), "danger")
                    else:
                        flash("SMTP salvo. Não há escola aguardando convite.", "success")
                else:
                    flash("SMTP da plataforma salvo.", "success")
            except Exception as e:
                flash(f"Não foi possível salvar o SMTP: {e}", "danger")
            if conexao:
                conexao.close()
        elif acao == "criar_escola":
            try:
                email_novo = request.form.get("email_admin")
                if request.form.get("recadastrar") and buscar_escola_por_email(email_novo):
                    antiga = buscar_escola_por_email(email_novo)
                    excluir_escola(antiga["id"])
                escola = cadastrar_escola(request.form.get("nome"), email_novo)
                ok, erro, link = _enviar_convite_escola(escola)
                if erro:
                    flash(
                        f"Escola criada, mas o e-mail ainda não saiu para {escola['email_admin']}. "
                        f"Clique em Permitir envio de e-mail e depois em Reenviar e-mail. ({erro})",
                        "danger",
                    )
                else:
                    flash(
                        f"E-mail com o código enviado para {escola['email_admin']}. Abra a caixa de entrada e o Spam.",
                        "success",
                    )
            except Exception as e:
                flash(f"Não foi possível cadastrar a escola: {e}", "danger")
        elif acao == "reenviar_convite":
            token = request.form.get("token")
            escola = buscar_escola_por_token(token)
            if not escola:
                flash("Escola não encontrada.", "danger")
            else:
                ok, erro, link = _enviar_convite_escola(escola)
                if erro:
                    flash(f"O e-mail não chegou em {escola['email_admin']} ({erro}).", "danger")
                else:
                    flash(f"E-mail com o código enviado para {escola['email_admin']}.", "success")
        elif acao == "alterar_email":
            try:
                escola = atualizar_email_admin_escola(
                    request.form.get("token"),
                    request.form.get("email_admin"),
                )
                ok, erro, link = _enviar_convite_escola(escola)
                if erro:
                    flash(
                        f"E-mail atualizado para {escola['email_admin']}, mas o envio falhou ({erro}). "
                        f"Link: {link} — código {escola['convite_codigo']}",
                        "danger",
                    )
                else:
                    flash(f"Código enviado para {escola['email_admin']}.", "success")
            except Exception as e:
                flash(f"Não foi possível alterar o e-mail: {e}", "danger")
        elif acao == "pausar_escola":
            try:
                escola = definir_status_escola(request.form.get("escola_id"), False)
                flash(
                    f"Escola {escola['nome']} pausada. Login e todo o sistema dessa escola estão bloqueados até retomar.",
                    "success",
                )
            except Exception as e:
                flash(f"Não foi possível pausar: {e}", "danger")
        elif acao == "retomar_escola":
            try:
                escola = definir_status_escola(request.form.get("escola_id"), True)
                flash(f"Escola {escola['nome']} retomada. O acesso voltou a funcionar.", "success")
            except Exception as e:
                flash(f"Não foi possível retomar: {e}", "danger")
        elif acao == "excluir_escola":
            try:
                escola = excluir_escola(request.form.get("escola_id"))
                flash(f"Escola {escola['nome']} excluída. O banco e o acesso foram removidos.", "success")
            except Exception as e:
                flash(f"Não foi possível excluir: {e}", "danger")
        elif acao == "redefinir_senha":
            try:
                escola = regenerar_convite_escola(request.form.get("escola_id"))
                ok, erro, link = _enviar_convite_escola(escola)
                if erro:
                    flash(
                        f"Senha da escola {escola['nome']} foi invalidada. Código: {escola['convite_codigo']}. "
                        f"O e-mail não saiu ({erro}). Link: {link}",
                        "danger",
                    )
                else:
                    flash(
                        f"Código para nova senha enviado a {escola['email_admin']}. "
                        f"A senha antiga deixa de valer.",
                        "success",
                    )
            except Exception as e:
                flash(f"Não foi possível redefinir a senha: {e}", "danger")
        elif acao == "acessar_escola":
            try:
                escola = buscar_escola_por_id(request.form.get("escola_id"))
                if not escola:
                    raise ValueError("Escola não encontrada.")
                if not escola.get("ativo", True):
                    raise ValueError("Retome a escola antes de acessar os dados.")
                plataforma_email = session.get("usuario_email") or email_super_admin()
                usuario = _usuario_admin_escola(escola)
                _entrar_escola(
                    usuario,
                    escola["email_admin"],
                    escola,
                    origem_plataforma=True,
                    plataforma_email=plataforma_email,
                )
                flash(f"Você está nos dados da escola {escola['nome']}.", "success")
                return redirect(url_for("dashboard"))
            except Exception as e:
                flash(f"Não foi possível abrir a escola: {e}", "danger")
        return redirect(url_for("plataforma_escolas"))
    smtp = {}
    conexao = obter_conexao(master=True)
    if conexao:
        try:
            with conexao.cursor() as cursor:
                cursor.execute("SELECT * FROM plataforma_smtp WHERE id = 1")
                smtp = cursor.fetchone() or {}
        finally:
            conexao.close()
    return render_template(
        "plataforma_escolas.html",
        escolas=listar_escolas(),
        smtp=smtp,
        google_login=_google_habilitado(),
    )


@app.route("/plataforma/voltar")
def plataforma_voltar():
    email = session.get("plataforma_email") or email_super_admin()
    if not session.get("origem_plataforma") and not session.get("super_admin"):
        return redirect(url_for("login"))
    admin = buscar_admin_plataforma(email)
    if not admin:
        flash("Não foi possível voltar à plataforma.", "danger")
        return redirect(url_for("login"))
    _entrar_plataforma(admin)
    return redirect(url_for("plataforma_escolas"))


@app.route("/escola/ativar/<token>", methods=["GET", "POST"])
def ativar_escola(token):
    escola = buscar_escola_por_token(token)
    if not escola:
        flash("Convite inválido.", "danger")
        return redirect(url_for("login"))
    if not escola.get("ativo", True):
        flash("Esta escola está pausada. O convite e o sistema estão bloqueados.", "danger")
        return redirect(url_for("login"))
    if request.method == "POST":
        codigo = (request.form.get("codigo") or "").strip()
        senha = (request.form.get("senha") or "").strip()
        senha2 = (request.form.get("senha2") or "").strip()
        if codigo != (escola.get("convite_codigo") or ""):
            flash("Código inválido.", "danger")
        elif senha != senha2:
            flash("As senhas não coincidem.", "danger")
        else:
            try:
                concluir_ativacao_escola(escola, senha)
                flash("Senha criada. Entre com o e-mail da escola.", "success")
                session["login_email"] = escola["email_admin"]
                return redirect(url_for("login_senha"))
            except Exception as e:
                flash(str(e), "danger")
    return render_template("ativar_escola.html", escola=escola)


@app.route("/logout")
def logout():
    session.clear()
    flash("Você saiu da sua conta com sucesso.", "success")
    return redirect(url_for("login"))


@app.route("/usuarios/gerenciar", methods=["GET", "POST"])
def gerenciar_usuarios():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    if session.get("usuario_papel") != "admin" and not pode_modulo(session.get("usuario_papel"), "usuarios"):
        flash("Acesso negado. Area restrita para administradores.", "danger")
        return redirect(url_for("dashboard"))

    garantir_tabelas_folha()
    conexao = obter_conexao()

    if request.method == "POST":
        acao = request.form.get("acao") or "salvar"
        if conexao:
            try:
                with conexao.cursor() as cursor:
                    if acao == "excluir":
                        uid = request.form.get("usuario_id", type=int)
                        if uid:
                            cursor.execute("UPDATE funcionarios SET usuario_id = NULL WHERE usuario_id = %s", (uid,))
                            cursor.execute("DELETE FROM usuarios WHERE id = %s", (uid,))
                            conexao.commit()
                            flash("Usuário de acesso removido. O cadastro de folha foi mantido.", "success")
                        return redirect(url_for("gerenciar_usuarios"))

                    nome = limpar_campo("nome")
                    email = limpar_campo("email")
                    senha = (request.form.get("senha") or "").strip()
                    papel = normalizar_papel(limpar_campo("papel") or "funcionario")
                    uid = request.form.get("usuario_id", type=int)
                    fid = request.form.get("funcionario_id", type=int)
                    if not nome or not email:
                        raise ValueError("Informe nome e e-mail.")
                    exigencia_email(email, "E-mail do colaborador")

                    if uid:
                        if senha:
                            cursor.execute(
                                "UPDATE usuarios SET nome = %s, email = %s, senha = %s, papel = %s WHERE id = %s",
                                (nome, email, senha, papel, uid),
                            )
                        else:
                            cursor.execute(
                                "UPDATE usuarios SET nome = %s, email = %s, papel = %s WHERE id = %s",
                                (nome, email, papel, uid),
                            )
                    else:
                        if not senha:
                            raise ValueError("Informe a senha do primeiro acesso.")
                        cursor.execute(
                            """
                            INSERT INTO usuarios (nome, email, senha, papel)
                            VALUES (%s, %s, %s, %s)
                            RETURNING id
                            """,
                            (nome, email, senha, papel),
                        )
                        uid = cursor.fetchone()["id"]

                    cargo = limpar_campo("cargo") or _cargo_do_papel(papel)
                    cpf = limpar_campo("cpf") or _cpf_provisorio(email)
                    telefone = limpar_campo("telefone") or "(00) 00000-0000"
                    nasc = limpar_campo("data_nascimento") or "2000-01-01"
                    ativo = request.form.get("ativo", "1") != "0"
                    if not fid:
                        cursor.execute(
                            """
                            SELECT id FROM funcionarios
                            WHERE usuario_id = %s OR LOWER(COALESCE(email, '')) = LOWER(%s)
                            ORDER BY CASE WHEN usuario_id = %s THEN 0 ELSE 1 END
                            LIMIT 1
                            """,
                            (uid, email, uid),
                        )
                        existente = cursor.fetchone()
                        if existente:
                            fid = existente["id"]

                    valores_folha = (
                        nome, cpf, nasc, cargo, telefone, email,
                        limpar_campo("especialidade"), limpar_campo("formacao"),
                        limpar_campo("rg"), limpar_campo("cep"), limpar_campo("rua"),
                        limpar_campo("numero"), limpar_campo("bairro"), limpar_campo("cidade"),
                        (limpar_campo("estado") or "")[:2] or None,
                        limpar_campo("banco"), limpar_campo("agencia"), limpar_campo("conta"),
                        limpar_campo("tipo_conta"), limpar_campo("pix"), limpar_campo("pis_nit"),
                        limpar_campo("cnpj"),
                        _float_form("salario"), request.form.get("tipo_contrato") or "clt_mensalista",
                        _float_form("valor_hora"), _float_form("horas_mes"),
                        request.form.get("reter_federal") == "1",
                        request.form.get("reter_iss") == "1",
                        _float_form("aliquota_iss", 5.0),
                        limpar_campo("data_contratacao") or datetime.now().strftime("%Y-%m-%d"),
                        ativo, uid,
                    )
                    if fid:
                        cursor.execute(
                            """
                            UPDATE funcionarios SET
                                nome_completo = %s, cpf = %s, data_nascimento = %s, cargo = %s,
                                telefone = %s, email = %s, especialidade = %s, formacao = %s,
                                rg = %s, cep = %s, rua = %s, numero = %s, bairro = %s, cidade = %s, estado = %s,
                                banco = %s, agencia = %s, conta = %s, tipo_conta = %s, pix = %s, pis_nit = %s, cnpj = %s,
                                salario = %s, tipo_contrato = %s, valor_hora = %s, horas_mes = %s,
                                reter_federal = %s, reter_iss = %s, aliquota_iss = %s,
                                data_contratacao = COALESCE(%s::date, data_contratacao),
                                ativo = %s, usuario_id = %s
                            WHERE id = %s
                            """,
                            valores_folha + (fid,),
                        )
                    else:
                        cursor.execute(
                            """
                            INSERT INTO funcionarios (
                                nome_completo, cpf, data_nascimento, cargo, telefone, email,
                                especialidade, formacao, rg, cep, rua, numero, bairro, cidade, estado,
                                banco, agencia, conta, tipo_conta, pix, pis_nit, cnpj,
                                salario, tipo_contrato, valor_hora, horas_mes,
                                reter_federal, reter_iss, aliquota_iss, data_contratacao, ativo, usuario_id
                            ) VALUES (
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                            )
                            RETURNING id
                            """,
                            valores_folha,
                        )
                        fid = cursor.fetchone()["id"]
                    conexao.commit()
                    flash("Cadastro de usuário e folha salvo.", "success")
                    return redirect(url_for("gerenciar_usuarios", uid=uid))
            except Exception as e:
                conexao.rollback()
                flash(f"Erro ao salvar usuário: {e}", "danger")
            finally:
                if conexao:
                    conexao.close()
        return redirect(url_for("gerenciar_usuarios"))

    usuarios_cadastrados = []
    sem_login = []
    cadastro = {
        "usuario_id": None,
        "funcionario_id": None,
        "nome": "",
        "email": "",
        "papel": "professor",
        "ativo": True,
        "tipo_contrato": "clt_mensalista",
        "salario": 0,
        "valor_hora": 0,
        "horas_mes": 0,
        "aliquota_iss": 5,
        "reter_federal": False,
        "reter_iss": False,
    }
    uid = request.args.get("uid", type=int)
    fid = request.args.get("fid", type=int)
    busca_u = request.args.get("q", "").strip()
    preview_folha = None
    regime_folha = "simples_nacional"

    if conexao:
        try:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT u.id, u.nome, u.email, u.papel,
                           f.id AS funcionario_id, f.cpf, f.cargo, f.telefone,
                           f.tipo_contrato, f.salario, f.ativo
                    FROM usuarios u
                    LEFT JOIN LATERAL (
                        SELECT * FROM funcionarios
                        WHERE usuario_id = u.id OR LOWER(COALESCE(email, '')) = LOWER(u.email)
                        ORDER BY CASE WHEN usuario_id = u.id THEN 0 ELSE 1 END
                        LIMIT 1
                    ) f ON TRUE
                    ORDER BY u.nome ASC
                    """
                )
                usuarios_cadastrados = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT f.id AS funcionario_id, f.nome_completo AS nome, f.email, f.cargo,
                           f.cpf, f.telefone, f.tipo_contrato, f.salario, f.ativo
                    FROM funcionarios f
                    WHERE NOT EXISTS (
                        SELECT 1 FROM usuarios u
                        WHERE u.id = f.usuario_id OR LOWER(COALESCE(u.email, '')) = LOWER(COALESCE(f.email, ''))
                    )
                    ORDER BY f.nome_completo
                    """
                )
                sem_login = cursor.fetchall()

                alvo = None
                if uid:
                    cursor.execute("SELECT * FROM usuarios WHERE id = %s", (uid,))
                    urow = cursor.fetchone() or {}
                    cursor.execute(
                        """
                        SELECT * FROM funcionarios
                        WHERE usuario_id = %s OR LOWER(COALESCE(email, '')) = LOWER(%s)
                        ORDER BY CASE WHEN usuario_id = %s THEN 0 ELSE 1 END
                        LIMIT 1
                        """,
                        (uid, urow.get("email") or "", uid),
                    )
                    frow = cursor.fetchone() or {}
                    alvo = (urow, frow)
                elif fid:
                    cursor.execute("SELECT * FROM funcionarios WHERE id = %s", (fid,))
                    frow = cursor.fetchone() or {}
                    cursor.execute(
                        "SELECT * FROM usuarios WHERE id = %s OR LOWER(email) = LOWER(%s) LIMIT 1",
                        (frow.get("usuario_id"), frow.get("email") or ""),
                    )
                    urow = cursor.fetchone() or {}
                    alvo = (urow, frow)
                if alvo:
                    urow, frow = alvo
                    cadastro = {
                        "usuario_id": urow.get("id"),
                        "funcionario_id": frow.get("id"),
                        "nome": urow.get("nome") or frow.get("nome_completo") or "",
                        "email": urow.get("email") or frow.get("email") or "",
                        "papel": normalizar_papel(urow.get("papel") or "funcionario"),
                        "cpf": frow.get("cpf") or "",
                        "rg": frow.get("rg") or "",
                        "data_nascimento": _data_iso(frow.get("data_nascimento")),
                        "telefone": frow.get("telefone") or "",
                        "cargo": frow.get("cargo") or _cargo_do_papel(urow.get("papel")),
                        "especialidade": frow.get("especialidade") or "",
                        "formacao": frow.get("formacao") or "",
                        "cep": frow.get("cep") or "",
                        "rua": frow.get("rua") or "",
                        "numero": frow.get("numero") or "",
                        "bairro": frow.get("bairro") or "",
                        "cidade": frow.get("cidade") or "",
                        "estado": frow.get("estado") or "",
                        "banco": frow.get("banco") or "",
                        "agencia": frow.get("agencia") or "",
                        "conta": frow.get("conta") or "",
                        "tipo_conta": frow.get("tipo_conta") or "",
                        "pix": frow.get("pix") or "",
                        "pis_nit": frow.get("pis_nit") or "",
                        "cnpj": frow.get("cnpj") or "",
                        "tipo_contrato": frow.get("tipo_contrato") or "clt_mensalista",
                        "salario": frow.get("salario") or 0,
                        "valor_hora": frow.get("valor_hora") or 0,
                        "horas_mes": frow.get("horas_mes") or 0,
                        "reter_federal": bool(frow.get("reter_federal")),
                        "reter_iss": bool(frow.get("reter_iss")),
                        "aliquota_iss": frow.get("aliquota_iss") or 5,
                        "data_contratacao": _data_iso(frow.get("data_contratacao")),
                        "ativo": True if frow.get("ativo") is None else bool(frow.get("ativo")),
                    }
                    cursor.execute("SELECT regime_tributario FROM configuracoes WHERE id = 1")
                    cfg_folha = cursor.fetchone() or {}
                    regime_folha = cfg_folha.get("regime_tributario") or regime_folha
                    if frow.get("id"):
                        agora = datetime.now()
                        preview_folha = calcular_folha_pessoa(dict(frow), regime_folha, agora.year, agora.month)
                        preview_folha["rotulo_contrato"] = rotulo_contrato(preview_folha["tipo_contrato"])
        except Exception as e:
            _log(f"Erro ao listar usuários: {e}")
        finally:
            conexao.close()

    if busca_u:
        termo = busca_u.lower()
        usuarios_cadastrados = [
            u for u in usuarios_cadastrados
            if termo in (u.get("nome") or "").lower() or termo in (u.get("email") or "").lower()
            or termo in (u.get("cargo") or "").lower()
        ]
        sem_login = [
            u for u in sem_login
            if termo in (u.get("nome") or "").lower() or termo in (u.get("email") or "").lower()
        ]

    return render_template(
        "gerenciar_usuarios.html",
        usuarios=usuarios_cadastrados,
        sem_login=sem_login,
        cadastro=cadastro,
        busca_u=busca_u,
        rotulo_contrato=rotulo_contrato,
        nome_do_papel=rotulo_papel,
        preview_folha=preview_folha,
        regime_folha=regime_folha,
    )


@app.route("/dashboard")
def dashboard():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    metrics = {"total_alunos": 0, "total_professores": 0, "total_turmas": 0, "total_usuarios": 0, "total_funcionarios": 0}

    conexao = obter_conexao()
    if conexao:
        try:
            with conexao.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*) AS total FROM alunos
                    WHERE COALESCE(NULLIF(status, ''), situacao::text, 'ativo') ILIKE 'ativo'
                    """
                )
                metrics["total_alunos"] = _contar(cursor.fetchone())
        except Exception as e:
            conexao.rollback()
            try:
                with conexao.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) AS total FROM alunos WHERE situacao = 'ativo'")
                    metrics["total_alunos"] = _contar(cursor.fetchone())
            except Exception:
                conexao.rollback()
                try:
                    with conexao.cursor() as cursor:
                        cursor.execute("SELECT COUNT(*) AS total FROM alunos")
                        metrics["total_alunos"] = _contar(cursor.fetchone())
                except Exception as e2:
                    conexao.rollback()
                    _log(f"Erro dashboard alunos: {e}; {e2}")
        try:
            with conexao.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*) AS total FROM funcionarios
                    WHERE LOWER(COALESCE(cargo, '')) LIKE '%professor%' AND COALESCE(ativo, TRUE) = TRUE
                    """
                )
                metrics["total_professores"] = _contar(cursor.fetchone())
                cursor.execute("SELECT COUNT(*) AS total FROM turmas")
                metrics["total_turmas"] = _contar(cursor.fetchone())
                cursor.execute("SELECT COUNT(*) AS total FROM usuarios")
                metrics["total_usuarios"] = _contar(cursor.fetchone())
                cursor.execute("SELECT COUNT(*) AS total FROM funcionarios WHERE COALESCE(ativo, TRUE) = TRUE")
                metrics["total_funcionarios"] = _contar(cursor.fetchone())
        except Exception as e:
            conexao.rollback()
            _log(f"Erro ao consultar dashboard: {e}")
        finally:
            conexao.close()

    return render_template("dashboard.html", metrics=metrics)


@app.route('/calendario_escolar', methods=['GET', 'POST'])
def calendario_escolar():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    garantir_tabelas_pedagogicas()
    visao_req = (request.args.get("visao") or request.form.get("visao") or "").strip()
    busca_aluno = (request.args.get("busca_aluno") or request.form.get("busca_aluno") or "").strip()
    contexto_aluno_id = request.values.get("aluno_id", type=int)
    contexto_turma_id = request.values.get("turma_id", type=int)
    if not contexto_aluno_id:
        contexto_aluno_id = request.form.get("aluno_id", type=int)
    if not contexto_turma_id:
        contexto_turma_id = request.form.get("turma_id", type=int)
    if visao_req == "geral":
        contexto_aluno_id = None
        contexto_turma_id = None
    elif visao_req == "turma":
        contexto_aluno_id = None
    elif visao_req == "aluno":
        contexto_turma_id = None

    if request.method == 'POST':
        acao = request.form.get("acao") or "criar_evento"
        conexao = obter_conexao()
        if conexao:
            try:
                with conexao.cursor() as cursor:
                    if acao == "marcar_frequencia":
                        data_aula = request.form.get("data_aula")
                        turma_id = request.form.get("turma_id") or None
                        if turma_id in ("", "None"):
                            turma_id = None
                        lancamentos = []
                        aluno_unico = request.form.get("aluno_id")
                        if aluno_unico and aluno_unico not in ("", "None"):
                            lancamentos.append((aluno_unico, request.form.get("status") or "presente"))
                        for chave, valor in request.form.items():
                            if chave.startswith("status_"):
                                aluno_freq = chave.replace("status_", "", 1)
                                if aluno_freq.isdigit():
                                    lancamentos.append((aluno_freq, valor or "presente"))
                        if not data_aula:
                            raise ValueError("Selecione o dia da aula.")
                        if not lancamentos:
                            raise ValueError("Nenhum aluno para lançar presença.")
                        for aluno_freq, status in lancamentos:
                            _lancar_frequencia_materias(
                                cursor,
                                aluno_freq,
                                turma_id,
                                data_aula,
                                status,
                                request.form.get("disciplina") or "",
                            )
                        conexao.commit()
                        flash("✅ Frequência registrada.", "success")
                    else:
                        titulo = limpar_campo('titulo')
                        descricao = limpar_campo('descricao')
                        data_evento = limpar_campo('data_evento')
                        tipo = limpar_campo('tipo') or 'geral'
                        turma_id = request.form.get('turma_id') or None
                        if turma_id in ("", "None"):
                            turma_id = None
                        professor_id = request.form.get('professor_id') or None
                        aluno_id = request.form.get('aluno_id') or None
                        horario = request.form.get('horario') or None
                        if horario in ("", "None"):
                            horario = None
                        cursor.execute(
                            '''
                            INSERT INTO calendario_eventos (titulo, descricao, data_evento, tipo, turma_id, professor_id, aluno_id, horario)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            ''',
                            (titulo, descricao, data_evento, tipo, turma_id, professor_id, aluno_id, horario),
                        )
                        if tipo == "prova" and data_evento:
                            cursor.execute(
                                """
                                INSERT INTO provas_turma (turma_id, materia, titulo, descricao, data_prova, horario)
                                VALUES (%s, %s, %s, %s, %s, %s)
                                """,
                                (turma_id, limpar_campo("materia_prova"), titulo, descricao, data_evento, horario),
                            )
                        conexao.commit()
                        flash("✅ Evento adicionado ao calendário da escola.", "success")
            except Exception as e:
                conexao.rollback()
                flash(f"❌ Erro ao salvar: {e}", "danger")
            finally:
                conexao.close()

        kwargs = {}
        if visao_req:
            kwargs["visao"] = visao_req
        if busca_aluno:
            kwargs["busca_aluno"] = busca_aluno
        if contexto_aluno_id:
            kwargs["aluno_id"] = contexto_aluno_id
        if contexto_turma_id:
            kwargs["turma_id"] = contexto_turma_id
        data_aula = request.form.get("data_aula")
        if data_aula:
            kwargs["dia"] = data_aula
            try:
                data_ref = datetime.strptime(data_aula[:10], "%Y-%m-%d")
                kwargs["mes"] = data_ref.month
                kwargs["ano"] = data_ref.year
            except ValueError:
                pass
        return redirect(url_for("calendario_escolar", **kwargs))

    ano = request.args.get("ano", type=int) or datetime.now().year
    mes = request.args.get("mes", type=int) or datetime.now().month
    dia_sel = request.args.get("dia") or request.form.get("data_aula")

    cal = calendario_lib.Calendar(firstweekday=6)
    dias_do_mes = cal.monthdatescalendar(ano, mes)
    nomes_meses = {
        1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
        5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
        9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
    }
    nome_mes_atual = f"{nomes_meses.get(mes, 'Mês')} {ano}"
    mes_anterior = mes - 1 if mes > 1 else 12
    ano_anterior = ano if mes > 1 else ano - 1
    mes_proximo = mes + 1 if mes < 12 else 1
    ano_proximo = ano if mes < 12 else ano + 1

    turmas, professores, alunos, eventos = [], [], [], []
    contexto_aluno = contexto_turma = None
    frequencia_mes = {}
    lista_frequencia_dia = []
    frequencia_aluno_dia = None
    provas_mes = []
    alunos_busca = []
    turmas_do_aluno = set()

    conexao = obter_conexao()
    if conexao:
        try:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT id, nome FROM turmas ORDER BY nome ASC")
                turmas = cursor.fetchall()
                cursor.execute(
                    "SELECT id, nome_completo FROM funcionarios WHERE LOWER(cargo) LIKE '%professor%' AND ativo = TRUE ORDER BY nome_completo"
                )
                professores = cursor.fetchall()
                cursor.execute("SELECT id, nome_completo, matricula, cpf FROM alunos ORDER BY nome_completo")
                alunos = cursor.fetchall()

                if busca_aluno and not contexto_aluno_id and visao_req in ("", "aluno"):
                    digits = "".join(ch for ch in busca_aluno if ch.isdigit())
                    cursor.execute(
                        """
                        SELECT id, nome_completo, matricula, cpf
                        FROM alunos
                        WHERE matricula ILIKE %s
                           OR cpf ILIKE %s
                           OR regexp_replace(COALESCE(cpf, ''), '[^0-9]', '', 'g') LIKE %s
                        ORDER BY nome_completo
                        LIMIT 8
                        """,
                        (f"%{busca_aluno}%", f"%{busca_aluno}%", f"%{digits or busca_aluno}%"),
                    )
                    alunos_busca = cursor.fetchall()
                    if len(alunos_busca) == 1:
                        contexto_aluno_id = alunos_busca[0]["id"]
                        alunos_busca = []
                    elif not alunos_busca:
                        flash("❌ Nenhum aluno encontrado com essa matrícula ou CPF.", "danger")

                cursor.execute(
                    """
                    SELECT c.*, t.nome as turma_nome, f.nome_completo as professor_nome, a.nome_completo as aluno_nome
                    FROM calendario_eventos c
                    LEFT JOIN turmas t ON c.turma_id = t.id
                    LEFT JOIN funcionarios f ON c.professor_id = f.id
                    LEFT JOIN alunos a ON c.aluno_id = a.id
                    WHERE COALESCE(c.tipo, 'geral') <> 'aluno_vinculado_turma'
                    ORDER BY c.data_evento ASC
                    """
                )
                eventos = cursor.fetchall()

                if contexto_aluno_id:
                    cursor.execute("SELECT id, nome_completo, matricula, cpf FROM alunos WHERE id = %s", (contexto_aluno_id,))
                    contexto_aluno = cursor.fetchone()
                    cursor.execute("SELECT turma_id FROM turma_alunos WHERE aluno_id = %s", (contexto_aluno_id,))
                    turmas_do_aluno = {row["turma_id"] for row in cursor.fetchall()}
                    cursor.execute(
                        """
                        SELECT data_aula, status FROM frequencia
                        WHERE aluno_id = %s AND EXTRACT(MONTH FROM data_aula) = %s AND EXTRACT(YEAR FROM data_aula) = %s
                        """,
                        (contexto_aluno_id, mes, ano),
                    )
                    for row in cursor.fetchall():
                        frequencia_mes[row["data_aula"].isoformat()] = row["status"]
                    if dia_sel:
                        cursor.execute(
                            "SELECT * FROM frequencia WHERE aluno_id = %s AND data_aula = %s",
                            (contexto_aluno_id, dia_sel),
                        )
                        frequencia_aluno_dia = cursor.fetchone()

                if contexto_turma_id:
                    cursor.execute("SELECT id, nome FROM turmas WHERE id = %s", (contexto_turma_id,))
                    contexto_turma = cursor.fetchone()
                    if dia_sel:
                        cursor.execute(
                            """
                            SELECT a.id, a.nome_completo, a.matricula, f.status
                            FROM turma_alunos ta
                            JOIN alunos a ON a.id = ta.aluno_id
                            LEFT JOIN frequencia f ON f.aluno_id = a.id AND f.data_aula = %s
                            WHERE ta.turma_id = %s
                            ORDER BY a.nome_completo
                            """,
                            (dia_sel, contexto_turma_id),
                        )
                        lista_frequencia_dia = cursor.fetchall()

                cursor.execute(
                    """
                    SELECT p.*, t.nome AS turma_nome
                    FROM provas_turma p
                    LEFT JOIN turmas t ON t.id = p.turma_id
                    WHERE EXTRACT(MONTH FROM p.data_prova) = %s AND EXTRACT(YEAR FROM p.data_prova) = %s
                    ORDER BY p.data_prova, p.horario NULLS LAST
                    """,
                    (mes, ano),
                )
                provas_mes = cursor.fetchall()
        finally:
            conexao.close()

    visao = visao_req or (
        "aluno" if contexto_aluno_id else "turma" if contexto_turma_id else "geral"
    )

    def _serve_evento(item, campo_turma="turma_id"):
        tid = item.get(campo_turma)
        if visao == "turma":
            return not tid or tid == contexto_turma_id
        if visao == "aluno":
            return not tid or tid in turmas_do_aluno
        return True

    eventos = [ev for ev in eventos if _serve_evento(ev)]
    provas_mes = [pv for pv in provas_mes if _serve_evento(pv)]

    eventos_por_dia = {}
    for ev in eventos:
        data_ev = ev.get("data_evento")
        if not data_ev:
            continue
        if hasattr(data_ev, "isoformat"):
            chave = data_ev.isoformat()[:10]
        else:
            chave = str(data_ev)[:10]
        eventos_por_dia.setdefault(chave, []).append(ev)

    provas_por_dia = {}
    for pv in provas_mes:
        data_pv = pv.get("data_prova")
        if not data_pv:
            continue
        chave = data_pv.isoformat()[:10] if hasattr(data_pv, "isoformat") else str(data_pv)[:10]
        provas_por_dia.setdefault(chave, []).append(pv)

    eventos_do_dia = eventos_por_dia.get(dia_sel, []) if dia_sel else []
    provas_do_dia = provas_por_dia.get(dia_sel, []) if dia_sel else []
    if contexto_turma_id:
        provas_do_dia = [
            p for p in provas_do_dia
            if not p.get("turma_id") or p.get("turma_id") == contexto_turma_id
        ]
    provas_unicas = []
    chaves_prova = set()
    for item in list(provas_do_dia) + [
        {
            "titulo": ev.get("titulo"),
            "materia": None,
            "horario": ev.get("horario"),
            "turma_nome": ev.get("turma_nome"),
            "descricao": ev.get("descricao"),
            "turma_id": ev.get("turma_id"),
        }
        for ev in eventos_do_dia
        if (ev.get("tipo") or "") == "prova"
    ]:
        chave = (
            (item.get("titulo") or "").strip().lower(),
            str(item.get("horario") or ""),
            item.get("turma_id"),
        )
        if chave in chaves_prova:
            continue
        chaves_prova.add(chave)
        provas_unicas.append(item)
    provas_do_dia = provas_unicas
    dia_feriado = any((ev.get("tipo") or "") == "feriado" for ev in eventos_do_dia)
    dia_normal = bool(dia_sel) and not dia_feriado

    modo_presenca = bool(contexto_aluno_id or contexto_turma_id)
    cal_params = {"visao": visao}
    if busca_aluno:
        cal_params["busca_aluno"] = busca_aluno
    if contexto_aluno_id:
        cal_params["aluno_id"] = contexto_aluno_id
    if contexto_turma_id:
        cal_params["turma_id"] = contexto_turma_id

    return render_template(
        "calendario_escolar.html",
        dias_do_mes=dias_do_mes,
        mes_atual=mes,
        ano_atual=ano,
        nome_mes_atual=nome_mes_atual,
        mes_anterior=mes_anterior,
        ano_anterior=ano_anterior,
        mes_proximo=mes_proximo,
        ano_proximo=ano_proximo,
        data_hoje=datetime.now().date(),
        turmas=turmas,
        professores=professores,
        alunos=alunos,
        eventos=eventos,
        eventos_por_dia=eventos_por_dia,
        modo_presenca=modo_presenca,
        contexto_aluno=contexto_aluno,
        contexto_turma=contexto_turma,
        contexto_aluno_id=contexto_aluno_id,
        contexto_turma_id=contexto_turma_id,
        frequencia_mes=frequencia_mes,
        lista_frequencia_dia=lista_frequencia_dia,
        frequencia_aluno_dia=frequencia_aluno_dia,
        dia_selecionado=dia_sel,
        cal_params=cal_params,
        provas_por_dia=provas_por_dia,
        eventos_do_dia=eventos_do_dia,
        provas_do_dia=provas_do_dia,
        dia_feriado=dia_feriado,
        dia_normal=dia_normal,
        visao=visao,
        busca_aluno=busca_aluno,
        alunos_busca=alunos_busca,
    )



NOMES_MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}


def _periodo_intervalo(periodo, data_ref):
    if isinstance(data_ref, str):
        data_ref = datetime.strptime(data_ref[:10], "%Y-%m-%d").date()
    periodo = (periodo or "mes").strip().lower()
    if periodo == "dia":
        return data_ref, data_ref, data_ref.strftime("%d/%m/%Y")
    if periodo == "semana":
        inicio = data_ref - timedelta(days=(data_ref.weekday() + 1) % 7)
        fim = inicio + timedelta(days=6)
        return inicio, fim, f"{inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}"
    inicio = date(data_ref.year, data_ref.month, 1)
    if data_ref.month == 12:
        fim = date(data_ref.year, 12, 31)
    else:
        fim = date(data_ref.year, data_ref.month + 1, 1) - timedelta(days=1)
    return inicio, fim, f"{NOMES_MESES_PT.get(data_ref.month, 'Mês')} de {data_ref.year}"


@app.route("/relatorio/pdf", methods=["GET", "POST"])
def relatorio_pdf_consulta():
    return relatorio_pdf_periodo(request.values.get("tipo") or "chamada")


@app.route("/relatorio/pdf/<tipo>", methods=["GET", "POST"])
def relatorio_pdf_periodo(tipo):
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    tipo = (tipo or "").strip().lower()
    if tipo not in ("chamada", "eventos", "completo"):
        flash("❌ Tipo de relatório inválido.", "danger")
        return redirect(url_for("calendario_escolar"))

    periodo = request.values.get("periodo") or "mes"
    data_str = request.values.get("data") or date.today().isoformat()
    turma_id = request.values.get("turma_id", type=int)
    aluno_id = request.values.get("aluno_id", type=int)
    origem = request.values.get("origem") or "calendario"
    destino_erro = url_for("calendario_escolar") if origem != "pedagogico" else url_for("pagina_pedagogico")

    try:
        inicio, fim, periodo_label = _periodo_intervalo(periodo, data_str)
    except ValueError:
        flash("❌ Data inválida para o relatório.", "danger")
        return redirect(destino_erro)

    garantir_tabelas_pedagogicas()
    conexao = obter_conexao()
    if not conexao:
        flash("❌ Sem conexão com o banco.", "danger")
        return redirect(destino_erro)

    chamada, eventos, provas = [], [], []
    escola = "Gestão Escolar"
    contexto_partes = []
    try:
        with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT nome_escola FROM configuracoes LIMIT 1;")
            cfg = cursor.fetchone() or {}
            escola = cfg.get("nome_escola") or escola

            if turma_id:
                cursor.execute("SELECT nome FROM turmas WHERE id = %s", (turma_id,))
                turma = cursor.fetchone()
                if turma:
                    contexto_partes.append(f"Turma {turma['nome']}")
            if aluno_id:
                cursor.execute("SELECT nome_completo, matricula FROM alunos WHERE id = %s", (aluno_id,))
                aluno = cursor.fetchone()
                if aluno:
                    contexto_partes.append(
                        f"Aluno {aluno['nome_completo']}"
                        + (f" (Mat. {aluno['matricula']})" if aluno.get("matricula") else "")
                    )

            if tipo in ("chamada", "completo"):
                sql = """
                    SELECT f.data_aula, f.status, f.disciplina, a.nome_completo, a.matricula, t.nome AS turma_nome
                    FROM frequencia f
                    JOIN alunos a ON a.id = f.aluno_id
                    LEFT JOIN turmas t ON t.id = f.turma_id
                    WHERE f.data_aula BETWEEN %s AND %s
                """
                params = [inicio, fim]
                if turma_id:
                    sql += " AND f.turma_id = %s"
                    params.append(turma_id)
                if aluno_id:
                    sql += " AND f.aluno_id = %s"
                    params.append(aluno_id)
                sql += " ORDER BY f.data_aula, t.nome, a.nome_completo, f.disciplina"
                cursor.execute(sql, params)
                chamada = cursor.fetchall()

            if tipo in ("eventos", "completo"):
                sql_ev = """
                    SELECT c.data_evento, c.titulo, c.tipo, c.horario, c.descricao, t.nome AS turma_nome
                    FROM calendario_eventos c
                    LEFT JOIN turmas t ON c.turma_id = t.id
                    WHERE c.data_evento BETWEEN %s AND %s
                      AND COALESCE(c.tipo, 'geral') <> 'aluno_vinculado_turma'
                """
                params_ev = [inicio, fim]
                if turma_id:
                    sql_ev += " AND (c.turma_id IS NULL OR c.turma_id = %s)"
                    params_ev.append(turma_id)
                sql_ev += " ORDER BY c.data_evento, c.horario NULLS LAST, c.titulo"
                cursor.execute(sql_ev, params_ev)
                eventos = cursor.fetchall()

                sql_pv = """
                    SELECT p.data_prova, p.titulo, p.materia, p.horario, p.descricao, t.nome AS turma_nome
                    FROM provas_turma p
                    LEFT JOIN turmas t ON t.id = p.turma_id
                    WHERE p.data_prova BETWEEN %s AND %s
                """
                params_pv = [inicio, fim]
                if turma_id:
                    sql_pv += " AND (p.turma_id IS NULL OR p.turma_id = %s)"
                    params_pv.append(turma_id)
                sql_pv += " ORDER BY p.data_prova, p.horario NULLS LAST, p.titulo"
                cursor.execute(sql_pv, params_pv)
                provas = cursor.fetchall()
    except Exception as e:
        flash(f"❌ Não foi possível gerar o PDF: {e}", "danger")
        return redirect(destino_erro)
    finally:
        conexao.close()

    resumo = {"presente": 0, "falta": 0, "justificada": 0}
    for row in chamada:
        st = (row.get("status") or "").lower()
        if st in resumo:
            resumo[st] += 1

    buffer = pdf_historico_periodo(
        escola,
        periodo_label,
        " · ".join(contexto_partes) if contexto_partes else "Escola (geral)",
        incluir_chamada=tipo in ("chamada", "completo"),
        incluir_eventos=tipo in ("eventos", "completo"),
        chamada=chamada,
        eventos=eventos,
        provas=provas,
        resumo_chamada=resumo,
    )
    nome_arq = f"{tipo}_{periodo}_{inicio.isoformat()}_{fim.isoformat()}.pdf"
    if request.args.get("enviar") or request.method == "POST":
        destinos = []
        conexao2 = obter_conexao()
        if conexao2:
            try:
                with conexao2.cursor() as cursor:
                    if aluno_id:
                        destinos = emails_contato_aluno(cursor, aluno_id)
                    else:
                        if turma_id:
                            cursor.execute(
                                "SELECT aluno_id FROM turma_alunos WHERE turma_id = %s",
                                (turma_id,),
                            )
                            for row in cursor.fetchall() or []:
                                destinos.extend(emails_contato_aluno(cursor, row["aluno_id"] if isinstance(row, dict) else row[0]))
                        cursor.execute(
                            "SELECT email FROM funcionarios WHERE COALESCE(ativo, TRUE) = TRUE AND COALESCE(email,'') <> ''"
                        )
                        for row in cursor.fetchall() or []:
                            bruto = row["email"] if isinstance(row, dict) else row[0]
                            if email_valido(bruto):
                                destinos.append(bruto)
            finally:
                conexao2.close()
        lista = enviar_email(
            destinos,
            f"Documento escolar ({tipo}) — {periodo_label}",
            "Segue em anexo o PDF solicitado pela secretaria (chamada, eventos/férias ou histórico).",
            [{"nome": nome_arq, "dados": bytes_pdf(buffer)}],
        )
        flash(f"PDF enviado para {len(lista)} destinatário(s).", "success")
        return redirect(destino_erro)
    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=nome_arq,
    )


@app.route("/cadastrar_evento", methods=["POST"])
def cadastrar_evento():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    conexao = obter_conexao()
    if conexao:
        try:
            titulo = limpar_campo("titulo")
            data = limpar_campo("data")
            categoria = limpar_campo("categoria")
            with conexao.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO calendario_eventos (titulo, data_evento, tipo)
                    VALUES (%s, %s, %s);
                """, (titulo, data, categoria))
                conexao.commit()
                flash("✅ Evento adicionado ao calendário!", "success")
        except Exception as e:
            conexao.rollback()
            flash(f"❌ Erro ao cadastrar evento: {e}", "danger")
        finally:
            conexao.close()
    return redirect(url_for("calendario_escolar"))


@app.route("/excluir_aluno/<int:id>", methods=["POST"])
def excluir_aluno_rota(id):
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    conexao = obter_conexao()
    if conexao:
        try:
            with conexao.cursor() as cursor:
                cursor.execute("DELETE FROM alunos WHERE id = %s;", (id,))
                conexao.commit()
                flash("✅ Aluno excluído com sucesso!", "success")
        except Exception as e:
            conexao.rollback()
            flash(f"❌ Erro ao excluir aluno: {e}", "danger")
        finally:
            conexao.close()
    return redirect(url_for("pagina_alunos"))


@app.route("/alunos", methods=["GET", "POST"])
def pagina_alunos():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    garantir_tabelas_folha()
    garantir_tabelas_pedagogicas()

    if request.method == "POST":
        acao = request.form.get("acao", "cadastrar_aluno")
        
        if acao == "editar_aluno":
            aluno_id = request.form.get("aluno_id")
            if aluno_id:
                status_bruto = request.form.get("status")
                if status_bruto is not None:
                    status_bruto = status_bruto.strip().lower()
                status = "inativo" if status_bruto in ["inativo", "inactive", "false", "0", "off"] else "ativo"
                
                telefone_principal = limpar_campo("telefone_principal") or request.form.get("telefone_principal")

                conexao = obter_conexao()
                if conexao:
                    try:
                        with conexao.cursor() as cursor:
                            cursor.execute("""
                                UPDATE alunos 
                                SET nome_completo = %s,
                                    status = %s,
                                    cpf = %s,
                                    rg = %s,
                                    data_nascimento = %s,
                                    telefone_principal = %s,
                                    email = %s,
                                    rua = %s,
                                    numero = %s,
                                    bairro = %s,
                                    cidade = %s,
                                    estado = %s,
                                    contrato_meses = COALESCE(%s, contrato_meses),
                                    contrato_inicio = COALESCE(%s::date, contrato_inicio),
                                    turnos_mensalidade = COALESCE(%s, turnos_mensalidade)
                                WHERE id = %s;
                            """, (
                                limpar_campo("nome_completo"),
                                status,
                                limpar_campo("cpf"),
                                limpar_campo("rg"),
                                limpar_campo("data_nascimento") or "2000-01-01",
                                telefone_principal,
                                limpar_campo("email"),
                                limpar_campo("rua") or limpar_campo("logradouro"),
                                limpar_campo("numero"),
                                limpar_campo("bairro"),
                                limpar_campo("cidade"),
                                limpar_campo("estado") or limpar_campo("estado_uf"),
                                request.form.get("contrato_meses") or None,
                                limpar_campo("contrato_inicio"),
                                limpar_campo("turnos_mensalidade"),
                                aluno_id
                            ))
                            conexao.commit()
                            flash("✅ Dados do aluno atualizados com sucesso!", "success")
                    except Exception as e:
                        conexao.rollback()
                        flash(f"❌ Erro ao atualizar aluno: {e}", "danger")
                    finally:
                        conexao.close()
                return redirect(url_for("detalhes_aluno", aluno_id=aluno_id))

        if acao == "cadastrar_aluno":
            valor_mensalidade_raw = request.form.get("valor_mensalidade", "").strip()
            try:
                valor_mensalidade = float(valor_mensalidade_raw.replace(",", ".")) if valor_mensalidade_raw else 0.0
            except ValueError:
                valor_mensalidade = 0.0

            desconto_valor_raw = request.form.get("desconto_valor", "0.0").strip()
            try:
                desconto_valor = float(desconto_valor_raw.replace(",", ".")) if desconto_valor_raw else 0.0
            except ValueError:
                desconto_valor = 0.0

            desconto_tipo_raw = request.form.get("desconto_tipo", "nenhum").strip().lower()
            mapeamento_desconto = {
                "porcentagem": "percentual",
                "percentual": "percentual",
                "fixo": "valor_fixo",
                "valor_fixo": "valor_fixo",
                "bolsa": "bolsa",
                "nenhum": "nenhum",
            }
            desconto_tipo = mapeamento_desconto.get(desconto_tipo_raw, "nenhum")

            dados_aluno = {
                "nome_completo": limpar_campo("nome_completo"),
                "cpf": limpar_campo("cpf"),
                "rg": limpar_campo("rg"),
                "certidao_nascimento": limpar_campo("certidao_nascimento"),
                "data_nascimento": limpar_campo("data_nascimento") or "2000-01-01",
                "sexo": limpar_campo("sexo"),
                "telefone_principal": limpar_campo("telefone_principal") or "(00) 0000-0000",
                "telefone_secundario": limpar_campo("telefone_secundario"),
                "email": limpar_campo("email"),
                "cep": limpar_campo("cep"),
                "rua": limpar_campo("rua"),
                "numero": limpar_campo("numero"),
                "bairro": limpar_campo("bairro"),
                "cidade": limpar_campo("cidade"),
                "estado": limpar_campo("estado"),
                "valor_mensalidade": valor_mensalidade,
                "desconto_tipo": desconto_tipo,
                "desconto_valor": desconto_valor,
                "turma_id": request.form.get("turma_id") or None,
            }

            resp1_nome = limpar_campo("resp1_nome")
            resp1 = {
                "nome_completo": resp1_nome,
                "cpf": limpar_campo("resp1_cpf"),
                "grau_parentesco": limpar_campo("resp1_parentesco"),
                "telefone": limpar_campo("resp1_telefone"),
                "email": limpar_campo("resp1_email"),
                "local_trabalho": limpar_campo("resp1_trabalho"),
                "telefone_trabalho": limpar_campo("resp1_tel_trabalho"),
            } if resp1_nome else None

            resp2_nome = limpar_campo("resp2_nome")
            resp2 = {
                "nome_completo": resp2_nome,
                "cpf": limpar_campo("resp2_cpf"),
                "grau_parentesco": limpar_campo("resp2_parentesco"),
                "telefone": limpar_campo("resp2_telefone"),
                "email": limpar_campo("resp2_email"),
                "local_trabalho": limpar_campo("resp2_trabalho"),
                "telefone_trabalho": limpar_campo("resp2_tel_trabalho"),
            } if resp2_nome else None

            try:
                if dados_aluno.get("email"):
                    exigencia_email(dados_aluno["email"], "E-mail do aluno")
                if resp1 and resp1.get("email"):
                    exigencia_email(resp1["email"], "E-mail do responsável 1")
                elif resp1:
                    raise ValueError("Informe um e-mail válido do responsável 1 para envio de boletos, notas e avisos.")
                if resp2 and resp2.get("email"):
                    exigencia_email(resp2["email"], "E-mail do responsável 2")
                if not dados_aluno.get("email") and not (resp1 and resp1.get("email")):
                    raise ValueError("Cadastre um e-mail válido do aluno ou do responsável principal.")
                matricula = cadastrar_aluno(dados_aluno, responsavel_1=resp1, responsavel_2=resp2)
                if matricula:
                    flash(f"Aluno cadastrado com sucesso! Matrícula: {matricula}", "success")
                    garantir_tabelas_folha()
                    conexao_c = obter_conexao()
                    if conexao_c:
                        try:
                            meses_c = int(request.form.get("contrato_meses") or 12)
                            turnos_c = request.form.get("turnos_mensalidade") or "manha"
                            inicio_c = request.form.get("contrato_inicio") or datetime.now().strftime("%Y-%m-%d")
                            with conexao_c.cursor() as cursor:
                                cursor.execute(
                                    """
                                    UPDATE alunos
                                    SET contrato_meses = %s, contrato_inicio = %s, turnos_mensalidade = %s
                                    WHERE matricula = %s
                                    RETURNING id
                                    """,
                                    (meses_c, inicio_c, turnos_c, matricula),
                                )
                                row_al = cursor.fetchone()
                                al_id = row_al["id"] if row_al else None
                                if al_id and valor_mensalidade > 0:
                                    nger = _gerar_mensalidades_contrato(
                                        cursor, al_id, valor_mensalidade, inicio_c, meses_c, turnos_c
                                    )
                                    flash(f"Contrato de {meses_c} meses gerou {nger} mensalidade(s).", "success")
                                conexao_c.commit()
                        except Exception as e:
                            conexao_c.rollback()
                            flash(f"Aluno salvo, mas o contrato de mensalidade falhou: {e}", "danger")
                        finally:
                            conexao_c.close()
                else:
                    flash("Erro ao cadastrar aluno. Verifique os campos.", "danger")
            except Exception as e:
                flash(f"Erro de banco de dados: {e}", "danger")

        return redirect(url_for("pagina_alunos"))

    termo_busca = request.args.get("q", "").strip()
    alunos = listar_alunos(termo_busca)
    return render_template("alunos.html", alunos=alunos, termo_busca=termo_busca)


@app.route("/cadastrar_aluno", methods=["POST"])
def cadastrar_aluno_rota():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    return pagina_alunos()


@app.route("/alunos/<int:aluno_id>")
def detalhes_aluno(aluno_id):
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    conexao = obter_conexao()
    aluno, responsaveis, turmas_aluno, financeiro_aluno, pessoas_autorizadas, provas_notas = None, [], [], [], [], []
    frequencias, boletins_anexos = [], []
    disciplinas_por_turma = {}
    resumo_frequencia = {"presente": 0, "falta": 0, "justificada": 0}

    garantir_tabelas_folha()
    garantir_tabelas_pedagogicas()

    if conexao:
        try:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT * FROM alunos WHERE id = %s", (aluno_id,))
                aluno = cursor.fetchone()

                cursor.execute("SELECT * FROM responsaveis_aluno WHERE aluno_id = %s", (aluno_id,))
                responsaveis = cursor.fetchall()

                cursor.execute("""
                    SELECT t.id as turma_id, t.nome, t.ano_letivo, t.turno, f.nome_completo as professor
                    FROM turma_alunos ta
                    JOIN turmas t ON t.id = ta.turma_id
                    LEFT JOIN funcionarios f ON f.id = t.professor_responsavel_id
                    WHERE ta.aluno_id = %s
                """, (aluno_id,))
                turmas_aluno = cursor.fetchall()

                cursor.execute("""
                    SELECT id, descricao, valor, data_vencimento, data_pagamento, status, forma_pagamento
                    FROM financeiro_mensalidades
                    WHERE aluno_id = %s
                    ORDER BY data_vencimento DESC;
                """, (aluno_id,))
                financeiro_aluno = cursor.fetchall()

                cursor.execute("""
                    SELECT id, nome_completo, cpf, telefone, vinculo, endereco 
                    FROM pessoas_autorizadas 
                    WHERE aluno_id = %s
                """, (aluno_id,))
                pessoas_autorizadas = cursor.fetchall()

                cursor.execute("""
                    SELECT id, turma_id, materia, trimestre, titulo_avaliacao, nota, arquivo_pdf, data_registro
                    FROM provas_notas
                    WHERE aluno_id = %s
                    ORDER BY trimestre ASC, materia ASC;
                """, (aluno_id,))
                provas_notas = cursor.fetchall()

                cursor.execute(
                    """
                    SELECT id, data_aula, status, disciplina, observacao
                    FROM frequencia
                    WHERE aluno_id = %s
                    ORDER BY data_aula DESC
                    LIMIT 90;
                    """,
                    (aluno_id,),
                )
                frequencias = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT status, COUNT(*) AS qtd FROM frequencia
                    WHERE aluno_id = %s GROUP BY status;
                    """,
                    (aluno_id,),
                )
                for row in cursor.fetchall():
                    if row["status"] in resumo_frequencia:
                        resumo_frequencia[row["status"]] = row["qtd"]

                cursor.execute(
                    """
                    SELECT id, trimestre, descricao, arquivo_pdf, criado_em
                    FROM boletins_anexos WHERE aluno_id = %s
                    ORDER BY criado_em DESC;
                    """,
                    (aluno_id,),
                )
                boletins_anexos = cursor.fetchall()

                cursor.execute(
                    """
                    SELECT td.turma_id, d.nome
                    FROM turma_disciplinas td
                    JOIN disciplinas d ON d.id = td.disciplina_id
                    JOIN turma_alunos ta ON ta.turma_id = td.turma_id
                    WHERE ta.aluno_id = %s
                    ORDER BY d.nome;
                    """,
                    (aluno_id,),
                )
                disciplinas_por_turma = {}
                for row in cursor.fetchall():
                    disciplinas_por_turma.setdefault(row["turma_id"], []).append(row["nome"])
        finally:
            conexao.close()

    if not aluno:
        flash("❌ Aluno não encontrado.", "danger")
        return redirect(url_for("pagina_alunos"))

    disciplinas_aluno = []
    vistos = set()
    for nomes in disciplinas_por_turma.values():
        for nome in nomes:
            if nome not in vistos:
                vistos.add(nome)
                disciplinas_aluno.append(nome)

    return render_template(
        "aluno_detalhes.html",
        aluno=aluno,
        responsaveis=responsaveis,
        turmas=turmas_aluno,
        financeiro=financeiro_aluno,
        pessoas_autorizadas=pessoas_autorizadas,
        provas_notas=provas_notas,
        frequencias=frequencias,
        resumo_frequencia=resumo_frequencia,
        boletins_anexos=boletins_anexos,
        disciplinas_por_turma=disciplinas_por_turma,
        disciplinas_aluno=disciplinas_aluno,
        hoje=date.today().isoformat(),
    )


@app.route("/alunos/<int:aluno_id>/editar", methods=["POST"])
def editar_aluno(aluno_id):
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    conexao = obter_conexao()
    if conexao:
        try:
            status_bruto = request.form.get("status")
            if status_bruto is not None:
                status_bruto = status_bruto.strip().lower()
            
            status = "inativo" if status_bruto in ["inativo", "inactive", "false", "0", "off"] else "ativo"
            
            telefone_principal = limpar_campo("telefone_principal") or request.form.get("telefone_principal")

            with conexao.cursor() as cursor:
                cursor.execute("""
                    UPDATE alunos 
                    SET nome_completo = %s,
                        status = %s,
                        cpf = %s,
                        rg = %s,
                        data_nascimento = %s,
                        telefone_principal = %s,
                        email = %s,
                        rua = %s,
                        numero = %s,
                        bairro = %s,
                        cidade = %s,
                        estado = %s
                    WHERE id = %s;
                """, (
                    limpar_campo("nome_completo"),
                    status,
                    limpar_campo("cpf"),
                    limpar_campo("rg"),
                    limpar_campo("data_nascimento") or "2000-01-01",
                    telefone_principal,
                    limpar_campo("email"),
                    limpar_campo("rua") or limpar_campo("logradouro"),
                    limpar_campo("numero"),
                    limpar_campo("bairro"),
                    limpar_campo("cidade"),
                    limpar_campo("estado") or limpar_campo("estado_uf"),
                    aluno_id
                ))
                conexao.commit()
                flash("✅ Dados do aluno atualizados com sucesso!", "success")
        except Exception as e:
            conexao.rollback()
            flash(f"❌ Erro ao atualizar aluno: {e}", "danger")
        finally:
            conexao.close()
            
    return redirect(url_for("detalhes_aluno", aluno_id=aluno_id))


@app.route("/alunos/<int:aluno_id>/responsavel", methods=["POST"])
def salvar_responsavel(aluno_id):
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    acao = request.form.get("acao")
    resp_id = request.form.get("responsavel_id")
    try:
        if acao == "deletar_responsavel":
            if resp_id:
                deletar_responsavel(resp_id)
                flash("Responsável removido.", "success")
        else:
            if not resp_id:
                raise ValueError("Responsável não encontrado.")
            email_resp = exigencia_email(limpar_campo("email"), "E-mail do responsável")
            atualizar_responsavel(resp_id, {
                "nome_completo": limpar_campo("nome_completo"),
                "cpf": limpar_campo("cpf"),
                "grau_parentesco": limpar_campo("grau_parentesco") or limpar_campo("parentesco"),
                "telefone": limpar_campo("telefone") or limpar_campo("telefone_principal"),
                "email": email_resp,
                "local_trabalho": limpar_campo("local_trabalho"),
                "telefone_trabalho": limpar_campo("telefone_trabalho"),
            })
            flash("Responsável atualizado.", "success")
    except Exception as e:
        flash(f"Não foi possível salvar o responsável: {e}", "danger")
    return redirect(url_for("detalhes_aluno", aluno_id=aluno_id))


@app.route("/alunos/<int:aluno_id>/adicionar_responsavel", methods=["POST"])
def adicionar_responsavel(aluno_id):
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    conexao = obter_conexao()
    if conexao:
        try:
            with conexao.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS total FROM responsaveis_aluno WHERE aluno_id = %s;", (aluno_id,))
                proximo_tipo = _contar(cursor.fetchone()) + 1
                cursor.execute(
                    """
                    SELECT conname FROM pg_constraint
                    WHERE conrelid = 'responsaveis_aluno'::regclass AND contype = 'c'
                      AND pg_get_constraintdef(oid) ILIKE '%tipo_responsavel%'
                    """
                )
                for row in cursor.fetchall() or []:
                    nome = row["conname"] if isinstance(row, dict) else row[0]
                    cursor.execute(f'ALTER TABLE responsaveis_aluno DROP CONSTRAINT IF EXISTS "{nome}"')

                parentesco = limpar_campo("grau_parentesco") or limpar_campo("parentesco")
                telefone = limpar_campo("telefone") or limpar_campo("telefone_principal")
                email_resp = exigencia_email(limpar_campo("email"), "E-mail do responsável")

                cursor.execute("""
                    INSERT INTO responsaveis_aluno (
                        aluno_id, tipo_responsavel, nome_completo, cpf, grau_parentesco, 
                        telefone, email, local_trabalho, telefone_trabalho
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (
                    aluno_id, proximo_tipo, limpar_campo("nome_completo"), limpar_campo("cpf"),
                    parentesco, telefone, email_resp,
                    limpar_campo("local_trabalho"), limpar_campo("telefone_trabalho")
                ))
                conexao.commit()
                flash("✅ Responsável legal adicionado com sucesso!", "success")
        except Exception as e:
            conexao.rollback()
            flash(f"❌ Erro ao cadastrar responsável: {e}", "danger")
        finally:
            conexao.close()
    return redirect(url_for("detalhes_aluno", aluno_id=aluno_id))


@app.route("/alunos/<int:aluno_id>/adicionar_autorizado", methods=["POST"])
def adicionar_autorizado(aluno_id):
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    conexao = obter_conexao()
    if conexao:
        try:
            with conexao.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO pessoas_autorizadas (aluno_id, nome_completo, cpf, telefone, vinculo, endereco)
                    VALUES (%s, %s, %s, %s, %s, %s);
                """, (aluno_id, limpar_campo("nome_completo"), limpar_campo("cpf"), 
                      limpar_campo("telefone"), limpar_campo("vinculo") or limpar_campo("grau_parentesco"), 
                      limpar_campo("endereco")))
                conexao.commit()
                flash("✅ Pessoa autorizada cadastrada com sucesso!", "success")
        except Exception as e:
            conexao.rollback()
            flash(f"❌ Erro ao cadastrar pessoa autorizada: {e}", "danger")
        finally:
            conexao.close()
    return redirect(url_for("detalhes_aluno", aluno_id=aluno_id))


@app.route("/alunos/<int:aluno_id>/adicionar_nota", methods=["POST"])
def adicionar_nota(aluno_id):
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    conexao = obter_conexao()
    if conexao:
        try:
            materia = request.form.get("materia")
            trimestre = request.form.get("trimestre")
            titulo = request.form.get("titulo_avaliacao")
            nota_raw = request.form.get("nota", "0").replace(",", ".")
            nota = float(nota_raw) if nota_raw else 0.0
            turma_id = request.form.get("turma_id") or None

            arquivo = request.files.get("arquivo_pdf")
            nome_arquivo = None
            if arquivo and arquivo.filename != "":
                nome_seguro = secure_filename(arquivo.filename)
                nome_arquivo = f"aluno_{aluno_id}_{nome_seguro}"
                caminho_salvar = os.path.join(PASTA_UPLOADS_PROVAS, nome_arquivo)
                arquivo.save(caminho_salvar)

            with conexao.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO provas_notas (aluno_id, turma_id, materia, trimestre, titulo_avaliacao, nota, arquivo_pdf)
                    VALUES (%s, %s, %s, %s, %s, %s, %s);
                """, (aluno_id, turma_id, materia, trimestre, titulo, nota, nome_arquivo))
                conexao.commit()
                flash("✅ Nota e prova anexadas com sucesso!", "success")
        except Exception as e:
            conexao.rollback()
            flash(f"❌ Erro ao salvar nota: {e}", "danger")
        finally:
            conexao.close()
    return redirect(url_for("detalhes_aluno", aluno_id=aluno_id))


@app.route("/alunos/<int:aluno_id>/boletim", methods=["GET", "POST"])
@app.route("/alunos/<int:aluno_id>/boletim.pdf", methods=["GET", "POST"])
def boletim_pdf(aluno_id):
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    garantir_tabelas_pedagogicas()
    conexao = obter_conexao()
    if not conexao:
        flash("❌ Sem conexão com o banco.", "danger")
        return redirect(url_for("detalhes_aluno", aluno_id=aluno_id))
    aluno = None
    notas = []
    turmas_aluno = []
    cfg = {}
    resumo = {"presente": 0, "falta": 0, "justificada": 0}
    try:
        with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT nome_escola FROM configuracoes WHERE id = 1;")
            cfg = cursor.fetchone() or {}
            cursor.execute("SELECT * FROM alunos WHERE id = %s", (aluno_id,))
            aluno = cursor.fetchone()
            cursor.execute(
                """
                SELECT trimestre, materia, titulo_avaliacao, nota
                FROM provas_notas WHERE aluno_id = %s
                ORDER BY trimestre, materia;
                """,
                (aluno_id,),
            )
            notas = cursor.fetchall()
            cursor.execute(
                """
                SELECT t.nome, t.ano_letivo, t.turno
                FROM turma_alunos ta
                JOIN turmas t ON t.id = ta.turma_id
                WHERE ta.aluno_id = %s
                """,
                (aluno_id,),
            )
            turmas_aluno = cursor.fetchall()
            cursor.execute(
                "SELECT status, COUNT(*) AS qtd FROM frequencia WHERE aluno_id = %s GROUP BY status;",
                (aluno_id,),
            )
            for row in cursor.fetchall():
                if row["status"] in resumo:
                    resumo[row["status"]] = row["qtd"]
        if not aluno:
            flash("❌ Aluno não encontrado.", "danger")
            return redirect(url_for("pagina_alunos"))
        buffer = pdf_boletim(
            cfg.get("nome_escola") or "Gestão Escolar",
            aluno,
            notas,
            resumo,
            turmas_aluno,
        )
        matricula = secure_filename(str(aluno.get("matricula") or aluno_id))
        nome_arq = f"boletim_{matricula}.pdf"
        if request.args.get("enviar") or request.method == "POST":
            with conexao.cursor() as cursor:
                destinos = emails_contato_aluno(cursor, aluno_id)
            enviar_email(
                destinos,
                f"Boletim escolar — {aluno.get('nome_completo')}",
                "Segue em anexo o boletim do aluno.",
                [{"nome": nome_arq, "dados": bytes_pdf(buffer)}],
            )
            flash(f"Boletim enviado para {', '.join(destinos)}.", "success")
            return redirect(url_for("detalhes_aluno", aluno_id=aluno_id) + "#notas")
        return send_file(
            buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=nome_arq,
        )
    except Exception as e:
        flash(f"❌ Não foi possível gerar o boletim: {e}", "danger")
        return redirect(url_for("detalhes_aluno", aluno_id=aluno_id))
    finally:
        conexao.close()


@app.route("/alunos/<int:aluno_id>/anexar_boletim", methods=["POST"])
def anexar_boletim(aluno_id):
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    garantir_tabelas_pedagogicas()
    arquivo = request.files.get("arquivo_boletim")
    if not arquivo or arquivo.filename == "":
        flash("❌ Selecione um PDF de boletim para anexar.", "danger")
        return redirect(url_for("detalhes_aluno", aluno_id=aluno_id))
    nome_seguro = secure_filename(arquivo.filename)
    nome_arquivo = f"boletim_{aluno_id}_{nome_seguro}"
    arquivo.save(os.path.join(PASTA_UPLOADS_BOLETINS, nome_arquivo))
    conexao = obter_conexao()
    if conexao:
        try:
            with conexao.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO boletins_anexos (aluno_id, trimestre, descricao, arquivo_pdf)
                    VALUES (%s, %s, %s, %s);
                    """,
                    (
                        aluno_id,
                        request.form.get("trimestre") or None,
                        limpar_campo("descricao_boletim") or "Boletim anexo",
                        nome_arquivo,
                    ),
                )
                conexao.commit()
                flash("✅ Boletim anexado.", "success")
        except Exception as e:
            conexao.rollback()
            flash(f"❌ Erro ao anexar boletim: {e}", "danger")
        finally:
            conexao.close()
    return redirect(url_for("detalhes_aluno", aluno_id=aluno_id))


@app.route("/alunos/<int:aluno_id>/frequencia", methods=["POST"])
def lancar_frequencia_aluno(aluno_id):
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    garantir_tabelas_pedagogicas()
    conexao = obter_conexao()
    if conexao:
        try:
            with conexao.cursor() as cursor:
                turma_id = request.form.get("turma_id") or None
                disciplina = request.form.get("disciplina") or ""
                status = request.form.get("status") or "presente"
                data_aula = request.form.get("data_aula")
                if not data_aula:
                    raise ValueError("Informe a data.")
                if disciplina in ("__todas__", "todas") and not turma_id:
                    raise ValueError("Escolha a turma para lançar em todas as matérias.")
                _lancar_frequencia_materias(cursor, aluno_id, turma_id, data_aula, status, disciplina)
                conexao.commit()
                flash("✅ Presença/falta lançada na disciplina.", "success")
        except Exception as e:
            conexao.rollback()
            flash(f"❌ Erro ao lançar frequência: {e}", "danger")
        finally:
            conexao.close()
    return redirect(url_for("detalhes_aluno", aluno_id=aluno_id) + "#faltas")


@app.route("/professores", methods=["GET", "POST"])
def pagina_professores():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        flash("Cadastre professores e equipe em Gerenciar Usuários.", "success")
        return redirect(url_for("gerenciar_usuarios"))

    garantir_tabelas_folha()
    garantir_tabelas_pedagogicas()

    busca_prof = request.args.get("q", "").strip()
    professores_cadastrados = []
    conexao = obter_conexao()
    if conexao:
        try:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT f.id, f.nome_completo, f.especialidade as disciplina, f.email, f.telefone, f.salario,
                           STRING_AGG(t.nome, ', ') AS turmas_lecionadas
                    FROM funcionarios f
                    LEFT JOIN turmas t ON t.professor_responsavel_id = f.id
                    WHERE COALESCE(f.ativo, TRUE) = TRUE
                      AND LOWER(COALESCE(f.cargo, '')) LIKE '%professor%'
                    GROUP BY f.id, f.nome_completo, f.especialidade, f.email, f.telefone, f.salario
                    ORDER BY f.nome_completo ASC;
                """)
                professores_cadastrados = cursor.fetchall()
        finally:
            conexao.close()

    if busca_prof:
        termo = busca_prof.lower()
        professores_cadastrados = [
            p for p in professores_cadastrados
            if termo in (p.get("nome_completo") or "").lower()
            or termo in (p.get("email") or "").lower()
            or termo in (p.get("disciplina") or "").lower()
        ]

    return render_template("professores.html", professores=professores_cadastrados, busca_prof=busca_prof)


@app.route("/professores/<int:professor_id>", methods=["GET", "POST"])
def detalhes_professor(professor_id):
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    conexao = obter_conexao()

    if request.method == "POST":
        if conexao:
            conexao.close()
        return redirect(url_for("gerenciar_usuarios", fid=professor_id))

    professor = None
    turmas = []
    eventos = []
    config = None

    if conexao:
        try:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT * FROM funcionarios WHERE id = %s;", (professor_id,))
                professor = cursor.fetchone()

                cursor.execute("""
                    SELECT t.id, t.nome, t.ano_letivo, t.turno,
                           (SELECT COUNT(*) FROM turma_alunos ta WHERE ta.turma_id = t.id) as total_alunos
                    FROM turmas t
                    WHERE t.professor_responsavel_id = %s;
                """, (professor_id,))
                turmas = cursor.fetchall()

                cursor.execute("""
                    SELECT * FROM calendario_eventos 
                    WHERE professor_id = %s OR tipo = 'geral'
                    ORDER BY data_evento ASC;
                """, (professor_id,))
                eventos = cursor.fetchall()

                # Busca configurações da escola para extrair o regime tributário
                cursor.execute("SELECT * FROM configuracoes LIMIT 1;")
                config = cursor.fetchone()
        finally:
            conexao.close()

    if not professor:
        flash("❌ Professor não encontrado.", "danger")
        return redirect(url_for("pagina_professores"))

    # Tratamento de regras e encargos CLT para o template
    regime_db = config.get('regime_tributario', 'Simples Nacional') if config else 'Simples Nacional'
    salario_base = float(professor.get('salario', 0.0) or 0.0)

    fgts = salario_base * 0.08
    provisao_13 = salario_base / 12.0
    provisao_ferias = (salario_base + (salario_base / 3.0)) / 12.0
    reflexos_fgts = (provisao_13 + provisao_ferias) * 0.08

    if regime_db in ['lucro_presumido', 'Lucro Presumido', 'Lucro Presumido/Real']:
        inss_patronal = salario_base * 0.20
        rat = salario_base * 0.01
        sistema_s = salario_base * 0.058
        regime_tributario = "Lucro Presumido/Real"
    else:
        inss_patronal = 0.0
        rat = 0.0
        sistema_s = 0.0
        regime_tributario = "Simples Nacional"

    custo_total = salario_base + fgts + provisao_13 + provisao_ferias + reflexos_fgts + inss_patronal + rat + sistema_s

    return render_template(
        "professor_detalhes.html",
        professor=professor,
        turmas=turmas,
        eventos=eventos,
        salario_base=salario_base,
        regime_tributario=regime_tributario,
        fgts=fgts,
        provisao_13=provisao_13,
        provisao_ferias=provisao_ferias,
        reflexos_fgts=reflexos_fgts,
        inss_patronal=inss_patronal,
        rat=rat,
        sistema_s=sistema_s,
        custo_total=custo_total
    )


@app.route("/cadastrar_professor", methods=["POST"])
def cadastrar_professor():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    flash("Cadastre a equipe em Gerenciar Usuários.", "success")
    return redirect(url_for("gerenciar_usuarios"))


@app.route("/professor/excluir/<int:id>", methods=["POST"])
def excluir_professor(id):
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    conexao = obter_conexao()
    if conexao:
        try:
            with conexao.cursor() as cursor:
                cursor.execute("DELETE FROM funcionarios WHERE id = %s AND cargo = 'Professor';", (id,))
                conexao.commit()
                flash("✅ Professor excluído com sucesso!", "success")
        except Exception as e:
            conexao.rollback()
            flash(f"❌ Erro ao excluir professor: {e}", "danger")
        finally:
            conexao.close()
            
    return redirect(url_for("pagina_professores"))


@app.route("/pedagogico", methods=["GET", "POST"])
def pagina_pedagogico():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        acao = request.form.get("acao", "criar_turma")
        conexao = obter_conexao()
        garantir_tabelas_pedagogicas()

        if conexao:
            try:
                with conexao.cursor() as cursor:
                    if acao in ["criar_turma", "nova_turma"]:
                        cursor.execute(
                            """
                            INSERT INTO turmas (nome, ano_letivo, turno, professor_responsavel_id)
                            VALUES (%s, %s, %s, %s);
                            """,
                            (
                                limpar_campo("nome_turma") or limpar_campo("nome"),
                                limpar_campo("ano_letivo") or "2026",
                                limpar_campo("turno"),
                                limpar_campo("professor_id"),
                            ),
                        )
                        conexao.commit()
                        flash("✅ Turma cadastrada com sucesso!", "success")

                    elif acao in ["vincular_aluno", "incluir_aluno"]:
                        cursor.execute(
                            """
                            INSERT INTO turma_alunos (turma_id, aluno_id)
                            VALUES (%s, %s)
                            ON CONFLICT DO NOTHING;
                            """,
                            (limpar_campo("turma_id"), limpar_campo("aluno_id")),
                        )
                        conexao.commit()
                        flash("✅ Aluno vinculado à turma com sucesso!", "success")

                    elif acao in ("criar_disciplina", "criar_disciplina_turma"):
                        nome_disc = limpar_campo("nome_disciplina")
                        if not nome_disc:
                            raise ValueError("Informe o nome da matéria.")
                        tipo, aulas, minutos, vezes, dias, carga, grade_json = _ler_carga_materia()
                        turma_id = request.form.get("turma_id")
                        cursor.execute(
                            "SELECT id FROM disciplinas WHERE LOWER(nome) = LOWER(%s) LIMIT 1;",
                            (nome_disc,),
                        )
                        existente = cursor.fetchone()
                        if existente:
                            disc_id = existente[0] if not isinstance(existente, dict) else existente["id"]
                            cursor.execute(
                                """
                                UPDATE disciplinas
                                SET tipo_frequencia = %s, aulas_semana = %s, minutos_aula = %s,
                                    vezes_mes = %s, dias_semana = %s, carga_horaria = %s, grade_json = %s
                                WHERE id = %s
                                """,
                                (tipo, aulas, minutos, vezes, dias, carga, grade_json, disc_id),
                            )
                        else:
                            codigo = "".join(ch for ch in nome_disc if ch.isalnum())[:16].upper() or "MAT"
                            cursor.execute("SELECT id FROM disciplinas WHERE codigo = %s", (codigo,))
                            if cursor.fetchone():
                                codigo = f"{codigo[:14]}{aulas}{minutos % 10}"
                            cursor.execute(
                                """
                                INSERT INTO disciplinas (
                                    codigo, nome, carga_horaria, tipo_frequencia,
                                    aulas_semana, minutos_aula, vezes_mes, dias_semana, grade_json
                                )
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                                RETURNING id;
                                """,
                                (codigo, nome_disc, carga, tipo, aulas, minutos, vezes, dias, grade_json),
                            )
                            criado = cursor.fetchone()
                            disc_id = criado[0] if not isinstance(criado, dict) else criado["id"]
                        if turma_id:
                            cursor.execute(
                                """
                                INSERT INTO turma_disciplinas (
                                    turma_id, disciplina_id, tipo_frequencia, aulas_semana,
                                    minutos_aula, vezes_mes, dias_semana, grade_json
                                )
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                                ON CONFLICT (turma_id, disciplina_id) DO UPDATE SET
                                    tipo_frequencia = EXCLUDED.tipo_frequencia,
                                    aulas_semana = EXCLUDED.aulas_semana,
                                    minutos_aula = EXCLUDED.minutos_aula,
                                    vezes_mes = EXCLUDED.vezes_mes,
                                    dias_semana = EXCLUDED.dias_semana,
                                    grade_json = EXCLUDED.grade_json;
                                """,
                                (turma_id, disc_id, tipo, aulas, minutos, vezes, dias, grade_json),
                            )
                            conexao.commit()
                            flash("✅ Matéria cadastrada nesta turma.", "success")
                        else:
                            conexao.commit()
                            flash("✅ Matéria cadastrada.", "success")

                    elif acao == "vincular_disciplina":
                        turma_id = request.form.get("turma_id")
                        disciplina_id = request.form.get("disciplina_id")
                        cursor.execute(
                            """
                            SELECT tipo_frequencia, aulas_semana, minutos_aula, vezes_mes, dias_semana, grade_json
                            FROM disciplinas WHERE id = %s
                            """,
                            (disciplina_id,),
                        )
                        base = cursor.fetchone() or {}
                        if not isinstance(base, dict):
                            base = {
                                "tipo_frequencia": base[0] if base else "semanal",
                                "aulas_semana": base[1] if base else 2,
                                "minutos_aula": base[2] if base else 60,
                                "vezes_mes": base[3] if base else 1,
                                "dias_semana": base[4] if base else "",
                                "grade_json": base[5] if base and len(base) > 5 else "[]",
                            }
                        cursor.execute(
                            """
                            INSERT INTO turma_disciplinas (
                                turma_id, disciplina_id, tipo_frequencia, aulas_semana,
                                minutos_aula, vezes_mes, dias_semana, grade_json
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (turma_id, disciplina_id) DO UPDATE SET
                                tipo_frequencia = EXCLUDED.tipo_frequencia,
                                aulas_semana = EXCLUDED.aulas_semana,
                                minutos_aula = EXCLUDED.minutos_aula,
                                vezes_mes = EXCLUDED.vezes_mes,
                                dias_semana = EXCLUDED.dias_semana,
                                grade_json = EXCLUDED.grade_json;
                            """,
                            (
                                turma_id,
                                disciplina_id,
                                base.get("tipo_frequencia") or "semanal",
                                base.get("aulas_semana") or 2,
                                base.get("minutos_aula") or 60,
                                base.get("vezes_mes") or 1,
                                base.get("dias_semana") or "",
                                base.get("grade_json") or "[]",
                            ),
                        )
                        conexao.commit()
                        flash("✅ Matéria incluída nesta turma.", "success")

                    elif acao == "excluir_disciplina":
                        cursor.execute(
                            "DELETE FROM disciplinas WHERE id = %s;",
                            (request.form.get("disciplina_id"),),
                        )
                        conexao.commit()
                        flash("✅ Matéria excluída.", "success")

                    elif acao == "excluir_disciplina_turma":
                        cursor.execute(
                            "DELETE FROM turma_disciplinas WHERE turma_id = %s AND disciplina_id = %s;",
                            (request.form.get("turma_id"), request.form.get("disciplina_id")),
                        )
                        conexao.commit()
                        flash("✅ Matéria removida desta turma.", "success")

                    elif acao == "marcar_presenca_aluno":
                        data_aula = request.form.get("data_aula")
                        turma_id = request.form.get("turma_id")
                        aluno_id = request.form.get("aluno_id")
                        disciplina = request.form.get("disciplina") or "__todas__"
                        status = request.form.get("status") or "presente"
                        if not data_aula or not turma_id or not aluno_id:
                            raise ValueError("Informe data, turma e aluno.")
                        _lancar_frequencia_materias(cursor, aluno_id, turma_id, data_aula, status, disciplina)
                        conexao.commit()
                        flash("✅ Presença atualizada.", "success")

                    elif acao == "marcar_presenca_turma":
                        data_aula = request.form.get("data_aula")
                        turma_id = request.form.get("turma_id")
                        disciplina = request.form.get("disciplina") or "__todas__"
                        status = request.form.get("status") or "presente"
                        if not data_aula or not turma_id:
                            raise ValueError("Informe data e turma.")
                        cursor.execute("SELECT aluno_id FROM turma_alunos WHERE turma_id = %s", (turma_id,))
                        alunos_ids = [row[0] if not isinstance(row, dict) else row["aluno_id"] for row in cursor.fetchall()]
                        if not alunos_ids:
                            raise ValueError("Nenhum aluno nesta turma.")
                        for aid in alunos_ids:
                            _lancar_frequencia_materias(cursor, aid, turma_id, data_aula, status, disciplina)
                        conexao.commit()
                        flash("✅ Chamada da turma lançada.", "success")

                    elif acao == "criar_prova_turma":
                        turma_id = request.form.get("turma_id")
                        titulo = limpar_campo("titulo_prova") or "Prova"
                        materia = limpar_campo("materia_prova")
                        descricao = limpar_campo("descricao_prova")
                        data_prova = request.form.get("data_prova")
                        horario = request.form.get("horario_prova") or None
                        trimestre = request.form.get("trimestre_prova") or None
                        cursor.execute(
                            """
                            INSERT INTO provas_turma (turma_id, materia, titulo, descricao, data_prova, horario, trimestre)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            """,
                            (turma_id, materia, titulo, descricao, data_prova, horario, trimestre),
                        )
                        cursor.execute(
                            """
                            INSERT INTO calendario_eventos (titulo, descricao, data_evento, tipo, turma_id, horario)
                            VALUES (%s, %s, %s, 'prova', %s, %s)
                            """,
                            (
                                f"{titulo}" + (f" — {materia}" if materia else ""),
                                descricao,
                                data_prova,
                                turma_id,
                                horario,
                            ),
                        )
                        conexao.commit()
                        flash("✅ Prova da turma cadastrada no calendário.", "success")
            except Exception as e:
                conexao.rollback()
                flash(f"❌ Ocorreu um erro: {e}", "danger")
            finally:
                conexao.close()

        destino = {"aba": request.form.get("aba") or "turmas"}
        if request.form.get("turma_id") and acao != "criar_turma":
            destino["turma_sel"] = request.form.get("turma_id")
        if request.form.get("painel"):
            destino["painel"] = request.form.get("painel")
        if request.form.get("data_aula") and acao in ("marcar_presenca_aluno", "marcar_presenca_turma"):
            destino["data_chamada"] = request.form.get("data_aula")
            destino["disc_chamada"] = request.form.get("disciplina") or "__todas__"
            destino["painel"] = "alunos"
        return redirect(url_for("pagina_pedagogico", **destino))

    termo_turma = request.args.get("turma", "").strip()
    termo_professor = request.args.get("professor", "").strip()
    filtro_turno = request.args.get("turno", "").strip()

    turmas, professores, alunos_cadastrados, disciplinas = [], [], [], []
    alunos_por_turma = {}
    disciplinas_por_turma = {}
    quadros_por_turma = {}
    provas_por_turma = {}
    presenca_aluno = {}
    data_chamada = request.args.get("data_chamada") or date.today().isoformat()
    disc_chamada = request.args.get("disc_chamada") or "__todas__"

    garantir_tabelas_pedagogicas()
    conexao = obter_conexao()
    if conexao:
        try:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                query_turmas = """
                    SELECT t.id, t.nome, t.ano_letivo, t.turno, f.nome_completo,
                           COUNT(ta.aluno_id) AS total_alunos
                    FROM turmas t
                    LEFT JOIN funcionarios f ON t.professor_responsavel_id = f.id
                    LEFT JOIN turma_alunos ta ON t.id = ta.turma_id
                    WHERE 1=1
                """
                params_turmas = []

                if termo_turma:
                    query_turmas += " AND (t.nome ILIKE %s OR CAST(t.id AS TEXT) = %s)"
                    params_turmas.extend([f"%{termo_turma}%", termo_turma])

                if termo_professor:
                    query_turmas += " AND f.nome_completo ILIKE %s"
                    params_turmas.append(f"%{termo_professor}%")

                if filtro_turno:
                    query_turmas += " AND t.turno = %s"
                    params_turmas.append(filtro_turno)

                query_turmas += """
                    GROUP BY t.id, t.nome, t.ano_letivo, t.turno, f.nome_completo
                    ORDER BY t.nome ASC;
                """

                cursor.execute(query_turmas, params_turmas)
                turmas = cursor.fetchall()

                cursor.execute("""
                    SELECT id, nome_completo FROM funcionarios 
                    WHERE LOWER(cargo) LIKE '%professor%' AND ativo = TRUE ORDER BY nome_completo ASC;
                """)
                professores = cursor.fetchall()

                cursor.execute("SELECT id, nome_completo, matricula FROM alunos ORDER BY nome_completo ASC;")
                alunos_cadastrados = cursor.fetchall()

                cursor.execute(
                    """
                    SELECT id, nome, tipo_frequencia, aulas_semana, minutos_aula, vezes_mes, dias_semana, carga_horaria, grade_json
                    FROM disciplinas ORDER BY nome;
                    """
                )
                disciplinas = cursor.fetchall()
                disciplinas = [{**dict(d), "resumo": _quadro_materia(d)["resumo"]} for d in disciplinas]

                cursor.execute("""
                    SELECT ta.turma_id, a.id, a.nome_completo, a.matricula 
                    FROM turma_alunos ta
                    JOIN alunos a ON ta.aluno_id = a.id
                    ORDER BY a.nome_completo ASC;
                """)
                for row in cursor.fetchall():
                    alunos_por_turma.setdefault(row["turma_id"], []).append(
                        {"id": row["id"], "nome": row["nome_completo"], "matricula": row["matricula"]}
                    )

                cursor.execute("""
                    SELECT td.turma_id, d.id, d.nome,
                           COALESCE(td.tipo_frequencia, d.tipo_frequencia, 'semanal') AS tipo_frequencia,
                           COALESCE(td.aulas_semana, d.aulas_semana, 2) AS aulas_semana,
                           COALESCE(td.minutos_aula, d.minutos_aula, 60) AS minutos_aula,
                           COALESCE(td.vezes_mes, d.vezes_mes, 1) AS vezes_mes,
                           COALESCE(td.dias_semana, d.dias_semana, '') AS dias_semana,
                           COALESCE(NULLIF(td.grade_json, ''), NULLIF(d.grade_json, ''), '[]') AS grade_json
                    FROM turma_disciplinas td
                    JOIN disciplinas d ON d.id = td.disciplina_id
                    ORDER BY d.nome;
                """)
                for row in cursor.fetchall():
                    disciplinas_por_turma.setdefault(row["turma_id"], []).append(row["nome"])
                    item = _quadro_materia(row)
                    item["disciplina_id"] = row["id"]
                    item["turma_id"] = row["turma_id"]
                    quadros_por_turma.setdefault(row["turma_id"], []).append(item)

                cursor.execute(
                    """
                    SELECT turma_id, titulo, materia, data_prova, horario
                    FROM provas_turma
                    WHERE data_prova >= CURRENT_DATE - INTERVAL '30 days'
                    ORDER BY data_prova, horario
                    """
                )
                for row in cursor.fetchall():
                    provas_por_turma.setdefault(row["turma_id"], []).append(row)

                data_chamada = request.args.get("data_chamada") or date.today().isoformat()
                disc_chamada = request.args.get("disc_chamada") or "__todas__"
                turma_sel_id = request.args.get("turma_sel", type=int)
                if turma_sel_id:
                    cursor.execute(
                        """
                        SELECT aluno_id, disciplina, status FROM frequencia
                        WHERE turma_id = %s AND data_aula = %s
                        """,
                        (turma_sel_id, data_chamada),
                    )
                    por_aluno = {}
                    for row in cursor.fetchall():
                        por_aluno.setdefault(row["aluno_id"], {})[row["disciplina"] or ""] = row["status"]
                    materias_sel = disciplinas_por_turma.get(turma_sel_id, [])
                    for aid, discs in por_aluno.items():
                        if disc_chamada in ("__todas__", "todas"):
                            if materias_sel and all(discs.get(m) == "presente" for m in materias_sel):
                                presenca_aluno[aid] = "presente"
                            elif materias_sel and all(discs.get(m) == "falta" for m in materias_sel):
                                presenca_aluno[aid] = "falta"
                        else:
                            if discs.get(disc_chamada):
                                presenca_aluno[aid] = discs.get(disc_chamada)
        finally:
            conexao.close()

    return render_template(
        "pedagogico.html",
        turmas=turmas,
        professores=professores,
        alunos_cadastrados=alunos_cadastrados,
        alunos_por_turma=alunos_por_turma,
        disciplinas=disciplinas,
        disciplinas_por_turma=disciplinas_por_turma,
        quadros_por_turma=quadros_por_turma,
        provas_por_turma=provas_por_turma,
        busca_aluno=request.args.get("aluno", "").strip(),
        dias_semana_opcoes=DIAS_SEMANA_OPCOES,
        aba=(
            request.args.get("aba")
            or ("aluno" if request.args.get("aluno") else "turmas")
        ),
        turma_sel=request.args.get("turma_sel", type=int),
        painel=request.args.get("painel") or "horas",
        data_chamada=data_chamada,
        disc_chamada=disc_chamada,
        presenca_aluno=presenca_aluno,
    )


@app.route("/financeiro", methods=["GET", "POST"])
def pagina_financeiro():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    garantir_tabelas_folha()
    mes_redir = request.form.get("mes") or request.args.get("mes") or datetime.now().strftime("%Y-%m")
    aba_redir = request.form.get("aba") or request.args.get("aba") or "resumo"

    if request.method == "POST":
        acao = request.form.get("acao")
        conexao = obter_conexao()
        if conexao:
            try:
                with conexao.cursor() as cursor:
                    if acao == "criar_cobranca":
                        aluno_id = request.form.get("aluno_id")
                        descricao = limpar_campo("descricao") or "Mensalidade"
                        valor_raw = request.form.get("valor", "0").replace(",", ".")
                        valor = float(valor_raw) if valor_raw else 0.0
                        data_vencimento = request.form.get("data_vencimento") or datetime.now().strftime("%Y-%m-%d")
                        try:
                            duracao = int(request.form.get("duracao") or 1)
                        except ValueError:
                            duracao = 1
                        turnos = request.form.get("turnos") or "manha"
                        geradas = _gerar_mensalidades_contrato(
                            cursor, aluno_id, valor, data_vencimento, duracao, turnos, descricao
                        )
                        conexao.commit()
                        flash(f"Cobrança gerada: {geradas} mensalidade(s) no contrato.", "success")

                    elif acao == "gerar_lote":
                        descricao_lote = request.form.get("descricao_lote") or "Mensalidade"
                        data_vencimento_lote = request.form.get("data_vencimento_lote") or datetime.now().strftime("%Y-%m-%d")
                        venc_lote = datetime.strptime(data_vencimento_lote[:10], "%Y-%m-%d").date()
                        cursor.execute(
                            """
                            SELECT id, valor_mensalidade, contrato_meses, contrato_inicio, turnos_mensalidade
                            FROM alunos
                            WHERE COALESCE(NULLIF(status, ''), situacao::text, 'ativo') ILIKE 'ativo'
                              AND valor_mensalidade > 0
                            """
                        )
                        geradas = 0
                        for al in cursor.fetchall():
                            inicio = al.get("contrato_inicio") or venc_lote
                            if isinstance(inicio, datetime):
                                inicio = inicio.date()
                            meses_c = int(al.get("contrato_meses") or 12)
                            fim = _add_months(inicio, meses_c - 1)
                            if not (inicio.replace(day=1) <= venc_lote.replace(day=1) <= fim.replace(day=1)):
                                continue
                            geradas += _gerar_mensalidades_contrato(
                                cursor,
                                al["id"],
                                float(al["valor_mensalidade"] or 0),
                                venc_lote,
                                1,
                                al.get("turnos_mensalidade") or "manha",
                                descricao_lote,
                            )
                        conexao.commit()
                        flash(f"Lote gerado: {geradas} cobrança(s) no mês, respeitando o prazo do contrato.", "success")

                    elif acao == "dar_baixa":
                        cursor.execute(
                            """
                            UPDATE financeiro_mensalidades
                            SET status = 'Pago', forma_pagamento = %s, data_pagamento = %s
                            WHERE id = %s;
                            """,
                            (
                                request.form.get("forma_pagamento"),
                                request.form.get("data_pagamento"),
                                request.form.get("cobranca_id"),
                            ),
                        )
                        conexao.commit()
                        flash("✅ Baixa realizada com sucesso!", "success")

                    elif acao == "salvar_funcionario":
                        salario = float((request.form.get("salario") or "0").replace(",", ".") or 0)
                        valor_hora = float((request.form.get("valor_hora") or "0").replace(",", ".") or 0)
                        horas_mes = float((request.form.get("horas_mes") or "0").replace(",", ".") or 0)
                        cursor.execute(
                            """
                            INSERT INTO funcionarios (
                                nome_completo, cpf, data_nascimento, cargo, telefone, email, salario, ativo,
                                tipo_contrato, valor_hora, horas_mes, reter_federal, reter_iss, aliquota_iss
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                limpar_campo("nome_completo"),
                                limpar_campo("cpf") or f"TMP{datetime.now().strftime('%H%M%S')}",
                                limpar_campo("data_nascimento") or "2000-01-01",
                                limpar_campo("cargo") or "Funcionário",
                                limpar_campo("telefone") or "(00) 00000-0000",
                                limpar_campo("email"),
                                salario,
                                request.form.get("tipo_contrato") or "clt_mensalista",
                                valor_hora,
                                horas_mes,
                                request.form.get("reter_federal") == "1",
                                request.form.get("reter_iss") == "1",
                                float((request.form.get("aliquota_iss") or "5").replace(",", ".") or 5),
                            ),
                        )
                        conexao.commit()
                        flash("✅ Funcionário incluído na folha.", "success")

                    elif acao == "atualizar_contrato":
                        fid = request.form.get("funcionario_id")
                        salario = float((request.form.get("salario") or "0").replace(",", ".") or 0)
                        valor_hora = float((request.form.get("valor_hora") or "0").replace(",", ".") or 0)
                        horas_mes = float((request.form.get("horas_mes") or "0").replace(",", ".") or 0)
                        cursor.execute(
                            """
                            UPDATE funcionarios SET
                                tipo_contrato = %s, salario = %s, valor_hora = %s, horas_mes = %s,
                                reter_federal = %s, reter_iss = %s, aliquota_iss = %s
                            WHERE id = %s
                            """,
                            (
                                request.form.get("tipo_contrato") or "clt_mensalista",
                                salario,
                                valor_hora,
                                horas_mes,
                                request.form.get("reter_federal") == "1",
                                request.form.get("reter_iss") == "1",
                                float((request.form.get("aliquota_iss") or "5").replace(",", ".") or 5),
                                fid,
                            ),
                        )
                        conexao.commit()
                        flash("✅ Contrato atualizado.", "success")

                    elif acao == "criar_custo":
                        tipo = request.form.get("tipo_custo") or "avista"
                        descricao = limpar_campo("descricao_custo") or "Custo"
                        categoria = limpar_campo("categoria_custo") or "operacional"
                        data_base = request.form.get("data_custo") or datetime.now().strftime("%Y-%m-%d")
                        data_ini = request.form.get("data_inicio_custo") or data_base
                        data_fim = limpar_campo("data_fim_custo")
                        forma = request.form.get("forma_custo") or "dinheiro"
                        prestador = limpar_campo("prestador_custo")
                        try:
                            n_parc = max(int(request.form.get("parcelas_custo") or 1), 1)
                        except ValueError:
                            n_parc = 1
                        valor_unit = _float_form("valor_custo") or _float_form("valor_unitario_custo")
                        valor_bruto = _float_form("valor_bruto_custo") or valor_unit
                        reter_fed = request.form.get("custo_reter_federal") == "1"
                        reter_iss = request.form.get("custo_reter_iss") == "1"
                        aliq_iss = _float_form("custo_aliquota_iss", 5.0)
                        fed_nota = request.form.get("federal_na_nota") != "0"
                        iss_nota = request.form.get("iss_na_nota") != "0"
                        impostos = impostos_nota(
                            valor_bruto or valor_unit,
                            reter_fed,
                            reter_iss,
                            aliq_iss,
                            _float_form("custo_aliq_irrf", 1.5),
                            _float_form("custo_aliq_pis", 0.65),
                            _float_form("custo_aliq_cofins", 3.0),
                            _float_form("custo_aliq_csll", 1.0),
                        )
                        custo_ok = True
                        if tipo == "servico":
                            if not (valor_bruto or valor_unit):
                                flash("Informe o valor bruto da NFS-e.", "danger")
                                custo_ok = False
                            desconto_nota = 0.0
                            if reter_fed and fed_nota:
                                desconto_nota += impostos["irrf"] + impostos["pis"] + impostos["cofins"] + impostos["csll"]
                            if reter_iss and iss_nota:
                                desconto_nota += impostos["iss"]
                            valor_lancar = round((valor_bruto or valor_unit) - desconto_nota, 2)
                        else:
                            if not valor_unit:
                                flash("Informe o valor unitário do custo.", "danger")
                                custo_ok = False
                            valor_lancar = valor_unit
                            impostos = {"irrf": 0, "pis": 0, "cofins": 0, "csll": 0, "iss": 0, "retido": 0, "liquido": valor_unit}

                        def _inserir_custo(data_ref, valor_ref, parcela_n=1, parcelas_t=1, grupo=None):
                            cursor.execute(
                                """
                                INSERT INTO financeiro_custos (
                                    descricao, categoria, valor, data_custo, tipo, forma, parcelas, parcela_num,
                                    grupo_id, data_inicio, data_fim, valor_unitario, valor_bruto, prestador,
                                    reter_federal, reter_iss, aliquota_iss, federal_na_nota, iss_na_nota,
                                    irrf, pis, cofins, csll, iss, ativo
                                ) VALUES (
                                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE
                                )
                                """,
                                (
                                    descricao, categoria, valor_ref, data_ref, tipo, forma, parcelas_t, parcela_n,
                                    grupo, data_ini, data_fim or None, valor_unit, valor_bruto or valor_unit, prestador,
                                    reter_fed, reter_iss, aliq_iss, fed_nota, iss_nota,
                                    impostos["irrf"], impostos["pis"], impostos["cofins"], impostos["csll"], impostos["iss"],
                                ),
                            )

                        if custo_ok:
                            if tipo == "parcelado":
                                grupo = uuid.uuid4().hex[:12]
                                for i in range(n_parc):
                                    _inserir_custo(_add_months(data_ini, i), valor_unit, i + 1, n_parc, grupo)
                                conexao.commit()
                                flash(f"Custo parcelado em {n_parc} vezes de R$ {valor_unit:.2f}.", "success")
                            elif tipo == "recorrente":
                                _inserir_custo(data_ini, valor_unit, 1, 1, uuid.uuid4().hex[:12])
                                conexao.commit()
                                flash("Custo recorrente cadastrado. Ele entra em todos os meses do período.", "success")
                            else:
                                _inserir_custo(data_ini if tipo == "servico" else data_base, valor_lancar, 1, 1, uuid.uuid4().hex[:12])
                                conexao.commit()
                                flash("Custo registrado.", "success")
            except Exception as e:
                conexao.rollback()
                flash(f"❌ Erro ao processar financeiro: {e}", "danger")
            finally:
                conexao.close()
        params_redir = {"mes": mes_redir, "aba": aba_redir}
        if request.form.get("funcionario_id"):
            params_redir["colab"] = request.form.get("funcionario_id")
        if request.form.get("colab_q") or request.args.get("colab_q"):
            params_redir["colab_q"] = request.form.get("colab_q") or request.args.get("colab_q")
        return redirect(url_for("pagina_financeiro", **params_redir))

    lancamentos, alunos, professores_detalhes = [], [], []
    custos_mes = []
    totais = {
        "recebido": 0.0,
        "pendente": 0.0,
        "atrasado": 0.0,
        "folha_pagamento": 0.0,
        "tributos": 0.0,
        "liquido": 0.0,
        "custos": 0.0,
        "custos_compras": 0.0,
        "custos_servicos": 0.0,
    }
    totais_folha = {"bruto": 0.0, "liquido": 0.0, "encargos": 0.0, "custo_escola": 0.0, "inss_patronal": 0.0, "fgts": 0.0}
    apuracao_simples = None
    apuracao_pis_cofins = None
    apuracao_presumido = None
    nome_escola = "Gestão Escolar"

    busca = request.args.get("busca", "").strip()
    status_filtro = request.args.get("status", "").strip()
    aba = request.args.get("aba") or "resumo"
    
    mes_filtro = request.args.get("mes", "").strip()
    if not mes_filtro:
        mes_filtro = datetime.now().strftime('%Y-%m')

    conexao = obter_conexao()
    regime_tributario = "lucro_presumido" # Padrão caso não encontre

    if conexao:
        try:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                # BUSCA O REGIME TRIBUTÁRIO CONFIGURADO NO BANCO[cite: 5]
                cursor.execute("SELECT nome_escola, regime_tributario FROM configuracoes WHERE id = 1;")
                config_regime = cursor.fetchone()
                nome_escola = "Gestão Escolar"
                if config_regime:
                    if config_regime.get("regime_tributario"):
                        regime_tributario = config_regime["regime_tributario"]
                    if config_regime.get("nome_escola"):
                        nome_escola = config_regime["nome_escola"]

                # 1. Atualiza faturas vencidas para 'Atrasado' globalmente[cite: 5]
                cursor.execute(
                    """
                    UPDATE financeiro_mensalidades 
                    SET status = 'Atrasado' 
                    WHERE status = 'Pendente' AND data_vencimento < CURRENT_DATE;
                    """
                )
                conexao.commit()

                # 2. Totais filtrados pelo mês de vencimento[cite: 5]
                cursor.execute(
                    """
                    SELECT 
                        COALESCE(SUM(CASE WHEN status = 'Pago' THEN valor::numeric ELSE 0 END), 0) AS recebido,
                        COALESCE(SUM(CASE WHEN status = 'Pendente' THEN valor::numeric ELSE 0 END), 0) AS pendente,
                        COALESCE(SUM(CASE WHEN status = 'Atrasado' THEN valor::numeric ELSE 0 END), 0) AS atrasado
                    FROM financeiro_mensalidades
                    WHERE TO_CHAR(data_vencimento, 'YYYY-MM') = %s;
                    """,
                    (mes_filtro,)
                )
                resumo_mensalidades = cursor.fetchone()
                if resumo_mensalidades:
                    totais["recebido"] = float(resumo_mensalidades["recebido"])
                    totais["pendente"] = float(resumo_mensalidades["pendente"])
                    totais["atrasado"] = float(resumo_mensalidades["atrasado"])

                # 3. Folha de pagamento por tipo de contrato
                professores_detalhes, totais_folha = montar_folha_contratos(cursor, regime_tributario, mes_filtro)
                totais["folha_pagamento"] = totais_folha["custo_escola"]

                custos_mes = listar_custos_do_mes(cursor, mes_filtro)
                resumo_custos = resumir_custos_operacionais(custos_mes)
                totais["custos_compras"] = resumo_custos["compras"]
                totais["custos_servicos"] = resumo_custos["servicos"]
                totais["custos"] = resumo_custos["custos"]

                apuracao_simples = None
                apuracao_pis_cofins = None
                apuracao_presumido = None
                receita_mes_bruta = receita_do_mes(cursor, mes_filtro)

                if regime_tributario == "simples_nacional":
                    apuracao_simples, _colabs_fator_r = calcular_apuracao_simples(cursor, mes_filtro)
                    totais["tributos"] = apuracao_simples["das"]
                    totais["receita_bruta_mes"] = apuracao_simples["receita_mes"]
                    totais["liquido"] = totais["recebido"] - totais["folha_pagamento"] - totais["tributos"] - totais["custos"]
                elif regime_tributario == "lucro_real":
                    apuracao_pis_cofins = apurar_pis_cofins(receita_mes_bruta, "lucro_real")
                    totais["tributos"] = 0.0
                    totais["receita_bruta_mes"] = receita_mes_bruta
                    totais["liquido"] = totais["recebido"] - totais["folha_pagamento"] - totais["custos"]
                else:
                    colaboradores_folha, _folha_cheia = montar_folha_colaboradores(cursor)
                    apuracao_presumido = apurar_lucro_presumido(receita_mes_bruta, colaboradores_folha)
                    totais["tributos"] = apuracao_presumido["tributos"]
                    totais["receita_bruta_mes"] = receita_mes_bruta
                    totais["liquido"] = totais["recebido"] - totais["folha_pagamento"] - totais["tributos"] - totais["custos"]

                # Restante das consultas de lançamentos...[cite: 5]
                query_lancamentos = """
                    SELECT f.id, f.aluno_id, a.nome_completo, f.descricao, f.valor, f.data_vencimento, 
                           f.data_pagamento, f.status, f.forma_pagamento
                    FROM financeiro_mensalidades f
                    LEFT JOIN alunos a ON f.aluno_id = a.id
                    WHERE TO_CHAR(f.data_vencimento, 'YYYY-MM') = %s
                """
                params = [mes_filtro]

                if busca:
                    query_lancamentos += " AND a.nome_completo ILIKE %s"
                    params.append(f"%{busca}%")

                if status_filtro:
                    query_lancamentos += " AND f.status = %s"
                    params.append(status_filtro)

                query_lancamentos += " ORDER BY f.data_vencimento DESC;"

                cursor.execute(query_lancamentos, params)
                lancamentos = cursor.fetchall()

                cursor.execute("SELECT id, nome_completo, valor_mensalidade FROM alunos ORDER BY nome_completo ASC;")
                alunos = cursor.fetchall()
        finally:
            conexao.close()

    colab_q = request.args.get("colab_q", "").strip()
    colab_id = request.args.get("colab", type=int)
    colaboradores_busca = professores_detalhes or []
    if colab_q:
        termo_c = colab_q.lower()
        colaboradores_busca = [
            p for p in colaboradores_busca
            if termo_c in (p.get("nome_completo") or "").lower()
            or termo_c in (p.get("cargo") or "").lower()
        ]
    colaborador_sel = next((p for p in (professores_detalhes or []) if p.get("id") == colab_id), None)

    return render_template(
        "financeiro.html",
        lancamentos=lancamentos,
        alunos=alunos,
        professores_detalhes=professores_detalhes,
        totais_folha=totais_folha,
        custos_mes=custos_mes,
        aba=aba,
        totais=totais,
        busca=busca,
        status=status_filtro,
        regime_atual=regime_tributario,
        mes_atual=mes_filtro,
        data_hoje=datetime.now().strftime('%Y-%m-%d'),
        apuracao_simples=apuracao_simples,
        apuracao_pis_cofins=apuracao_pis_cofins,
        apuracao_presumido=apuracao_presumido,
        nome_escola=nome_escola,
        mes_label=nome_mes_extenso(mes_filtro),
        colab_q=colab_q,
        colab_id=colab_id,
        colaboradores_busca=colaboradores_busca,
        colaborador_sel=colaborador_sel,
    )

@app.route("/financeiro/excluir/<int:id>", methods=["POST"])
def excluir_financeiro(id):
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    conexao = obter_conexao()
    if conexao:
        try:
            with conexao.cursor() as cursor:
                cursor.execute("DELETE FROM financeiro_mensalidades WHERE id = %s;", (id,))
                conexao.commit()
                flash("🗑️ Cobrança excluída com sucesso!", "success")
        except Exception as e:
            conexao.rollback()
            flash(f"❌ Erro ao excluir cobrança: {e}", "danger")
        finally:
            conexao.close()
    return redirect(url_for("pagina_financeiro"))


@app.route("/financeiro/relatorio-tributario")
def relatorio_tributario():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    mes_filtro = request.args.get("mes", "").strip() or datetime.now().strftime("%Y-%m")
    conexao = obter_conexao()
    if not conexao:
        flash("❌ Sem conexão com o banco para gerar o relatório.", "danger")
        return redirect(url_for("pagina_financeiro", mes=mes_filtro))

    try:
        with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT nome_escola, regime_tributario FROM configuracoes WHERE id = 1;")
            config = cursor.fetchone() or {}
            regime = config.get("regime_tributario") or "lucro_presumido"
            escola = config.get("nome_escola") or "Gestão Escolar"
            mes_label = nome_mes_extenso(mes_filtro)

            if regime == "simples_nacional":
                apuracao, colaboradores = calcular_apuracao_simples(cursor, mes_filtro)
                receitas_mes = listar_lancamentos_mes(cursor, mes_filtro)
                buffer = pdf_simples_nacional(
                    escola, mes_label, regime, apuracao, colaboradores, receitas_mes
                )
                nome_arquivo = f"relatorio_simples_fator_r_{mes_filtro}.pdf"
            else:
                cursor.execute(
                    """
                    SELECT
                        COALESCE(SUM(CASE WHEN status = 'Pago' THEN valor::numeric ELSE 0 END), 0) AS recebido,
                        COALESCE(SUM(CASE WHEN status = 'Pendente' THEN valor::numeric ELSE 0 END), 0) AS pendente,
                        COALESCE(SUM(CASE WHEN status = 'Atrasado' THEN valor::numeric ELSE 0 END), 0) AS atrasado
                    FROM financeiro_mensalidades
                    WHERE TO_CHAR(data_vencimento, 'YYYY-MM') = %s;
                    """,
                    (mes_filtro,),
                )
                resumo = cursor.fetchone() or {}
                colaboradores, folha_mes = montar_folha_colaboradores(cursor)
                receita_mes = receita_do_mes(cursor, mes_filtro)
                pis_cofins = apurar_pis_cofins(receita_mes, regime)
                totais = {
                    "recebido": float(resumo.get("recebido") or 0),
                    "pendente": float(resumo.get("pendente") or 0),
                    "atrasado": float(resumo.get("atrasado") or 0),
                    "folha_pagamento": folha_mes,
                    "receita_bruta_mes": receita_mes,
                    "tributos": pis_cofins["total"] if regime == "lucro_presumido" else 0.0,
                }
                recebidos = listar_lancamentos_mes(cursor, mes_filtro, "Pago")
                pendentes = listar_lancamentos_mes(cursor, mes_filtro, "Pendente")
                atrasados = listar_lancamentos_mes(cursor, mes_filtro, "Atrasado")
                resumo_custos = resumir_custos_operacionais(listar_custos_do_mes(cursor, mes_filtro))
                totais["custos_compras"] = resumo_custos["compras"]
                totais["custos_servicos"] = resumo_custos["servicos"]
                totais["custos"] = resumo_custos["custos"]
                if regime == "lucro_presumido":
                    apuracao_p = apurar_lucro_presumido(receita_mes, colaboradores)
                    totais["tributos"] = apuracao_p["tributos"]
                    totais["folha_pagamento"] = apuracao_p["folha_total"]
                    buffer = pdf_lucro_presumido(
                        escola, mes_label, regime, apuracao_p, totais, recebidos
                    )
                    nome_arquivo = f"relatorio_lucro_presumido_{mes_filtro}.pdf"
                else:
                    buffer = pdf_lucro_real(
                        escola,
                        mes_label,
                        regime,
                        totais,
                        recebidos,
                        pendentes,
                        atrasados,
                        colaboradores,
                        pis_cofins,
                    )
                    nome_arquivo = f"relatorio_receitas_pagamentos_{mes_filtro}.pdf"
    finally:
        conexao.close()

    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=nome_arquivo,
    )


@app.route("/financeiro/pdf-folha")
def relatorio_pdf_folha():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    mes_filtro = request.args.get("mes") or datetime.now().strftime("%Y-%m")
    garantir_tabelas_folha()
    conexao = obter_conexao()
    if not conexao:
        flash("❌ Sem conexão com o banco.", "danger")
        return redirect(url_for("pagina_financeiro", mes=mes_filtro, aba="folha"))
    try:
        with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT nome_escola, regime_tributario FROM configuracoes WHERE id = 1;")
            cfg = cursor.fetchone() or {}
            regime = cfg.get("regime_tributario") or "lucro_presumido"
            itens, totais = montar_folha_contratos(cursor, regime, mes_filtro)
            buffer = pdf_folha_pagamento(
                cfg.get("nome_escola") or "Gestão Escolar",
                nome_mes_extenso(mes_filtro),
                regime,
                itens,
                totais,
            )
        return send_file(
            buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"folha_{mes_filtro}.pdf",
        )
    finally:
        conexao.close()


@app.route("/contracheque")
def contracheque():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    mes_filtro = request.args.get("mes") or datetime.now().strftime("%Y-%m")
    garantir_tabelas_folha()
    conexao = obter_conexao()
    item = None
    escola = "Gestão Escolar"
    if conexao:
        try:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT nome_escola, regime_tributario FROM configuracoes WHERE id = 1;")
                cfg = cursor.fetchone() or {}
                escola = cfg.get("nome_escola") or escola
                regime = cfg.get("regime_tributario") or "lucro_presumido"
                fid = session.get("funcionario_id")
                if not fid and pode_modulo(session.get("usuario_papel"), "financeiro"):
                    fid = request.args.get("funcionario_id", type=int)
                if fid:
                    cursor.execute("SELECT * FROM funcionarios WHERE id = %s", (fid,))
                    func = cursor.fetchone()
                    if func:
                        ano, mes = parse_mes(mes_filtro)
                        item = calcular_folha_pessoa(dict(func), regime, ano, mes)
                        item["rotulo_contrato"] = rotulo_contrato(item["tipo_contrato"])
        finally:
            conexao.close()
    return render_template(
        "contracheque.html",
        item=item,
        mes_atual=mes_filtro,
        mes_label=nome_mes_extenso(mes_filtro),
        escola=escola,
    )


@app.route("/contracheque/pdf", methods=["GET", "POST"])
def pdf_contracheque_rota():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    mes_filtro = request.values.get("mes") or datetime.now().strftime("%Y-%m")
    garantir_tabelas_folha()
    conexao = obter_conexao()
    if not conexao:
        return redirect(url_for("contracheque", mes=mes_filtro))
    try:
        with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT nome_escola, regime_tributario FROM configuracoes WHERE id = 1;")
            cfg = cursor.fetchone() or {}
            regime = cfg.get("regime_tributario") or "lucro_presumido"
            fid = session.get("funcionario_id")
            if not fid and pode_modulo(session.get("usuario_papel"), "financeiro"):
                fid = request.values.get("funcionario_id", type=int)
            if not fid:
                flash("❌ Nenhum colaborador vinculado a este usuário.", "danger")
                return redirect(url_for("contracheque"))
            cursor.execute("SELECT * FROM funcionarios WHERE id = %s", (fid,))
            func = cursor.fetchone()
            if not func:
                flash("❌ Colaborador não encontrado.", "danger")
                return redirect(url_for("contracheque"))
            ano, mes = parse_mes(mes_filtro)
            item = calcular_folha_pessoa(dict(func), regime, ano, mes)
            item["rotulo_contrato"] = rotulo_contrato(item["tipo_contrato"])
            buffer = pdf_contracheque(cfg.get("nome_escola") or "Gestão Escolar", nome_mes_extenso(mes_filtro), item)
        nome_arq = f"contracheque_{fid}_{mes_filtro}.pdf"
        if request.args.get("enviar") or request.method == "POST":
            destinos = []
            if email_valido((func or {}).get("email")):
                destinos.append(func["email"])
            if not destinos:
                flash("O colaborador não tem e-mail válido cadastrado.", "danger")
                return redirect(url_for("contracheque", mes=mes_filtro))
            enviar_email(
                destinos,
                f"Contra-cheque {nome_mes_extenso(mes_filtro)}",
                "Segue em anexo o contra-cheque do período.",
                [{"nome": nome_arq, "dados": bytes_pdf(buffer)}],
            )
            flash(f"Contra-cheque enviado para {', '.join(destinos)}.", "success")
            return redirect(request.referrer or url_for("contracheque", mes=mes_filtro))
        return send_file(
            buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"contracheque_{mes_filtro}.pdf",
        )
    finally:
        conexao.close()


@app.route("/configuracoes", methods=["GET", "POST"])
def pagina_configuracoes():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    garantir_tabelas_folha()

    conexao = obter_conexao()
    if request.method == "POST":
        acao = request.form.get("acao")
        
        if acao == "salvar_parametros":
            nome_escola = request.form.get("nome_escola")
            ano_letivo = request.form.get("ano_letivo")
            email_contato = request.form.get("email_contato")
            regime_tributario = request.form.get("regime_tributario")
            smtp_host = (request.form.get("smtp_host") or "").strip()
            smtp_port = int(request.form.get("smtp_port") or 587)
            smtp_user = (request.form.get("smtp_user") or "").strip()
            smtp_password = request.form.get("smtp_password") or ""
            smtp_from = (request.form.get("smtp_from") or smtp_user or email_contato or "").strip()
            smtp_tls = request.form.get("smtp_tls") != "0"
            
            if conexao:
                try:
                    with conexao.cursor() as cursor:
                        if not smtp_password:
                            cursor.execute("SELECT smtp_password FROM configuracoes WHERE id = 1")
                            atual = cursor.fetchone() or {}
                            smtp_password = (atual.get("smtp_password") if isinstance(atual, dict) else None) or ""
                        cursor.execute(
                            """
                            INSERT INTO configuracoes (
                                id, nome_escola, ano_letivo, email_contato, regime_tributario,
                                smtp_host, smtp_port, smtp_user, smtp_password, smtp_from, smtp_tls
                            )
                            VALUES (1, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (id) DO UPDATE 
                            SET nome_escola = EXCLUDED.nome_escola,
                                ano_letivo = EXCLUDED.ano_letivo,
                                email_contato = EXCLUDED.email_contato,
                                regime_tributario = EXCLUDED.regime_tributario,
                                smtp_host = EXCLUDED.smtp_host,
                                smtp_port = EXCLUDED.smtp_port,
                                smtp_user = EXCLUDED.smtp_user,
                                smtp_password = CASE
                                    WHEN EXCLUDED.smtp_password = '' THEN configuracoes.smtp_password
                                    ELSE EXCLUDED.smtp_password
                                END,
                                smtp_from = EXCLUDED.smtp_from,
                                smtp_tls = EXCLUDED.smtp_tls;
                            """,
                            (
                                nome_escola, ano_letivo, email_contato, regime_tributario,
                                smtp_host, smtp_port, smtp_user, smtp_password, smtp_from, smtp_tls,
                            ),
                        )
                        conexao.commit()
                        flash("✅ Parâmetros salvos com sucesso!", "success")
                except Exception as e:
                    conexao.rollback()
                    flash(f"❌ Erro ao salvar parâmetros: {e}", "danger")
                finally:
                    conexao.close()

        return redirect(url_for("pagina_configuracoes"))

    config = {}
    if conexao:
        try:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                try:
                    cursor.execute("SELECT * FROM configuracoes WHERE id = 1;")
                    config = cursor.fetchone() or {}
                except Exception:
                    conexao.rollback()
        finally:
            conexao.close()

    return render_template("configuracoes.html", config=config)

@app.route("/excluir_usuario_sistema/<int:id>", methods=["POST"])
def excluir_usuario_sistema(id):
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    conexao = obter_conexao()
    if conexao:
        try:
            with conexao.cursor() as cursor:
                cursor.execute("UPDATE funcionarios SET usuario_id = NULL WHERE usuario_id = %s;", (id,))
                cursor.execute("DELETE FROM usuarios WHERE id = %s;", (id,))
                conexao.commit()
                flash("Usuário excluído com sucesso.", "success")
        except Exception as e:
            conexao.rollback()
            flash(f"Erro ao excluir usuário: {e}", "danger")
        finally:
            conexao.close()
    return redirect(url_for("gerenciar_usuarios"))

@app.route("/turmas/excluir/<int:turma_id>", methods=["POST"])
def excluir_turma(turma_id):
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    conexao = obter_conexao()
    if conexao:
        try:
            with conexao.cursor() as cursor:
                # Opcional: remover vínculos antes ou deixar em cascata
                cursor.execute("DELETE FROM turmas WHERE id = %s;", (turma_id,))
                conexao.commit()
                flash("✅ Turma excluída com sucesso!", "success")
        except Exception as e:
            conexao.rollback()
            flash(f"❌ Erro ao excluir turma: {e}", "danger")
        finally:
            conexao.close()

    return redirect(url_for("pagina_pedagogico"))


@app.route("/financeiro/cobranca/<int:cobranca_id>/pdf")
def cobranca_pdf(cobranca_id):
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    conexao = obter_conexao()
    if not conexao:
        flash("Sem conexão com o banco.", "danger")
        return redirect(url_for("pagina_financeiro"))
    try:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT nome_escola FROM configuracoes WHERE id = 1")
            cfg = cursor.fetchone() or {}
            cursor.execute(
                """
                SELECT f.*, a.nome_completo, a.matricula, a.email AS aluno_email
                FROM financeiro_mensalidades f
                LEFT JOIN alunos a ON a.id = f.aluno_id
                WHERE f.id = %s
                """,
                (cobranca_id,),
            )
            cobranca = cursor.fetchone()
        if not cobranca:
            flash("Cobrança não encontrada.", "danger")
            return redirect(url_for("pagina_financeiro"))
        buffer = pdf_cobranca_mensalidade(cfg.get("nome_escola") or "Gestão Escolar", cobranca, cobranca)
        return send_file(
            buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"cobranca_{cobranca_id}.pdf",
        )
    finally:
        conexao.close()


@app.route("/financeiro/cobranca/<int:cobranca_id>/email", methods=["POST"])
def cobranca_email(cobranca_id):
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    garantir_tabelas_folha()
    destino = url_for("pagina_financeiro", aba="receitas")
    conexao = obter_conexao()
    if not conexao:
        flash("Sem conexão com o banco.", "danger")
        return redirect(destino)
    try:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT nome_escola FROM configuracoes WHERE id = 1")
            cfg = cursor.fetchone() or {}
            cursor.execute(
                """
                SELECT f.*, a.nome_completo, a.matricula
                FROM financeiro_mensalidades f
                LEFT JOIN alunos a ON a.id = f.aluno_id
                WHERE f.id = %s
                """,
                (cobranca_id,),
            )
            cobranca = cursor.fetchone()
            if not cobranca:
                flash("Cobrança não encontrada.", "danger")
                return redirect(destino)
            destinos = emails_contato_aluno(cursor, cobranca.get("aluno_id")) if cobranca.get("aluno_id") else []
            buffer = pdf_cobranca_mensalidade(cfg.get("nome_escola") or "Gestão Escolar", cobranca, cobranca)
            lista = enviar_email(
                destinos,
                f"Cobrança / boleto — {cobranca.get('descricao') or 'Mensalidade'}",
                "Segue o aviso de cobrança da mensalidade em PDF. Em caso de dúvida, fale com a secretaria.",
                [{"nome": f"cobranca_{cobranca_id}.pdf", "dados": bytes_pdf(buffer)}],
            )
        flash(f"Cobrança enviada para {', '.join(lista)}.", "success")
    except Exception as e:
        flash(f"Não foi possível enviar o e-mail: {e}", "danger")
    finally:
        conexao.close()
    return redirect(request.referrer or url_for("pagina_financeiro", aba="receitas"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=not ambiente_producao())
