import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from flask import Flask, Response, flash, g, redirect, render_template, request, url_for, session, send_file
from markupsafe import escape
from werkzeug.exceptions import HTTPException
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
    diagnostico_envio,
    normalizar_email,
    aviso_caixa_entrada,
)
from psycopg2.extras import RealDictCursor, execute_values
from alunos import (
    cadastrar_aluno,
    cadastrar_alunos_lote,
    importar_planilha_alunos,
    aplicar_aluno_simples,
    salvar_alunos_simples,
    ler_planilha_alunos_simples,
    _mapa_turmas,
    parse_data_livre,
    listar_alunos,
    atualizar_responsavel,
    deletar_responsavel,
    buscar_cpf_repetido,
    mensagem_cpf_repetido,
)
from simples_nacional import (
    montar_quadro_simples,
    upsert_competencia,
    importar_competencias,
    gravar_importacao,
    carregar_sistema,
    janela_competencias,
    receita_sistema_mes,
    resumo_emitido_e_caixa,
    listar_recebimentos_mes,
    folha_sistema_mes,
    listar_folha_janela,
    _linhas_arquivo,
    parse_moeda_livre,
)
from database import obter_conexao, garantir_tabelas_pedagogicas, garantir_tabelas_folha, definir_banco_escola, limpar_banco_escola, resetar_tenant, erro_conexao_atual, host_postgres_configurado
from nfse import (
    anexar_ultima_nota,
    cancelar_nota,
    consultar_nota,
    definir_emissao_habilitada,
    emissao_nfse_ligada,
    emitir_cobranca_plataforma,
    documento_da_nota,
    emitir_mensalidade,
    faturamento_das_notas,
    listar_alunos_nfse,
    listar_mensalidades_emissao,
    ler_config_plataforma_tela,
    listar_cobrancas_plataforma,
    listar_notas_escola,
    listar_notas_plataforma,
    preparar_config_tela,
    salvar_config_escola,
    salvar_config_plataforma,
    salvar_tomador_escola,
    substituir_nota,
    valor_na_competencia,
)
from tributacao import (
    apurar_simples,
    apurar_pis_cofins,
    apurar_lucro_presumido,
    meses_do_trimestre,
    normalizar_regime_apuracao,
    folha_mensal_fator_r,
    janela_12_meses_anteriores,
    parse_mes,
    br_money,
)
from relatorios_pdf import (
    pdf_boletim,
    pdf_contracheque,
    pdf_historico_periodo,
    pdf_folha_pagamento,
    pdf_custos,
    pdf_lucro_presumido,
    pdf_lucro_real,
    pdf_simples_nacional,
    pdf_extrato_pgdas,
    pdf_calculo_rbt12,
    pdf_calculo_fs12,
    pdf_calculo_fator_r,
    pdf_cobranca_mensalidade,
    pdf_composicao_mensalidades,
    pdf_composicao_custos,
    pdf_caixa_restante,
    pdf_regime_apuracao,
    pdf_regime_detalhado,
    pdf_prova,
    pdf_lista_alunos,
    pdf_lista_equipe,
    pdf_turmas,
    pdf_notas_fiscais,
    pdf_auditoria,
    pdf_pasta_professor,
)
from folha import (
    calcular_folha_pessoa,
    rotulo_contrato,
    impostos_nota,
    contrato_vigente,
    dia_pagamento_valido,
    aplicar_ajuste_competencia,
)
from permissoes import (
    AREAS_ACESSO,
    TELAS_PLANO,
    classificar_requisicao,
    endpoint_no_plano,
    modulo_no_plano,
    pode_acao,
    pode_endpoint,
    pode_modulo,
    pode_requisicao,
    normalizar_papel,
    rotulo_papel,
    CARGOS_ESCOLA,
    cargos_escola_planos,
    permissoes_efetivas,
    permissoes_padrao,
    padroes_por_papel,
)
from auditoria import (
    classificar_movimento,
    listar_auditoria,
    modulo_da_rota,
    montar_detalhe,
    registrar_auditoria,
)
from plataforma import (
    buscar_admin_plataforma,
    buscar_escola_por_email,
    buscar_escola_por_token,
    cadastrar_escola,
    atualizar_email_admin_escola,
    definir_status_escola,
    definir_senha_escola_por_admin,
    excluir_escola,
    regenerar_convite_escola,
    buscar_escola_por_id,
    definir_pacote_escola,
    preparar_cobranca_escolas,
    salvar_regra_cobranca_escola,
    listar_pacotes,
    salvar_pacote,
    painel_financeiro_plataforma,
    gerar_cobrancas_plataforma,
    atualizar_cobrancas_abertas_plataforma,
    criar_cobranca_plataforma,
    editar_cobranca_plataforma,
    baixar_cobrancas_plataforma,
    tirar_baixa_cobrancas_plataforma,
    excluir_cobranca_plataforma,
    criar_custo_plataforma,
    excluir_custo_plataforma,
    telas_contratadas,
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
    garantir_login_colaborador,
    usuario_da_escola,
    validar_otp,
    ativar_escola as concluir_ativacao_escola,
)
import calendar as calendario_lib
from datetime import datetime, date, timedelta
import json
import hashlib
import secrets
import threading
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


def _pagina_erro(e):
    import traceback
    traceback.print_exc()
    caminho = "/login"
    try:
        caminho = request.path or "/login"
    except Exception:
        pass
    detalhe = escape(str(e) or "erro interno")
    destino = escape(caminho)
    return (
        "<!doctype html><html lang=pt-br><meta charset=utf-8>"
        "<title>Erro</title>"
        "<body style='font-family:sans-serif;max-width:520px;margin:40px auto;line-height:1.5'>"
        "<h1>O site teve um erro neste passo</h1>"
        f"<p style='color:#64748b;font-size:0.9rem'>{detalhe}</p>"
        f"<p><a href='{destino}'>Tentar de novo</a> · <a href='/login'>Login</a></p>"
        "</body></html>"
    ), 200


@app.errorhandler(500)
def _erro_interno(e):
    return _pagina_erro(e)


@app.errorhandler(Exception)
def _qualquer_erro(e):
    if isinstance(e, HTTPException) and e.code != 500:
        return e
    return _pagina_erro(e)


@app.route("/ping")
@app.route("/health")
def ping():
    try:
        _processar_contracheques_todas_escolas()
    except Exception as e:
        print(f"ping folha: {e}")
    return "ok", 200, {"Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store"}

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


def _acrescimos_form():
    juros = _parse_moeda(request.form.get("juros_percentual"), 0.0)
    multa = _parse_moeda(request.form.get("multa_valor"), 0.0)
    if juros < 0:
        juros = 0.0
    if multa < 0:
        multa = 0.0
    return round(juros, 4), round(multa, 2)


def _parse_moeda(bruto, padrao=0.0):
    if bruto is None:
        return padrao
    s = str(bruto).strip().replace("R$", "").replace("\xa0", "").replace(" ", "")
    if not s:
        return padrao
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    elif s.count(".") == 1:
        esquerda, direita = s.split(".")
        if len(direita) == 3 and esquerda.replace("-", "").isdigit():
            s = esquerda + direita
    try:
        return float(s)
    except ValueError:
        return padrao


def _float_form(nome, padrao=0.0):
    return _parse_moeda(request.form.get(nome), padrao)


def _moeda_br(valor, vazio_se_zero=False):
    try:
        n = float(valor or 0)
    except (TypeError, ValueError):
        n = 0.0
    if vazio_se_zero and n <= 0:
        return ""
    sinal = "-" if n < 0 else ""
    inteiro, frac = f"{abs(n):.2f}".split(".")
    grupos = []
    while inteiro:
        grupos.append(inteiro[-3:])
        inteiro = inteiro[:-3]
    return sinal + ".".join(reversed(grupos)) + "," + frac


@app.template_filter("moeda")
def moeda_exibicao(valor):
    return _moeda_br(valor)


@app.template_filter("moeda_campo")
def moeda_campo(valor):
    return _moeda_br(valor, vazio_se_zero=True)


@app.template_filter("url_foto")
def url_foto(valor):
    texto = (valor or "").strip().replace("\\", "/")
    if not texto:
        return ""
    if texto.startswith("midia/"):
        try:
            return url_for("servir_midia", midia_id=int(texto.split("/", 1)[1]))
        except (TypeError, ValueError):
            return ""
    if texto.startswith(("http://", "https://", "/")):
        return texto
    return url_for("static", filename=texto.lstrip("/"))


@app.template_filter("hora_h")
def hora_h(valor):
    try:
        n = float(valor or 0)
    except (TypeError, ValueError):
        return 0
    return int(n)


@app.template_filter("hora_m")
def hora_m(valor):
    try:
        n = float(valor or 0)
    except (TypeError, ValueError):
        return 0
    minutos = int(round((n - int(n)) * 60))
    if minutos >= 60:
        return 0
    opcoes = (0, 15, 30, 45, 50)
    return min(opcoes, key=lambda x: abs(x - minutos))


def _formacao_do_form():
    flags = [item.strip() for item in request.form.getlist("formacao_flag") if (item or "").strip()]
    curso = (request.form.get("formacao_curso") or request.form.get("formacao") or "").strip()
    partes = []
    for item in flags:
        if item not in partes:
            partes.append(item)
    if curso and curso not in partes:
        partes.append(curso)
    return " | ".join(partes)[:150]


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
        "admin": "Administrador(a)",
        "supervisor": "Supervisor(a) pedagógico(a)",
        "financeiro": "Financeiro",
        "direcao": "Diretor(a)",
        "secretaria": "Secretário(a) escolar",
        "professor": "Professor(a)",
        "funcionario": "Auxiliar",
    }
    return mapa.get(normalizar_papel(papel), "Auxiliar")


def _disciplina_visivel(valor):
    texto = (valor or "").strip()
    if not texto or texto.lower() in {"gerais", "geral", "n/a", "-", "nao se aplica", "não se aplica"}:
        return ""
    return texto


def _especialidade_form():
    texto = (request.form.get("especialidade") or "").strip()
    if texto.lower() in {"gerais", "geral", "n/a", "-"}:
        return ""
    return texto[:150]


def _permissoes_do_form(papel):
    if not any(str(chave).startswith("perm_") for chave in request.form.keys()):
        return None
    dados = {}
    for area, _rotulo in AREAS_ACESSO:
        dados[area] = {
            acao: request.form.get(f"perm_{area}_{acao}") == "1"
            for acao in ("acessar", "ver", "alterar", "excluir")
        }
    return permissoes_efetivas(papel, dados)


def _cargo_do_form(papel=None):
    cargo = (request.form.get("cargo") or "").strip()
    if cargo == "Outro":
        cargo = (request.form.get("cargo_outro") or "").strip()
    if cargo:
        return cargo[:150]
    return _cargo_do_papel(papel)


def _data_iso(valor):
    if not valor:
        return ""
    if hasattr(valor, "strftime"):
        return valor.strftime("%Y-%m-%d")
    return str(valor)[:10]


def _salvar_foto(campo, pasta="fotos"):
    arquivo = request.files.get(campo) if request.files else None
    if not arquivo or not (arquivo.filename or "").strip():
        return None
    nome = secure_filename(arquivo.filename)
    ext = nome.rsplit(".", 1)[-1].lower() if "." in nome else "jpg"
    if ext not in {"jpg", "jpeg", "png", "webp", "gif"}:
        raise ValueError("A foto precisa ser JPG, PNG ou WEBP.")
    dados = arquivo.read()
    if not dados:
        raise ValueError("A foto chegou vazia. Escolha o arquivo de novo.")
    if len(dados) > 5 * 1024 * 1024:
        raise ValueError("A foto precisa ter no máximo 5 MB.")
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp", "gif": "image/gif"}[ext]
    from database import _aplicar_schema, _nome_banco_atual, obter_conexao_nova
    schema = _nome_banco_atual(master=False)
    if not schema:
        raise ValueError("Não foi possível guardar a foto: sessão sem banco da escola.")
    conexao = obter_conexao_nova()
    try:
        _aplicar_schema(conexao, schema)
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS midia (
                    id SERIAL PRIMARY KEY,
                    mime VARCHAR(40) NOT NULL,
                    dados BYTEA NOT NULL
                )
                """
            )
            cursor.execute(
                "INSERT INTO midia (mime, dados) VALUES (%s, %s) RETURNING id",
                (mime, dados),
            )
            row = cursor.fetchone() or {}
            mid = row.get("id") if isinstance(row, dict) else row[0]
        conexao.commit()
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Não foi possível guardar a foto: {e}") from e
    finally:
        conexao.close()
    return f"midia/{mid}"


def _salvar_midia(campo, extensoes):
    arquivo = request.files.get(campo) if request.files else None
    if not arquivo or not (arquivo.filename or "").strip():
        return None
    nome = secure_filename(arquivo.filename)
    ext = nome.rsplit(".", 1)[-1].lower() if "." in nome else ""
    if ext not in extensoes:
        raise ValueError("Envie um arquivo PDF.")
    dados = arquivo.read()
    if not dados:
        raise ValueError("O arquivo chegou vazio.")
    if len(dados) > 8 * 1024 * 1024:
        raise ValueError("O arquivo precisa ter no máximo 8 MB.")
    mime = "application/pdf" if ext == "pdf" else "application/octet-stream"
    from database import _aplicar_schema, _nome_banco_atual, obter_conexao_nova
    schema = _nome_banco_atual(master=False)
    if not schema:
        raise ValueError("Sessão sem banco da escola.")
    conexao = obter_conexao_nova()
    try:
        _aplicar_schema(conexao, schema)
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS midia (
                    id SERIAL PRIMARY KEY,
                    mime VARCHAR(40) NOT NULL,
                    dados BYTEA NOT NULL
                )
                """
            )
            cursor.execute(
                "INSERT INTO midia (mime, dados) VALUES (%s, %s) RETURNING id",
                (mime, dados),
            )
            row = cursor.fetchone() or {}
            mid = row.get("id") if isinstance(row, dict) else row[0]
        conexao.commit()
    finally:
        conexao.close()
    return mid


@app.route("/midia/<int:midia_id>")
def servir_midia(midia_id):
    if "usuario_id" not in session or not session.get("escola_db"):
        return "", 404
    conexao = obter_conexao()
    if not conexao:
        return "", 404
    try:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT mime, dados FROM midia WHERE id = %s", (midia_id,))
            row = cursor.fetchone()
    except Exception:
        return "", 404
    finally:
        conexao.close()
    if not row or not row.get("dados"):
        return "", 404
    resp = app.response_class(bytes(row["dados"]), mimetype=row.get("mime") or "image/jpeg")
    resp.headers["Cache-Control"] = "private, max-age=86400"
    return resp


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


def _texto_planilha(valor):
    if valor is None:
        return ""
    if hasattr(valor, "strftime"):
        return valor.strftime("%Y-%m-%d")
    return str(valor).strip()


def _coluna_planilha(cabecalho, *chaves):
    for chave in chaves:
        for i, nome in enumerate(cabecalho):
            if nome == chave:
                return i
    for chave in chaves:
        if len(chave) < 4:
            continue
        for i, nome in enumerate(cabecalho):
            if chave in nome:
                return i
    return None


def _celula_planilha(row, idx):
    if idx is None or idx >= len(row):
        return ""
    return _texto_planilha(row[idx])


def _tipo_custo_planilha(texto):
    s = (texto or "").strip().lower()
    if any(k in s for k in ("servi", "nfs")):
        return "servico"
    if "parcel" in s:
        return "parcelado"
    if any(k in s for k in ("recorr", "mensal", "fixo")):
        return "recorrente"
    return "avista"


def _forma_custo_planilha(texto):
    s = (texto or "").strip().lower()
    if "cart" in s or "crédito" in s or "credito" in s:
        return "cartao"
    if "financ" in s:
        return "financiamento"
    if "boleto" in s:
        return "boleto"
    return "dinheiro"


def _flag_planilha(texto, padrao=False):
    s = (texto or "").strip().lower()
    if not s:
        return padrao
    if s in ("1", "sim", "s", "true", "yes", "retido", "calcular"):
        return True
    if s in ("0", "nao", "não", "n", "false", "no", "nao se aplica", "não se aplica"):
        return False
    return padrao


def _gravar_custo(cursor, dados):
    tipo = dados.get("tipo") or "avista"
    if tipo not in ("avista", "recorrente", "parcelado", "servico"):
        tipo = "avista"
    descricao = (dados.get("descricao") or "").strip() or "Custo"
    categoria = (dados.get("categoria") or "").strip() or "operacional"
    data_base = dados.get("data") or datetime.now().strftime("%Y-%m-%d")
    data_ini = dados.get("data_inicio") or data_base
    data_fim = dados.get("data_fim") or None
    forma = dados.get("forma") or "dinheiro"
    prestador = (dados.get("prestador") or "").strip() or None
    try:
        n_parc = max(int(float(dados.get("parcelas") or 1)), 1)
    except (TypeError, ValueError):
        n_parc = 1
    valor_unit = float(dados.get("valor") or 0)
    valor_bruto = float(dados.get("valor_bruto") or 0) or valor_unit
    reter_fed = bool(dados.get("reter_federal"))
    reter_iss = bool(dados.get("reter_iss"))
    aliq_iss = float(dados.get("aliquota_iss") or 5)
    fed_nota = dados.get("federal_na_nota", True)
    iss_nota = dados.get("iss_na_nota", True)
    impostos = impostos_nota(
        valor_bruto or valor_unit,
        reter_fed,
        reter_iss,
        aliq_iss,
        float(dados.get("aliq_irrf") or 1.5),
        float(dados.get("aliq_pis") or 0.65),
        float(dados.get("aliq_cofins") or 3),
        float(dados.get("aliq_csll") or 1),
    )
    if tipo == "servico":
        if not (valor_bruto or valor_unit):
            raise ValueError(f"Informe o valor de '{descricao}'.")
        desconto_nota = 0.0
        if reter_fed and fed_nota:
            desconto_nota += impostos["irrf"] + impostos["pis"] + impostos["cofins"] + impostos["csll"]
        if reter_iss and iss_nota:
            desconto_nota += impostos["iss"]
        valor_lancar = round((valor_bruto or valor_unit) - desconto_nota, 2)
    else:
        if not valor_unit:
            raise ValueError(f"Informe o valor de '{descricao}'.")
        valor_lancar = valor_unit
        impostos = {"irrf": 0, "pis": 0, "cofins": 0, "csll": 0, "iss": 0}

    def _inserir(data_ref, valor_ref, parcela_n=1, parcelas_t=1, grupo=None):
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
                grupo, data_ini, data_fim, valor_unit, valor_bruto or valor_unit, prestador,
                reter_fed, reter_iss, aliq_iss, bool(fed_nota), bool(iss_nota),
                impostos["irrf"], impostos["pis"], impostos["cofins"], impostos["csll"], impostos["iss"],
            ),
        )

    if tipo == "parcelado":
        grupo = uuid.uuid4().hex[:12]
        for i in range(n_parc):
            _inserir(_add_months(data_ini, i), valor_unit, i + 1, n_parc, grupo)
        return n_parc
    if tipo == "recorrente":
        _inserir(data_ini, valor_unit, 1, 1, uuid.uuid4().hex[:12])
        return 1
    _inserir(data_ini if tipo == "servico" else data_base, valor_lancar, 1, 1, uuid.uuid4().hex[:12])
    return 1


def importar_planilha_custos(arquivo):
    linhas = _linhas_arquivo(arquivo)
    if not linhas:
        return []
    cab = [str(c or "").strip().lower() for c in linhas[0]]
    col = {
        "tipo": _coluna_planilha(cab, "tipo_custo", "tipo"),
        "descricao": _coluna_planilha(cab, "descricao", "descrição", "historico", "histórico"),
        "categoria": _coluna_planilha(cab, "categoria"),
        "valor_bruto": _coluna_planilha(cab, "valor_bruto", "bruto"),
        "valor": _coluna_planilha(cab, "valor_unitario", "valor", "mensal"),
        "data_fim": _coluna_planilha(cab, "data_fim", "fim"),
        "data_inicio": _coluna_planilha(cab, "data_inicio", "inicio", "início"),
        "data": _coluna_planilha(cab, "data_custo", "data", "vencimento"),
        "parcelas": _coluna_planilha(cab, "parcelas", "n_parcelas"),
        "forma": _coluna_planilha(cab, "forma", "pagamento"),
        "prestador": _coluna_planilha(cab, "prestador", "fornecedor"),
        "reter_federal": _coluna_planilha(cab, "reter_federal", "federais"),
        "reter_iss": _coluna_planilha(cab, "reter_iss"),
        "aliquota_iss": _coluna_planilha(cab, "aliquota_iss", "aliq_iss"),
        "federal_na_nota": _coluna_planilha(cab, "federal_na_nota"),
        "iss_na_nota": _coluna_planilha(cab, "iss_na_nota"),
    }
    if col["descricao"] is None and col["valor"] is None:
        raise ValueError("A planilha precisa das colunas descrição e valor.")
    itens = []
    for row in linhas[1:]:
        if not row or not any(_texto_planilha(c) for c in row):
            continue
        descricao = _celula_planilha(row, col["descricao"])
        valor = parse_moeda_livre(_celula_planilha(row, col["valor"]))
        valor_bruto = parse_moeda_livre(_celula_planilha(row, col["valor_bruto"]))
        if not descricao and not valor and not valor_bruto:
            continue
        data = parse_data_livre(_celula_planilha(row, col["data"]))
        inicio = parse_data_livre(_celula_planilha(row, col["data_inicio"])) or data
        itens.append({
            "tipo": _tipo_custo_planilha(_celula_planilha(row, col["tipo"])),
            "descricao": descricao or "Custo",
            "categoria": _celula_planilha(row, col["categoria"]) or "operacional",
            "valor": valor or valor_bruto,
            "valor_bruto": valor_bruto or valor,
            "data": data or inicio,
            "data_inicio": inicio or data,
            "data_fim": parse_data_livre(_celula_planilha(row, col["data_fim"])),
            "parcelas": _celula_planilha(row, col["parcelas"]) or 1,
            "forma": _forma_custo_planilha(_celula_planilha(row, col["forma"])),
            "prestador": _celula_planilha(row, col["prestador"]),
            "reter_federal": _flag_planilha(_celula_planilha(row, col["reter_federal"])),
            "reter_iss": _flag_planilha(_celula_planilha(row, col["reter_iss"])),
            "aliquota_iss": parse_moeda_livre(_celula_planilha(row, col["aliquota_iss"])) or 5,
            "federal_na_nota": _flag_planilha(_celula_planilha(row, col["federal_na_nota"]), True),
            "iss_na_nota": _flag_planilha(_celula_planilha(row, col["iss_na_nota"]), True),
        })
    return itens


def _rotulo_turno_mensalidade(turnos):
    mapa = {
        "manha": "manhã",
        "tarde": "tarde",
        "noite": "noite",
        "hibrido": "híbrido (manhã e tarde)",
        "híbrido": "híbrido (manhã e tarde)",
        "integral": "híbrido (manhã e tarde)",
        "dois": "híbrido (manhã e tarde)",
        "tarde_noite": "tarde e noite",
    }
    return mapa.get((turnos or "manha").strip().lower(), "manhã")


def _gerar_mensalidades_lote(cursor, alunos_ok):
    ids = [row["aluno_id"] for row in alunos_ok if row.get("aluno_id")]
    if not ids:
        return 0
    cursor.execute(
        """
        SELECT aluno_id, TO_CHAR(data_vencimento, 'YYYY-MM') AS comp
        FROM financeiro_mensalidades
        WHERE aluno_id = ANY(%s)
        """,
        (ids,),
    )
    existentes = set()
    for row in cursor.fetchall() or []:
        existentes.add((row["aluno_id"], row["comp"]))
    linhas = []
    for row in alunos_ok:
        dados = row.get("aluno") or {}
        valor = float(dados.get("valor_mensalidade") or 0)
        if valor <= 0 or not row.get("aluno_id"):
            continue
        inicio = dados.get("contrato_inicio") or datetime.now().strftime("%Y-%m-%d")
        meses = max(int(dados.get("contrato_meses") or 12), 1)
        turnos = dados.get("turnos_mensalidade") or "manha"
        rotulo = _rotulo_turno_mensalidade(turnos)
        for i in range(meses):
            venc = _add_months(inicio, i)
            comp = venc.strftime("%Y-%m")
            if (row["aluno_id"], comp) in existentes:
                continue
            descricao = f"Mensalidade {venc.strftime('%m/%Y')} ({i + 1}/{meses}) · {rotulo}"
            linhas.append((row["aluno_id"], descricao, valor, venc, "Pendente", turnos, i + 1))
    if not linhas:
        return 0
    execute_values(
        cursor,
        """
        INSERT INTO financeiro_mensalidades
            (aluno_id, descricao, valor, data_vencimento, status, turno, parcela_contrato)
        VALUES %s
        """,
        linhas,
        page_size=500,
    )
    return len(linhas)


def _gerar_mensalidades_contrato(cursor, aluno_id, valor, inicio, meses, turnos, descricao_base="Mensalidade", forcar=False):
    if not aluno_id or not valor or valor <= 0:
        return 0
    meses = max(int(meses or 1), 1)
    turnos = turnos or "manha"
    geradas = 0
    for i in range(meses):
        venc = _add_months(inicio, i)
        competencia = venc.strftime("%Y-%m")
        if not forcar:
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
    cid = (_CFG.get("GOOGLE_CLIENT_ID") or "").strip()
    secret = (_CFG.get("GOOGLE_CLIENT_SECRET") or "").strip()
    google_login = False
    smtp_ok = bool(
        (_CFG.get("BREVO_API_KEY") or _CFG.get("RESEND_API_KEY") or _CFG.get("SENDGRID_API_KEY"))
        or (_CFG.get("SMTP_PASSWORD") and _CFG.get("SMTP_USER"))
        or session.get("gmail_envio")
    )
    login_publico = (request.endpoint or "") in {
        "login", "logout", "ping", "login_google", "login_google_callback",
        "login_codigo", "login_senha", "ativar_escola", "login_conectar_gmail", "login_esqueci_senha",
        "plataforma_escolas", "plataforma_autorizar_gmail", "plataforma_voltar",
    }
    if not smtp_ok and not login_publico and not session.get("super_admin"):
        smtp_ok = bool(_CFG.get("BREVO_API_KEY")) or (
            (not ambiente_producao()) and bool(_CFG.get("SMTP_PASSWORD") and _CFG.get("SMTP_USER"))
        )
    def _no_plano(modulo):
        return modulo_no_plano(modulo, session.get("escola_telas"))

    return {
        "papel_atual": papel,
        "rotulo_papel": rotulo_papel(papel),
        "nfse_liberada": bool(getattr(g, "nfse_liberada", False)),
        "pode": lambda modulo: (modulo != "nfse" or getattr(g, "nfse_liberada", False)) and _no_plano(modulo) and pode_acao(papel, modulo, "acessar", session.get("permissoes")),
        "pode_alterar": lambda modulo: (modulo != "nfse" or getattr(g, "nfse_liberada", False)) and _no_plano(modulo) and pode_acao(papel, modulo, "alterar", session.get("permissoes")),
        "pode_excluir": lambda modulo: (modulo != "nfse" or getattr(g, "nfse_liberada", False)) and _no_plano(modulo) and pode_acao(papel, modulo, "excluir", session.get("permissoes")),
        "smtp_ok": smtp_ok,
        "google_login": google_login,
        "super_admin": bool(session.get("super_admin")),
        "escola_nome": session.get("escola_nome"),
        "origem_plataforma": bool(session.get("origem_plataforma")),
        "cargos_escola": CARGOS_ESCOLA,
        "cargos_escola_planos": cargos_escola_planos(),
        "rotulo_turno": _rotulo_turno_mensalidade,
    }


@app.before_request
def isolar_banco_da_requisicao():
    resetar_tenant()
    if session.get("escola_db") and not session.get("super_admin"):
        definir_banco_escola(session.get("escola_db"))


@app.teardown_request
def encerrar_tenant(_erro):
    resetar_tenant()


_AUDITORIA_IGNORAR = {
    None, "login", "logout", "static", "ping", "login_google", "login_google_callback",
    "login_codigo", "login_senha", "ativar_escola", "login_conectar_gmail", "login_esqueci_senha",
    "pagina_auditoria", "relatorio_tributario", "relatorio_pdf_folha", "relatorio_pdf_custos",
    "relatorio_cartao_financeiro",
    "cobranca_pdf", "cobranca_email", "memoria_simples_pdf", "extrato_pgdas_pdf", "boletim_pdf", "pdf_contracheque_rota",
    "modelo_alunos_csv", "modelo_custos_csv", "modelo_simples_csv", "modelo_alunos_financeiro_csv",
}


def _flash_de_erro():
    for item in session.get("_flashes") or []:
        if isinstance(item, (list, tuple)) and item and item[0] == "danger":
            return True
    return False


@app.after_request
def gravar_auditoria(resposta):
    try:
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return resposta
        if resposta.status_code >= 400:
            return resposta
        endpoint = request.endpoint
        if endpoint in _AUDITORIA_IGNORAR or (endpoint or "").endswith("_pdf"):
            return resposta
        if not session.get("usuario_id") and not session.get("super_admin"):
            return resposta
        if _flash_de_erro():
            return resposta
        acao = (request.form.get("acao") or "").strip()
        tipo, rotulo = classificar_movimento(endpoint, acao)
        detalhe = montar_detalhe(request.form, request.files)
        assunto = ""
        for chave in ("nome_completo", "nome", "aluno_nome", "descricao", "titulo", "email"):
            assunto = (request.form.get(chave) or "").strip()
            if assunto:
                break
        resumo = f"{rotulo}: {assunto}" if assunto else rotulo
        escola_id = session.get("escola_id")
        if not escola_id:
            bruto = (request.form.get("escola_id") or "").strip()
            if bruto.isdigit():
                escola_id = int(bruto)
        registrar_auditoria(
            escola_id,
            session.get("escola_nome") or ("Plataforma" if session.get("super_admin") else ""),
            session.get("usuario_nome"),
            session.get("usuario_email"),
            tipo,
            modulo_da_rota(endpoint),
            resumo,
            detalhe,
        )
    except Exception as erro:
        print(f"auditoria: {erro}")
    return resposta


_ROTAS_NFSE = {
    "pagina_notas_fiscais",
    "nfse_emitir",
    "nfse_cancelar",
    "nfse_substituir",
    "nfse_consultar",
    "nfse_lote",
    "nfse_xml",
    "nfse_danfse",
    "relatorio_nfse_pdf",
}


@app.before_request
def proteger_rotas():
    endpoint = request.endpoint
    publicos = {
        None, "login", "logout", "static", "ping", "login_google", "login_google_callback",
        "login_codigo", "login_senha", "ativar_escola", "login_conectar_gmail", "login_esqueci_senha",
    }
    if endpoint in publicos:
        g.nfse_liberada = False
        return None
    try:
        g.nfse_liberada = emissao_nfse_ligada()
    except Exception:
        g.nfse_liberada = False
    if session.get("super_admin"):
        if endpoint not in {"plataforma_escolas", "plataforma_autorizar_gmail", "logout", "plataforma_voltar"}:
            return redirect(url_for("plataforma_escolas"))
        return None
    if endpoint == "plataforma_voltar" and session.get("origem_plataforma"):
        return None
    if session.get("escola_id") and session.get("escola_bloqueada"):
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
    acao_form = request.form.get("acao") if request.method == "POST" else ""
    if isinstance(session.get("escola_telas"), list) and not endpoint_no_plano(endpoint, session.get("escola_telas"), acao_form):
        flash("Esta tela não está no pacote contratado por esta escola.", "danger")
        return redirect(url_for("dashboard"))
    if endpoint in _ROTAS_NFSE and not g.nfse_liberada:
        flash("A geração de NFS-e está desligada.", "danger")
        return redirect(url_for("dashboard"))
    if not pode_requisicao(papel, endpoint, request.method, session.get("permissoes"), acao_form):
        tipo, _modulo = classificar_requisicao(endpoint, request.method, acao_form)
        if tipo == "excluir":
            flash("❌ Sem permissão para excluir nesta área.", "danger")
        else:
            flash("❌ Sem permissão para acessar ou alterar esta área.", "danger")
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


def _endereco_do_form():
    rua = limpar_campo("rua") or limpar_campo("logradouro")
    numero = limpar_campo("numero")
    bairro = limpar_campo("bairro")
    cidade = limpar_campo("cidade")
    estado = (limpar_campo("estado") or "")[:2] or None
    cep = limpar_campo("cep")
    if rua or cidade or cep:
        partes = []
        if rua:
            partes.append(f"{rua}, {numero}" if numero else rua)
        if bairro:
            partes.append(bairro)
        if cidade and estado:
            partes.append(f"{cidade}/{estado}")
        elif cidade or estado:
            partes.append(cidade or estado)
        if cep:
            partes.append(cep)
        return " — ".join(partes)
    return limpar_campo("endereco")


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


def _garantir_folha_ajustes(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS folha_ajustes (
            funcionario_id INT NOT NULL,
            competencia VARCHAR(7) NOT NULL,
            horas_extras NUMERIC(10,2) DEFAULT 0,
            horas_extras_100 NUMERIC(10,2) DEFAULT 0,
            valor_hora_extra NUMERIC(12,2) DEFAULT 0,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (funcionario_id, competencia)
        )
        """
    )
    cursor.execute(
        "ALTER TABLE funcionarios ADD COLUMN IF NOT EXISTS horas_extras_100 NUMERIC(10,2) DEFAULT 0"
    )


def _mapa_ajustes_folha(cursor, competencia):
    if not competencia:
        return {}
    _garantir_folha_ajustes(cursor)
    cursor.execute(
        """
        SELECT funcionario_id, horas_extras, horas_extras_100, valor_hora_extra
        FROM folha_ajustes
        WHERE competencia = %s
        """,
        (competencia,),
    )
    return {row["funcionario_id"]: dict(row) for row in (cursor.fetchall() or [])}


def _ajuste_folha(cursor, funcionario_id, competencia):
    if not funcionario_id or not competencia:
        return None
    _garantir_folha_ajustes(cursor)
    cursor.execute(
        """
        SELECT horas_extras, horas_extras_100, valor_hora_extra
        FROM folha_ajustes
        WHERE funcionario_id = %s AND competencia = %s
        """,
        (funcionario_id, competencia),
    )
    return cursor.fetchone()


def _func_com_ajuste(cursor, func, competencia):
    dados = dict(func or {})
    return aplicar_ajuste_competencia(dados, _ajuste_folha(cursor, dados.get("id"), competencia))


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
        SELECT *
        FROM funcionarios
        WHERE COALESCE(ativo, TRUE) = TRUE
        ORDER BY nome_completo
        """
    )
    funcionarios = list(cursor.fetchall() or [])
    ajustes = _mapa_ajustes_folha(cursor, mes_filtro)
    itens = []
    totais = {
        "bruto": 0.0,
        "liquido": 0.0,
        "encargos": 0.0,
        "custo_escola": 0.0,
        "inss_patronal": 0.0,
        "fgts": 0.0,
    }
    for row in funcionarios:
        dados = aplicar_ajuste_competencia(dict(row), ajustes.get(row.get("id")))
        if not contrato_vigente(dados, ano, mes):
            continue
        calc = calcular_folha_pessoa(dados, regime, ano, mes)
        calc["rotulo_contrato"] = rotulo_contrato(calc["tipo_contrato"])
        try:
            calc["valor_hora_extra_cadastro"] = float(dados.get("valor_hora_extra") or 0)
        except (TypeError, ValueError):
            calc["valor_hora_extra_cadastro"] = 0.0
        calc["reter_federal"] = row.get("reter_federal")
        calc["reter_iss"] = row.get("reter_iss")
        calc["aliquota_iss"] = row.get("aliquota_iss") or 5
        calc["email"] = row.get("email")
        calc["data_inicio_contrato"] = _data_iso(row.get("data_inicio_contrato") or row.get("data_contratacao"))
        calc["data_fim_contrato"] = _data_iso(row.get("data_fim_contrato"))
        calc["enviar_contracheque"] = True if row.get("enviar_contracheque") is None else bool(row.get("enviar_contracheque"))
        calc["foto_url"] = row.get("foto_url")
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


def _registrar_folha_item(cursor, item, competencia):
    import json
    cursor.execute(
        """
        INSERT INTO folha_itens (
            funcionario_id, competencia, tipo_contrato, bruto, dsr,
            inss_funcionario, irrf, liquido, encargos, custo_escola, detalhes
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (funcionario_id, competencia) DO UPDATE SET
            tipo_contrato = EXCLUDED.tipo_contrato,
            bruto = EXCLUDED.bruto,
            dsr = EXCLUDED.dsr,
            inss_funcionario = EXCLUDED.inss_funcionario,
            irrf = EXCLUDED.irrf,
            liquido = EXCLUDED.liquido,
            encargos = EXCLUDED.encargos,
            custo_escola = EXCLUDED.custo_escola,
            detalhes = EXCLUDED.detalhes
        """,
        (
            item.get("id"),
            competencia,
            item.get("tipo_contrato"),
            item.get("bruto") or 0,
            item.get("dsr") or 0,
            item.get("inss_funcionario") or 0,
            item.get("irrf") or 0,
            item.get("liquido") or 0,
            item.get("encargos") or 0,
            item.get("custo_escola") or 0,
            json.dumps({
                "horas_extras": item.get("horas_extras") or 0,
                "horas_extras_100": item.get("horas_extras_100") or 0,
                "adicional_he": item.get("adicional_he") or 0,
                "adicional_he_50": item.get("adicional_he_50") or 0,
                "adicional_he_100": item.get("adicional_he_100") or 0,
                "dsr_he": item.get("dsr_he") or 0,
                "dia_pagamento": item.get("dia_pagamento") or 5,
            }),
        ),
    )


def _montar_pdf_contracheque(escola, mes_filtro, func, regime):
    ano, mes = parse_mes(mes_filtro)
    item = calcular_folha_pessoa(dict(func), regime, ano, mes)
    item["rotulo_contrato"] = rotulo_contrato(item["tipo_contrato"])
    buffer = pdf_contracheque(escola or "Gestão Escolar", nome_mes_extenso(mes_filtro), item)
    return item, buffer


def _emails_colaborador(func, cursor=None):
    destinos = []
    vistos = set()
    candidatos = [func.get("email")]
    if cursor:
        uid = func.get("usuario_id")
        if uid:
            cursor.execute("SELECT email FROM usuarios WHERE id = %s", (uid,))
            row = cursor.fetchone() or {}
            candidatos.append(row.get("email") if isinstance(row, dict) else None)
        email_func = (func.get("email") or "").strip()
        if email_func:
            cursor.execute(
                "SELECT email FROM usuarios WHERE LOWER(email) = LOWER(%s) LIMIT 1",
                (email_func,),
            )
            row = cursor.fetchone() or {}
            candidatos.append(row.get("email") if isinstance(row, dict) else None)
    for bruto in candidatos:
        if email_valido(bruto):
            n = normalizar_email(bruto)
            if n not in vistos:
                vistos.add(n)
                destinos.append(n)
    return destinos


def _enviar_contracheque_pessoa(func, regime, mes_filtro, escola, destinos=None):
    destinos = list(destinos or [])
    if not destinos:
        destinos = _emails_colaborador(func)
    if not destinos:
        raise RuntimeError(f"{func.get('nome_completo') or 'Colaborador'} sem e-mail válido para receber o contra-cheque.")
    item, buffer = _montar_pdf_contracheque(escola, mes_filtro, func, regime)
    nome_arq = f"contracheque_{func.get('id')}_{mes_filtro}.pdf"
    nome = item.get("nome_completo") or func.get("nome_completo") or "colaborador"
    enviar_email(
        destinos,
        f"Contra-cheque {nome_mes_extenso(mes_filtro)} — {nome}",
        (
            f"Olá, {nome}.\n\n"
            f"Segue em anexo o contra-cheque de {nome_mes_extenso(mes_filtro)}.\n"
            f"Escola: {escola}.\n"
        ),
        [{"nome": nome_arq, "dados": bytes_pdf(buffer)}],
    )
    return destinos


def _processar_contracheques_escola(hoje=None, enviar=True, limite=3):
    hoje = hoje or date.today()
    competencia = hoje.strftime("%Y-%m")
    garantir_tabelas_folha()
    conexao = obter_conexao()
    if not conexao:
        return 0, 0
    enviados = gerados = 0
    try:
        with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT nome_escola, regime_tributario, email_contato FROM configuracoes WHERE id = 1")
            cfg = cursor.fetchone() or {}
            if cfg.get("email_contato"):
                try:
                    from flask import has_request_context, session as sess
                    if has_request_context():
                        sess["escola_email_contato"] = cfg["email_contato"]
                except Exception:
                    pass
            regime = cfg.get("regime_tributario") or "simples_nacional"
            escola = cfg.get("nome_escola") or "Gestão Escolar"
            ajustes = _mapa_ajustes_folha(cursor, competencia)
            cursor.execute("SELECT * FROM funcionarios WHERE COALESCE(ativo, TRUE) = TRUE")
            for func in cursor.fetchall() or []:
                dados = aplicar_ajuste_competencia(dict(func), ajustes.get(func.get("id")))
                if not contrato_vigente(dados, hoje.year, hoje.month):
                    continue
                if dia_pagamento_valido(dados.get("dia_pagamento")) != hoje.day:
                    continue
                item = calcular_folha_pessoa(dados, regime, hoje.year, hoje.month)
                item["rotulo_contrato"] = rotulo_contrato(item["tipo_contrato"])
                _registrar_folha_item(cursor, item, competencia)
                gerados += 1
                if not enviar or enviados >= limite:
                    continue
                if dados.get("enviar_contracheque") is False:
                    continue
                cursor.execute(
                    "SELECT 1 FROM folha_envios WHERE funcionario_id = %s AND competencia = %s",
                    (dados.get("id"), competencia),
                )
                if cursor.fetchone():
                    continue
                try:
                    destinos = _emails_colaborador(dados, cursor)
                    _enviar_contracheque_pessoa(dados, regime, competencia, escola, destinos=destinos)
                    cursor.execute(
                        """
                        INSERT INTO folha_envios (funcionario_id, competencia)
                        VALUES (%s, %s)
                        ON CONFLICT (funcionario_id, competencia) DO NOTHING
                        """,
                        (dados.get("id"), competencia),
                    )
                    enviados += 1
                except Exception as e:
                    print(f"contracheque auto {dados.get('id')}: {e}")
        conexao.commit()
    except Exception as e:
        print(f"processar contracheques: {e}")
        try:
            conexao.rollback()
        except Exception:
            pass
    finally:
        conexao.close()
    return gerados, enviados


def _processar_contracheques_todas_escolas():
    from plataforma import listar_escolas
    for escola in listar_escolas() or []:
        if escola.get("ativo") is False:
            continue
        schema = escola.get("db_nome")
        if not schema:
            continue
        token = None
        try:
            token = definir_banco_escola(schema)
            _processar_contracheques_escola()
        except Exception as e:
            print(f"folha escola {schema}: {e}")
        finally:
            if token:
                try:
                    limpar_banco_escola(token)
                except Exception:
                    resetar_tenant()
            else:
                resetar_tenant()


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


def regime_apuracao_escola(cursor):
    try:
        cursor.execute("SELECT regime_apuracao FROM configuracoes WHERE id = 1")
        row = cursor.fetchone() or {}
        return normalizar_regime_apuracao(row.get("regime_apuracao"))
    except Exception:
        return "competencia"


def receita_do_mes(cursor, mes_filtro, regime_apuracao=None):
    if regime_apuracao is None:
        regime_apuracao = regime_apuracao_escola(cursor)
    return receita_sistema_mes(cursor, mes_filtro, regime_apuracao)


def _titulos_base_imposto(cursor, mes_filtro, regime_apuracao):
    if regime_apuracao == "caixa":
        return listar_recebimentos_mes(cursor, mes_filtro)
    cursor.execute(
        """
        SELECT f.data_pagamento, f.data_vencimento, f.descricao, f.forma_pagamento, f.valor,
               a.nome_completo
        FROM financeiro_mensalidades f
        LEFT JOIN alunos a ON a.id = f.aluno_id
        WHERE TO_CHAR(f.data_vencimento, 'YYYY-MM') = %s
          AND LOWER(COALESCE(f.status, '')) NOT IN ('cancelado', 'cancelada')
        ORDER BY f.data_vencimento, a.nome_completo
        """,
        (mes_filtro,),
    )
    return cursor.fetchall() or []


def _mensalidades_do_cartao(cursor, mes_filtro, status):
    cursor.execute(
        """
        SELECT a.nome_completo, f.descricao, f.valor, f.data_vencimento,
               f.data_pagamento, f.forma_pagamento, f.status
        FROM financeiro_mensalidades f
        LEFT JOIN alunos a ON a.id = f.aluno_id
        WHERE TO_CHAR(f.data_vencimento, 'YYYY-MM') = %s
          AND f.status = %s
        ORDER BY f.data_vencimento, a.nome_completo
        """,
        (mes_filtro, status),
    )
    return cursor.fetchall() or []


def _listas_regime(cursor, mes_filtro):
    colunas = """
        a.nome_completo, a.matricula, f.descricao, f.parcela_contrato, f.valor,
        COALESCE(f.juros_percentual, 0) AS juros_percentual,
        COALESCE(f.juros_valor, 0) AS juros_valor,
        COALESCE(f.multa_valor, 0) AS multa_valor,
        f.data_vencimento, f.data_pagamento, f.forma_pagamento, f.status
    """
    cursor.execute(
        f"""
        SELECT {colunas}
        FROM financeiro_mensalidades f
        LEFT JOIN alunos a ON a.id = f.aluno_id
        WHERE LOWER(COALESCE(f.status, '')) = 'pago'
          AND f.data_pagamento IS NOT NULL
          AND TO_CHAR(f.data_pagamento, 'YYYY-MM') = %s
        ORDER BY f.data_pagamento, a.nome_completo
        """,
        (mes_filtro,),
    )
    recebidos = cursor.fetchall() or []
    cursor.execute(
        f"""
        SELECT {colunas}
        FROM financeiro_mensalidades f
        LEFT JOIN alunos a ON a.id = f.aluno_id
        WHERE TO_CHAR(f.data_vencimento, 'YYYY-MM') = %s
          AND f.status = 'Pendente'
        ORDER BY f.data_vencimento, a.nome_completo
        """,
        (mes_filtro,),
    )
    pendentes = cursor.fetchall() or []
    cursor.execute(
        f"""
        SELECT {colunas}
        FROM financeiro_mensalidades f
        LEFT JOIN alunos a ON a.id = f.aluno_id
        WHERE f.data_vencimento < CURRENT_DATE
          AND TO_CHAR(f.data_vencimento, 'YYYY-MM') <= %s
          AND LOWER(COALESCE(f.status, '')) NOT IN ('pago', 'cancelado', 'cancelada')
        ORDER BY f.data_vencimento, a.nome_completo
        """,
        (mes_filtro,),
    )
    atrasados = cursor.fetchall() or []
    return recebidos, pendentes, atrasados


def _porque_custo(item):
    valor = float(item.get("valor") or 0)
    efeito, tipo = _efeito_caixa_custo(item)
    data = item.get("data_custo") or item.get("data_inicio") or ""
    if hasattr(data, "strftime"):
        data = data.strftime("%d/%m/%Y")
    else:
        data = str(data)[:10]
    rotulo_tipo = {
        "avista": "À vista",
        "recorrente": "Recorrente no mês",
        "parcelado": "Parcela",
        "servico": "Serviço",
    }.get(tipo, tipo)
    partes = [rotulo_tipo]
    if item.get("categoria"):
        partes.append(str(item.get("categoria")))
    if item.get("prestador"):
        partes.append(str(item.get("prestador")))
    if data:
        partes.append(data)
    partes.append(f"valor lançado {br_money(valor)}")
    if abs(efeito - valor) > 0.004:
        partes.append(
            "impostos que não estavam na nota somam "
            + br_money(efeito - valor)
            + "; o cartão usa o lançado mais esses impostos"
        )
    elif tipo == "servico":
        partes.append("os impostos já estavam na nota, então o cartão usa o valor lançado")
    return " · ".join(partes), efeito


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
    regime = regime_apuracao_escola(cursor)
    quadro = montar_quadro_simples(cursor, mes_filtro, regime)
    n_meses = quadro["meses_validos"] or 1
    colaboradores, _folha_mes = montar_folha_colaboradores(cursor)
    apuracao = apurar_simples(quadro["rbt12"], quadro["fs12"], n_meses, quadro["receita_mes"])
    ano, mes = parse_mes(mes_filtro)
    inicio_janela, fim_janela = janela_12_meses_anteriores(ano, mes)
    apuracao["inicio_janela"] = inicio_janela
    apuracao["fim_janela"] = fim_janela
    apuracao["inicio_escola"] = quadro.get("primeira")
    apuracao["quadro"] = quadro
    apuracao["regime_apuracao"] = regime
    return apuracao, colaboradores


def nome_mes_extenso(mes_filtro):
    meses = [
        "janeiro", "fevereiro", "março", "abril", "maio", "junho",
        "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
    ]
    ano, mes = parse_mes(mes_filtro)
    return f"{meses[mes - 1].capitalize()}/{ano}"


def _id_funcionario_da_sessao(email=None):
    """Liga o login ao cadastro da equipe pelo usuário ou pelo mesmo e-mail."""
    email = (email or session.get("usuario_email") or "").strip().lower()
    uid = session.get("usuario_id")
    conexao = obter_conexao()
    if not conexao:
        return None
    try:
        with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
            row = None
            if uid:
                cursor.execute(
                    "SELECT id FROM funcionarios WHERE usuario_id = %s ORDER BY id LIMIT 1",
                    (uid,),
                )
                row = cursor.fetchone()
            if not row and email:
                cursor.execute(
                    "SELECT id FROM funcionarios WHERE LOWER(TRIM(email)) = %s ORDER BY id LIMIT 1",
                    (email,),
                )
                row = cursor.fetchone()
                if row and uid:
                    cursor.execute(
                        "UPDATE funcionarios SET usuario_id = %s WHERE id = %s AND usuario_id IS NULL",
                        (uid, row["id"]),
                    )
                    conexao.commit()
            return row["id"] if row else None
    except Exception:
        try:
            conexao.rollback()
        except Exception:
            pass
        return None
    finally:
        conexao.close()


def _iniciar_sessao(usuario, email):
    session["usuario_id"] = usuario["id"]
    session["usuario_nome"] = usuario.get("nome") or usuario.get("nome_completo") or email
    session["usuario_papel"] = normalizar_papel(usuario.get("papel") or usuario.get("cargo") or "admin")
    session["usuario_email"] = email
    session["permissoes"] = permissoes_efetivas(session["usuario_papel"], usuario.get("permissoes"))
    session["funcionario_id"] = _id_funcionario_da_sessao(email)


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
    session["escola_email"] = (escola.get("email_admin") or "").strip()
    session["escola_email_contato"] = (escola.get("email_admin") or "").strip()
    session["super_admin"] = False
    if origem_plataforma:
        session["origem_plataforma"] = True
        session["plataforma_email"] = plataforma_email or email_super_admin()
    telas = telas_contratadas(escola)
    if telas is None:
        session.pop("escola_telas", None)
    else:
        session["escola_telas"] = telas
    _iniciar_sessao(usuario, email)


def _usuario_admin_escola(escola):
    token = definir_banco_escola(escola["db_nome"])
    try:
        conexao = obter_conexao()
        if not conexao:
            raise RuntimeError("Não conectou no espaço da escola.")
        try:
            with conexao.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS usuarios (
                        id SERIAL PRIMARY KEY,
                        nome VARCHAR(150) NOT NULL,
                        email VARCHAR(150) UNIQUE NOT NULL,
                        senha VARCHAR(255),
                        papel VARCHAR(40) DEFAULT 'admin'
                    )
                    """
                )
                cursor.execute(
                    "SELECT * FROM usuarios WHERE LOWER(email) = %s",
                    (escola["email_admin"],),
                )
                usuario = cursor.fetchone()
                if not usuario:
                    cursor.execute(
                        "INSERT INTO usuarios (nome, email, senha, papel) VALUES (%s, %s, %s, 'admin') RETURNING *",
                        (escola["nome"], escola["email_admin"], secrets.token_urlsafe(12)),
                    )
                    usuario = cursor.fetchone()
            conexao.commit()
            if not usuario:
                raise RuntimeError("Não foi possível criar o usuário admin da escola.")
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


def _enviar_codigo_acesso(email, finalidade="login"):
    codigo = gerar_otp(email, finalidade)
    session["otp_local"] = codigo
    session["otp_email_ok"] = False
    session["login_email"] = email
    session["otp_finalidade"] = finalidade
    corpo = (
        f"Seu código de confirmação da Gestão Escolar é: {codigo}\n\n"
        "Ele vale por 20 minutos. Use este mesmo código se receber o e-mail mais de uma vez.\n"
        "Se você não pediu este acesso, ignore o e-mail."
    )
    ok, erro = enviar_codigo(email, codigo, "Código de acesso — Gestão Escolar", corpo)
    session["otp_email_ok"] = bool(ok)
    if ok:
        flash(
            "Enviamos um código de 6 dígitos para o seu e-mail. Confira a caixa de entrada e o Spam."
            + aviso_caixa_entrada([email]),
            "success",
        )
    else:
        flash(f"Não foi possível enviar o código por e-mail. ({erro})", "danger")
    return redirect(url_for("login_codigo"))


def _enviar_codigo_colaborador(email, nome):
    codigo = gerar_otp(email, "login_escola")
    corpo = (
        f"Olá, {nome}.\n\n"
        f"Seu acesso à Gestão Escolar foi criado.\n"
        f"Entre em {request.host_url}login com este e-mail: {email}\n"
        f"Código de confirmação: {codigo}\n\n"
        "O código vale por 20 minutos. Na tela de login clique em Continuar e depois em "
        "Esqueci a senha ou Receber código, e informe estes 6 dígitos para criar sua senha.\n"
    )
    return enviar_codigo(email, codigo, "Acesso à Gestão Escolar — código de login", corpo)


def _enviar_codigo_plataforma(email, access_token=None):
    return _enviar_codigo_acesso(email, "login_plataforma")


@app.route("/login/esqueci-senha")
def login_esqueci_senha():
    garantir_plataforma()
    email = session.get("login_email")
    if not email:
        flash("Informe o e-mail na tela inicial.", "danger")
        return redirect(url_for("login"))
    if eh_super_admin(email):
        session["redefinir_senha"] = True
        return _enviar_codigo_acesso(email, "login_plataforma")
    escola = buscar_escola_por_email(email) or localizar_escola_do_email(email)
    if not escola:
        flash("Este e-mail não está cadastrado.", "danger")
        return redirect(url_for("login"))
    session["redefinir_senha_escola"] = True
    return _enviar_codigo_acesso(email, "login_escola")


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
        acoes = request.form.getlist("acao")
        quer_codigo = "codigo" in acoes
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
            email_admin = (escola.get("email_admin") or "").strip().lower()
            if not escola.get("senha_definida") and email_admin == email.strip().lower():
                flash("Esta escola ainda precisa ativar o acesso. O código foi enviado ao e-mail cadastrado.", "danger")
                return redirect(url_for("ativar_escola", token=escola.get("convite_token")))
            if not escola.get("senha_definida"):
                flash("A escola ainda não ativou o acesso. Peça ao administrador da plataforma para concluir o cadastro.", "danger")
                return render_template("login.html")
            login_novo = garantir_login_colaborador(email, escola)
            if quer_codigo or login_novo:
                return _enviar_codigo_acesso(email, "login_escola")
            return redirect(url_for("login_senha"))
        flash(
            "Este e-mail não está na equipe da escola. Cadastre a pessoa em Usuários, com o perfil Professor, "
            "e use o mesmo e-mail iCloud. Não crie uma escola nova para o professor.",
            "danger",
        )
    return render_template("login.html")


@app.route("/login/conectar-gmail", methods=["GET", "POST"])
def login_conectar_gmail():
    try:
        garantir_plataforma()
    except Exception as e:
        print(f"garantir_plataforma: {e}")
    email = (
        request.form.get("email")
        or request.form.get("smtp_user")
        or session.get("login_email")
        or ""
    ).strip()
    if not email:
        flash("Informe o e-mail para receber o código.", "danger")
        return render_template("login_conectar_gmail.html", email="")
    try:
        email = exigencia_email(email, "E-mail")
    except ValueError as e:
        flash(str(e), "danger")
        return render_template("login_conectar_gmail.html", email=email)
    session["login_email"] = email
    if eh_super_admin(email):
        return _enviar_codigo_acesso(email, "login_plataforma")
    escola = buscar_escola_por_email(email) or localizar_escola_do_email(email)
    if escola:
        return _enviar_codigo_acesso(email, "login_escola")
    flash("Informe um e-mail cadastrado para receber o código.", "danger")
    return redirect(url_for("login"))


@app.route("/login/google")
def login_google():
    return redirect(url_for("login_conectar_gmail"))


@app.route("/login/google/callback")
def login_google_callback():
    code = (request.args.get("code") or "").strip()
    if not code:
        flash("Conexão com o Gmail cancelada.", "danger")
        return redirect(url_for("plataforma_escolas") if session.get("super_admin") else url_for("login"))
    if not session.get("super_admin") or request.args.get("state") != session.get("oauth_state"):
        flash("A autorização do Gmail expirou. Entre na plataforma e clique em Conectar Gmail de novo.", "danger")
        return redirect(url_for("login"))
    session.pop("oauth_state", None)
    cred = credenciais_google()
    destino = url_for("login_google_callback", _external=True)
    try:
        import json
        import urllib.parse
        import urllib.request
        corpo = urllib.parse.urlencode(
            {
                "code": code,
                "client_id": (cred.get("client_id") or "").strip(),
                "client_secret": (cred.get("client_secret") or "").strip(),
                "redirect_uri": destino,
                "grant_type": "authorization_code",
            }
        ).encode("utf-8")
        req = urllib.request.Request("https://oauth2.googleapis.com/token", data=corpo, method="POST")
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        refresh = (payload.get("refresh_token") or "").strip()
        if not refresh:
            raise RuntimeError("O Google não devolveu a autorização permanente. Clique em Conectar Gmail de novo.")
        salvar_google_refresh(refresh)
    except Exception as e:
        flash(
            f"Não foi possível conectar o Gmail ({e}). No Google Cloud, a URI de redirecionamento tem que ser exatamente {destino}.",
            "danger",
        )
        return redirect(url_for("plataforma_escolas"))
    flash("Gmail conectado. Hotmail, iCloud e Yahoo passam a receber pelo envio do Google.", "success")
    return redirect(url_for("plataforma_escolas"))


@app.route("/login/codigo", methods=["GET", "POST"])
def login_codigo():
    email = session.get("login_email")
    if not email:
        return redirect(url_for("login"))
    if request.method == "POST":
        codigo = (request.form.get("codigo") or "").strip()
        finalidade = session.get("otp_finalidade") or "login_plataforma"
        if validar_otp(email, codigo, finalidade) or validar_otp(email, codigo):
            session["otp_ok"] = True
            session.pop("otp_local", None)
            if eh_super_admin(email) or finalidade == "login_plataforma":
                session["login_tipo"] = "plataforma"
                session["redefinir_senha"] = True
                flash("Código confirmado. Agora defina a senha de acesso da plataforma.", "success")
            else:
                session["login_tipo"] = "escola"
                session["redefinir_senha_escola"] = True
                flash("Código confirmado. Agora defina a nova senha de acesso.", "success")
            return redirect(url_for("login_senha"))
        flash("Código inválido ou vencido. Use os 6 dígitos enviados ao e-mail.", "danger")
    return render_template(
        "login_codigo.html",
        email=email,
        email_enviado=bool(session.get("otp_email_ok")),
    )


@app.route("/login/senha", methods=["GET", "POST"])
def login_senha():
    email = session.get("login_email")
    if not email:
        return redirect(url_for("login"))
    try:
        return _login_senha(email)
    except Exception as e:
        flash(f"Não foi possível entrar: {e}", "danger")
        return render_template("login_senha.html", email=email, criar=False)


def _login_senha(email):
    criar = False
    if eh_super_admin(email):
        admin = buscar_admin_plataforma(email)
        criar = (not (admin and admin.get("senha"))) or bool(session.get("redefinir_senha"))
        if criar and not session.get("otp_ok"):
            flash("Confirme o código enviado ao e-mail antes de criar ou redefinir a senha.", "danger")
            return redirect(url_for("login_conectar_gmail"))
    elif session.get("redefinir_senha_escola"):
        criar = True
        if not session.get("otp_ok"):
            flash("Confirme o código enviado ao e-mail antes de redefinir a senha.", "danger")
            return redirect(url_for("login_conectar_gmail"))
    if request.method != "POST":
        return render_template("login_senha.html", email=email, criar=criar)
    senha = (request.form.get("senha") or "").strip()
    senha2 = (request.form.get("senha2") or "").strip()
    if criar and eh_super_admin(email):
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
    if criar and session.get("redefinir_senha_escola"):
        if senha != senha2:
            flash("As senhas não coincidem.", "danger")
            return render_template("login_senha.html", email=email, criar=True)
        if len(senha) < 6:
            flash("A senha deve ter pelo menos 6 caracteres.", "danger")
            return render_template("login_senha.html", email=email, criar=True)
        escola = buscar_escola_por_email(email) or localizar_escola_do_email(email)
        if not escola:
            flash("E-mail não encontrado.", "danger")
            return redirect(url_for("login"))
        token = definir_banco_escola(escola["db_nome"])
        try:
            conexao = obter_conexao()
            if not conexao:
                raise RuntimeError("Sem conexão com o banco da escola.")
            with conexao.cursor() as cursor:
                cursor.execute(
                    "UPDATE usuarios SET senha = %s WHERE LOWER(email) = %s",
                    (senha, email),
                )
            conexao.commit()
            conexao.close()
        finally:
            limpar_banco_escola(token)
        session.pop("otp_ok", None)
        session.pop("redefinir_senha_escola", None)
        usuario, escola = usuario_da_escola(email, senha, escola)
        if usuario:
            _entrar_escola(usuario, email, escola)
            return redirect(url_for("dashboard"))
        flash("Senha atualizada. Entre com o e-mail e a nova senha.", "success")
        return redirect(url_for("login_senha"))
    if eh_super_admin(email):
        admin = buscar_admin_plataforma(email)
        armazenada = (admin.get("senha") if admin else "") or ""
        if admin and armazenada.strip() == senha:
            _entrar_plataforma(admin)
            return redirect(url_for("plataforma_escolas"))
        flash("Senha incorreta. Use a senha que você criou neste sistema (não a do Gmail e não 123456, a menos que tenha escolhido essa).", "danger")
        return render_template("login_senha.html", email=email, criar=False)
    escola = buscar_escola_por_email(email) or localizar_escola_do_email(email)
    if not escola:
        flash("E-mail ou senha incorretos.", "danger")
        return render_template("login_senha.html", email=email, criar=False)
    if not escola.get("ativo", True):
        flash("Esta escola está pausada. O acesso está bloqueado.", "danger")
        return redirect(url_for("login"))
    usuario, escola = usuario_da_escola(email, senha, escola)
    if usuario:
        _entrar_escola(usuario, email, escola)
        return redirect(url_for("dashboard"))
    flash("Senha incorreta.", "danger")
    return render_template("login_senha.html", email=email, criar=False)


def _enviar_convite_escola(escola, access_token=None, link=None):
    if not link:
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
    )
    return ok, erro, link


def _avisar_envio(escola, ok, erro, acao="cadastro"):
    dest = escola.get("email_admin") or ""
    session.pop("gmail_manual", None)
    if ok:
        if acao == "cadastro":
            flash(f"Escola {escola.get('nome')} cadastrada. Código enviado para {dest}.", "success")
        else:
            flash(f"Código de acesso enviado para {dest}.", "success")
        return
    flash(
        f"Escola criada, mas falhou o envio automático para {dest}. Erro: {erro}"
        if acao == "cadastro"
        else f"O envio automático para {dest} falhou. Erro: {erro}",
        "danger",
    )


@app.route("/plataforma/autorizar-gmail")
def plataforma_autorizar_gmail():
    if not session.get("super_admin"):
        return redirect(url_for("login"))
    cred = credenciais_google()
    cid = (cred.get("client_id") or "").strip()
    secret = (cred.get("client_secret") or "").strip()
    if "@" in cid or "googleusercontent.com" not in cid or not secret:
        flash(
            "Ainda falta o aplicativo do Google. Cole o Client ID e o Client secret no quadro Envio automático e salve. "
            "O Client ID termina com .apps.googleusercontent.com.",
            "danger",
        )
        return redirect(url_for("plataforma_escolas"))
    estado = secrets.token_urlsafe(24)
    session["oauth_state"] = estado
    from urllib.parse import urlencode
    destino = url_for("login_google_callback", _external=True)
    query = urlencode(
        {
            "client_id": cid,
            "redirect_uri": destino,
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/gmail.send",
            "access_type": "offline",
            "prompt": "consent",
            "state": estado,
            "login_hint": email_super_admin(),
        }
    )
    return redirect("https://accounts.google.com/o/oauth2/v2/auth?" + query)


def _ids_cobranca_form():
    ids = []
    for bruto in request.form.getlist("cobranca_id"):
        try:
            cobranca_id = int(bruto)
        except (TypeError, ValueError):
            continue
        if cobranca_id not in ids:
            ids.append(cobranca_id)
    return ids


def _redirect_plataforma():
    acao = (request.form.get("acao") or "").strip()
    abas = {"escolas", "pacotes", "financeiro", "envio", "auditoria"}
    aba = (request.form.get("aba") or "escolas").strip()
    if acao in {
        "gerar_assinaturas",
        "atualizar_abertas",
        "criar_cobranca",
        "editar_cobranca",
        "dar_baixa",
        "dar_baixa_lote",
        "tirar_baixa",
        "tirar_baixa_lote",
        "excluir_cobranca",
        "criar_custo",
        "excluir_custo",
    }:
        aba = "financeiro"
    if aba not in abas:
        aba = "escolas"
    kwargs = {"aba": aba}
    if aba != "financeiro":
        return redirect(url_for("plataforma_escolas", **kwargs))
    fin = (request.form.get("fin") or "resumo").strip()
    if acao in {"criar_custo", "excluir_custo"}:
        fin = "custos"
    elif acao in {
        "gerar_assinaturas",
        "atualizar_abertas",
        "criar_cobranca",
        "editar_cobranca",
        "dar_baixa",
        "dar_baixa_lote",
        "tirar_baixa",
        "tirar_baixa_lote",
        "excluir_cobranca",
    }:
        fin = "assinaturas"
    if fin not in {"resumo", "assinaturas", "custos"}:
        fin = "resumo"
    kwargs["fin"] = fin
    mes = (request.form.get("mes") or "")[:7]
    if acao in {"editar_cobranca", "criar_cobranca"}:
        venc = (request.form.get("data_vencimento") or "")[:7]
        if len(venc) == 7:
            mes = venc
    if acao == "criar_custo":
        quando = (request.form.get("data_custo") or "")[:7]
        if len(quando) == 7:
            mes = quando
    if len(mes) == 7:
        kwargs["mes"] = mes
    status = (request.form.get("status") or "").strip()
    busca = (request.form.get("busca") or "").strip()
    if status:
        kwargs["status"] = status
    if busca:
        kwargs["busca"] = busca
    return redirect(url_for("plataforma_escolas", **kwargs))


@app.route("/plataforma/escolas", methods=["GET", "POST"])
def plataforma_escolas():
    garantir_plataforma()
    if not session.get("super_admin"):
        return redirect(url_for("login"))
    if request.method == "POST":
        acao = request.form.get("acao")
        conexao = None
        try:
            conexao = obter_conexao(master=True)
        except Exception as e:
            flash(f"Banco indisponível: {e}", "danger")
            return redirect(url_for("plataforma_escolas"))
        if acao == "definir_emissao_nfse":
            ligada = request.form.get("nfse_ligada") == "1"
            try:
                with conexao.cursor() as cursor:
                    definir_emissao_habilitada(cursor, ligada)
                conexao.commit()
                flash(
                    "A geração de NFS-e foi ligada em todas as escolas."
                    if ligada
                    else "A geração de NFS-e foi desligada em todas as escolas.",
                    "success",
                )
            except Exception as e:
                conexao.rollback()
                flash(f"Não foi possível salvar a geração de NFS-e: {e}", "danger")
            finally:
                conexao.close()
            return redirect(url_for("plataforma_escolas", aba=(request.form.get("aba") or "escolas")))
        if acao in {
            "salvar_nfse_plataforma",
            "emitir_nfse_plataforma",
            "cancelar_nfse_plataforma",
            "substituir_nfse_plataforma",
            "consultar_nfse_plataforma",
            "salvar_tomador_escola",
        }:
            if not getattr(g, "nfse_liberada", False):
                conexao.close()
                flash("A geração de NFS-e está desligada.", "danger")
                return redirect(url_for("plataforma_escolas"))
            mes_nf = (request.form.get("mes") or "")[:7]
            try:
                with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                    if acao == "salvar_nfse_plataforma":
                        salvar_config_plataforma(cursor, request.form, request.files.get("nfse_certificado"))
                        mensagem = "Token e certificado da plataforma salvos no servidor."
                    elif acao == "salvar_tomador_escola":
                        escola_id = request.form.get("escola_id", type=int)
                        if not escola_id:
                            raise ValueError("Escolha a escola tomadora.")
                        salvar_tomador_escola(cursor, escola_id, request.form)
                        mensagem = "Dados fiscais da escola salvos."
                    elif acao == "emitir_nfse_plataforma":
                        mensagem = emitir_cobranca_plataforma(cursor, request.form.get("cobranca_id", type=int))
                    elif acao == "cancelar_nfse_plataforma":
                        mensagem = cancelar_nota(
                            cursor,
                            request.form.get("nota_id", type=int),
                            "plataforma_notas_fiscais",
                            request.form.get("justificativa"),
                        )
                    elif acao == "substituir_nfse_plataforma":
                        mensagem = substituir_nota(
                            cursor,
                            request.form.get("nota_id", type=int),
                            "plataforma_notas_fiscais",
                        )
                    else:
                        mensagem = consultar_nota(
                            cursor,
                            request.form.get("nota_id", type=int),
                            "plataforma_notas_fiscais",
                        )
                if acao in {"salvar_nfse_plataforma", "salvar_tomador_escola"}:
                    conexao.commit()
                flash(mensagem, "success")
            except Exception as e:
                conexao.rollback()
                flash(str(e), "danger")
            finally:
                conexao.close()
            return redirect(url_for("plataforma_escolas", aba="nfse", mes=mes_nf))
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
        elif acao == "salvar_google":
            try:
                salvar_google_oauth(
                    request.form.get("google_client_id"),
                    request.form.get("google_client_secret"),
                )
                cred = credenciais_google()
                cid = (cred.get("client_id") or "").strip()
                secret = (cred.get("client_secret") or "").strip()
                if "@" in cid or "googleusercontent.com" not in cid or not secret:
                    flash(
                        "O Client ID precisa terminar com .apps.googleusercontent.com e o Client secret não pode ficar vazio.",
                        "danger",
                    )
                else:
                    if conexao:
                        try:
                            conexao.close()
                        except Exception:
                            pass
                    return redirect(url_for("plataforma_autorizar_gmail"))
            except Exception as e:
                flash(f"Não foi possível salvar o Google: {e}", "danger")
        elif acao == "criar_escola":
            if conexao:
                try:
                    conexao.close()
                except Exception:
                    pass
                conexao = None
            try:
                email_novo = request.form.get("email_admin")
                if request.form.get("recadastrar") and buscar_escola_por_email(email_novo):
                    antiga = buscar_escola_por_email(email_novo)
                    excluir_escola(antiga["id"])
                escola = cadastrar_escola(request.form.get("nome"), email_novo)
                ok, erro, _link = _enviar_convite_escola(escola)
                _avisar_envio(escola, ok, erro, acao="cadastro")
            except Exception as e:
                flash(f"Não foi possível cadastrar a escola: {e}", "danger")
        elif acao == "reenviar_convite":
            token = request.form.get("token")
            escola_id = request.form.get("escola_id")
            escola = buscar_escola_por_token(token) if token else buscar_escola_por_id(escola_id)
            if not escola:
                flash("Escola não encontrada.", "danger")
            elif escola.get("senha_definida"):
                codigo = gerar_otp(escola["email_admin"], "login_escola")
                corpo = (
                    f"Seu código para alterar a senha da Gestão Escolar é: {codigo}\n\n"
                    "Na tela de login informe este e-mail, clique em Continuar e depois em Esqueci a senha. "
                    "Use os 6 dígitos. O código vale 20 minutos.\n"
                    "Se o e-mail não chegar, peça ao administrador da plataforma para usar Redefinir senha."
                )
                ok, erro = enviar_codigo(
                    escola["email_admin"],
                    codigo,
                    "Código para alterar a senha — Gestão Escolar",
                    corpo,
                )
                if ok:
                    flash(
                        f"Código enviado para {escola['email_admin']}. "
                        "A escola entra em Esqueci a senha e usa este código. "
                        "Se não chegar, use Redefinir senha (último caso).",
                        "success",
                    )
                else:
                    flash(
                        f"O e-mail não saiu ({erro}). Use Redefinir senha ao lado para definir a senha manualmente.",
                        "danger",
                    )
            else:
                ok, erro, _link = _enviar_convite_escola(escola)
                _avisar_envio(escola, ok, erro, acao="reenviar")
        elif acao == "alterar_email":
            try:
                escola = atualizar_email_admin_escola(
                    request.form.get("token"),
                    request.form.get("email_admin"),
                )
                ok, erro, _link = _enviar_convite_escola(escola)
                _avisar_envio(escola, ok, erro, acao="reenviar")
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
                nova = (request.form.get("nova_senha") or "").strip()
                if len(nova) < 6:
                    raise ValueError("Informe a nova senha (mínimo 6 caracteres) no campo ao lado de Redefinir senha.")
                escola = definir_senha_escola_por_admin(request.form.get("escola_id"), nova)
                flash(
                    f"Senha da escola {escola.get('nome')} redefinida pelo administrador da plataforma. "
                    f"A escola entra com {escola.get('email_admin')} e a senha que você acabou de definir. "
                    "Não é preciso código por e-mail.",
                    "success",
                )
            except Exception as e:
                flash(f"Não foi possível redefinir a senha: {e}", "danger")
        elif acao == "salvar_pacote":
            try:
                bruto = (request.form.get("valor") or "").strip()
                valor = None if not bruto else _parse_moeda(bruto, 0.0)
                salvar_pacote(request.form.get("codigo"), valor, request.form.getlist("telas"))
                flash("Pacote atualizado. Escolas que já usam esse pacote passam a ver as telas marcadas no próximo login.", "success")
            except Exception as e:
                flash(f"Não foi possível salvar o pacote: {e}", "danger")
        elif acao == "definir_pacote":
            try:
                escola = definir_pacote_escola(request.form.get("escola_id"), request.form.get("pacote"))
                if escola.get("pacote"):
                    flash(
                        f"Pacote da escola {escola['nome']} atualizado. Quem já está logado precisa entrar de novo.",
                        "success",
                    )
                else:
                    flash(
                        f"A escola {escola['nome']} ficou com todas as telas, sem pacote. Quem já está logado precisa entrar de novo.",
                        "success",
                    )
            except Exception as e:
                flash(f"Não foi possível aplicar o pacote: {e}", "danger")
        elif acao == "salvar_cobranca_escola":
            try:
                mes = (request.form.get("mes") or datetime.now().strftime("%Y-%m"))[:7]
                escola, calculo = salvar_regra_cobranca_escola(
                    request.form.get("escola_id"),
                    request.form.get("cobranca_modo"),
                    request.form.get("cobranca_fixo"),
                    request.form.get("cobranca_percentual"),
                    request.form.get("faturamento_manual"),
                    request.form.get("desconto_modo"),
                    request.form.get("desconto_percentual"),
                    request.form.get("desconto_valor"),
                    mes,
                )
                flash(
                    f"Cobrança de {escola['nome']} salva. Estimativa deste mês: R$ {_moeda_br(calculo['valor'])}. {calculo['resumo']}.",
                    "success",
                )
            except Exception as e:
                flash(f"Não foi possível salvar o cálculo: {e}", "danger")
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
        elif acao == "gerar_assinaturas":
            try:
                resultado = gerar_cobrancas_plataforma(
                    request.form.get("mes"),
                    request.form.get("dia_vencimento") or 10,
                )
                texto = (
                    f"Assinaturas do mês: {resultado['criadas']} nova(s). "
                    f"{resultado['ja_existiam']} já existia(m) e foi mantida."
                )
                if resultado["sem_valor"]:
                    texto += " Sem valor de pacote: " + ", ".join(resultado["sem_valor"]) + "."
                flash(texto, "success" if resultado["criadas"] or resultado["ja_existiam"] else "warning")
            except Exception as e:
                flash(f"Não foi possível gerar as assinaturas: {e}", "danger")
        elif acao == "atualizar_abertas":
            try:
                qtd = atualizar_cobrancas_abertas_plataforma(request.form.get("mes"))
                flash(f"{qtd} assinatura(s) em aberto atualizada(s) com o valor atual do pacote.", "success")
            except Exception as e:
                flash(f"Não foi possível atualizar os valores: {e}", "danger")
        elif acao == "criar_cobranca":
            try:
                criar_cobranca_plataforma(
                    request.form.get("escola_id"),
                    _parse_moeda(request.form.get("valor"), 0.0),
                    request.form.get("data_vencimento"),
                    request.form.get("descricao"),
                )
                flash("Assinatura lançada.", "success")
            except Exception as e:
                flash(f"Não foi possível lançar a assinatura: {e}", "danger")
        elif acao == "editar_cobranca":
            try:
                editar_cobranca_plataforma(
                    int(request.form.get("cobranca_id")),
                    _parse_moeda(request.form.get("valor"), 0.0),
                    request.form.get("data_vencimento"),
                    request.form.get("descricao"),
                )
                flash("Assinatura atualizada.", "success")
            except Exception as e:
                flash(f"Não foi possível salvar a assinatura: {e}", "danger")
        elif acao == "dar_baixa":
            try:
                juros_percentual, multa_valor = _acrescimos_form()
                qtd = baixar_cobrancas_plataforma(
                    [request.form.get("cobranca_id")],
                    request.form.get("forma_pagamento"),
                    request.form.get("data_pagamento") or datetime.now().strftime("%Y-%m-%d"),
                    juros_percentual,
                    multa_valor,
                )
                flash("Baixa realizada." if qtd else "Essa assinatura já estava paga.", "success" if qtd else "warning")
            except Exception as e:
                flash(f"Não foi possível dar baixa: {e}", "danger")
        elif acao == "dar_baixa_lote":
            try:
                ids = _ids_cobranca_form()
                juros_percentual, multa_valor = _acrescimos_form()
                qtd = baixar_cobrancas_plataforma(
                    ids,
                    request.form.get("forma_pagamento") or "Pix",
                    request.form.get("data_pagamento") or datetime.now().strftime("%Y-%m-%d"),
                    juros_percentual,
                    multa_valor,
                )
                flash(f"Baixa registrada em {qtd} assinatura(s).", "success")
            except Exception as e:
                flash(f"Não foi possível dar baixa: {e}", "danger")
        elif acao in {"tirar_baixa", "tirar_baixa_lote"}:
            try:
                ids = _ids_cobranca_form()
                qtd = tirar_baixa_cobrancas_plataforma(ids)
                flash(f"Baixa retirada de {qtd} assinatura(s).", "success")
            except Exception as e:
                flash(f"Não foi possível tirar a baixa: {e}", "danger")
        elif acao == "excluir_cobranca":
            try:
                excluir_cobranca_plataforma(int(request.form.get("cobranca_id")))
                flash("Assinatura excluída.", "success")
            except Exception as e:
                flash(f"Não foi possível excluir a assinatura: {e}", "danger")
        elif acao == "criar_custo":
            try:
                criar_custo_plataforma(
                    request.form.get("descricao"),
                    request.form.get("categoria"),
                    _parse_moeda(request.form.get("valor"), 0.0),
                    request.form.get("data_custo") or datetime.now().strftime("%Y-%m-%d"),
                )
                flash("Custo da plataforma lançado.", "success")
            except Exception as e:
                flash(f"Não foi possível lançar o custo: {e}", "danger")
        elif acao == "excluir_custo":
            try:
                excluir_custo_plataforma(int(request.form.get("custo_id")))
                flash("Custo excluído.", "success")
            except Exception as e:
                flash(f"Não foi possível excluir o custo: {e}", "danger")
        if conexao:
            try:
                conexao.close()
            except Exception:
                pass
        return _redirect_plataforma()
    smtp = {}
    escolas = []
    try:
        conexao = obter_conexao(master=True)
        if conexao:
            try:
                with conexao.cursor() as cursor:
                    cursor.execute("SELECT * FROM plataforma_smtp WHERE id = 1")
                    smtp = cursor.fetchone() or {}
            finally:
                conexao.close()
        escolas = listar_escolas() or []
    except Exception as e:
        flash(f"Não foi possível carregar as escolas: {e}", "danger")
    try:
        diagnostico = diagnostico_envio()
    except Exception:
        diagnostico = {
            "status": "faltando",
            "detalhe": "Não foi possível diagnosticar o envio.",
            "smtp_user": False,
            "smtp_password": False,
            "smtp_host": "—",
            "smtp_port": 587,
            "producao_render": ambiente_producao(),
            "gmail_api": False,
            "resend": False,
            "brevo": False,
        }
    pacotes = []
    try:
        pacotes = listar_pacotes()
    except Exception as e:
        flash(f"Não foi possível carregar os pacotes: {e}", "danger")
    cred_google = {}
    try:
        cred_google = credenciais_google()
    except Exception:
        cred_google = {}
    cid_google = (cred_google.get("client_id") or "").strip()
    aba = (request.args.get("aba") or "escolas").strip()
    if aba not in {"escolas", "pacotes", "financeiro", "envio", "auditoria", "nfse"}:
        aba = "escolas"
    fin = (request.args.get("fin") or "resumo").strip()
    if fin not in {"resumo", "assinaturas", "custos"}:
        fin = "resumo"
    mes_atual = (request.args.get("mes") or datetime.now().strftime("%Y-%m")).strip()[:7]
    try:
        datetime.strptime(mes_atual, "%Y-%m")
    except ValueError:
        mes_atual = datetime.now().strftime("%Y-%m")
    status_fin = (request.args.get("status") or "").strip()
    busca_fin = (request.args.get("busca") or "").strip()
    if status_fin and fin == "resumo":
        fin = "assinaturas"
    painel = {
        "cobrancas": [],
        "custos": [],
        "sem_valor": [],
        "sem_lancamento": [],
        "totais": {
            "recebido": 0.0,
            "pendente": 0.0,
            "atrasado": 0.0,
            "previsto": 0.0,
            "custos": 0.0,
            "liquido": 0.0,
            "qtd_pago": 0,
            "qtd_pendente": 0,
            "qtd_atrasado": 0,
            "qtd": 0,
        },
    }
    if aba == "escolas":
        try:
            escolas = preparar_cobranca_escolas(escolas, pacotes, mes_atual)
        except Exception as e:
            flash(f"Não foi possível calcular a cobrança das escolas: {e}", "danger")
    if aba == "financeiro":
        try:
            painel = painel_financeiro_plataforma(mes_atual, status_fin, busca_fin)
        except Exception as e:
            flash(f"Não foi possível carregar o financeiro da plataforma: {e}", "danger")
    auditoria = []
    filtro_tipo = (request.args.get("tipo") or "").strip()
    filtro_escola = request.args.get("escola", type=int)
    if aba == "auditoria":
        try:
            auditoria = listar_auditoria(filtro_escola, filtro_tipo, busca_fin)
        except Exception as e:
            flash(f"Não foi possível carregar a auditoria: {e}", "danger")
    nfse_cfg = {}
    nfse_notas = []
    nfse_cobrancas = []
    nfse_faturado = 0
    if aba == "nfse":
        conexao_nf = None
        try:
            conexao_nf = obter_conexao(master=True)
            with conexao_nf.cursor(cursor_factory=RealDictCursor) as cursor:
                nfse_cfg = ler_config_plataforma_tela(cursor)
                nfse_notas = listar_notas_plataforma(cursor, (request.args.get("nota") or "").strip() or None)
                nfse_cobrancas = listar_cobrancas_plataforma(cursor, mes_atual)
                nfse_faturado = valor_na_competencia(listar_notas_plataforma(cursor), mes_atual)
        except Exception as e:
            flash(f"Não foi possível carregar as notas da plataforma: {e}", "danger")
        finally:
            if conexao_nf:
                conexao_nf.close()
    return render_template(
        "plataforma_escolas.html",
        escolas=escolas,
        pacotes=pacotes,
        telas_plano=TELAS_PLANO,
        aba=aba,
        fin=fin,
        mes_atual=mes_atual,
        mes_label=nome_mes_extenso(mes_atual),
        status=status_fin,
        busca=busca_fin,
        painel=painel,
        data_hoje=date.today().isoformat(),
        smtp=smtp,
        diagnostico=diagnostico,
        google_client_id=cid_google,
        google_app=bool(cred_google.get("client_secret") and "googleusercontent.com" in cid_google and "@" not in cid_google),
        google_login=_google_habilitado(),
        google_autorizado=bool((smtp or {}).get("google_refresh_token") if isinstance(smtp, dict) else getattr(smtp, "google_refresh_token", None)),
        google_redirect=url_for("login_google_callback", _external=True),
        auditoria=auditoria,
        filtro_tipo=filtro_tipo,
        filtro_escola=filtro_escola,
        nfse_cfg=nfse_cfg,
        nfse_notas=nfse_notas,
        nfse_cobrancas=nfse_cobrancas,
        nfse_faturado=nfse_faturado,
        nota_filtro=(request.args.get("nota") or "").strip(),
    )


@app.route("/auditoria")
def pagina_auditoria():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    if session.get("usuario_papel") != "admin":
        flash("A auditoria fica disponível apenas para o administrador da escola.", "danger")
        return redirect(url_for("dashboard"))
    tipo = (request.args.get("tipo") or "").strip()
    busca = (request.args.get("busca") or "").strip()
    registros = []
    try:
        registros = listar_auditoria(session.get("escola_id"), tipo, busca)
    except Exception as e:
        flash(f"Não foi possível carregar a auditoria: {e}", "danger")
    return render_template(
        "auditoria.html",
        registros=registros,
        tipo=tipo,
        busca=busca,
        escola_nome=session.get("escola_nome") or "",
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

    if session.get("usuario_papel") != "admin" and not pode_acao(session.get("usuario_papel"), "usuarios", "acessar", session.get("permissoes")):
        flash("Acesso negado. Area restrita para administradores.", "danger")
        return redirect(url_for("dashboard"))

    garantir_tabelas_folha()
    conexao = obter_conexao()

    if request.method == "POST":
        acao = request.form.get("acao") or "salvar"
        if conexao:
            try:
                with conexao.cursor() as cursor:
                    cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS permissoes TEXT")
                    if acao == "excluir":
                        uid = request.form.get("usuario_id", type=int)
                        if uid:
                            cursor.execute("UPDATE funcionarios SET usuario_id = NULL WHERE usuario_id = %s", (uid,))
                            cursor.execute("DELETE FROM usuarios WHERE id = %s", (uid,))
                            conexao.commit()
                            flash("Usuário de acesso removido. O cadastro de folha foi mantido.", "success")
                        return redirect(url_for("gerenciar_usuarios"))

                    nome = limpar_campo("nome")
                    email = exigencia_email(limpar_campo("email"), "E-mail do colaborador")
                    senha_informada = (request.form.get("senha") or "").strip()
                    senha = senha_informada
                    papel = normalizar_papel(limpar_campo("papel") or "funcionario")
                    uid = request.form.get("usuario_id", type=int)
                    fid = request.form.get("funcionario_id", type=int)
                    criar_login = request.form.get("criar_login") == "1"
                    if not nome or not email:
                        raise ValueError("Informe nome e e-mail para receber contra-cheque e avisos.")

                    papel_mudou = False
                    if criar_login:
                        novo_login = not uid
                        if novo_login and not senha:
                            senha = secrets.token_urlsafe(9)
                        if uid:
                            cursor.execute("SELECT papel FROM usuarios WHERE id = %s", (uid,))
                            atual = cursor.fetchone() or {}
                            papel_mudou = normalizar_papel(atual.get("papel") or "") != papel
                        perm_json = json.dumps(permissoes_padrao(papel), ensure_ascii=False)
                        if uid:
                            if senha and papel_mudou:
                                cursor.execute(
                                    "UPDATE usuarios SET nome = %s, email = %s, senha = %s, papel = %s, permissoes = %s WHERE id = %s",
                                    (nome, email, senha, papel, perm_json, uid),
                                )
                            elif senha:
                                cursor.execute(
                                    "UPDATE usuarios SET nome = %s, email = %s, senha = %s, papel = %s WHERE id = %s",
                                    (nome, email, senha, papel, uid),
                                )
                            elif papel_mudou:
                                cursor.execute(
                                    "UPDATE usuarios SET nome = %s, email = %s, papel = %s, permissoes = %s WHERE id = %s",
                                    (nome, email, papel, perm_json, uid),
                                )
                            else:
                                cursor.execute(
                                    "UPDATE usuarios SET nome = %s, email = %s, papel = %s WHERE id = %s",
                                    (nome, email, papel, uid),
                                )
                        else:
                            cursor.execute(
                                """
                                INSERT INTO usuarios (nome, email, senha, papel, permissoes)
                                VALUES (%s, %s, %s, %s, %s)
                                RETURNING id
                                """,
                                (nome, email, senha, papel, perm_json),
                            )
                            uid = cursor.fetchone()["id"]
                            papel_mudou = True
                    else:
                        novo_login = False
                        if uid:
                            cursor.execute(
                                "UPDATE usuarios SET nome = %s, email = %s WHERE id = %s",
                                (nome, email, uid),
                            )

                    cargo = _cargo_do_form(papel)
                    cpf = limpar_campo("cpf") or _cpf_provisorio(email)
                    telefone = limpar_campo("telefone") or "(00) 00000-0000"
                    nasc = limpar_campo("data_nascimento") or "2000-01-01"
                    ativo = request.form.get("ativo", "1") != "0"
                    if not fid:
                        cursor.execute(
                            """
                            SELECT id FROM funcionarios
                            WHERE (%s IS NOT NULL AND usuario_id = %s)
                               OR LOWER(COALESCE(email, '')) = LOWER(%s)
                            ORDER BY CASE WHEN usuario_id = %s THEN 0 ELSE 1 END
                            LIMIT 1
                            """,
                            (uid, uid, email, uid),
                        )
                        existente = cursor.fetchone()
                        if existente:
                            fid = existente["id"]

                    repetido = buscar_cpf_repetido(cursor, cpf, ignorar_funcionario_id=fid or None)
                    if repetido:
                        conexao.rollback()
                        flash(mensagem_cpf_repetido(*repetido), "danger")
                        if fid:
                            return redirect(url_for("gerenciar_usuarios", fid=fid))
                        return redirect(url_for("gerenciar_usuarios"))
                    inicio_contrato = limpar_campo("data_inicio_contrato") or limpar_campo("data_contratacao") or datetime.now().strftime("%Y-%m-%d")
                    valores_folha = (
                        nome, cpf, nasc, cargo, telefone, email,
                        _especialidade_form(), _formacao_do_form(),
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
                        inicio_contrato,
                        inicio_contrato,
                        limpar_campo("data_fim_contrato") or None,
                        dia_pagamento_valido(request.form.get("dia_pagamento")),
                        _float_form("horas_extras"),
                        _float_form("horas_extras_100"),
                        _float_form("valor_hora_extra"),
                        request.form.get("enviar_contracheque", "1") != "0",
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
                                data_inicio_contrato = %s, data_fim_contrato = %s, dia_pagamento = %s,
                                horas_extras = %s, horas_extras_100 = %s, valor_hora_extra = %s, enviar_contracheque = %s,
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
                                reter_federal, reter_iss, aliquota_iss, data_contratacao,
                                data_inicio_contrato, data_fim_contrato, dia_pagamento,
                                horas_extras, horas_extras_100, valor_hora_extra, enviar_contracheque, ativo, usuario_id
                            ) VALUES (
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s, %s, %s, %s, %s
                            )
                            RETURNING id
                            """,
                            valores_folha,
                        )
                        fid = cursor.fetchone()["id"]
                    foto_func = None
                    try:
                        foto_func = _salvar_foto("foto", "equipe")
                    except ValueError as e:
                        flash(str(e), "danger")
                    if foto_func and fid:
                        cursor.execute(
                            "UPDATE funcionarios SET foto_url = %s WHERE id = %s",
                            (foto_func, fid),
                        )
                    conexao.commit()
                    if uid and uid == session.get("usuario_id"):
                        session["usuario_papel"] = papel
                        if papel_mudou:
                            session["permissoes"] = permissoes_padrao(papel)
                    flash("Cadastro da equipe salvo. Contra-cheque e avisos vão para o e-mail informado.", "success")
                    if criar_login and papel_mudou and uid and uid != session.get("usuario_id"):
                        flash("O acesso voltou ao padrão da função. Ajuste em Configurações, se precisar. Vale no próximo acesso dela.", "success")
                    if criar_login and (novo_login or senha_informada):
                        try:
                            ok, erro = _enviar_codigo_colaborador(email, nome)
                            if ok:
                                flash(f"Código de acesso ao painel enviado para {email}.", "success")
                            else:
                                flash(f"Cadastro salvo, mas o código de acesso não saiu: {erro}", "danger")
                        except Exception as e:
                            flash(f"Cadastro salvo, mas o e-mail de acesso não saiu: {e}", "danger")
                    if uid:
                        return redirect(url_for("gerenciar_usuarios", uid=uid))
                    return redirect(url_for("gerenciar_usuarios", fid=fid))
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
        "permissoes": permissoes_padrao("professor"),
        "ativo": True,
        "tipo_contrato": "clt_mensalista",
        "salario": 0,
        "valor_hora": 0,
        "horas_mes": 0,
        "horas_extras": 0,
        "horas_extras_100": 0,
        "valor_hora_extra": 0,
        "dia_pagamento": 5,
        "enviar_contracheque": True,
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
                           f.tipo_contrato, f.salario, f.ativo, f.foto_url
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
                           f.cpf, f.telefone, f.tipo_contrato, f.salario, f.ativo, f.foto_url
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
                        "permissoes": permissoes_efetivas(
                            normalizar_papel(urow.get("papel") or "funcionario"),
                            urow.get("permissoes"),
                        ),
                        "cpf": frow.get("cpf") or "",
                        "rg": frow.get("rg") or "",
                        "data_nascimento": _data_iso(frow.get("data_nascimento")),
                        "telefone": frow.get("telefone") or "",
                        "cargo": frow.get("cargo") or _cargo_do_papel(urow.get("papel")),
                        "especialidade": _disciplina_visivel(frow.get("especialidade") or ""),
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
                        "horas_extras": frow.get("horas_extras") or 0,
                        "horas_extras_100": frow.get("horas_extras_100") or 0,
                        "valor_hora_extra": frow.get("valor_hora_extra") or 0,
                        "dia_pagamento": dia_pagamento_valido(frow.get("dia_pagamento")),
                        "data_inicio_contrato": _data_iso(frow.get("data_inicio_contrato") or frow.get("data_contratacao")),
                        "data_fim_contrato": _data_iso(frow.get("data_fim_contrato")),
                        "enviar_contracheque": True if frow.get("enviar_contracheque") is None else bool(frow.get("enviar_contracheque")),
                        "reter_federal": bool(frow.get("reter_federal")),
                        "reter_iss": bool(frow.get("reter_iss")),
                        "aliquota_iss": frow.get("aliquota_iss") or 5,
                        "data_contratacao": _data_iso(frow.get("data_contratacao")),
                        "ativo": True if frow.get("ativo") is None else bool(frow.get("ativo")),
                        "foto_url": frow.get("foto_url") or "",
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
                    WHERE COALESCE(ativo, TRUE) = TRUE
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


def _garantir_sala_professor():
    """Cria as tabelas da sala do professor e grava de vez (a conexão compartilhada faz rollback no close)."""
    from database import _nome_banco_atual, _tabelas_ok

    schema = _nome_banco_atual(master=False)
    if not schema:
        return
    chave = f"{schema}:sala_prof_v2"
    if chave in _tabelas_ok:
        return
    conexao = obter_conexao()
    if not conexao:
        return
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS professor_arquivos (
                    id SERIAL PRIMARY KEY,
                    funcionario_id INT NOT NULL,
                    turma_id INT,
                    tipo VARCHAR(30) NOT NULL,
                    titulo VARCHAR(180),
                    midia_id INT NOT NULL,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS provas_criadas (
                    id SERIAL PRIMARY KEY,
                    funcionario_id INT NOT NULL,
                    turma_id INT,
                    titulo VARCHAR(180) NOT NULL,
                    materia VARCHAR(100),
                    data_aplicacao DATE,
                    horario TIME,
                    evento_calendario_id INT,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute("ALTER TABLE provas_criadas ADD COLUMN IF NOT EXISTS data_aplicacao DATE")
            cursor.execute("ALTER TABLE provas_criadas ADD COLUMN IF NOT EXISTS horario TIME")
            cursor.execute("ALTER TABLE provas_criadas ADD COLUMN IF NOT EXISTS evento_calendario_id INT")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS provas_criadas_questoes (
                    id SERIAL PRIMARY KEY,
                    prova_id INT NOT NULL REFERENCES provas_criadas(id) ON DELETE CASCADE,
                    ordem INT DEFAULT 1,
                    enunciado TEXT NOT NULL,
                    tipo VARCHAR(20) NOT NULL,
                    alternativas TEXT,
                    resposta TEXT
                )
                """
            )
            cursor.execute("ALTER TABLE configuracoes ADD COLUMN IF NOT EXISTS logo_escola VARCHAR(255)")
            cursor.execute("ALTER TABLE configuracoes ADD COLUMN IF NOT EXISTS mensagem_prova TEXT")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS provas_criadas_notas (
                    id SERIAL PRIMARY KEY,
                    prova_id INT NOT NULL REFERENCES provas_criadas(id) ON DELETE CASCADE,
                    aluno_id INT NOT NULL,
                    nota VARCHAR(20) NOT NULL,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (prova_id, aluno_id)
                )
                """
            )
        conexao.commit()
        _tabelas_ok.add(chave)
    except Exception:
        try:
            conexao.rollback()
        except Exception:
            pass
        raise
    finally:
        conexao.close()


def _professor_da_sessao(cursor, funcionario_id):
    if not funcionario_id:
        return None, []
    cursor.execute(
        "SELECT id, nome_completo FROM funcionarios WHERE id = %s",
        (funcionario_id,),
    )
    pessoa = cursor.fetchone()
    cursor.execute(
        """
        SELECT id, nome FROM turmas
        WHERE professor_responsavel_id = %s
        ORDER BY nome
        """,
        (funcionario_id,),
    )
    return pessoa, cursor.fetchall() or []


@app.route("/minhas-provas", methods=["GET", "POST"])
def sala_professor():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    garantir_tabelas_pedagogicas()
    try:
        _garantir_sala_professor()
    except Exception as e:
        flash(f"Não foi possível preparar a sala do professor: {e}", "danger")
        return redirect(url_for("dashboard"))

    funcionario_id = session.get("funcionario_id") or _id_funcionario_da_sessao()
    if funcionario_id:
        session["funcionario_id"] = funcionario_id

    conexao = obter_conexao()
    if not conexao:
        flash("Sem conexão com o banco.", "danger")
        return redirect(url_for("dashboard"))
    arquivos, provas, escola = [], [], {}
    pessoa, turmas = None, []
    try:
        with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
            pessoa, turmas = _professor_da_sessao(cursor, funcionario_id)
            if not pessoa:
                flash(
                    "Seu usuário não está ligado a um professor da equipe. "
                    "Peça à secretaria para vincular seu login ao cadastro em Equipe / Professores.",
                    "danger",
                )
                return redirect(url_for("dashboard"))
            if request.method == "POST":
                acao = request.form.get("acao")
                if acao == "enviar_arquivo":
                    tipo = (request.form.get("tipo") or "").strip()
                    if tipo not in {"atestado", "prova_aplicar", "prova_feita"}:
                        raise ValueError("Escolha o tipo do arquivo.")
                    turma_id = request.form.get("turma_id", type=int)
                    if tipo == "prova_feita" and not turma_id:
                        raise ValueError("Escolha a turma da prova que já foi feita.")
                    if turma_id and turma_id not in {item["id"] for item in turmas}:
                        raise ValueError("Essa turma não está vinculada a você.")
                    midia_id = _salvar_midia("arquivo", {"pdf"})
                    if not midia_id:
                        raise ValueError("Envie o PDF.")
                    cursor.execute(
                        """
                        INSERT INTO professor_arquivos (funcionario_id, turma_id, tipo, titulo, midia_id)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            pessoa["id"],
                            turma_id if tipo == "prova_feita" else None,
                            tipo,
                            (request.form.get("titulo") or "Arquivo").strip()[:180],
                            midia_id,
                        ),
                    )
                    flash("PDF guardado.", "success")
                elif acao == "excluir_arquivo":
                    cursor.execute(
                        "DELETE FROM professor_arquivos WHERE id = %s AND funcionario_id = %s",
                        (request.form.get("arquivo_id", type=int), pessoa["id"]),
                    )
                    flash("Arquivo removido.", "success")
                elif acao == "criar_prova":
                    titulo = (request.form.get("titulo") or "").strip()
                    if not titulo:
                        raise ValueError("Dê um nome para a prova.")
                    turma_id = request.form.get("turma_id", type=int)
                    if turma_id and turma_id not in {item["id"] for item in turmas}:
                        raise ValueError("Essa turma não está vinculada a você.")
                    data_aplicacao = (request.form.get("data_aplicacao") or "").strip()
                    if not data_aplicacao:
                        raise ValueError("Informe a data de aplicação da prova.")
                    try:
                        datetime.strptime(data_aplicacao[:10], "%Y-%m-%d")
                    except ValueError:
                        raise ValueError("Data de aplicação inválida.")
                    horario = (request.form.get("horario") or "").strip() or None
                    if horario in ("", "None"):
                        horario = None
                    materia = (request.form.get("materia") or "").strip()[:100]
                    enunciados = request.form.getlist("enunciado")
                    tipos = request.form.getlist("tipo_questao")
                    respostas = request.form.getlist("resposta")
                    letras = [
                        request.form.getlist("alt_a"),
                        request.form.getlist("alt_b"),
                        request.form.getlist("alt_c"),
                        request.form.getlist("alt_d"),
                    ]
                    questoes = []
                    for indice, texto in enumerate(enunciados):
                        texto = (texto or "").strip()
                        if not texto:
                            continue
                        tipo = tipos[indice] if indice < len(tipos) else "descritiva"
                        if tipo not in {"multipla", "descritiva"}:
                            tipo = "descritiva"
                        alternativas = []
                        if tipo == "multipla":
                            for coluna in letras:
                                alternativas.append((coluna[indice] if indice < len(coluna) else "").strip())
                        questoes.append((
                            texto,
                            tipo,
                            "\n".join(alternativas),
                            (respostas[indice] if indice < len(respostas) else "").strip(),
                        ))
                    if not questoes:
                        raise ValueError("Escreva pelo menos uma pergunta.")
                    titulo_evento = titulo if not materia else f"{titulo} — {materia}"
                    descricao_evento = f"Prova criada por {pessoa.get('nome_completo') or 'professor'}."
                    cursor.execute(
                        """
                        INSERT INTO calendario_eventos
                            (titulo, descricao, data_evento, tipo, turma_id, professor_id, horario)
                        VALUES (%s, %s, %s, 'prova', %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            titulo_evento[:180],
                            descricao_evento,
                            data_aplicacao[:10],
                            turma_id,
                            pessoa["id"],
                            horario,
                        ),
                    )
                    evento_id = (cursor.fetchone() or {}).get("id")
                    if turma_id:
                        cursor.execute(
                            """
                            INSERT INTO provas_turma (turma_id, materia, titulo, descricao, data_prova, horario)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                            (
                                turma_id,
                                materia,
                                titulo[:180],
                                descricao_evento,
                                data_aplicacao[:10],
                                horario,
                            ),
                        )
                    cursor.execute(
                        """
                        INSERT INTO provas_criadas
                            (funcionario_id, turma_id, titulo, materia, data_aplicacao, horario, evento_calendario_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
                        """,
                        (
                            pessoa["id"],
                            turma_id,
                            titulo[:180],
                            materia,
                            data_aplicacao[:10],
                            horario,
                            evento_id,
                        ),
                    )
                    prova_id = (cursor.fetchone() or {}).get("id")
                    for ordem, item in enumerate(questoes, start=1):
                        cursor.execute(
                            """
                            INSERT INTO provas_criadas_questoes
                                (prova_id, ordem, enunciado, tipo, alternativas, resposta)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                            (prova_id, ordem, *item),
                        )
                    flash("Prova criada e incluída no calendário. O PDF já pode ser gerado.", "success")
                elif acao == "excluir_prova":
                    prova_id = request.form.get("prova_id", type=int)
                    cursor.execute(
                        """
                        SELECT evento_calendario_id, turma_id, titulo, data_aplicacao
                        FROM provas_criadas
                        WHERE id = %s AND funcionario_id = %s
                        """,
                        (prova_id, pessoa["id"]),
                    )
                    prova = cursor.fetchone() or {}
                    evento_id = prova.get("evento_calendario_id")
                    if evento_id:
                        cursor.execute("DELETE FROM calendario_eventos WHERE id = %s", (evento_id,))
                    if prova.get("turma_id") and prova.get("data_aplicacao"):
                        cursor.execute(
                            """
                            DELETE FROM provas_turma
                            WHERE turma_id = %s AND data_prova = %s AND titulo = %s
                            """,
                            (prova.get("turma_id"), prova.get("data_aplicacao"), prova.get("titulo")),
                        )
                    cursor.execute(
                        "DELETE FROM provas_criadas WHERE id = %s AND funcionario_id = %s",
                        (prova_id, pessoa["id"]),
                    )
                    flash("Prova excluída e retirada do calendário.", "success")
                elif acao == "lancar_nota":
                    prova_id = request.form.get("prova_id", type=int)
                    cursor.execute(
                        "SELECT id, turma_id FROM provas_criadas WHERE id = %s AND funcionario_id = %s",
                        (prova_id, pessoa["id"]),
                    )
                    prova = cursor.fetchone()
                    if not prova:
                        raise ValueError("Prova não encontrada.")
                    busca = (request.form.get("busca_aluno") or "").strip()
                    if not busca:
                        raise ValueError("Informe a matrícula ou o CPF do aluno.")
                    digitos = "".join(ch for ch in busca if ch.isdigit())
                    params = [f"%{busca}%", f"%{busca}%", f"%{digitos or busca}%"]
                    sql_aluno = """
                        SELECT a.id, a.nome_completo, a.matricula, a.cpf
                        FROM alunos a
                        WHERE (
                            COALESCE(a.matricula, '') ILIKE %s
                            OR COALESCE(a.cpf, '') ILIKE %s
                            OR regexp_replace(COALESCE(a.cpf, ''), '[^0-9]', '', 'g') LIKE %s
                        )
                    """
                    if prova.get("turma_id"):
                        sql_aluno += """
                            AND EXISTS (
                                SELECT 1 FROM turma_alunos ta
                                WHERE ta.aluno_id = a.id AND ta.turma_id = %s
                            )
                        """
                        params.append(prova["turma_id"])
                    sql_aluno += " ORDER BY a.nome_completo LIMIT 8"
                    cursor.execute(sql_aluno, params)
                    encontrados = cursor.fetchall() or []
                    if not encontrados:
                        raise ValueError("Nenhum aluno encontrado com essa matrícula ou CPF.")
                    if len(encontrados) > 1:
                        raise ValueError(
                            "Achei mais de um aluno. Use a matrícula completa ou o CPF completo."
                        )
                    aluno = encontrados[0]
                    nota = (request.form.get("nota") or "").strip()
                    if not nota:
                        raise ValueError("Informe a nota.")
                    if len(nota) > 20:
                        raise ValueError("A nota pode ter no máximo 20 caracteres.")
                    cursor.execute(
                        """
                        INSERT INTO provas_criadas_notas (prova_id, aluno_id, nota)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (prova_id, aluno_id)
                        DO UPDATE SET nota = EXCLUDED.nota
                        """,
                        (prova_id, aluno["id"], nota),
                    )
                    flash(
                        f"Nota {nota} lançada para {aluno.get('nome_completo')} "
                        f"(Mat. {aluno.get('matricula') or '—'}).",
                        "success",
                    )
                elif acao == "excluir_nota":
                    nota_id = request.form.get("nota_id", type=int)
                    cursor.execute(
                        """
                        DELETE FROM provas_criadas_notas n
                        USING provas_criadas p
                        WHERE n.id = %s AND n.prova_id = p.id AND p.funcionario_id = %s
                        """,
                        (nota_id, pessoa["id"]),
                    )
                    flash("Nota removida.", "success")
                conexao.commit()
                return redirect(url_for("sala_professor"))
            cursor.execute(
                """
                SELECT a.*, t.nome AS turma_nome
                FROM professor_arquivos a
                LEFT JOIN turmas t ON t.id = a.turma_id
                WHERE a.funcionario_id = %s
                ORDER BY a.criado_em DESC
                """,
                (pessoa["id"],),
            )
            arquivos = cursor.fetchall() or []
            cursor.execute(
                """
                SELECT p.*, t.nome AS turma_nome
                FROM provas_criadas p
                LEFT JOIN turmas t ON t.id = p.turma_id
                WHERE p.funcionario_id = %s
                ORDER BY p.criado_em DESC
                """,
                (pessoa["id"],),
            )
            provas = [dict(row) for row in (cursor.fetchall() or [])]
            notas_por_prova = {}
            if provas:
                ids = [item["id"] for item in provas]
                cursor.execute(
                    """
                    SELECT n.id, n.prova_id, n.nota, a.nome_completo, a.matricula, a.cpf
                    FROM provas_criadas_notas n
                    JOIN alunos a ON a.id = n.aluno_id
                    WHERE n.prova_id = ANY(%s)
                    ORDER BY a.nome_completo
                    """,
                    (ids,),
                )
                for row in cursor.fetchall() or []:
                    notas_por_prova.setdefault(row["prova_id"], []).append(dict(row))
            for prova in provas:
                prova["notas"] = notas_por_prova.get(prova["id"], [])
            cursor.execute(
                "SELECT logo_escola, nome_escola, mensagem_prova FROM configuracoes WHERE id = 1"
            )
            escola = cursor.fetchone() or {}
    except Exception as e:
        conexao.rollback()
        flash(str(e), "danger")
        if request.method == "POST":
            return redirect(url_for("sala_professor"))
        return redirect(url_for("dashboard"))
    finally:
        conexao.close()
    return render_template(
        "sala_professor.html",
        pessoa=pessoa,
        turmas=turmas,
        arquivos=arquivos,
        provas=provas,
        escola=escola,
    )


@app.route("/minhas-provas/<int:prova_id>/pdf")
def prova_pdf(prova_id):
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    try:
        _garantir_sala_professor()
    except Exception as e:
        flash(f"Não foi possível preparar a sala do professor: {e}", "danger")
        return redirect(url_for("sala_professor"))
    funcionario_id = session.get("funcionario_id") or _id_funcionario_da_sessao()
    conexao = obter_conexao()
    if not conexao:
        flash("Sem conexão com o banco.", "danger")
        return redirect(url_for("sala_professor"))
    try:
        with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
            pessoa, _turmas = _professor_da_sessao(cursor, funcionario_id)
            if not pessoa:
                raise ValueError("Seu usuário não está ligado a um professor da equipe.")
            cursor.execute(
                """
                SELECT p.*, t.nome AS turma_nome
                FROM provas_criadas p
                LEFT JOIN turmas t ON t.id = p.turma_id
                WHERE p.id = %s AND p.funcionario_id = %s
                """,
                (prova_id, pessoa["id"]),
            )
            prova = cursor.fetchone()
            if not prova:
                raise ValueError("Prova não encontrada.")
            cursor.execute(
                """
                SELECT enunciado, tipo, alternativas, resposta
                FROM provas_criadas_questoes
                WHERE prova_id = %s
                ORDER BY ordem, id
                """,
                (prova_id,),
            )
            questoes = []
            for item in cursor.fetchall() or []:
                questoes.append({
                    "enunciado": item.get("enunciado"),
                    "tipo": item.get("tipo"),
                    "alternativas": [parte for parte in (item.get("alternativas") or "").split("\n")],
                    "resposta": item.get("resposta"),
                })
            cursor.execute(
                "SELECT nome_escola, logo_escola, mensagem_prova FROM configuracoes WHERE id = 1"
            )
            cfg = cursor.fetchone() or {}
            logo = None
            caminho = cfg.get("logo_escola") or ""
            if caminho.startswith("midia/"):
                cursor.execute("SELECT mime, dados FROM midia WHERE id = %s", (int(caminho.split("/")[-1]),))
                mid = cursor.fetchone()
                if mid and mid.get("dados"):
                    logo = (bytes(mid["dados"]), mid.get("mime"))
            tarja = (cfg.get("mensagem_prova") or "").strip()
    except Exception as e:
        flash(str(e), "danger")
        return redirect(url_for("sala_professor"))
    finally:
        conexao.close()
    buffer = pdf_prova(
        cfg.get("nome_escola") or "Gestão Escolar",
        prova.get("turma_nome") or "",
        prova.get("titulo"),
        prova.get("materia"),
        questoes,
        logo=logo,
        com_gabarito=request.args.get("gabarito") == "1",
        tarja=tarja,
    )
    nome = "gabarito" if request.args.get("gabarito") == "1" else "prova"
    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=False,
        download_name=f"{nome}_{prova_id}.pdf",
    )


@app.route("/minhas-provas/arquivo/<int:arquivo_id>")
def arquivo_professor(arquivo_id):
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    funcionario_id = _id_funcionario_da_sessao()
    conexao = obter_conexao()
    if not conexao:
        return "", 404
    try:
        with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
            pessoa, _turmas = _professor_da_sessao(cursor, funcionario_id)
            if not pessoa:
                return "", 404
            cursor.execute(
                """
                SELECT a.titulo, m.mime, m.dados
                FROM professor_arquivos a
                JOIN midia m ON m.id = a.midia_id
                WHERE a.id = %s AND a.funcionario_id = %s
                """,
                (arquivo_id, pessoa["id"]),
            )
            row = cursor.fetchone()
    finally:
        conexao.close()
    if not row or not row.get("dados"):
        return "", 404
    resp = app.response_class(bytes(row["dados"]), mimetype=row.get("mime") or "application/pdf")
    resp.headers["Content-Disposition"] = f"inline; filename=arquivo_{arquivo_id}.pdf"
    return resp


@app.route('/calendario_escolar', methods=['GET', 'POST'])
def calendario_escolar():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    garantir_tabelas_pedagogicas()
    papel_cal = normalizar_papel(session.get("usuario_papel"))
    gestor_calendario = papel_cal in {"admin", "direcao", "supervisor", "secretaria"}
    meu_professor_id = _id_funcionario_da_sessao()
    filtro_professor = request.values.get("professor_id", type=int)
    if papel_cal == "professor":
        filtro_professor = meu_professor_id
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
                    cursor.execute(
                        "ALTER TABLE calendario_eventos ADD COLUMN IF NOT EXISTS periodo VARCHAR(20)"
                    )
                    if acao == "excluir_rotina":
                        evento_id = request.form.get("evento_id", type=int)
                        cursor.execute(
                            "SELECT professor_id, tipo FROM calendario_eventos WHERE id = %s",
                            (evento_id,),
                        )
                        dono = cursor.fetchone() or {}
                        if not str(dono.get("tipo") or "").startswith("rotina"):
                            raise ValueError("Só a rotina do professor pode ser apagada por aqui.")
                        if papel_cal == "professor" and dono.get("professor_id") != meu_professor_id:
                            raise ValueError("Essa rotina é de outro professor.")
                        cursor.execute("DELETE FROM calendario_eventos WHERE id = %s", (evento_id,))
                        conexao.commit()
                        flash("Rotina removida.", "success")
                    elif acao == "marcar_frequencia":
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
                        periodo = (request.form.get("periodo") or "").strip() or None
                        if horario in ("", "None"):
                            horario = None
                        if tipo == "rotina":
                            if papel_cal == "professor":
                                professor_id = meu_professor_id
                            if not professor_id:
                                raise ValueError("Escolha o professor da rotina.")
                            if papel_cal == "professor" and not meu_professor_id:
                                raise ValueError("Seu usuário não está ligado a um professor da equipe.")
                        cursor.execute(
                            '''
                            INSERT INTO calendario_eventos (titulo, descricao, data_evento, tipo, turma_id, professor_id, aluno_id, horario, periodo)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ''',
                            (titulo, descricao, data_evento, tipo, turma_id, professor_id, aluno_id, horario, periodo),
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
        if filtro_professor and papel_cal != "professor":
            kwargs["professor_id"] = filtro_professor
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
                cursor.execute(
                    "ALTER TABLE calendario_eventos ADD COLUMN IF NOT EXISTS periodo VARCHAR(20)"
                )
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
                visiveis = []
                for ev in eventos:
                    if not str(ev.get("tipo") or "").startswith("rotina"):
                        visiveis.append(ev)
                        continue
                    dono = ev.get("professor_id")
                    if papel_cal == "professor" and dono == meu_professor_id:
                        visiveis.append(ev)
                    elif gestor_calendario and filtro_professor and dono == filtro_professor:
                        visiveis.append(ev)
                eventos = visiveis

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

    def _data_evento(valor):
        if isinstance(valor, datetime):
            return valor.date()
        if isinstance(valor, date):
            return valor
        try:
            return datetime.strptime(str(valor)[:10], "%Y-%m-%d").date()
        except ValueError:
            return None

    dias_visiveis = {dia for semana in dias_do_mes for dia in semana}
    eventos_por_dia = {}
    rotinas_do_mes = []
    for ev in eventos:
        data_ev = _data_evento(ev.get("data_evento"))
        if not data_ev:
            continue
        periodo = (ev.get("periodo") or "").strip().lower()
        ev["periodo"] = periodo or None
        eh_rotina = str(ev.get("tipo") or "").startswith("rotina")
        if eh_rotina and periodo == "semana":
            inicio = data_ev - timedelta(days=(data_ev.weekday() + 1) % 7)
            datas = [inicio + timedelta(days=i) for i in range(7)]
        elif eh_rotina and periodo == "mes":
            datas = [
                dia for dia in dias_visiveis
                if dia.year == data_ev.year and dia.month == data_ev.month
            ]
            if data_ev.year == ano and data_ev.month == mes:
                rotinas_do_mes.append(ev)
        else:
            datas = [data_ev]
        ev["aparece_mes"] = any(dia.year == ano and dia.month == mes for dia in datas)
        for dia in datas:
            if dia not in dias_visiveis:
                continue
            eventos_por_dia.setdefault(dia.isoformat(), []).append(ev)

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
    if filtro_professor and papel_cal != "professor":
        cal_params["professor_id"] = filtro_professor

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
        filtro_professor=filtro_professor,
        meu_professor_id=meu_professor_id,
        gestor_calendario=gestor_calendario,
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
        rotinas_do_mes=rotinas_do_mes,
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


def _como_data(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        return datetime.strptime(str(valor)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _rotina_no_intervalo(data_ev, periodo, inicio, fim):
    data_ev = _como_data(data_ev)
    if not data_ev:
        return False
    periodo = (periodo or "dia").strip().lower()
    if periodo == "semana":
        inicio_sem = data_ev - timedelta(days=(data_ev.weekday() + 1) % 7)
        fim_sem = inicio_sem + timedelta(days=6)
        return inicio_sem <= fim and fim_sem >= inicio
    if periodo == "mes":
        inicio_mes = date(data_ev.year, data_ev.month, 1)
        if data_ev.month == 12:
            fim_mes = date(data_ev.year, 12, 31)
        else:
            fim_mes = date(data_ev.year, data_ev.month + 1, 1) - timedelta(days=1)
        return inicio_mes <= fim and fim_mes >= inicio
    return inicio <= data_ev <= fim


@app.route("/relatorio/pdf", methods=["GET", "POST"])
def relatorio_pdf_consulta():
    return relatorio_pdf_periodo(request.values.get("tipo") or "chamada")


@app.route("/relatorio/pdf/<tipo>", methods=["GET", "POST"])
def relatorio_pdf_periodo(tipo):
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    tipo = (tipo or "").strip().lower()
    if tipo not in ("chamada", "eventos", "rotina", "completo"):
        flash("❌ Tipo de relatório inválido.", "danger")
        return redirect(url_for("calendario_escolar"))

    periodo = request.values.get("periodo") or "mes"
    data_str = request.values.get("data") or date.today().isoformat()
    turma_id = request.values.get("turma_id", type=int)
    aluno_id = request.values.get("aluno_id", type=int)
    origem = request.values.get("origem") or "calendario"
    destino_erro = url_for("calendario_escolar") if origem != "pedagogico" else url_for("pagina_pedagogico")
    papel_pdf = normalizar_papel(session.get("usuario_papel"))
    gestor_pdf = papel_pdf in {"admin", "direcao", "supervisor", "secretaria"}
    meu_professor_pdf = _id_funcionario_da_sessao()
    filtro_professor_pdf = request.values.get("professor_id", type=int)
    if papel_pdf == "professor":
        filtro_professor_pdf = meu_professor_pdf

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

            if filtro_professor_pdf and papel_pdf != "professor":
                cursor.execute(
                    "SELECT nome_completo FROM funcionarios WHERE id = %s",
                    (filtro_professor_pdf,),
                )
                dono = cursor.fetchone()
                if dono:
                    contexto_partes.append(f"Rotina de {dono.get('nome_completo')}")

            if tipo in ("eventos", "rotina", "completo"):
                cursor.execute(
                    "ALTER TABLE calendario_eventos ADD COLUMN IF NOT EXISTS periodo VARCHAR(20)"
                )
                sql_ev = """
                    SELECT c.data_evento, c.titulo, c.tipo, c.horario, c.descricao, c.periodo,
                           c.professor_id, t.nome AS turma_nome, f.nome_completo AS professor_nome
                    FROM calendario_eventos c
                    LEFT JOIN turmas t ON c.turma_id = t.id
                    LEFT JOIN funcionarios f ON f.id = c.professor_id
                    WHERE c.data_evento BETWEEN %s AND %s
                      AND COALESCE(c.tipo, 'geral') <> 'aluno_vinculado_turma'
                """
                params_ev = [inicio - timedelta(days=31), fim + timedelta(days=6)]
                if turma_id:
                    sql_ev += " AND (c.turma_id IS NULL OR c.turma_id = %s)"
                    params_ev.append(turma_id)
                sql_ev += " ORDER BY c.data_evento, c.horario NULLS LAST, c.titulo"
                cursor.execute(sql_ev, params_ev)
                eventos = cursor.fetchall()

            if tipo in ("eventos", "completo"):
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

    def _mesmo_professor(valor):
        try:
            return int(valor) == int(filtro_professor_pdf)
        except (TypeError, ValueError):
            return False

    escolares = []
    rotinas = []
    for ev in eventos:
        eh_rotina = str(ev.get("tipo") or "").startswith("rotina")
        if eh_rotina:
            if aluno_id or not _rotina_no_intervalo(ev.get("data_evento"), ev.get("periodo"), inicio, fim):
                continue
            if papel_pdf == "professor" and _mesmo_professor(ev.get("professor_id")):
                rotinas.append(ev)
            elif gestor_pdf and filtro_professor_pdf and _mesmo_professor(ev.get("professor_id")):
                rotinas.append(ev)
            continue
        data_ev = _como_data(ev.get("data_evento"))
        if data_ev and inicio <= data_ev <= fim:
            escolares.append(ev)

    aviso_rotina = ""
    if tipo in ("rotina", "completo") and not aluno_id and not rotinas:
        if papel_pdf == "professor" and not meu_professor_pdf:
            aviso_rotina = "Seu usuário não está ligado a um professor, então a rotina não entra neste PDF."
        elif papel_pdf != "professor" and not filtro_professor_pdf:
            aviso_rotina = "A rotina de cada professor fica de fora. No calendário, filtre o professor para incluir só a rotina dele."

    titulos_pdf = {
        "chamada": "Chamada",
        "eventos": "Agenda da escola",
        "rotina": "Rotina do professor",
        "completo": "Histórico do período",
    }
    buffer = pdf_historico_periodo(
        escola,
        periodo_label,
        " · ".join(contexto_partes) if contexto_partes else "Escola (geral)",
        incluir_chamada=tipo in ("chamada", "completo"),
        incluir_eventos=tipo in ("eventos", "completo"),
        incluir_rotina=tipo in ("rotina", "completo") or (tipo == "eventos" and bool(rotinas)),
        incluir_provas=tipo in ("eventos", "completo"),
        chamada=chamada,
        eventos=escolares,
        rotinas=rotinas,
        provas=provas,
        resumo_chamada=resumo,
        aviso_rotina=aviso_rotina if tipo != "chamada" else "",
        titulo=titulos_pdf.get(tipo, "Histórico do período"),
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

        if acao == "excluir_alunos":
            ids = []
            for bruto in request.form.getlist("aluno_id"):
                try:
                    aluno_id = int(bruto)
                except (TypeError, ValueError):
                    continue
                if aluno_id not in ids:
                    ids.append(aluno_id)
            if not ids:
                flash("Selecione ao menos um aluno para excluir.", "danger")
                return redirect(url_for("pagina_alunos"))
            conexao = obter_conexao()
            if not conexao:
                flash("Não foi possível conectar ao banco para excluir os alunos.", "danger")
                return redirect(url_for("pagina_alunos"))
            try:
                with conexao.cursor() as cursor:
                    cursor.execute("DELETE FROM alunos WHERE id = ANY(%s)", (ids,))
                    apagados = cursor.rowcount
                conexao.commit()
                flash(f"{apagados} aluno(s) excluído(s).", "success")
            except Exception as e:
                conexao.rollback()
                flash(f"Erro ao excluir os alunos selecionados: {e}", "danger")
            finally:
                conexao.close()
            return redirect(url_for("pagina_alunos"))

        if acao == "editar_aluno":
            aluno_id = request.form.get("aluno_id")
            if aluno_id:
                status_bruto = request.form.get("status")
                if status_bruto is not None:
                    status_bruto = status_bruto.strip().lower()
                status = "inativo" if status_bruto in ["inativo", "inactive", "false", "0", "off"] else "ativo"
                
                telefone_principal = (
                    limpar_campo("telefone_principal")
                    or request.form.get("telefone_principal")
                    or limpar_campo("telefone")
                    or request.form.get("telefone")
                )
                foto_aluno = None
                try:
                    foto_aluno = _salvar_foto("foto")
                except ValueError as e:
                    flash(str(e), "danger")

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
                                    cep = %s,
                                    rua = %s,
                                    numero = %s,
                                    bairro = %s,
                                    cidade = %s,
                                    estado = %s,
                                    valor_mensalidade = COALESCE(%s, valor_mensalidade),
                                    contrato_meses = COALESCE(%s, contrato_meses),
                                    contrato_inicio = COALESCE(%s::date, contrato_inicio),
                                    turnos_mensalidade = COALESCE(%s, turnos_mensalidade),
                                    foto_url = COALESCE(%s, foto_url)
                                WHERE id = %s;
                            """, (
                                limpar_campo("nome_completo"),
                                status,
                                limpar_campo("cpf"),
                                limpar_campo("rg"),
                                limpar_campo("data_nascimento") or "2000-01-01",
                                telefone_principal,
                                limpar_campo("email"),
                                limpar_campo("cep"),
                                limpar_campo("rua") or limpar_campo("logradouro"),
                                limpar_campo("numero"),
                                limpar_campo("bairro"),
                                limpar_campo("cidade"),
                                (limpar_campo("estado") or limpar_campo("estado_uf") or "")[:2] or None,
                                _float_form("valor_mensalidade") or None,
                                request.form.get("contrato_meses") or None,
                                limpar_campo("contrato_inicio"),
                                limpar_campo("turnos_mensalidade"),
                                foto_aluno,
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

        if acao in ("editar_autorizado", "deletar_autorizado"):
            aluno_id = request.form.get("aluno_id")
            aut_id = request.form.get("autorizado_id")
            if aluno_id and aut_id:
                conexao = obter_conexao()
                if conexao:
                    try:
                        with conexao.cursor() as cursor:
                            if acao == "deletar_autorizado":
                                cursor.execute(
                                    "DELETE FROM pessoas_autorizadas WHERE id = %s AND aluno_id = %s",
                                    (aut_id, aluno_id),
                                )
                                flash("Pessoa autorizada removida.", "success")
                            else:
                                foto_aut = None
                                try:
                                    foto_aut = _salvar_foto("foto", "autorizados")
                                except ValueError as e:
                                    flash(str(e), "danger")
                                cursor.execute(
                                    """
                                    UPDATE pessoas_autorizadas
                                    SET nome_completo = %s, cpf = %s, telefone = %s, vinculo = %s, endereco = %s,
                                        foto_url = COALESCE(%s, foto_url)
                                    WHERE id = %s AND aluno_id = %s
                                    """,
                                    (
                                        limpar_campo("nome_completo"),
                                        limpar_campo("cpf"),
                                        limpar_campo("telefone"),
                                        limpar_campo("vinculo") or limpar_campo("grau_parentesco"),
                                        _endereco_do_form(),
                                        foto_aut,
                                        aut_id,
                                        aluno_id,
                                    ),
                                )
                                flash("Pessoa autorizada atualizada.", "success")
                        conexao.commit()
                    except Exception as e:
                        conexao.rollback()
                        flash(f"Erro ao atualizar pessoa autorizada: {e}", "danger")
                    finally:
                        conexao.close()
                return redirect(url_for("detalhes_aluno", aluno_id=aluno_id))

        if acao == "importar_alunos":
            arquivo = request.files.get("planilha_alunos")
            if not arquivo or not arquivo.filename:
                flash("Selecione uma planilha CSV ou Excel com os alunos.", "danger")
                return redirect(url_for("pagina_alunos"))
            try:
                itens = importar_planilha_alunos(arquivo)
                if not itens:
                    flash("A planilha não trouxe nenhum aluno válido.", "danger")
                    return redirect(url_for("pagina_alunos"))
                ok, erros, avisos = cadastrar_alunos_lote(itens)
            except Exception as e:
                flash(f"Não foi possível importar a planilha: {e}", "danger")
                return redirect(url_for("pagina_alunos"))
            if ok:
                conexao_lote = obter_conexao()
                if conexao_lote:
                    try:
                        with conexao_lote.cursor(cursor_factory=RealDictCursor) as cursor:
                            _gerar_mensalidades_lote(cursor, ok)
                        conexao_lote.commit()
                    except Exception as e:
                        conexao_lote.rollback()
                        flash(f"Alunos salvos, mas as mensalidades do lote falharam: {e}", "danger")
                    finally:
                        conexao_lote.close()
            novos = sum(1 for row in ok if not row.get("atualizado"))
            atualizados = len(ok) - novos
            partes = []
            if novos:
                partes.append(f"{novos} aluno(s) cadastrado(s)")
            if atualizados:
                partes.append(f"{atualizados} atualizado(s) com os dados da planilha")
            msg = ", ".join(partes) or "Nenhum aluno importado."
            if avisos:
                msg += " Avisos: " + " | ".join(avisos[:6])
            if erros:
                extra = " | ".join(erros[:8])
                if len(erros) > 8:
                    extra += f" (+{len(erros) - 8})"
                flash(extra, "danger")
            if ok:
                flash(msg, "success")
            elif not erros:
                flash(msg, "danger")
            return redirect(url_for("pagina_alunos"))

        if acao == "cadastrar_aluno":
            valor_mensalidade = _parse_moeda(request.form.get("valor_mensalidade"), 0.0)
            desconto_valor = _parse_moeda(request.form.get("desconto_valor"), 0.0)

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

            try:
                foto_aluno = _salvar_foto("foto")
                foto_r1 = _salvar_foto("resp1_foto")
                foto_r2 = _salvar_foto("resp2_foto")
            except ValueError as e:
                flash(str(e), "danger")
                foto_aluno = foto_r1 = foto_r2 = None

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
                "contrato_meses": request.form.get("contrato_meses") or 12,
                "contrato_inicio": limpar_campo("contrato_inicio") or None,
                "turnos_mensalidade": limpar_campo("turnos_mensalidade") or "manha",
                "foto_url": foto_aluno,
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
                "foto_url": foto_r1,
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
                "foto_url": foto_r2,
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
            except ValueError as e:
                flash(str(e), "danger")
            except Exception as e:
                flash(f"Erro de banco de dados: {e}", "danger")

        voltar_turma = request.form.get("voltar_turma")
        if voltar_turma:
            return redirect(url_for("pagina_pedagogico", aba="turmas", turma_sel=voltar_turma, painel="alunos"))
        return redirect(url_for("pagina_alunos"))

    termo_busca = request.args.get("q", "").strip()
    alunos = listar_alunos(termo_busca)
    turmas = []
    conexao_t = obter_conexao()
    if conexao_t:
        try:
            with conexao_t.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT t.id, t.nome, t.ano_letivo, t.turno, f.nome_completo AS professor
                    FROM turmas t
                    LEFT JOIN funcionarios f ON t.professor_responsavel_id = f.id
                    ORDER BY t.nome
                    """
                )
                turmas = cursor.fetchall()
        except Exception:
            turmas = []
        finally:
            conexao_t.close()
    turma_pre = request.args.get("turma_id") or ""
    abrir_cadastro = bool(request.args.get("novo") or turma_pre)
    return render_template(
        "alunos.html",
        alunos=alunos,
        termo_busca=termo_busca,
        turmas=turmas,
        turma_pre=turma_pre,
        abrir_cadastro=abrir_cadastro,
        voltar_turma=turma_pre if request.args.get("voltar") else "",
    )


def _nome_da_escola(cursor):
    cursor.execute("SELECT nome_escola FROM configuracoes WHERE id = 1")
    row = cursor.fetchone() or {}
    if isinstance(row, dict):
        return row.get("nome_escola") or "Gestão Escolar"
    return (row[0] if row else None) or "Gestão Escolar"


@app.route("/alunos/pdf")
def relatorio_alunos_pdf():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    termo = (request.args.get("q") or "").strip()
    alunos = listar_alunos(termo)
    escola = "Gestão Escolar"
    conexao = obter_conexao()
    if conexao:
        try:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                escola = _nome_da_escola(cursor)
        finally:
            conexao.close()
    buffer = pdf_lista_alunos(escola, alunos, termo)
    return send_file(buffer, mimetype="application/pdf", as_attachment=True, download_name="alunos.pdf")


@app.route("/professores/pdf")
def relatorio_equipe_pdf():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    termo = (request.args.get("q") or "").strip().lower()
    pessoas = []
    escola = "Gestão Escolar"
    conexao = obter_conexao()
    if conexao:
        try:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                escola = _nome_da_escola(cursor)
                cursor.execute(
                    """
                    SELECT f.nome_completo, f.especialidade AS disciplina, f.telefone, f.cargo, u.papel,
                           STRING_AGG(t.nome, ', ') AS turmas_lecionadas
                    FROM funcionarios f
                    LEFT JOIN turmas t ON t.professor_responsavel_id = f.id
                    LEFT JOIN LATERAL (
                        SELECT papel FROM usuarios
                        WHERE id = f.usuario_id OR LOWER(COALESCE(email, '')) = LOWER(COALESCE(f.email, ''))
                        ORDER BY CASE WHEN id = f.usuario_id THEN 0 ELSE 1 END
                        LIMIT 1
                    ) u ON TRUE
                    WHERE COALESCE(f.ativo, TRUE) = TRUE
                    GROUP BY f.id, f.nome_completo, f.especialidade, f.telefone, f.cargo, u.papel
                    ORDER BY f.nome_completo
                    """
                )
                pessoas = cursor.fetchall() or []
        finally:
            conexao.close()
    if termo:
        pessoas = [
            item for item in pessoas
            if termo in (item.get("nome_completo") or "").lower()
            or termo in (item.get("cargo") or "").lower()
            or termo in (item.get("disciplina") or "").lower()
            or termo in (item.get("turmas_lecionadas") or "").lower()
        ]
    buffer = pdf_lista_equipe(escola, pessoas)
    return send_file(buffer, mimetype="application/pdf", as_attachment=True, download_name="equipe.pdf")


@app.route("/pedagogico/turmas/pdf")
def relatorio_turmas_pdf():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    turmas = []
    escola = "Gestão Escolar"
    conexao = obter_conexao()
    if conexao:
        try:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                escola = _nome_da_escola(cursor)
                cursor.execute(
                    """
                    SELECT t.id, t.nome, t.ano_letivo, t.turno, f.nome_completo AS professor,
                           a.nome_completo AS aluno_nome, a.matricula
                    FROM turmas t
                    LEFT JOIN funcionarios f ON f.id = t.professor_responsavel_id
                    LEFT JOIN turma_alunos ta ON ta.turma_id = t.id
                    LEFT JOIN alunos a ON a.id = ta.aluno_id
                    ORDER BY t.nome, a.nome_completo
                    """
                )
                grupos = {}
                for row in cursor.fetchall() or []:
                    item = grupos.get(row["id"])
                    if not item:
                        item = {
                            "nome": row.get("nome"),
                            "ano_letivo": row.get("ano_letivo"),
                            "turno": row.get("turno"),
                            "professor": row.get("professor"),
                            "alunos": [],
                        }
                        grupos[row["id"]] = item
                        turmas.append(item)
                    if row.get("aluno_nome"):
                        item["alunos"].append({"nome": row.get("aluno_nome"), "matricula": row.get("matricula")})
        finally:
            conexao.close()
    buffer = pdf_turmas(escola, turmas)
    return send_file(buffer, mimetype="application/pdf", as_attachment=True, download_name="turmas.pdf")


@app.route("/notas-fiscais/pdf")
def relatorio_nfse_pdf():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    status = (request.args.get("status") or "").strip()
    aluno = request.args.get("aluno", type=int)
    mes = (request.args.get("mes") or datetime.now().strftime("%Y-%m"))[:7]
    grupos = []
    faturado = 0
    escola = "Gestão Escolar"
    conexao = obter_conexao()
    if conexao:
        try:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                escola = _nome_da_escola(cursor)
                grupos = listar_notas_escola(cursor, status or None, aluno)
                faturado = faturamento_das_notas(cursor, mes)
        finally:
            conexao.close()
    buffer = pdf_notas_fiscais(escola, mes, faturado, grupos)
    return send_file(buffer, mimetype="application/pdf", as_attachment=True, download_name=f"notas_fiscais_{mes}.pdf")


@app.route("/auditoria/pdf")
def relatorio_auditoria_pdf():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    if session.get("usuario_papel") != "admin":
        flash("A auditoria fica disponível apenas para o administrador da escola.", "danger")
        return redirect(url_for("dashboard"))
    tipo = (request.args.get("tipo") or "").strip()
    busca = (request.args.get("busca") or "").strip()
    registros = listar_auditoria(session.get("escola_id"), tipo, busca)
    buffer = pdf_auditoria(session.get("escola_nome") or "Gestão Escolar", registros)
    return send_file(buffer, mimetype="application/pdf", as_attachment=True, download_name="auditoria.pdf")


@app.route("/minhas-provas/pdf")
def pasta_professor_pdf():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    try:
        _garantir_sala_professor()
    except Exception as e:
        flash(f"Não foi possível preparar a sala do professor: {e}", "danger")
        return redirect(url_for("sala_professor"))
    funcionario_id = session.get("funcionario_id") or _id_funcionario_da_sessao()
    conexao = obter_conexao()
    if not conexao:
        flash("Sem conexão com o banco.", "danger")
        return redirect(url_for("sala_professor"))
    try:
        with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
            pessoa, _turmas = _professor_da_sessao(cursor, funcionario_id)
            if not pessoa:
                flash("Seu usuário não está ligado a um professor da equipe.", "danger")
                return redirect(url_for("dashboard"))
            escola = _nome_da_escola(cursor)
            cursor.execute(
                """
                SELECT a.tipo, a.titulo, t.nome AS turma_nome
                FROM professor_arquivos a
                LEFT JOIN turmas t ON t.id = a.turma_id
                WHERE a.funcionario_id = %s
                ORDER BY a.criado_em DESC
                """,
                (pessoa["id"],),
            )
            arquivos = cursor.fetchall() or []
            cursor.execute(
                """
                SELECT p.titulo, p.materia, t.nome AS turma_nome
                FROM provas_criadas p
                LEFT JOIN turmas t ON t.id = p.turma_id
                WHERE p.funcionario_id = %s
                ORDER BY p.criado_em DESC
                """,
                (pessoa["id"],),
            )
            provas = cursor.fetchall() or []
    finally:
        conexao.close()
    buffer = pdf_pasta_professor(escola, pessoa.get("nome_completo"), arquivos, provas)
    return send_file(buffer, mimetype="application/pdf", as_attachment=True, download_name="pasta_professor.pdf")


@app.route("/alunos/modelo.csv")
def modelo_alunos_csv():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    cab = (
        "nome_completo;data_nascimento;cpf;rg;sexo;telefone;email;cep;rua;numero;bairro;cidade;estado;"
        "mensalidade;turno;contrato_meses;contrato_inicio;turma;resp1_nome;resp1_cpf;resp1_parentesco;resp1_telefone;resp1_email\n"
        "Maria Silva;15/03/2018;;;F;(11) 99999-0000;responsavel@escola.com;01310-100;Av Paulista;1000;Bela Vista;São Paulo;SP;"
        "850,00;manha;12;01/02/2026;Infantil I;Ana Silva;000.000.000-00;mãe;(11) 98888-0000;ana@email.com\n"
    )
    return Response(
        "\ufeff" + cab,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=modelo_alunos.csv"},
    )


@app.route("/financeiro/alunos/modelo.csv")
def modelo_alunos_financeiro_csv():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    cab = (
        "aluno;nascimento;turma;inicio;responsavel;parentesco;telefone;email\n"
        "Maria Silva;15/03/2018;Infantil I;01/02/2026;Ana Silva;mãe;(11) 98888-0000;ana@email.com\n"
        "João Souza;02/08/2017;1º ano;01/02/2026;Carlos Souza;pai;(11) 97777-0000;carlos@email.com\n"
    )
    return Response(
        "\ufeff" + cab,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=modelo_alunos_financeiro.csv"},
    )


@app.route("/financeiro/custos/modelo.csv")
def modelo_custos_csv():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    cab = (
        "tipo;descricao;categoria;valor;data;forma;parcelas;data_fim;prestador;valor_bruto;reter_federal;reter_iss\n"
        "avista;Energia elétrica;operacional;890,50;22/09/2026;pix;;;;;\n"
        "recorrente;Aluguel;operacional;4500,00;01/02/2026;boleto;;31/12/2026;;;\n"
        "parcelado;Notebook;equipamento;350,00;01/03/2026;cartao;10;;;;\n"
        "servico;Contabilidade;servico;1200,00;05/09/2026;pix;;;Escritório Alfa;1200,00;sim;nao\n"
    )
    return Response(
        "\ufeff" + cab,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=modelo_custos.csv"},
    )


@app.route("/financeiro/simples/modelo.csv")
def modelo_simples_csv():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    cab = (
        "competencia;receita_bruta;folha_encargos\n"
        "2025-09;120000,00;38000,00\n"
        "2025-10;125000,00;38200,00\n"
    )
    return Response(
        "\ufeff" + cab,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=modelo_simples_rbt12.csv"},
    )


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
    todas_turmas = []
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
                    SELECT id, nome_completo, cpf, telefone, vinculo, endereco, foto_url
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
                cursor.execute(
                    """
                    SELECT t.id, t.nome, t.ano_letivo, t.turno, f.nome_completo AS professor
                    FROM turmas t
                    LEFT JOIN funcionarios f ON f.id = t.professor_responsavel_id
                    ORDER BY t.nome
                    """
                )
                todas_turmas = cursor.fetchall()
                try:
                    anexar_ultima_nota(cursor, financeiro_aluno)
                except Exception:
                    conexao.rollback()
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
        todas_turmas=todas_turmas,
    )


@app.route("/alunos/<int:aluno_id>/turma", methods=["POST"])
def aluno_vincular_turma(aluno_id):
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    turma_id = request.form.get("turma_id")
    acao = request.form.get("acao") or "vincular"
    permissao = "excluir" if acao == "desvincular" else "alterar"
    if not pode_acao(session.get("usuario_papel"), "pedagogico_cadastro", permissao, session.get("permissoes")):
        flash(
            "Sem permissão para tirar o aluno da turma." if permissao == "excluir" else "Sem permissão para enturmar aluno.",
            "danger",
        )
        return redirect(url_for("detalhes_aluno", aluno_id=aluno_id))
    conexao = obter_conexao()
    if conexao and turma_id:
        try:
            with conexao.cursor() as cursor:
                if acao == "desvincular":
                    cursor.execute(
                        "DELETE FROM turma_alunos WHERE turma_id = %s AND aluno_id = %s",
                        (turma_id, aluno_id),
                    )
                    flash("Aluno saiu da turma. O cadastro foi mantido.", "success")
                else:
                    cursor.execute(
                        """
                        INSERT INTO turma_alunos (turma_id, aluno_id)
                        VALUES (%s, %s)
                        ON CONFLICT (turma_id, aluno_id) DO NOTHING
                        """,
                        (turma_id, aluno_id),
                    )
                    flash("Aluno vinculado à turma a partir do cadastro.", "success")
            conexao.commit()
        except Exception as e:
            conexao.rollback()
            flash(f"Não foi possível atualizar a turma: {e}", "danger")
        finally:
            conexao.close()
    return redirect(url_for("detalhes_aluno", aluno_id=aluno_id) + "#turmas")


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
            cpf_aluno = limpar_campo("cpf")

            with conexao.cursor() as cursor:
                repetido = buscar_cpf_repetido(cursor, cpf_aluno, ignorar_aluno_id=aluno_id)
                if repetido:
                    flash(mensagem_cpf_repetido(*repetido), "danger")
                    return redirect(url_for("detalhes_aluno", aluno_id=aluno_id))
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
            foto_resp = _salvar_foto("foto")
            atualizar_responsavel(resp_id, {
                "nome_completo": limpar_campo("nome_completo"),
                "cpf": limpar_campo("cpf"),
                "grau_parentesco": limpar_campo("grau_parentesco") or limpar_campo("parentesco"),
                "telefone": limpar_campo("telefone") or limpar_campo("telefone_principal"),
                "email": email_resp,
                "local_trabalho": limpar_campo("local_trabalho"),
                "telefone_trabalho": limpar_campo("telefone_trabalho"),
                "foto_url": foto_resp,
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
                foto_resp = _salvar_foto("foto")

                cursor.execute("""
                    INSERT INTO responsaveis_aluno (
                        aluno_id, tipo_responsavel, nome_completo, cpf, grau_parentesco,
                        telefone, email, local_trabalho, telefone_trabalho, foto_url
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (
                    aluno_id, proximo_tipo, limpar_campo("nome_completo"), limpar_campo("cpf"),
                    parentesco, telefone, email_resp,
                    limpar_campo("local_trabalho"), limpar_campo("telefone_trabalho"),
                    foto_resp
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

    garantir_tabelas_folha()
    garantir_tabelas_pedagogicas()

    conexao = obter_conexao()
    if conexao:
        try:
            with conexao.cursor() as cursor:
                foto_aut = None
                try:
                    foto_aut = _salvar_foto("foto", "autorizados")
                except ValueError as e:
                    flash(str(e), "danger")
                cursor.execute("""
                    INSERT INTO pessoas_autorizadas (aluno_id, nome_completo, cpf, telefone, vinculo, endereco, foto_url)
                    VALUES (%s, %s, %s, %s, %s, %s, %s);
                """, (aluno_id, limpar_campo("nome_completo"), limpar_campo("cpf"),
                      limpar_campo("telefone"), limpar_campo("vinculo") or limpar_campo("grau_parentesco"),
                      _endereco_do_form(), foto_aut))
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
                           f.cargo, f.tipo_contrato, f.foto_url, u.papel,
                           STRING_AGG(t.nome, ', ') AS turmas_lecionadas
                    FROM funcionarios f
                    LEFT JOIN turmas t ON t.professor_responsavel_id = f.id
                    LEFT JOIN LATERAL (
                        SELECT papel FROM usuarios
                        WHERE id = f.usuario_id OR LOWER(COALESCE(email, '')) = LOWER(COALESCE(f.email, ''))
                        ORDER BY CASE WHEN id = f.usuario_id THEN 0 ELSE 1 END
                        LIMIT 1
                    ) u ON TRUE
                    WHERE COALESCE(f.ativo, TRUE) = TRUE
                    GROUP BY f.id, f.nome_completo, f.especialidade, f.email, f.telefone, f.salario,
                             f.cargo, f.tipo_contrato, f.foto_url, u.papel
                    ORDER BY f.nome_completo ASC;
                """)
                professores_cadastrados = cursor.fetchall()
                for p in professores_cadastrados:
                    p["disciplina"] = _disciplina_visivel(p.get("disciplina"))
                    if not (p.get("cargo") or "").strip():
                        p["cargo"] = _cargo_do_papel(p.get("papel"))
        finally:
            conexao.close()

    if busca_prof:
        termo = busca_prof.lower()
        professores_cadastrados = [
            p for p in professores_cadastrados
            if termo in (p.get("nome_completo") or "").lower()
            or termo in (p.get("email") or "").lower()
            or termo in (p.get("disciplina") or "").lower()
            or termo in (p.get("cargo") or "").lower()
            or termo in rotulo_papel(p.get("papel")).lower()
        ]

    return render_template(
        "professores.html",
        professores=professores_cadastrados,
        busca_prof=busca_prof,
        nome_do_papel=rotulo_papel,
    )


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
                        turma_id = limpar_campo("turma_id")
                        ids = [item for item in request.form.getlist("aluno_id") if str(item).strip()]
                        if not ids:
                            unico = limpar_campo("aluno_id")
                            if unico:
                                ids = [unico]
                        vinculados = 0
                        for aid in ids:
                            cursor.execute(
                                """
                                INSERT INTO turma_alunos (turma_id, aluno_id)
                                VALUES (%s, %s)
                                ON CONFLICT (turma_id, aluno_id) DO NOTHING;
                                """,
                                (turma_id, aid),
                            )
                            vinculados += cursor.rowcount or 0
                        conexao.commit()
                        if vinculados:
                            flash(f"{vinculados} aluno(s) cadastrado(s) nesta turma.", "success")
                        else:
                            flash("Marque pelo menos um aluno com Sim para cadastrar na turma.", "danger")

                    elif acao == "desvincular_aluno":
                        cursor.execute(
                            "DELETE FROM turma_alunos WHERE turma_id = %s AND aluno_id = %s",
                            (limpar_campo("turma_id"), limpar_campo("aluno_id")),
                        )
                        conexao.commit()
                        flash("Aluno saiu desta turma. O cadastro em Alunos foi mantido.", "success")

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
                    if filtro_turno.lower() in {"híbrido", "hibrido", "integral"}:
                        query_turmas += " AND t.turno IN ('Híbrido', 'híbrido', 'hibrido', 'Integral', 'integral')"
                    else:
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

                cursor.execute(
                    """
                    SELECT a.id, a.nome_completo, a.matricula, a.foto_url,
                           COALESCE(NULLIF(TRIM(a.status), ''), 'ativo') AS status,
                           STRING_AGG(t.nome, ', ') AS turmas_atuais
                    FROM alunos a
                    LEFT JOIN turma_alunos ta ON ta.aluno_id = a.id
                    LEFT JOIN turmas t ON t.id = ta.turma_id
                    GROUP BY a.id
                    ORDER BY a.nome_completo ASC
                    """
                )
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

    telas_escola = session.get("escola_telas")
    cadastro_simples = isinstance(telas_escola, (list, tuple, set)) and "alunos" not in telas_escola
    garantir_tabelas_folha()
    garantir_tabelas_pedagogicas()
    mes_redir = request.form.get("mes") or request.args.get("mes") or datetime.now().strftime("%Y-%m")
    aba_redir = request.form.get("aba") or request.args.get("aba") or "resumo"

    if request.method == "POST":
        acao = request.form.get("acao")
        if acao and str(acao).startswith("simples"):
            aba_redir = "simples"
        if acao == "importar_custos":
            aba_redir = "custos"
        conexao = obter_conexao()
        if conexao:
            try:
                with conexao.cursor() as cursor:
                    if acao == "cadastrar_aluno_simples":
                        aba_redir = "receitas"
                        if not cadastro_simples:
                            flash("O cadastro completo de alunos continua na tela Alunos.", "danger")
                        else:
                            nome = (request.form.get("aluno_nome") or "").strip()
                            turma = (request.form.get("turma_nome") or "").strip()
                            resp_nome = (request.form.get("resp_nome") or "").strip()
                            nascimento = parse_data_livre(request.form.get("aluno_nascimento"))
                            if request.form.get("aluno_nascimento") and not nascimento:
                                raise ValueError("Data de nascimento inválida. Use dd/mm/aaaa.")
                            inicio = parse_data_livre(request.form.get("contrato_inicio"))
                            if request.form.get("contrato_inicio") and not inicio:
                                raise ValueError("Data de início inválida.")
                            item = {
                                "aluno": {
                                    "nome_completo": nome,
                                    "data_nascimento": nascimento,
                                    "turma_nome": turma,
                                    "contrato_inicio": inicio,
                                },
                                "resp1": {
                                    "nome_completo": resp_nome,
                                    "grau_parentesco": request.form.get("resp_parentesco") or "responsável",
                                    "telefone": (request.form.get("resp_telefone") or "").strip(),
                                    "email": (request.form.get("resp_email") or "").strip(),
                                } if resp_nome else None,
                            }
                            resultado = aplicar_aluno_simples(cursor, item, _mapa_turmas(cursor))
                            conexao.commit()
                            if resultado["atualizado"]:
                                flash(f"{resultado['nome']} já estava cadastrado. Turma e responsável foram atualizados.", "success")
                            else:
                                flash(f"{resultado['nome']} incluído. Já pode gerar a mensalidade.", "success")

                    elif acao == "importar_alunos_simples":
                        aba_redir = "receitas"
                        if not cadastro_simples:
                            flash("O cadastro completo de alunos continua na tela Alunos.", "danger")
                        else:
                            arquivo = request.files.get("planilha")
                            if not arquivo or not arquivo.filename:
                                flash("Selecione a planilha de alunos.", "danger")
                            else:
                                itens = ler_planilha_alunos_simples(arquivo)
                                if not itens:
                                    flash("A planilha não trouxe nenhum aluno.", "danger")
                                else:
                                    novos, atualizados, erros = salvar_alunos_simples(cursor, itens)
                                    conexao.commit()
                                    partes = []
                                    if novos:
                                        partes.append(f"{novos} aluno(s) incluído(s)")
                                    if atualizados:
                                        partes.append(f"{atualizados} atualizado(s)")
                                    texto = ", ".join(partes) or "Nenhum aluno importado."
                                    if erros:
                                        texto += " " + " ".join(erros[:5])
                                        flash(texto, "danger" if not (novos or atualizados) else "success")
                                    else:
                                        flash(texto + ". Já podem receber mensalidade.", "success")

                    elif acao == "criar_cobranca":
                        aba_redir = "receitas"
                        aluno_id = request.form.get("aluno_id")
                        descricao = limpar_campo("descricao") or "Mensalidade"
                        valor = _parse_moeda(request.form.get("valor"), 0.0)
                        data_vencimento = request.form.get("data_vencimento") or datetime.now().strftime("%Y-%m-%d")
                        try:
                            duracao = int(request.form.get("duracao") or 1)
                        except ValueError:
                            duracao = 1
                        turnos = request.form.get("turnos") or "manha"
                        if not aluno_id:
                            flash("Selecione o aluno da cobrança.", "danger")
                        elif valor <= 0:
                            flash("Informe o valor da mensalidade.", "danger")
                        else:
                            geradas = _gerar_mensalidades_contrato(
                                cursor, aluno_id, valor, data_vencimento, duracao, turnos, descricao, forcar=True
                            )
                            conexao.commit()
                            mes_redir = str(data_vencimento)[:7]
                            if geradas:
                                flash(f"Cobrança salva: {geradas} mensalidade(s) a partir de {mes_redir[5:7]}/{mes_redir[:4]}.", "success")
                            else:
                                flash("A cobrança não foi gravada.", "danger")

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

                    elif acao == "editar_cobranca":
                        try:
                            cobranca_id = int(request.form.get("cobranca_id"))
                            venc_date = datetime.strptime((request.form.get("data_vencimento") or "")[:10], "%Y-%m-%d").date()
                        except (TypeError, ValueError):
                            flash("Informe a data de vencimento.", "danger")
                        else:
                            status_edit = request.form.get("status") or "Pendente"
                            pago = status_edit == "Pago"
                            data_pag = (request.form.get("data_pagamento") or "").strip() or None
                            if pago and not data_pag:
                                data_pag = datetime.now().date()
                            if not pago:
                                data_pag = None
                            cursor.execute(
                                """
                                UPDATE financeiro_mensalidades
                                SET descricao = CASE
                                        WHEN COALESCE(%s, descricao) ~ '^Mensalidade [0-9]{2}/[0-9]{4}'
                                        THEN regexp_replace(
                                            COALESCE(%s, descricao),
                                            '^Mensalidade [0-9]{2}/[0-9]{4}',
                                            'Mensalidade ' || to_char(%s, 'MM/YYYY')
                                        )
                                        ELSE COALESCE(%s, descricao)
                                    END,
                                    valor = %s,
                                    data_vencimento = %s,
                                    data_pagamento = %s,
                                    status = CASE
                                        WHEN %s THEN 'Pago'
                                        WHEN %s < CURRENT_DATE THEN 'Atrasado'
                                        ELSE 'Pendente'
                                    END
                                WHERE id = %s
                                RETURNING id
                                """,
                                (
                                    limpar_campo("descricao"),
                                    limpar_campo("descricao"),
                                    venc_date,
                                    limpar_campo("descricao"),
                                    _parse_moeda(request.form.get("valor"), 0.0),
                                    venc_date,
                                    data_pag,
                                    pago,
                                    venc_date,
                                    cobranca_id,
                                ),
                            )
                            if cursor.fetchone():
                                conexao.commit()
                                mes_redir = venc_date.strftime("%Y-%m")
                                flash(
                                    f"Vencimento salvo em {venc_date.strftime('%d/%m/%Y')}. Pendente e atrasado deste mês foram recalculados.",
                                    "success",
                                )
                            else:
                                flash("Não foi possível salvar a cobrança.", "danger")

                    elif acao == "alterar_data_vencimento":
                        try:
                            cobranca_id = int(request.form.get("cobranca_id"))
                            venc_date = datetime.strptime((request.form.get("data_vencimento") or "")[:10], "%Y-%m-%d").date()
                        except (TypeError, ValueError):
                            flash("Informe a data de vencimento.", "danger")
                        else:
                            cursor.execute(
                                """
                                UPDATE financeiro_mensalidades
                                SET data_vencimento = %s,
                                    descricao = CASE
                                        WHEN descricao ~ '^Mensalidade [0-9]{2}/[0-9]{4}'
                                        THEN regexp_replace(
                                            descricao,
                                            '^Mensalidade [0-9]{2}/[0-9]{4}',
                                            'Mensalidade ' || to_char(%s, 'MM/YYYY')
                                        )
                                        ELSE descricao
                                    END,
                                    status = CASE
                                        WHEN status = 'Pago' THEN status
                                        WHEN %s < CURRENT_DATE THEN 'Atrasado'
                                        ELSE 'Pendente'
                                    END
                                WHERE id = %s
                                RETURNING id
                                """,
                                (venc_date, venc_date, venc_date, cobranca_id),
                            )
                            if cursor.fetchone():
                                conexao.commit()
                                mes_redir = venc_date.strftime("%Y-%m")
                                flash(
                                    f"Vencimento salvo em {venc_date.strftime('%d/%m/%Y')}. Pendente e atrasado deste mês foram recalculados.",
                                    "success",
                                )
                            else:
                                flash("Não foi possível alterar o vencimento.", "danger")

                    elif acao == "alterar_data_pagamento":
                        data_pag = (request.form.get("data_pagamento") or "").strip()
                        if not data_pag:
                            flash("Informe a data de pagamento.", "danger")
                        else:
                            cursor.execute(
                                """
                                UPDATE financeiro_mensalidades
                                SET data_pagamento = %s
                                WHERE id = %s AND status = 'Pago'
                                """,
                                (data_pag, request.form.get("cobranca_id")),
                            )
                            conexao.commit()
                            if cursor.rowcount:
                                quando = data_pag[:10]
                                try:
                                    quando = datetime.strptime(quando, "%Y-%m-%d").strftime("%d/%m/%Y")
                                except ValueError:
                                    pass
                                if regime_apuracao_escola(cursor) == "caixa":
                                    flash(f"Data da baixa atualizada para {quando}. O valor entra no regime de caixa deste mês.", "success")
                                else:
                                    flash(f"Data da baixa atualizada para {quando}.", "success")
                            else:
                                flash("Só é possível alterar a data de uma mensalidade paga.", "danger")

                    elif acao == "dar_baixa":
                        data_pag = (request.form.get("data_pagamento") or "").strip()[:10]
                        try:
                            data_baixa = datetime.strptime(data_pag, "%Y-%m-%d").date()
                        except ValueError:
                            flash("Informe a data da baixa. No regime de caixa, essa data define o mês do imposto.", "danger")
                        else:
                            juros_percentual, multa_valor = _acrescimos_form()
                            cursor.execute(
                                """
                                UPDATE financeiro_mensalidades
                                SET status = 'Pago',
                                    forma_pagamento = %s,
                                    data_pagamento = %s,
                                    juros_percentual = %s,
                                    juros_valor = ROUND(COALESCE(valor, 0)::numeric * %s / 100.0, 2),
                                    multa_valor = %s
                                WHERE id = %s;
                                """,
                                (
                                    request.form.get("forma_pagamento"),
                                    data_baixa,
                                    juros_percentual,
                                    juros_percentual,
                                    multa_valor,
                                    request.form.get("cobranca_id"),
                                ),
                            )
                            conexao.commit()
                            quando = data_baixa.strftime("%d/%m/%Y")
                            acrescimo = ""
                            if juros_percentual or multa_valor:
                                acrescimo = " Juros e multa foram somados ao valor recebido."
                            if regime_apuracao_escola(cursor) == "caixa":
                                flash(f"Baixa registrada em {quando}. O valor entra no regime de caixa deste mês.{acrescimo}", "success")
                            else:
                                flash(f"Baixa registrada em {quando}.{acrescimo}", "success")

                    elif acao == "dar_baixa_lote":
                        ids = []
                        for bruto in request.form.getlist("cobranca_id"):
                            try:
                                cobranca_id = int(bruto)
                            except (TypeError, ValueError):
                                continue
                            if cobranca_id not in ids:
                                ids.append(cobranca_id)
                        data_pag = (request.form.get("data_pagamento") or "").strip()[:10]
                        try:
                            data_baixa = datetime.strptime(data_pag, "%Y-%m-%d").date()
                        except ValueError:
                            data_baixa = None
                        if not ids:
                            flash("Selecione ao menos uma mensalidade para dar baixa.", "danger")
                        elif not data_baixa:
                            flash("Informe a data da baixa. No regime de caixa, essa data define o mês do imposto.", "danger")
                        else:
                            juros_percentual, multa_valor = _acrescimos_form()
                            cursor.execute(
                                """
                                UPDATE financeiro_mensalidades
                                SET status = 'Pago',
                                    forma_pagamento = %s,
                                    data_pagamento = %s,
                                    juros_percentual = %s,
                                    juros_valor = ROUND(COALESCE(valor, 0)::numeric * %s / 100.0, 2),
                                    multa_valor = %s
                                WHERE id = ANY(%s) AND COALESCE(status, '') <> 'Pago'
                                """,
                                (
                                    request.form.get("forma_pagamento") or "Dinheiro",
                                    data_baixa,
                                    juros_percentual,
                                    juros_percentual,
                                    multa_valor,
                                    ids,
                                ),
                            )
                            conexao.commit()
                            qtd_baixa = cursor.rowcount
                            quando = data_baixa.strftime("%d/%m/%Y")
                            if regime_apuracao_escola(cursor) == "caixa":
                                flash(f"Baixa registrada em {qtd_baixa} mensalidade(s), em {quando}. O valor entra no regime de caixa deste mês.", "success")
                            else:
                                flash(f"Baixa registrada em {qtd_baixa} mensalidade(s), em {quando}.", "success")

                    elif acao in ("tirar_baixa", "tirar_baixa_lote"):
                        ids = []
                        for bruto in request.form.getlist("cobranca_id"):
                            try:
                                cobranca_id = int(bruto)
                            except (TypeError, ValueError):
                                continue
                            if cobranca_id not in ids:
                                ids.append(cobranca_id)
                        if not ids:
                            flash("Selecione ao menos uma mensalidade para tirar a baixa.", "danger")
                        else:
                            cursor.execute(
                                """
                                UPDATE financeiro_mensalidades
                                SET status = CASE
                                        WHEN data_vencimento < CURRENT_DATE THEN 'Atrasado'
                                        ELSE 'Pendente'
                                    END,
                                    forma_pagamento = NULL,
                                    data_pagamento = NULL,
                                    juros_percentual = 0,
                                    juros_valor = 0,
                                    multa_valor = 0
                                WHERE id = ANY(%s) AND status = 'Pago'
                                """,
                                (ids,),
                            )
                            conexao.commit()
                            flash(f"Baixa removida de {cursor.rowcount} mensalidade(s).", "success")

                    elif acao == "salvar_funcionario":
                        salario = _float_form("salario")
                        valor_hora = _float_form("valor_hora")
                        horas_mes = _float_form("horas_mes")
                        cpf_func = limpar_campo("cpf") or f"TMP{datetime.now().strftime('%H%M%S')}"
                        repetido = buscar_cpf_repetido(cursor, cpf_func)
                        if repetido:
                            flash(mensagem_cpf_repetido(*repetido), "danger")
                        else:
                            cursor.execute(
                                """
                                INSERT INTO funcionarios (
                                    nome_completo, cpf, data_nascimento, cargo, telefone, email, salario, ativo,
                                    tipo_contrato, valor_hora, horas_mes, reter_federal, reter_iss, aliquota_iss
                                ) VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s, %s, %s, %s, %s)
                                """,
                                (
                                    limpar_campo("nome_completo"),
                                    cpf_func,
                                    limpar_campo("data_nascimento") or "2000-01-01",
                                    _cargo_do_form() or "Auxiliar",
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
                        salario = _float_form("salario")
                        valor_hora = _float_form("valor_hora")
                        horas_mes = _float_form("horas_mes")
                        horas_extras = float((request.form.get("horas_extras") or "0").replace(",", ".") or 0)
                        horas_extras_100 = float((request.form.get("horas_extras_100") or "0").replace(",", ".") or 0)
                        valor_hora_extra = float((request.form.get("valor_hora_extra") or "0").replace(",", ".") or 0)
                        cursor.execute(
                            """
                            UPDATE funcionarios SET
                                tipo_contrato = %s, salario = %s, valor_hora = %s, horas_mes = %s,
                                reter_federal = %s, reter_iss = %s, aliquota_iss = %s,
                                horas_extras = %s, horas_extras_100 = %s, valor_hora_extra = %s, dia_pagamento = %s,
                                data_inicio_contrato = COALESCE(%s::date, data_inicio_contrato),
                                data_fim_contrato = %s
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
                                horas_extras,
                                horas_extras_100,
                                valor_hora_extra,
                                dia_pagamento_valido(request.form.get("dia_pagamento")),
                                request.form.get("data_inicio_contrato") or None,
                                request.form.get("data_fim_contrato") or None,
                                fid,
                            ),
                        )
                        conexao.commit()
                        flash("✅ Contrato atualizado.", "success")

                    elif acao == "criar_custo":
                        tipo = request.form.get("tipo_custo") or "avista"
                        try:
                            n = _gravar_custo(cursor, {
                                "tipo": tipo,
                                "descricao": limpar_campo("descricao_custo") or "Custo",
                                "categoria": limpar_campo("categoria_custo") or "operacional",
                                "data": request.form.get("data_custo") or datetime.now().strftime("%Y-%m-%d"),
                                "data_inicio": request.form.get("data_inicio_custo") or request.form.get("data_custo"),
                                "data_fim": limpar_campo("data_fim_custo"),
                                "forma": request.form.get("forma_custo") or "dinheiro",
                                "prestador": limpar_campo("prestador_custo"),
                                "parcelas": request.form.get("parcelas_custo") or 1,
                                "valor": _float_form("valor_custo") or _float_form("valor_unitario_custo"),
                                "valor_bruto": _float_form("valor_bruto_custo"),
                                "reter_federal": request.form.get("custo_reter_federal") == "1",
                                "reter_iss": request.form.get("custo_reter_iss") == "1",
                                "aliquota_iss": _float_form("custo_aliquota_iss", 5.0),
                                "aliq_irrf": _float_form("custo_aliq_irrf", 1.5),
                                "aliq_pis": _float_form("custo_aliq_pis", 0.65),
                                "aliq_cofins": _float_form("custo_aliq_cofins", 3.0),
                                "aliq_csll": _float_form("custo_aliq_csll", 1.0),
                                "federal_na_nota": request.form.get("federal_na_nota") != "0",
                                "iss_na_nota": request.form.get("iss_na_nota") != "0",
                            })
                            conexao.commit()
                            if tipo == "parcelado":
                                flash(f"Custo parcelado em {n} parcela(s).", "success")
                            elif tipo == "recorrente":
                                flash("Custo recorrente cadastrado. Ele entra em todos os meses do período.", "success")
                            else:
                                flash("Custo registrado.", "success")
                        except ValueError as e:
                            flash(str(e), "danger")

                    elif acao == "importar_custos":
                        arquivo = request.files.get("planilha_custos")
                        if not arquivo or not arquivo.filename:
                            flash("Selecione uma planilha CSV ou Excel com os custos.", "danger")
                        else:
                            try:
                                itens = importar_planilha_custos(arquivo)
                            except ValueError as e:
                                flash(str(e), "danger")
                                itens = None
                            if itens is not None:
                                if not itens:
                                    flash("A planilha não trouxe nenhum custo válido.", "danger")
                                else:
                                    ok, erros = 0, []
                                    for i, item in enumerate(itens, start=2):
                                        try:
                                            cursor.execute("SAVEPOINT custo_lote")
                                            _gravar_custo(cursor, item)
                                            cursor.execute("RELEASE SAVEPOINT custo_lote")
                                            ok += 1
                                        except Exception as e:
                                            cursor.execute("ROLLBACK TO SAVEPOINT custo_lote")
                                            erros.append(f"Linha {i} ({item.get('descricao')}): {e}")
                                    conexao.commit()
                                    msg = f"{ok} custo(s) importado(s)."
                                    if erros:
                                        extra = " | ".join(erros[:6])
                                        flash(f"{msg} Falhas: {extra}", "danger" if not ok else "success")
                                    else:
                                        flash(msg, "success")

                    elif acao == "simples_salvar_quadro":
                        competencias = request.form.getlist("competencia")
                        for comp in competencias:
                            rec = _parse_moeda(request.form.get(f"receita_{comp}"), 0.0)
                            folha = _parse_moeda(request.form.get(f"folha_{comp}"), 0.0)
                            upsert_competencia(cursor, comp, rec, folha, "manual", "Lançamento manual")
                        conexao.commit()
                        flash("Competências do Simples Nacional salvas.", "success")

                    elif acao == "simples_salvar_mes":
                        comp = request.form.get("competencia") or mes_redir
                        rec = _parse_moeda(request.form.get("receita_bruta"), 0.0)
                        folha = _parse_moeda(request.form.get("folha_encargos"), 0.0)
                        upsert_competencia(cursor, comp, rec, folha, "manual", "Lançamento manual")
                        conexao.commit()
                        flash(f"Competência {comp} salva no Simples Nacional.", "success")

                    elif acao == "simples_importar":
                        arquivo = request.files.get("arquivo_simples")
                        origem = request.form.get("origem_import") or "planilha"
                        if origem not in ("planilha", "pgdas"):
                            origem = "planilha"
                        if not arquivo or not arquivo.filename:
                            flash("Selecione um arquivo CSV, Excel ou extrato PGDAS.", "danger")
                        else:
                            try:
                                itens = importar_competencias(arquivo, origem)
                                gravar_importacao(cursor, itens)
                                conexao.commit()
                                flash(f"Importadas {len(itens)} competência(s) ({origem}).", "success")
                            except ValueError as e:
                                flash(str(e), "danger")

                    elif acao == "simples_carregar_sistema":
                        qtd = carregar_sistema(cursor, mes_redir, regime_apuracao_escola(cursor))
                        conexao.commit()
                        flash(f"Carregadas {qtd} competência(s) a partir das mensalidades e da folha.", "success")

                    elif acao == "simples_carregar_folha":
                        regime_carga = "simples_nacional"
                        cursor.execute("SELECT regime_tributario FROM configuracoes WHERE id = 1")
                        cfg_carga = cursor.fetchone() or {}
                        if cfg_carga.get("regime_tributario"):
                            regime_carga = cfg_carga["regime_tributario"]
                        qtd = 0
                        for comp in janela_competencias(mes_redir) + [mes_redir]:
                            folha = folha_sistema_mes(cursor, comp)
                            if not folha:
                                _det, totais_c = montar_folha_contratos(cursor, regime_carga, comp)
                                folha = float(totais_c.get("custo_escola") or 0)
                            if folha:
                                upsert_competencia(cursor, comp, None, folha, "folha", "Folha e encargos do sistema")
                                qtd += 1
                        conexao.commit()
                        flash(f"Folha e encargos carregados em {qtd} competência(s).", "success")
            except Exception as e:
                conexao.rollback()
                flash(f"❌ Erro ao processar financeiro: {e}", "danger")
            finally:
                conexao.close()
        voltar_aluno = request.form.get("voltar_aluno")
        if voltar_aluno and str(voltar_aluno).isdigit() and acao in ("tirar_baixa", "dar_baixa", "alterar_data_pagamento", "alterar_data_vencimento", "editar_cobranca"):
            return redirect(url_for("detalhes_aluno", aluno_id=int(voltar_aluno)))
        params_redir = {"mes": mes_redir, "aba": aba_redir}
        if request.form.get("status"):
            params_redir["status"] = request.form.get("status")
        if request.form.get("busca"):
            params_redir["busca"] = request.form.get("busca")
        if request.form.get("funcionario_id"):
            params_redir["colab"] = request.form.get("funcionario_id")
        if request.form.get("colab_q") or request.args.get("colab_q"):
            params_redir["colab_q"] = request.form.get("colab_q") or request.args.get("colab_q")
        return redirect(url_for("pagina_financeiro", **params_redir))

    lancamentos, alunos, professores_detalhes = [], [], []
    turmas_simples = []
    emails_escola = []
    custos_mes = []
    totais = {
        "recebido": 0.0,
        "pendente": 0.0,
        "atrasado": 0.0,
        "qtd_pago": 0,
        "qtd_pendente": 0,
        "qtd_atrasado": 0,
        "folha_pagamento": 0.0,
        "tributos": 0.0,
        "liquido": 0.0,
        "custos": 0.0,
        "custos_compras": 0.0,
        "custos_servicos": 0.0,
        "emitido": 0.0,
        "recebido_caixa": 0.0,
        "inadimplente": 0.0,
    }
    regime_apuracao = "competencia"
    recebimentos_caixa = []
    totais_folha = {"bruto": 0.0, "liquido": 0.0, "encargos": 0.0, "custo_escola": 0.0, "inss_patronal": 0.0, "fgts": 0.0}
    apuracao_simples = None
    apuracao_pis_cofins = None
    apuracao_presumido = None
    quadro_simples = None
    nome_escola = "Gestão Escolar"

    nfse_aluno = request.args.get("nfse_aluno", type=int)
    mensalidades_nfse = []
    busca = request.args.get("busca", "").strip()
    status_filtro = request.args.get("status", "").strip()
    aba = request.args.get("aba") or "resumo"
    if status_filtro and aba == "resumo":
        aba = "receitas"
    
    mes_filtro = request.args.get("mes", "").strip()
    if not mes_filtro:
        mes_filtro = datetime.now().strftime('%Y-%m')

    conexao = obter_conexao()
    regime_tributario = "lucro_presumido" # Padrão caso não encontre

    if conexao:
        try:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                # BUSCA O REGIME TRIBUTÁRIO CONFIGURADO NO BANCO[cite: 5]
                cursor.execute("SELECT nome_escola, regime_tributario, regime_apuracao, email_contato FROM configuracoes WHERE id = 1;")
                config_regime = cursor.fetchone()
                nome_escola = "Gestão Escolar"
                if config_regime:
                    if config_regime.get("regime_tributario"):
                        regime_tributario = config_regime["regime_tributario"]
                    regime_apuracao = normalizar_regime_apuracao(config_regime.get("regime_apuracao"))
                    if config_regime.get("nome_escola"):
                        nome_escola = config_regime["nome_escola"]

                # 1. Atualiza faturas vencidas para 'Atrasado' globalmente[cite: 5]
                cursor.execute(
                    """
                    UPDATE financeiro_mensalidades
                    SET status = CASE
                        WHEN data_vencimento < CURRENT_DATE THEN 'Atrasado'
                        ELSE 'Pendente'
                    END
                    WHERE COALESCE(status, '') <> 'Pago'
                      AND data_vencimento IS NOT NULL
                      AND status IS DISTINCT FROM (
                          CASE
                              WHEN data_vencimento < CURRENT_DATE THEN 'Atrasado'
                              ELSE 'Pendente'
                          END
                      );
                    """
                )
                conexao.commit()

                # 2. Totais filtrados pelo mês de vencimento[cite: 5]
                cursor.execute(
                    """
                    SELECT 
                        COALESCE(SUM(CASE WHEN status = 'Pago' THEN valor::numeric ELSE 0 END), 0) AS recebido,
                        COALESCE(SUM(CASE WHEN status = 'Pendente' THEN valor::numeric ELSE 0 END), 0) AS pendente,
                        COALESCE(SUM(CASE WHEN status = 'Atrasado' THEN valor::numeric ELSE 0 END), 0) AS atrasado,
                        COALESCE(SUM(CASE WHEN status = 'Pago' THEN 1 ELSE 0 END), 0) AS qtd_pago,
                        COALESCE(SUM(CASE WHEN status = 'Pendente' THEN 1 ELSE 0 END), 0) AS qtd_pendente,
                        COALESCE(SUM(CASE WHEN status = 'Atrasado' THEN 1 ELSE 0 END), 0) AS qtd_atrasado
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
                    totais["qtd_pago"] = int(resumo_mensalidades["qtd_pago"] or 0)
                    totais["qtd_pendente"] = int(resumo_mensalidades["qtd_pendente"] or 0)
                    totais["qtd_atrasado"] = int(resumo_mensalidades["qtd_atrasado"] or 0)
                visao_fiscal = resumo_emitido_e_caixa(cursor, mes_filtro)
                totais["emitido"] = visao_fiscal["emitido"]
                totais["recebido_caixa"] = visao_fiscal["recebido_caixa"]
                totais["inadimplente"] = visao_fiscal["inadimplente"]
                if regime_apuracao == "caixa":
                    recebimentos_caixa = listar_recebimentos_mes(cursor, mes_filtro)

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
                receita_mes_bruta = receita_do_mes(cursor, mes_filtro, regime_apuracao)

                if regime_tributario == "simples_nacional":
                    apuracao_simples, _colabs_fator_r = calcular_apuracao_simples(cursor, mes_filtro)
                    quadro_simples = apuracao_simples.get("quadro")
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
                    receita_tri = sum(
                        receita_sistema_mes(cursor, comp, regime_apuracao)
                        for comp in meses_do_trimestre(mes_filtro)
                    )
                    apuracao_presumido = apurar_lucro_presumido(
                        receita_mes_bruta, colaboradores_folha, receita_tri
                    )
                    totais["tributos"] = apuracao_presumido["tributos"]
                    totais["receita_bruta_mes"] = receita_mes_bruta
                    totais["liquido"] = totais["recebido"] - totais["folha_pagamento"] - totais["tributos"] - totais["custos"]

                # Restante das consultas de lançamentos...[cite: 5]
                query_lancamentos = """
                    SELECT f.id, f.aluno_id, a.nome_completo, f.descricao, f.valor, f.data_vencimento,
                           f.data_pagamento, f.status, f.forma_pagamento,
                           (
                               SELECT t.nome FROM turma_alunos ta
                               JOIN turmas t ON t.id = ta.turma_id
                               WHERE ta.aluno_id = a.id
                               ORDER BY ta.turma_id DESC
                               LIMIT 1
                           ) AS turma_nome
                    FROM financeiro_mensalidades f
                    LEFT JOIN alunos a ON f.aluno_id = a.id
                    WHERE TO_CHAR(f.data_vencimento, 'YYYY-MM') = %s
                """
                params = [mes_filtro]

                if busca:
                    termo = f"%{busca.strip()}%"
                    digitos = "".join(caractere for caractere in busca if caractere.isdigit())
                    query_lancamentos += """
                        AND (
                            a.nome_completo ILIKE %s
                            OR COALESCE(a.matricula, '') ILIKE %s
                            OR COALESCE(a.cpf, '') ILIKE %s
                    """
                    params.extend([termo, termo, termo])
                    if digitos:
                        query_lancamentos += " OR regexp_replace(COALESCE(a.cpf, ''), '\\D', '', 'g') LIKE %s"
                        params.append(f"%{digitos}%")
                    query_lancamentos += ")"

                if status_filtro:
                    status_norm = status_filtro.strip().lower()
                    if status_norm == "atrasado":
                        query_lancamentos += """
                            AND (
                                LOWER(COALESCE(f.status, '')) = 'atrasado'
                                OR (f.data_vencimento < CURRENT_DATE AND LOWER(COALESCE(f.status, '')) <> 'pago')
                            )
                        """
                    else:
                        query_lancamentos += " AND LOWER(COALESCE(f.status, '')) = %s"
                        params.append(status_norm)

                query_lancamentos += " ORDER BY a.nome_completo, f.data_vencimento;"

                cursor.execute(query_lancamentos, params)
                lancamentos = cursor.fetchall()

                cursor.execute(
                    """
                    SELECT a.id, a.nome_completo, a.matricula, a.cpf, a.valor_mensalidade,
                           TO_CHAR(a.contrato_inicio, 'YYYY-MM-DD') AS contrato_inicio,
                           (
                               SELECT t.nome FROM turma_alunos ta
                               JOIN turmas t ON t.id = ta.turma_id
                               WHERE ta.aluno_id = a.id
                               ORDER BY ta.turma_id DESC
                               LIMIT 1
                           ) AS turma_nome
                    FROM alunos a
                    ORDER BY a.nome_completo ASC
                    """
                )
                alunos = cursor.fetchall()
                if cadastro_simples:
                    cursor.execute("SELECT id, nome FROM turmas ORDER BY nome")
                    turmas_simples = cursor.fetchall()
                vistos_email = set()

                def _guardar_email(valor):
                    texto = (valor or "").strip()
                    chave = texto.lower()
                    if email_valido(texto) and chave not in vistos_email:
                        vistos_email.add(chave)
                        emails_escola.append(texto)

                _guardar_email((config_regime or {}).get("email_contato"))
                _guardar_email(session.get("usuario_email"))
                try:
                    cursor.execute(
                        "SELECT email FROM usuarios WHERE COALESCE(TRIM(email), '') <> '' ORDER BY email"
                    )
                    for row_email in cursor.fetchall() or []:
                        _guardar_email(row_email.get("email"))
                except Exception:
                    pass
                if aba == "simples" and quadro_simples is None:
                    quadro_simples = montar_quadro_simples(cursor, mes_filtro, regime_apuracao)
                    if apuracao_simples is None:
                        apuracao_simples, _colabs_fator_r = calcular_apuracao_simples(cursor, mes_filtro)
                try:
                    anexar_ultima_nota(cursor, lancamentos)
                    if nfse_aluno:
                        mensalidades_nfse = listar_mensalidades_emissao(cursor, nfse_aluno)
                except Exception:
                    conexao.rollback()
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
        cadastro_simples=cadastro_simples,
        turmas_simples=turmas_simples,
        professores_detalhes=professores_detalhes,
        totais_folha=totais_folha,
        custos_mes=custos_mes,
        aba=aba,
        totais=totais,
        busca=busca,
        status=status_filtro,
        regime_atual=regime_tributario,
        regime_apuracao=regime_apuracao,
        recebimentos_caixa=recebimentos_caixa,
        mes_atual=mes_filtro,
        data_hoje=datetime.now().strftime('%Y-%m-%d'),
        apuracao_simples=apuracao_simples,
        quadro_simples=quadro_simples,
        apuracao_pis_cofins=apuracao_pis_cofins,
        apuracao_presumido=apuracao_presumido,
        nome_escola=nome_escola,
        emails_escola=emails_escola,
        mes_label=nome_mes_extenso(mes_filtro),
        colab_q=colab_q,
        colab_id=colab_id,
        colaboradores_busca=colaboradores_busca,
        colaborador_sel=colaborador_sel,
        nfse_aluno=nfse_aluno,
        mensalidades_nfse=mensalidades_nfse,
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


def _pdf_memoria_simples(mes_filtro):
    garantir_tabelas_folha()
    conexao = obter_conexao()
    if not conexao:
        return None, None, "Sem conexão com o banco para gerar a memória de cálculo."
    try:
        with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT nome_escola, regime_tributario FROM configuracoes WHERE id = 1;")
            config = cursor.fetchone() or {}
            escola = config.get("nome_escola") or "Gestão Escolar"
            apuracao, _colabs = calcular_apuracao_simples(cursor, mes_filtro)
            buffer = pdf_simples_nacional(
                escola,
                nome_mes_extenso(mes_filtro),
                "simples_nacional",
                apuracao,
                [],
                [],
            )
        return buffer, f"memoria_simples_{mes_filtro}.pdf", None
    finally:
        conexao.close()


@app.route("/financeiro/simples/pgdas")
def extrato_pgdas_pdf():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    mes_filtro = (request.args.get("mes") or "").strip() or datetime.now().strftime("%Y-%m")
    garantir_tabelas_folha()
    conexao = obter_conexao()
    if not conexao:
        flash("Sem conexão com o banco para gerar o extrato PGDAS.", "danger")
        return redirect(url_for("pagina_financeiro", mes=mes_filtro, aba="simples"))
    try:
        with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT nome_escola, regime_apuracao FROM configuracoes WHERE id = 1;")
            config = cursor.fetchone() or {}
            escola = config.get("nome_escola") or "Gestão Escolar"
            regime_apuracao = normalizar_regime_apuracao(config.get("regime_apuracao"))
            apuracao, _colabs = calcular_apuracao_simples(cursor, mes_filtro)
            campo = (request.args.get("campo") or "").strip()
            mes_label = nome_mes_extenso(mes_filtro)
            if campo == "rbt12":
                buffer = pdf_calculo_rbt12(escola, mes_label, apuracao, regime_apuracao)
                nome_arquivo = f"calculo_rbt12_{mes_filtro}.pdf"
            elif campo == "fs12":
                quadro = apuracao.get("quadro") or {}
                comps = [linha.get("competencia") for linha in (quadro.get("linhas") or [])]
                apuracao_mes = quadro.get("linha_apuracao") or {}
                if apuracao_mes.get("competencia"):
                    comps.append(apuracao_mes.get("competencia"))
                folhas = listar_folha_janela(cursor, comps)
                itens_mes, totais_mes = montar_folha_contratos(cursor, "simples_nacional", mes_filtro)
                buffer = pdf_calculo_fs12(
                    escola, mes_label, apuracao, regime_apuracao,
                    folhas=folhas, itens_mes=itens_mes, totais_mes=totais_mes,
                )
                nome_arquivo = f"calculo_folha_{mes_filtro}.pdf"
            elif campo == "fator":
                buffer = pdf_calculo_fator_r(escola, mes_label, apuracao, regime_apuracao)
                nome_arquivo = f"calculo_fator_r_{mes_filtro}.pdf"
            else:
                pendentes, atrasados = [], []
                if regime_apuracao == "caixa":
                    _recebidos, pendentes, atrasados = _listas_regime(cursor, mes_filtro)
                buffer = pdf_extrato_pgdas(
                    escola, mes_label, apuracao, regime_apuracao,
                    pendentes=pendentes, atrasados=atrasados, mes_filtro=mes_filtro,
                )
                nome_arquivo = f"extrato_pgdas_{mes_filtro}.pdf"
    except Exception as e:
        flash(f"Não foi possível gerar o extrato PGDAS: {e}", "danger")
        return redirect(url_for("pagina_financeiro", mes=mes_filtro, aba="simples"))
    finally:
        conexao.close()
    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=nome_arquivo,
    )


@app.route("/financeiro/simples/pdf")
def memoria_simples_pdf():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    mes_filtro = (request.args.get("mes") or "").strip() or datetime.now().strftime("%Y-%m")
    try:
        buffer, nome_arq, erro = _pdf_memoria_simples(mes_filtro)
    except Exception as e:
        flash(f"Não foi possível gerar o PDF: {e}", "danger")
        return redirect(url_for("pagina_financeiro", mes=mes_filtro, aba="simples"))
    if erro or buffer is None:
        flash(erro or "Não foi possível gerar o PDF.", "danger")
        return redirect(url_for("pagina_financeiro", mes=mes_filtro, aba="simples"))
    return send_file(buffer, mimetype="application/pdf", as_attachment=True, download_name=nome_arq)


@app.route("/financeiro/simples/enviar", methods=["POST"])
def enviar_memoria_simples():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    mes_filtro = (request.form.get("mes") or "").strip() or datetime.now().strftime("%Y-%m")
    destino = url_for("pagina_financeiro", mes=mes_filtro, aba="simples")
    escolhido = (request.form.get("email_cadastrado") or "").strip()
    manual = (request.form.get("email") or "").strip()
    destinos = []
    for bruto in (escolhido, manual):
        if email_valido(bruto) and bruto.lower() not in {item.lower() for item in destinos}:
            destinos.append(bruto)
    if not destinos:
        flash("Escolha um e-mail cadastrado ou digite um e-mail válido.", "danger")
        return redirect(destino)
    try:
        buffer, nome_arq, erro = _pdf_memoria_simples(mes_filtro)
        if erro or buffer is None:
            flash(erro or "Não foi possível gerar o PDF.", "danger")
            return redirect(destino)
        enviar_email(
            destinos,
            f"Memória de cálculo do Simples Nacional — {nome_mes_extenso(mes_filtro)}",
            "Segue em anexo o PDF com o cálculo da RBT12, da FS12, do Fator R e do DAS.",
            [{"nome": nome_arq, "dados": bytes_pdf(buffer)}],
        )
        flash(f"Memória de cálculo enviada para {', '.join(destinos)}.", "success")
    except Exception as e:
        flash(f"Não foi possível enviar o PDF: {e}", "danger")
    return redirect(destino)


@app.route("/financeiro/relatorio/<tipo>")
def relatorio_cartao_financeiro(tipo):
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    mes_filtro = request.args.get("mes", "").strip() or datetime.now().strftime("%Y-%m")
    tipos = {
        "recebido", "pendente", "atrasado", "folha", "compras", "servicos",
        "caixa", "pago_mes", "regime", "regime_pago", "regime_nao_pago",
    }
    if tipo not in tipos:
        flash("Esse relatório não existe.", "danger")
        return redirect(url_for("pagina_financeiro", mes=mes_filtro))
    garantir_tabelas_folha()
    conexao = obter_conexao()
    if not conexao:
        flash("Sem conexão com o banco para gerar o relatório.", "danger")
        return redirect(url_for("pagina_financeiro", mes=mes_filtro))
    try:
        with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                UPDATE financeiro_mensalidades
                SET status = CASE
                    WHEN data_vencimento < CURRENT_DATE THEN 'Atrasado'
                    ELSE 'Pendente'
                END
                WHERE COALESCE(status, '') <> 'Pago'
                  AND data_vencimento IS NOT NULL
                  AND status IS DISTINCT FROM (
                      CASE
                          WHEN data_vencimento < CURRENT_DATE THEN 'Atrasado'
                          ELSE 'Pendente'
                      END
                  )
                """
            )
            conexao.commit()
            cursor.execute("SELECT nome_escola, regime_tributario, regime_apuracao FROM configuracoes WHERE id = 1;")
            config = cursor.fetchone() or {}
            escola = config.get("nome_escola") or "Gestão Escolar"
            regime = config.get("regime_tributario") or "lucro_presumido"
            regime_apuracao = normalizar_regime_apuracao(config.get("regime_apuracao"))
            mes_label = nome_mes_extenso(mes_filtro)
            nome_arquivo = f"relatorio_{tipo}_{mes_filtro}.pdf"

            if tipo in ("recebido", "pendente", "atrasado"):
                status_mapa = {"recebido": "Pago", "pendente": "Pendente", "atrasado": "Atrasado"}
                status = status_mapa[tipo]
                itens = _mensalidades_do_cartao(cursor, mes_filtro, status)
                total = sum(float(item.get("valor") or 0) for item in itens)
                textos = {
                    "recebido": (
                        "Total recebido",
                        "Entram as mensalidades com vencimento neste mês que já receberam baixa. "
                        "A data da baixa mostra quando o valor entrou. Este cartão segue o vencimento, "
                        "não o mês da baixa. No regime de caixa, o imposto usa o relatório Pago no mês.",
                    ),
                    "pendente": (
                        "Total pendente",
                        "Entram as mensalidades com vencimento neste mês que ainda não venceram e não têm baixa.",
                    ),
                    "atrasado": (
                        "Total atrasado",
                        "Entram as mensalidades com vencimento neste mês que já passaram do dia e continuam sem baixa.",
                    ),
                }
                titulo, explicacao = textos[tipo]
                buffer = pdf_composicao_mensalidades(escola, mes_label, titulo, explicacao, itens, total)
            elif tipo == "pago_mes":
                itens = listar_recebimentos_mes(cursor, mes_filtro)
                total = sum(float(item.get("valor") or 0) for item in itens)
                buffer = pdf_composicao_mensalidades(
                    escola,
                    mes_label,
                    "Pago no mês",
                    "Entram as baixas cuja data cai neste mês, mesmo que o vencimento seja de outro mês. "
                    "No regime de caixa, esta lista é a base do imposto. Título sem baixa fica de fora.",
                    itens,
                    total,
                )
            elif tipo == "folha":
                itens, totais = montar_folha_contratos(cursor, regime, mes_filtro)
                buffer = pdf_folha_pagamento(escola, mes_label, regime, itens, totais)
                nome_arquivo = f"folha_{mes_filtro}.pdf"
            elif tipo in ("compras", "servicos"):
                custos = listar_custos_do_mes(cursor, mes_filtro)
                escolhidos = []
                total = 0.0
                for item in custos:
                    porque, efeito = _porque_custo(item)
                    if tipo == "servicos" and (item.get("tipo") or "").lower() != "servico":
                        continue
                    if tipo == "compras" and (item.get("tipo") or "").lower() == "servico":
                        continue
                    escolhidos.append({"descricao": item.get("descricao") or "Custo", "porque": porque, "valor": efeito})
                    total += efeito
                if tipo == "compras":
                    buffer = pdf_composicao_custos(
                        escola,
                        mes_label,
                        "Compras e custos fixos",
                        "Entram aluguel, energia, material e parcelas que não são contratação de serviço. "
                        "O valor do cartão é o que efetivamente sai no mês.",
                        escolhidos,
                        total,
                    )
                else:
                    buffer = pdf_composicao_custos(
                        escola,
                        mes_label,
                        "Contratação de serviços",
                        "Entram as NFS-e e os serviços de terceiros. Se IRRF, PIS, COFINS, CSLL ou ISS "
                        "não estavam na nota, eles somam ao valor do cartão.",
                        escolhidos,
                        total,
                    )
            elif tipo == "caixa":
                cursor.execute(
                    """
                    SELECT COALESCE(SUM(CASE WHEN status = 'Pago' THEN valor::numeric ELSE 0 END), 0) AS recebido
                    FROM financeiro_mensalidades
                    WHERE TO_CHAR(data_vencimento, 'YYYY-MM') = %s
                    """,
                    (mes_filtro,),
                )
                recebido = float((cursor.fetchone() or {}).get("recebido") or 0)
                _itens_folha, totais_folha = montar_folha_contratos(cursor, regime, mes_filtro)
                folha = float(totais_folha.get("custo_escola") or 0)
                custos = resumir_custos_operacionais(listar_custos_do_mes(cursor, mes_filtro))
                if regime == "simples_nacional":
                    apuracao, _colabs = calcular_apuracao_simples(cursor, mes_filtro)
                    tributos = float(apuracao.get("das") or 0)
                elif regime == "lucro_real":
                    tributos = 0.0
                else:
                    colaboradores, _folha = montar_folha_colaboradores(cursor)
                    receita_mes = receita_do_mes(cursor, mes_filtro, regime_apuracao)
                    receita_tri = sum(
                        receita_sistema_mes(cursor, comp, regime_apuracao)
                        for comp in meses_do_trimestre(mes_filtro)
                    )
                    tributos = float(apurar_lucro_presumido(receita_mes, colaboradores, receita_tri).get("tributos") or 0)
                total = recebido - folha - tributos - custos["compras"] - custos["servicos"]
                buffer = pdf_caixa_restante(
                    escola,
                    mes_label,
                    [
                        ("(+) Recebido nas mensalidades", recebido),
                        ("(−) Folha e encargos", folha),
                        ("(−) Tributos da empresa", tributos),
                        ("(−) Compras e custos fixos", custos["compras"]),
                        ("(−) Contratação de serviços", custos["servicos"]),
                    ],
                    total,
                    regime_apuracao,
                )
            else:
                recebidos, pendentes, atrasados = _listas_regime(cursor, mes_filtro)
                parte = {"regime_pago": "pago", "regime_nao_pago": "nao_pago"}.get(tipo, "")
                buffer = pdf_regime_detalhado(
                    escola, mes_label, regime_apuracao, regime, recebidos, pendentes, atrasados,
                    mes_filtro=mes_filtro, parte=parte,
                )
    finally:
        conexao.close()
    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=nome_arquivo,
    )


@app.route("/financeiro/custos/pdf")
def relatorio_pdf_custos():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    mes_filtro = request.args.get("mes", "").strip() or datetime.now().strftime("%Y-%m")
    garantir_tabelas_folha()
    conexao = obter_conexao()
    if not conexao:
        flash("Sem conexão com o banco para gerar o relatório.", "danger")
        return redirect(url_for("pagina_financeiro", mes=mes_filtro, aba="custos"))
    try:
        with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT nome_escola FROM configuracoes WHERE id = 1;")
            config = cursor.fetchone() or {}
            custos = listar_custos_do_mes(cursor, mes_filtro)
            resumo = resumir_custos_operacionais(custos)
        buffer = pdf_custos(
            config.get("nome_escola") or "Gestão Escolar",
            nome_mes_extenso(mes_filtro),
            custos,
            resumo,
        )
    finally:
        conexao.close()
    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"custos_{mes_filtro}.pdf",
    )


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
            cursor.execute("SELECT nome_escola, regime_tributario, regime_apuracao FROM configuracoes WHERE id = 1;")
            config = cursor.fetchone() or {}
            regime = config.get("regime_tributario") or "lucro_presumido"
            regime_apuracao = normalizar_regime_apuracao(config.get("regime_apuracao"))
            escola = config.get("nome_escola") or "Gestão Escolar"
            mes_label = nome_mes_extenso(mes_filtro)
            titulos_base = _titulos_base_imposto(cursor, mes_filtro, regime_apuracao)

            if regime == "simples_nacional":
                apuracao, colaboradores = calcular_apuracao_simples(cursor, mes_filtro)
                receitas_mes = listar_lancamentos_mes(cursor, mes_filtro)
                _itens_folha, totais_folha = montar_folha_contratos(cursor, regime, mes_filtro)
                custos = resumir_custos_operacionais(listar_custos_do_mes(cursor, mes_filtro))
                buffer = pdf_simples_nacional(
                    escola,
                    mes_label,
                    regime,
                    apuracao,
                    colaboradores,
                    receitas_mes,
                    dre={
                        "receita": apuracao.get("receita_mes"),
                        "das": apuracao.get("das"),
                        "folha": totais_folha.get("custo_escola"),
                        "compras": custos.get("compras"),
                        "servicos": custos.get("servicos"),
                    },
                    titulos=titulos_base,
                    regime_apuracao=regime_apuracao,
                )
                nome_arquivo = f"relatorio_simples_dasn_{mes_filtro}.pdf"
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
                receita_mes = receita_do_mes(cursor, mes_filtro, regime_apuracao)
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
                    receita_tri = sum(
                        receita_sistema_mes(cursor, comp, regime_apuracao)
                        for comp in meses_do_trimestre(mes_filtro)
                    )
                    apuracao_p = apurar_lucro_presumido(receita_mes, colaboradores, receita_tri)
                    _itens_folha, totais_folha = montar_folha_contratos(cursor, regime, mes_filtro)
                    totais["tributos"] = apuracao_p["tributos"]
                    totais["folha_pagamento"] = totais_folha.get("custo_escola") or 0
                    buffer = pdf_lucro_presumido(
                        escola, mes_label, regime, apuracao_p, totais, recebidos,
                        titulos=titulos_base, regime_apuracao=regime_apuracao,
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
                        titulos=titulos_base,
                        regime_apuracao=regime_apuracao,
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


@app.route("/financeiro/pdf-folha", methods=["GET", "POST"])
def relatorio_pdf_folha():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    mes_filtro = request.values.get("mes") or datetime.now().strftime("%Y-%m")
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
        nome_arq = f"folha_{mes_filtro}.pdf"
        if request.values.get("enviar") or request.method == "POST":
            destinos = []
            email_sessao = session.get("usuario_email")
            if email_valido(email_sessao):
                destinos.append(email_sessao)
            extra = (request.values.get("email") or "").strip()
            if email_valido(extra) and extra.lower() not in {d.lower() for d in destinos}:
                destinos.append(extra)
            if not destinos:
                flash("Informe um e-mail válido para enviar a folha.", "danger")
                return redirect(url_for("pagina_financeiro", mes=mes_filtro, aba="folha"))
            enviar_email(
                destinos,
                f"Folha de pagamento {nome_mes_extenso(mes_filtro)}",
                "Segue em anexo o PDF da folha do período.",
                [{"nome": nome_arq, "dados": bytes_pdf(buffer)}],
            )
            flash(f"Folha enviada para {', '.join(destinos)}.", "success")
            return redirect(url_for("pagina_financeiro", mes=mes_filtro, aba="folha"))
        return send_file(
            buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=nome_arq,
        )
    finally:
        conexao.close()


@app.route("/contracheque")
def contracheque():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    mes_filtro = request.args.get("mes") or datetime.now().strftime("%Y-%m")
    garantir_tabelas_folha()
    try:
        _processar_contracheques_escola(enviar=False)
    except Exception:
        pass
    if not session.get("funcionario_id"):
        session["funcionario_id"] = _id_funcionario_da_sessao()
    conexao = obter_conexao()
    item = None
    itens = []
    escola = "Gestão Escolar"
    admin_folha = pode_modulo(session.get("usuario_papel"), "financeiro")
    if conexao:
        try:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT nome_escola, regime_tributario FROM configuracoes WHERE id = 1;")
                cfg = cursor.fetchone() or {}
                escola = cfg.get("nome_escola") or escola
                regime = cfg.get("regime_tributario") or "lucro_presumido"
                fid = session.get("funcionario_id")
                if admin_folha:
                    itens, _totais = montar_folha_contratos(cursor, regime, mes_filtro)
                    fid = request.args.get("funcionario_id", type=int) or fid
                if fid:
                    cursor.execute("SELECT * FROM funcionarios WHERE id = %s", (fid,))
                    func = cursor.fetchone()
                    if func:
                        ano, mes = parse_mes(mes_filtro)
                        dados = _func_com_ajuste(cursor, func, mes_filtro)
                        item = calcular_folha_pessoa(dados, regime, ano, mes)
                        item["rotulo_contrato"] = rotulo_contrato(item["tipo_contrato"])
                        try:
                            item["valor_hora_extra_cadastro"] = float(dados.get("valor_hora_extra") or 0)
                        except (TypeError, ValueError):
                            item["valor_hora_extra_cadastro"] = 0.0
        finally:
            conexao.close()
    return render_template(
        "contracheque.html",
        item=item,
        itens=itens,
        admin_folha=admin_folha,
        mes_atual=mes_filtro,
        mes_label=nome_mes_extenso(mes_filtro),
        escola=escola,
    )


@app.route("/contracheque/enviar-mes", methods=["POST"])
def enviar_contracheques_mes():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    if not pode_modulo(session.get("usuario_papel"), "financeiro"):
        flash("Sem permissão para enviar a folha do mês.", "danger")
        return redirect(url_for("contracheque"))
    mes_filtro = request.form.get("mes") or datetime.now().strftime("%Y-%m")
    garantir_tabelas_folha()
    conexao = obter_conexao()
    if not conexao:
        flash("Sem conexão com o banco.", "danger")
        return redirect(url_for("contracheque", mes=mes_filtro))
    enviados = 0
    falhas = []
    todos_dest = []
    try:
        with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT nome_escola, regime_tributario, email_contato FROM configuracoes WHERE id = 1;")
            cfg = cursor.fetchone() or {}
            if cfg.get("email_contato"):
                session["escola_email_contato"] = cfg["email_contato"]
            regime = cfg.get("regime_tributario") or "simples_nacional"
            escola = cfg.get("nome_escola") or "Gestão Escolar"
            itens, _totais = montar_folha_contratos(cursor, regime, mes_filtro)
            for item in itens:
                cursor.execute("SELECT * FROM funcionarios WHERE id = %s", (item.get("id"),))
                func = cursor.fetchone()
                if not func:
                    continue
                try:
                    dados = _func_com_ajuste(cursor, func, mes_filtro)
                    destinos = _emails_colaborador(dados, cursor)
                    dest = _enviar_contracheque_pessoa(dados, regime, mes_filtro, escola, destinos=destinos)
                    todos_dest.extend(dest or destinos)
                    _registrar_folha_item(cursor, item, mes_filtro)
                    cursor.execute(
                        """
                        INSERT INTO folha_envios (funcionario_id, competencia)
                        VALUES (%s, %s)
                        ON CONFLICT (funcionario_id, competencia) DO UPDATE SET enviado_em = CURRENT_TIMESTAMP
                        """,
                        (item.get("id"), mes_filtro),
                    )
                    enviados += 1
                except Exception as e:
                    falhas.append(f"{item.get('nome_completo')}: {e}")
        conexao.commit()
    except Exception as e:
        conexao.rollback()
        flash(f"Não foi possível enviar os contra-cheques: {e}", "danger")
        return redirect(url_for("contracheque", mes=mes_filtro))
    finally:
        conexao.close()
    if enviados:
        flash(f"{enviados} contra-cheque(s) enviado(s) por e-mail.{aviso_caixa_entrada(todos_dest)}", "success")
    if falhas:
        flash("Falhas: " + " | ".join(falhas[:8]), "danger")
    if not enviados and not falhas:
        flash("Nenhum colaborador com contrato vigente e e-mail neste mês.", "danger")
    return redirect(url_for("contracheque", mes=mes_filtro))


@app.route("/contracheque/ajustar", methods=["POST"])
def ajustar_contracheque():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    if not pode_modulo(session.get("usuario_papel"), "financeiro"):
        flash("Sem permissão para ajustar o contra-cheque.", "danger")
        return redirect(url_for("contracheque"))
    mes_filtro = request.form.get("mes") or datetime.now().strftime("%Y-%m")
    fid = request.form.get("funcionario_id", type=int)
    if not fid:
        flash("Selecione o colaborador.", "danger")
        return redirect(url_for("contracheque", mes=mes_filtro))
    horas_extras = _float_form("horas_extras")
    horas_extras_100 = _float_form("horas_extras_100")
    valor_hora_extra = _float_form("valor_hora_extra")
    garantir_tabelas_folha()
    conexao = obter_conexao()
    if not conexao:
        flash("Sem conexão com o banco.", "danger")
        return redirect(url_for("contracheque", mes=mes_filtro, funcionario_id=fid))
    try:
        with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT id FROM funcionarios WHERE id = %s", (fid,))
            if not cursor.fetchone():
                flash("Colaborador não encontrado.", "danger")
                return redirect(url_for("contracheque", mes=mes_filtro))
            cursor.execute(
                """
                INSERT INTO folha_ajustes (
                    funcionario_id, competencia, horas_extras, horas_extras_100, valor_hora_extra, atualizado_em
                ) VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (funcionario_id, competencia) DO UPDATE SET
                    horas_extras = EXCLUDED.horas_extras,
                    horas_extras_100 = EXCLUDED.horas_extras_100,
                    valor_hora_extra = EXCLUDED.valor_hora_extra,
                    atualizado_em = CURRENT_TIMESTAMP
                """,
                (fid, mes_filtro, horas_extras, horas_extras_100, valor_hora_extra),
            )
        conexao.commit()
        flash("Horas extras do mês atualizadas. O líquido já considera INSS e IRRF da CLT.", "success")
    except Exception as e:
        conexao.rollback()
        flash(f"Não foi possível salvar o ajuste: {e}", "danger")
    finally:
        conexao.close()
    return redirect(url_for("contracheque", mes=mes_filtro, funcionario_id=fid))


@app.route("/contracheque/pdf", methods=["GET", "POST"])
def pdf_contracheque_rota():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    mes_filtro = request.values.get("mes") or datetime.now().strftime("%Y-%m")
    garantir_tabelas_folha()
    if not session.get("funcionario_id"):
        session["funcionario_id"] = _id_funcionario_da_sessao()
    conexao = obter_conexao()
    if not conexao:
        return redirect(url_for("contracheque", mes=mes_filtro))
    try:
        with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT nome_escola, regime_tributario FROM configuracoes WHERE id = 1;")
            cfg = cursor.fetchone() or {}
            regime = cfg.get("regime_tributario") or "lucro_presumido"
            fid = request.values.get("funcionario_id", type=int)
            admin_folha = pode_modulo(session.get("usuario_papel"), "financeiro")
            if not fid:
                fid = session.get("funcionario_id")
            if not fid:
                flash("❌ Nenhum colaborador vinculado a este usuário.", "danger")
                return redirect(url_for("contracheque"))
            if not admin_folha and fid != session.get("funcionario_id"):
                flash("Sem permissão para este contra-cheque.", "danger")
                return redirect(url_for("contracheque"))
            cursor.execute("SELECT * FROM funcionarios WHERE id = %s", (fid,))
            func = cursor.fetchone()
            if not func:
                flash("❌ Colaborador não encontrado.", "danger")
                return redirect(url_for("contracheque"))
            dados = _func_com_ajuste(cursor, func, mes_filtro)
            ano, mes = parse_mes(mes_filtro)
            item = calcular_folha_pessoa(dados, regime, ano, mes)
            item["rotulo_contrato"] = rotulo_contrato(item["tipo_contrato"])
            buffer = pdf_contracheque(cfg.get("nome_escola") or "Gestão Escolar", nome_mes_extenso(mes_filtro), item)
        nome_arq = f"contracheque_{fid}_{mes_filtro}.pdf"
        if request.args.get("enviar") or request.method == "POST":
            destinos = _emails_colaborador(dados, cursor)
            if not destinos:
                flash("O colaborador não tem e-mail válido cadastrado.", "danger")
                return redirect(url_for("contracheque", mes=mes_filtro))
            enviar_email(
                destinos,
                f"Contra-cheque {nome_mes_extenso(mes_filtro)}",
                f"Olá, {func.get('nome_completo') or ''}.\n\nSegue em anexo o contra-cheque de {nome_mes_extenso(mes_filtro)}.\n",
                [{"nome": nome_arq, "dados": bytes_pdf(buffer)}],
            )
            flash(f"Contra-cheque enviado para {', '.join(destinos)}.{aviso_caixa_entrada(destinos)}", "success")
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
        
        if acao == "salvar_nfse":
            if not getattr(g, "nfse_liberada", False):
                if conexao:
                    conexao.close()
                flash("A geração de NFS-e está desligada.", "danger")
                return redirect(url_for("pagina_configuracoes"))
            if conexao:
                try:
                    with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                        aceito, aviso = salvar_config_escola(cursor, request.form, request.files.get("nfse_certificado"))
                        conexao.commit()
                        flash("Dados da nota fiscal salvos. " + aviso, "success" if aceito else "danger")
                except Exception as e:
                    conexao.rollback()
                    flash(f"Não foi possível salvar a nota fiscal: {e}", "danger")
                finally:
                    conexao.close()
            return redirect(url_for("pagina_configuracoes"))

        if acao == "salvar_acesso":
            uid = request.form.get("usuario_id", type=int)
            if conexao and uid:
                try:
                    with conexao.cursor() as cursor:
                        cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS permissoes TEXT")
                        cursor.execute("SELECT papel, permissoes FROM usuarios WHERE id = %s", (uid,))
                        row = cursor.fetchone() or {}
                        papel = normalizar_papel(row.get("papel") or "funcionario")
                        perm_salvas = _permissoes_do_form(papel) or permissoes_padrao(papel)
                        if not getattr(g, "nfse_liberada", False):
                            anteriores = permissoes_efetivas(papel, row.get("permissoes"))
                            perm_salvas["nfse"] = anteriores.get("nfse") or {}
                        cursor.execute(
                            "UPDATE usuarios SET permissoes = %s WHERE id = %s",
                            (json.dumps(perm_salvas, ensure_ascii=False), uid),
                        )
                        conexao.commit()
                        if uid == session.get("usuario_id"):
                            session["permissoes"] = perm_salvas
                        flash("Acesso desta pessoa salvo. Vale no próximo login dela.", "success")
                except Exception as e:
                    conexao.rollback()
                    flash(f"Não foi possível salvar o acesso: {e}", "danger")
                finally:
                    conexao.close()
            return redirect(url_for("pagina_configuracoes", uid=uid))

        if acao == "salvar_logo":
            if conexao:
                try:
                    caminho = _salvar_foto("logo_escola")
                    mensagem = (request.form.get("mensagem_prova") or "").strip()[:500]
                    with conexao.cursor() as cursor:
                        cursor.execute(
                            "ALTER TABLE configuracoes ADD COLUMN IF NOT EXISTS logo_escola VARCHAR(255)"
                        )
                        cursor.execute(
                            "ALTER TABLE configuracoes ADD COLUMN IF NOT EXISTS mensagem_prova TEXT"
                        )
                        if caminho:
                            cursor.execute(
                                """
                                UPDATE configuracoes
                                SET logo_escola = %s, mensagem_prova = %s
                                WHERE id = 1
                                """,
                                (caminho, mensagem or None),
                            )
                            if cursor.rowcount == 0:
                                cursor.execute(
                                    """
                                    INSERT INTO configuracoes (id, logo_escola, mensagem_prova)
                                    VALUES (1, %s, %s)
                                    """,
                                    (caminho, mensagem or None),
                                )
                        else:
                            cursor.execute(
                                "UPDATE configuracoes SET mensagem_prova = %s WHERE id = 1",
                                (mensagem or None,),
                            )
                            if cursor.rowcount == 0:
                                cursor.execute(
                                    "INSERT INTO configuracoes (id, mensagem_prova) VALUES (1, %s)",
                                    (mensagem or None,),
                                )
                        conexao.commit()
                        flash("Identidade das provas salva (logo e tarja).", "success")
                except Exception as e:
                    conexao.rollback()
                    flash(f"Não foi possível salvar a identidade das provas: {e}", "danger")
                finally:
                    conexao.close()
            return redirect(url_for("pagina_configuracoes"))

        if acao == "salvar_parametros":
            nome_escola = request.form.get("nome_escola")
            ano_letivo = request.form.get("ano_letivo")
            email_contato = request.form.get("email_contato")
            regime_tributario = request.form.get("regime_tributario")
            regime_apuracao = normalizar_regime_apuracao(request.form.get("regime_apuracao"))
            if conexao:
                try:
                    with conexao.cursor() as cursor:
                        cursor.execute(
                            "ALTER TABLE configuracoes ADD COLUMN IF NOT EXISTS regime_apuracao VARCHAR(20) DEFAULT 'competencia'"
                        )
                        cursor.execute(
                            """
                            INSERT INTO configuracoes (
                                id, nome_escola, ano_letivo, email_contato, regime_tributario, regime_apuracao
                            )
                            VALUES (1, %s, %s, %s, %s, %s)
                            ON CONFLICT (id) DO UPDATE
                            SET nome_escola = EXCLUDED.nome_escola,
                                ano_letivo = EXCLUDED.ano_letivo,
                                email_contato = EXCLUDED.email_contato,
                                regime_tributario = EXCLUDED.regime_tributario,
                                regime_apuracao = EXCLUDED.regime_apuracao;
                            """,
                            (nome_escola, ano_letivo, email_contato, regime_tributario, regime_apuracao),
                        )
                        conexao.commit()
                        session["escola_email_contato"] = (email_contato or "").strip()
                        session["escola_nome"] = nome_escola or session.get("escola_nome")
                        flash("✅ Parâmetros salvos com sucesso!", "success")
                except Exception as e:
                    conexao.rollback()
                    flash(f"❌ Erro ao salvar parâmetros: {e}", "danger")
                finally:
                    conexao.close()

        return redirect(url_for("pagina_configuracoes"))

    config = {}
    equipe_acesso = []
    acesso = None
    uid_acesso = request.args.get("uid", type=int)
    if conexao:
        try:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                try:
                    cursor.execute(
                        "ALTER TABLE configuracoes ADD COLUMN IF NOT EXISTS logo_escola VARCHAR(255)"
                    )
                    cursor.execute(
                        "ALTER TABLE configuracoes ADD COLUMN IF NOT EXISTS mensagem_prova TEXT"
                    )
                    cursor.execute("SELECT * FROM configuracoes WHERE id = 1;")
                    config = preparar_config_tela(cursor.fetchone() or {})
                except Exception:
                    conexao.rollback()
                try:
                    cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS permissoes TEXT")
                    cursor.execute(
                        """
                        SELECT u.id, u.nome, u.email, u.papel, u.permissoes, f.cargo
                        FROM usuarios u
                        LEFT JOIN LATERAL (
                            SELECT cargo FROM funcionarios
                            WHERE usuario_id = u.id OR LOWER(COALESCE(email, '')) = LOWER(u.email)
                            ORDER BY CASE WHEN usuario_id = u.id THEN 0 ELSE 1 END
                            LIMIT 1
                        ) f ON TRUE
                        ORDER BY u.nome
                        """
                    )
                    equipe_acesso = cursor.fetchall() or []
                    conexao.commit()
                except Exception:
                    conexao.rollback()
                    equipe_acesso = []
            if equipe_acesso and not any(pessoa.get("id") == uid_acesso for pessoa in equipe_acesso):
                uid_acesso = equipe_acesso[0]["id"]
            escolhido = next((pessoa for pessoa in equipe_acesso if pessoa.get("id") == uid_acesso), None)
            if escolhido:
                papel_pessoa = normalizar_papel(escolhido.get("papel") or "funcionario")
                acesso = {
                    "id": escolhido.get("id"),
                    "nome": escolhido.get("nome") or escolhido.get("email") or "",
                    "email": escolhido.get("email") or "",
                    "cargo": escolhido.get("cargo") or "",
                    "papel": papel_pessoa,
                    "permissoes": permissoes_efetivas(papel_pessoa, escolhido.get("permissoes")),
                }
        finally:
            conexao.close()

    return render_template(
        "configuracoes.html",
        config=config,
        equipe_acesso=equipe_acesso,
        acesso=acesso,
        areas_acesso=[
            area for area in AREAS_ACESSO
            if modulo_no_plano(area[0], session.get("escola_telas"))
            and (area[0] != "nfse" or getattr(g, "nfse_liberada", False))
        ],
        padroes_acesso=padroes_por_papel(),
        nome_do_papel=rotulo_papel,
    )

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


@app.route("/financeiro/cobranca/<int:cobranca_id>/pdf", methods=["GET", "POST"])
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
                SELECT f.*, a.nome_completo, a.matricula, a.email AS aluno_email, a.id AS aluno_id
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
        nome_arq = f"cobranca_{cobranca_id}.pdf"
        if request.values.get("enviar") or request.method == "POST":
            destinos = []
            aluno_id = cobranca.get("aluno_id")
            if aluno_id:
                with conexao.cursor() as cursor:
                    destinos = emails_contato_aluno(cursor, aluno_id)
            extra = cobranca.get("aluno_email")
            if email_valido(extra) and extra.lower() not in {d.lower() for d in destinos}:
                destinos.append(extra)
            if not destinos:
                flash("O aluno não tem e-mail cadastrado para enviar a cobrança.", "danger")
                return redirect(url_for("pagina_financeiro"))
            enviar_email(
                destinos,
                f"Cobrança de mensalidade — {cobranca.get('nome_completo') or 'aluno'}",
                "Segue em anexo o PDF da cobrança.",
                [{"nome": nome_arq, "dados": bytes_pdf(buffer)}],
            )
            flash(f"Cobrança enviada para {', '.join(destinos)}.", "success")
            return redirect(url_for("pagina_financeiro"))
        return send_file(
            buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=nome_arq,
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


def _redirecionar_nfse():
    destino = (request.form.get("voltar") or "").strip()
    aluno_id = request.form.get("aluno_id", type=int)
    if destino == "aluno" and aluno_id:
        return redirect(url_for("detalhes_aluno", aluno_id=aluno_id))
    if destino == "financeiro":
        extra = {"aba": "receitas"}
        if request.form.get("mes"):
            extra["mes"] = request.form.get("mes")
        if aluno_id:
            extra["nfse_aluno"] = aluno_id
        return redirect(url_for("pagina_financeiro", **extra))
    params = {}
    status_nota = (request.form.get("status_nota") or "").strip()
    if status_nota:
        params["status"] = status_nota
    if request.form.get("mes"):
        params["mes"] = request.form.get("mes")
    if aluno_id:
        params["aluno"] = aluno_id
    return redirect(url_for("pagina_notas_fiscais", **params))


def _executar_nfse(funcao):
    garantir_tabelas_folha()
    conexao = obter_conexao()
    if not conexao:
        flash("Sem conexão com o banco.", "danger")
        return _redirecionar_nfse()
    try:
        with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
            mensagem = funcao(cursor)
        flash(mensagem, "success")
    except Exception as e:
        try:
            conexao.rollback()
        except Exception:
            pass
        flash(str(e), "danger")
    finally:
        conexao.close()
    return _redirecionar_nfse()


@app.route("/notas-fiscais")
def pagina_notas_fiscais():
    garantir_tabelas_folha()
    status = (request.args.get("status") or "").strip()
    aluno = request.args.get("aluno", type=int)
    mes = (request.args.get("mes") or datetime.now().strftime("%Y-%m"))[:7]
    grupos = []
    faturado = 0
    alunos_nfse = []
    mensalidades_nfse = []
    conexao = obter_conexao()
    if conexao:
        try:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                alunos_nfse = listar_alunos_nfse(cursor)
                mensalidades_nfse = listar_mensalidades_emissao(cursor, aluno)
                grupos = listar_notas_escola(cursor, status or None, aluno)
                faturado = faturamento_das_notas(cursor, mes)
        except Exception as e:
            flash(f"Não foi possível listar as notas: {e}", "danger")
        finally:
            conexao.close()
    return render_template(
        "notas_fiscais.html",
        grupos=grupos,
        status=status,
        aluno_id=aluno,
        mes=mes,
        faturado=faturado,
        alunos_nfse=alunos_nfse,
        mensalidades_nfse=mensalidades_nfse,
    )


@app.route("/notas-fiscais/emitir", methods=["POST"])
def nfse_emitir():
    return _executar_nfse(lambda cursor: emitir_mensalidade(cursor, request.form.get("mensalidade_id", type=int)))


@app.route("/notas-fiscais/cancelar", methods=["POST"])
def nfse_cancelar():
    return _executar_nfse(
        lambda cursor: cancelar_nota(
            cursor,
            request.form.get("nota_id", type=int),
            "notas_fiscais",
            request.form.get("justificativa"),
        )
    )


@app.route("/notas-fiscais/substituir", methods=["POST"])
def nfse_substituir():
    return _executar_nfse(
        lambda cursor: substituir_nota(cursor, request.form.get("nota_id", type=int), "notas_fiscais")
    )


@app.route("/notas-fiscais/consultar", methods=["POST"])
def nfse_consultar():
    return _executar_nfse(
        lambda cursor: consultar_nota(cursor, request.form.get("nota_id", type=int), "notas_fiscais")
    )


@app.route("/notas-fiscais/lote", methods=["POST"])
def nfse_lote():
    garantir_tabelas_folha()
    conexao = obter_conexao()
    if not conexao:
        flash("Sem conexão com o banco.", "danger")
        return _redirecionar_nfse()
    ids = [int(item) for item in request.form.getlist("cobranca_id") if str(item).isdigit()]
    if not ids:
        flash("Selecione ao menos uma mensalidade.", "danger")
        conexao.close()
        return _redirecionar_nfse()
    feitos = 0
    erros = []
    try:
        with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
            for item in ids:
                try:
                    emitir_mensalidade(cursor, item)
                    feitos += 1
                except Exception as erro:
                    conexao.rollback()
                    erros.append(str(erro))
    finally:
        conexao.close()
    if feitos:
        flash(f"{feitos} NFS-e processada(s).", "success")
    if erros:
        flash(" ; ".join(erros[:5]), "danger")
    return _redirecionar_nfse()


def _arquivo_nfse(nota_id, tipo):
    garantir_tabelas_folha()
    conexao = obter_conexao()
    if not conexao:
        flash("Sem conexão com o banco.", "danger")
        return redirect(request.referrer or url_for("pagina_notas_fiscais"))
    try:
        with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
            conteudo, mime, nome = documento_da_nota(cursor, nota_id, tipo)
        disposicao = "attachment" if tipo == "xml" else "inline"
        return Response(
            conteudo,
            mimetype=mime,
            headers={"Content-Disposition": f'{disposicao}; filename="{nome}"'},
        )
    except Exception as e:
        try:
            conexao.rollback()
        except Exception:
            pass
        flash(str(e), "danger")
        return redirect(request.referrer or url_for("pagina_notas_fiscais"))
    finally:
        conexao.close()


@app.route("/notas-fiscais/<int:nota_id>/xml")
def nfse_xml(nota_id):
    return _arquivo_nfse(nota_id, "xml")


@app.route("/notas-fiscais/<int:nota_id>/danfse")
def nfse_danfse(nota_id):
    return _arquivo_nfse(nota_id, "danfse")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=not ambiente_producao())
