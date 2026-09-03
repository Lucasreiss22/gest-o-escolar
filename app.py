import os
from flask import Flask, flash, redirect, render_template, request, url_for, session
from werkzeug.utils import secure_filename
from psycopg2.extras import RealDictCursor
from alunos import cadastrar_aluno, listar_alunos, atualizar_responsavel, deletar_responsavel
from database import obter_conexao
import calendar as calendario_lib  # Import renomeado para evitar conflito de variáveis
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "chave_secreta_gestao_escolar")

# Pasta onde os PDFs das provas serão salvos
PASTA_UPLOADS_PROVAS = "static/uploads/provas"
os.makedirs(PASTA_UPLOADS_PROVAS, exist_ok=True)


# Função auxiliar para limpar e sanitizar dados do formulário (aceita argumentos extras para evitar erros de TypeError)
def limpar_campo(campo_nome, *args, **kwargs):
    valor = request.form.get(campo_nome)
    if valor is not None:
        valor = valor.strip()
        return valor if valor != "" else None
    return None


# --- ROTA DE AUTENTICAÇÃO: LOGIN ---
@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        senha = request.form.get("senha")
        
        conexao = obter_conexao()
        if conexao:
            try:
                with conexao.cursor() as cursor:
                    # Ajustado para buscar também a coluna 'papel'
                    cursor.execute("SELECT id, nome, senha, papel FROM usuarios WHERE email = %s;", (email,))
                    usuario = cursor.fetchone()
                    
                    if usuario and usuario[2] == senha: 
                        session["usuario_id"] = usuario[0]
                        session["usuario_nome"] = usuario[1]
                        session["usuario_papel"] = usuario[3] or 'admin'
                        return redirect(url_for("dashboard"))
                    else:
                        flash("E-mail ou senha incorretos.", "danger")
            finally:
                conexao.close()
                
    return render_template("login.html")


# --- ROTA DE AUTENTICAÇÃO: LOGOUT ---
@app.route("/logout")
def logout():
    session.clear()
    flash("Você saiu da sua conta com sucesso.", "success")
    return redirect(url_for("login"))


# --- ROTA DE GERENCIAMENTO DE USUÁRIOS (RESTRITA A ADMIN) ---
@app.route("/usuarios/gerenciar", methods=["GET", "POST"])
def gerenciar_usuarios():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    
    # Restrição estrita para administradores
    if session.get("usuario_papel") != "admin":
        flash("❌ Acesso negado. Área restrita para administradores.", "danger")
        return redirect(url_for("dashboard"))

    conexao = obter_conexao()
    if request.method == "POST":
        nome = limpar_campo("nome")
        email = limpar_campo("email")
        senha = limpar_campo("senha")
        papel = limpar_campo("papel")  # admin, professor, pai_mae, aluno

        if conexao:
            try:
                with conexao.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO usuarios (nome, email, senha, papel)
                        VALUES (%s, %s, %s, %s);
                    """, (nome, email, senha, papel))
                    conexao.commit()
                    flash("✅ Usuário cadastrado com sucesso!", "success")
            except Exception as e:
                conexao.rollback()
                flash(f"❌ Erro ao cadastrar usuário: {e}", "danger")
            finally:
                conexao.close()
        return redirect(url_for("gerenciar_usuarios"))

    usuarios_cadastrados = []
    if conexao:
        try:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT id, nome, email, papel FROM usuarios ORDER BY nome ASC;")
                usuarios_cadastrados = cursor.fetchall()
        except Exception as e:
            print(f"Erro ao listar usuários: {e}")
        finally:
            conexao.close()

    return render_template("gerenciar_usuarios.html", usuarios=usuarios_cadastrados)


# --- ROTA 1: DASHBOARD ---
@app.route("/dashboard")
def dashboard():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    metrics = {"total_alunos": 0, "total_professores": 0, "total_turmas": 0}

    conexao = obter_conexao()
    if conexao:
        try:
            with conexao.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM alunos WHERE situacao = 'ativo';")
                metrics["total_alunos"] = cursor.fetchone()[0]

                cursor.execute(
                    "SELECT COUNT(*) FROM funcionarios WHERE cargo = 'Professor' AND ativo = TRUE;"
                )
                metrics["total_professores"] = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM turmas;")
                metrics["total_turmas"] = cursor.fetchone()[0]
        except Exception as e:
            print(f"❌ Erro ao consultar dashboard: {e}")
        finally:
            conexao.close()

    return render_template("dashboard.html", metrics=metrics)


# --- ROTA GERAL: CALENDÁRIO ESCOLAR ---
@app.route('/calendario_escolar', methods=['GET', 'POST'])
def calendario_escolar():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    if request.method == 'POST':
        titulo = limpar_campo('titulo')
        descricao = limpar_campo('descricao')
        data_evento = limpar_campo('data_evento')
        tipo = limpar_campo('tipo', 'geral')
        turma_id = request.form.get('turma_id') or None
        professor_id = request.form.get('professor_id') or None
        aluno_id = request.form.get('aluno_id') or None

        conexao = obter_conexao()
        if conexao:
            try:
                with conexao.cursor() as cursor:
                    cursor.execute('''
                        INSERT INTO calendario_eventos (titulo, descricao, data_evento, tipo, turma_id, professor_id, aluno_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ''', (titulo, descricao, data_evento, tipo, turma_id, professor_id, aluno_id))
                    
                    if tipo == 'turma' and turma_id:
                        cursor.execute('SELECT aluno_id FROM turma_alunos WHERE turma_id = %s', (turma_id,))
                        alunos_da_turma = cursor.fetchall()
                        for al in alunos_da_turma:
                            al_id = al[0] if isinstance(al, tuple) else al['aluno_id']
                            cursor.execute('''
                                INSERT INTO calendario_eventos (titulo, descricao, data_evento, tipo, turma_id, aluno_id)
                                VALUES (%s, %s, %s, 'aluno_vinculado_turma', %s, %s)
                            ''', (f"[Turma] {titulo}", descricao, data_evento, turma_id, al_id))

                    conexao.commit()
                    flash('✅ Evento adicionado com sucesso e sincronizado!', 'success')
            except Exception as e:
                conexao.rollback()
                print(f"❌ Erro ao salvar evento no calendário: {e}")
                flash(f'❌ Erro ao salvar evento: {e}', 'danger')
            finally:
                conexao.close()

        return redirect(url_for('calendario_escolar'))

    ano = request.args.get('ano', type=int) or datetime.now().year
    mes = request.args.get('mes', type=int) or datetime.now().month

    cal = calendario_lib.Calendar(firstweekday=6)
    dias_do_mes = cal.monthdatescalendar(ano, mes)

    nomes_meses = {
        1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
        5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
        9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
    }
    
    nome_mes_atual = f"{nomes_meses.get(mes, 'Mês')} {ano}"

    mes_anterior = mes - 1 if mes > 1 else 12
    ano_anterior = ano if mes > 1 else ano - 1
    
    mes_proximo = mes + 1 if mes < 12 else 1
    ano_proximo = ano if mes < 12 else ano + 1

    turmas, professores, alunos, eventos = [], [], [], []

    conexao = obter_conexao()
    if conexao:
        try:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute('SELECT id, nome FROM turmas ORDER BY nome ASC')
                turmas = cursor.fetchall()

                cursor.execute("SELECT id, nome_completo FROM funcionarios WHERE cargo = 'Professor' AND ativo = TRUE ORDER BY nome_completo ASC")
                professores = cursor.fetchall()

                cursor.execute('SELECT id, nome_completo FROM alunos ORDER BY nome_completo ASC')
                alunos = cursor.fetchall()

                cursor.execute('''
                    SELECT c.*, t.nome as turma_nome, f.nome_completo as professor_nome, a.nome_completo as aluno_nome
                    FROM calendario_eventos c
                    LEFT JOIN turmas t ON c.turma_id = t.id
                    LEFT JOIN funcionarios f ON c.professor_id = f.id
                    LEFT JOIN alunos a ON c.aluno_id = a.id
                    ORDER BY c.data_evento ASC
                ''')
                eventos = cursor.fetchall()
        except Exception as e:
            print(f"❌ Erro ao buscar dados do calendário: {e}")
        finally:
            conexao.close()

    return render_template(
        'calendario_escolar.html',
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
        eventos=eventos
    )


# --- ROTA ADICIONAL: CADASTRAR EVENTO ---
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


# --- ROTA 2: GESTÃO DE ALUNOS ---
@app.route("/alunos", methods=["GET", "POST"])
def pagina_alunos():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        acao = request.form.get("acao", "cadastrar_aluno")
        
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
            }

            resp1_nome = limpar_campo("resp1_nome")
            resp1 = {
                "nome_completo": resp1_nome,
                "cpf": limpar_campo("resp1_cpf"),
                "grau_parentesco": limpar_campo("resp1_parentesco"),
                "telefone": limpar_campo("resp1_telefone"),
                "local_trabalho": limpar_campo("resp1_trabalho"),
                "telefone_trabalho": limpar_campo("resp1_tel_trabalho"),
            } if resp1_nome else None

            resp2_nome = limpar_campo("resp2_nome")
            resp2 = {
                "nome_completo": resp2_nome,
                "cpf": limpar_campo("resp2_cpf"),
                "grau_parentesco": limpar_campo("resp2_parentesco"),
                "telefone": limpar_campo("resp2_telefone"),
                "local_trabalho": limpar_campo("resp2_trabalho"),
                "telefone_trabalho": limpar_campo("resp2_tel_trabalho"),
            } if resp2_nome else None

            try:
                matricula = cadastrar_aluno(dados_aluno, responsavel_1=resp1, responsavel_2=resp2)
                if matricula:
                    flash(f"✅ Aluno cadastrado com sucesso! Matrícula: {matricula}", "success")
                else:
                    flash("❌ Erro ao cadastrar aluno. Verifique os campos.", "danger")
            except Exception as e:
                print(f"❌ Exceção ao cadastrar aluno: {e}")
                flash(f"❌ Erro de banco de dados: {e}", "danger")

        elif acao == "editar_responsavel":
            resp_id = request.form.get("responsavel_id")
            aluno_id = request.form.get("aluno_id")
            try:
                atualizar_responsavel(resp_id, {
                    "nome_completo": limpar_campo("nome_completo"),
                    "grau_parentesco": limpar_campo("grau_parentesco"),
                    "telefone": limpar_campo("telefone"),
                    "email": limpar_campo("email"),
                    "local_trabalho": limpar_campo("local_trabalho"),
                    "telefone_trabalho": limpar_campo("telefone_trabalho")
                })
                flash("✅ Responsável atualizado com sucesso!", "success")
            except Exception as e:
                flash(f"❌ Erro ao atualizar responsável: {e}", "danger")
            return redirect(url_for("detalhes_aluno", aluno_id=aluno_id))

        elif acao == "deletar_responsavel":
            resp_id = request.form.get("responsavel_id")
            aluno_id = request.form.get("aluno_id")
            try:
                deletar_responsavel(resp_id)
                flash("✅ Responsável removido com sucesso!", "success")
            except Exception as e:
                flash(f"❌ Erro ao remover responsável: {e}", "danger")
            return redirect(url_for("detalhes_aluno", aluno_id=aluno_id))

        return redirect(url_for("pagina_alunos"))

    alunos = listar_alunos()
    return render_template("alunos.html", alunos=alunos)


@app.route("/cadastrar_aluno", methods=["POST"])
def cadastrar_aluno_rota():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    return pagina_alunos()


# --- ROTA 2.1: PERFIL DO ALUNO ---
@app.route("/alunos/<int:aluno_id>")
def detalhes_aluno(aluno_id):
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    conexao = obter_conexao()
    aluno, responsaveis, turmas_aluno, financeiro_aluno, pessoas_autorizadas, provas_notas = None, [], [], [], [], []

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
        except Exception as e:
            print(f"❌ Erro ao carregar detalhes do aluno: {e}")
        finally:
            conexao.close()

    if not aluno:
        flash("❌ Aluno não encontrado.", "danger")
        return redirect(url_for("pagina_alunos"))

    return render_template(
        "aluno_detalhes.html",
        aluno=aluno,
        responsaveis=responsaveis,
        turmas=turmas_aluno,
        financeiro=financeiro_aluno,
        pessoas_autorizadas=pessoas_autorizadas,
        provas_notas=provas_notas,
    )


@app.route("/alunos/<int:aluno_id>/adicionar_responsavel", methods=["POST"])
def adicionar_responsavel(aluno_id):
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    conexao = obter_conexao()
    if conexao:
        try:
            with conexao.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM responsaveis_aluno WHERE aluno_id = %s;", (aluno_id,))
                proximo_tipo = cursor.fetchone()[0] + 1

                cursor.execute("""
                    INSERT INTO responsaveis_aluno (
                        aluno_id, tipo_responsavel, nome_completo, cpf, grau_parentesco, 
                        telefone, local_trabalho, telefone_trabalho
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                """, (
                    aluno_id, proximo_tipo, limpar_campo("nome_completo"), limpar_campo("cpf"),
                    limpar_campo("grau_parentesco"), limpar_campo("telefone"),
                    limpar_campo("local_trabalho"), limpar_campo("telefone_trabalho")
                ))
                conexao.commit()
                flash("✅ Responsável adicionado com sucesso!", "success")
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


# --- ROTA 3: PROFESSORES ---
@app.route("/professores", methods=["GET", "POST"])
def pagina_professores():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        salario_raw = request.form.get("salario", "").strip()
        try:
            salario = float(salario_raw.replace(",", ".")) if salario_raw else 0.0
        except ValueError:
            salario = 0.0

        # Garantir um valor padrão caso o telefone não venha do formulário
        telefone = limpar_campo("telefone") or "(00) 00000-0000"

        conexao = obter_conexao()
        if conexao:
            try:
                with conexao.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO funcionarios (
                            nome_completo, cpf, data_nascimento, cargo, especialidade, telefone, email, salario, ativo
                        ) VALUES (%s, %s, %s, 'Professor', %s, %s, %s, %s, TRUE);
                        """,
                        (
                            limpar_campo("nome_completo"),
                            limpar_campo("cpf"),
                            limpar_campo("data_nascimento") or "2000-01-01",
                            limpar_campo("especialidade"),
                            telefone,
                            limpar_campo("email"),
                            salario,
                        ),
                    )
                    conexao.commit()
                    flash("✅ Professor cadastrado com sucesso!", "success")
            except Exception as e:
                conexao.rollback()
                flash(f"❌ Erro ao cadastrar professor: {e}", "danger")
            finally:
                conexao.close()

        return redirect(url_for("pagina_professores"))

    # Correção aplicada: Adicionado o retorno do template GET para quando a página for carregada normalmente
    professores_cadastrados = []
    conexao = obter_conexao()
    if conexao:
        try:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT id, nome_completo, especialidade, email FROM funcionarios WHERE cargo = 'Professor' AND ativo = TRUE ORDER BY nome_completo ASC;")
                professores_cadastrados = cursor.fetchall()
        except Exception as e:
            print(f"❌ Erro ao listar professores: {e}")
        finally:
            conexao.close()

    return render_template("professores.html", professores=professores_cadastrados)


# --- ROTA DE ALIAS: CADASTRAR PROFESSOR (Corrige o Werkzeug BuildError) ---
@app.route("/cadastrar_professor", methods=["POST"])
def cadastrar_professor():
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    return pagina_professores()


# --- ROTA 4: PEDAGÓGICO ---
@app.route("/pedagogico", methods=["GET", "POST"])
def pagina_pedagogico():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        acao = request.form.get("acao", "criar_turma")
        conexao = obter_conexao()

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
            except Exception as e:
                conexao.rollback()
                print(f"Erro na ação pedagógica: {e}")
                flash(f"❌ Ocorreu um erro: {e}", "danger")
            finally:
                conexao.close()

        return redirect(url_for("pagina_pedagogico"))

    turmas, professores, alunos_cadastrados = [], [], []
    alunos_por_turma = {}

    conexao = obter_conexao()
    if conexao:
        try:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT t.id, t.nome, t.ano_letivo, t.turno, f.nome_completo,
                           COUNT(ta.aluno_id) AS total_alunos
                    FROM turmas t
                    LEFT JOIN funcionarios f ON t.professor_responsavel_id = f.id
                    LEFT JOIN turma_alunos ta ON t.id = ta.turma_id
                    GROUP BY t.id, t.nome, t.ano_letivo, t.turno, f.nome_completo
                    ORDER BY t.nome ASC;
                """)
                turmas = cursor.fetchall()

                cursor.execute("""
                    SELECT id, nome_completo FROM funcionarios 
                    WHERE cargo = 'Professor' AND ativo = TRUE ORDER BY nome_completo ASC;
                """)
                professores = cursor.fetchall()

                cursor.execute("SELECT id, nome_completo, matricula FROM alunos ORDER BY nome_completo ASC;")
                alunos_cadastrados = cursor.fetchall()

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
        except Exception as e:
            print(f"Erro ao carregar dados pedagógicos: {e}")
        finally:
            conexao.close()

    return render_template(
        "pedagogico.html",
        turmas=turmas,
        professores=professores,
        alunos_cadastrados=alunos_cadastrados,
        alunos_por_turma=alunos_por_turma,
    )


@app.route("/excluir_turma/<int:id>", methods=["POST"])
def excluir_turma(id):
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    conexao = obter_conexao()
    if conexao:
        try:
            with conexao.cursor() as cursor:
                cursor.execute("DELETE FROM turmas WHERE id = %s;", (id,))
                conexao.commit()
                flash("✅ Turma excluída com sucesso!", "success")
        except Exception as e:
            conexao.rollback()
            flash(f"❌ Erro ao excluir turma: {e}", "danger")
        finally:
            conexao.close()
    return redirect(url_for("pagina_pedagogico"))


@app.route("/remover_aluno_turma/<int:turma_id>/<int:aluno_id>", methods=["POST"])
def remover_aluno_turma(turma_id, aluno_id):
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    conexao = obter_conexao()
    if conexao:
        try:
            with conexao.cursor() as cursor:
                cursor.execute("DELETE FROM turma_alunos WHERE turma_id = %s AND aluno_id = %s;", (turma_id, aluno_id))
                conexao.commit()
                flash("✅ Aluno removido da turma com sucesso!", "success")
        except Exception as e:
            conexao.rollback()
            flash(f"❌ Erro ao remover aluno da turma: {e}", "danger")
        finally:
            conexao.close()
    return redirect(url_for("pagina_pedagogico"))

# --- ROTA 5: FINANCEIRO ---
@app.route("/financeiro", methods=["GET", "POST"])
def pagina_financeiro():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        acao = request.form.get("acao", "criar_cobranca")
        conexao = obter_conexao()

        if conexao:
            try:
                with conexao.cursor() as cursor:
                    if acao == "criar_cobranca":
                        valor_raw = request.form.get("valor", "0").replace(".", "").replace(",", ".")
                        try:
                            valor = float(valor_raw)
                        except ValueError:
                            valor = 0.0

                        cursor.execute(
                            """
                            INSERT INTO financeiro_mensalidades (aluno_id, descricao, valor, data_vencimento, status)
                            VALUES (%s, %s, %s, %s, 'Pendente');
                            """,
                            (
                                limpar_campo("aluno_id"),
                                limpar_campo("descricao"),
                                valor,
                                limpar_campo("data_vencimento"),
                            ),
                        )
                        conexao.commit()
                        flash("✅ Cobrança gerada com sucesso!", "success")

                    elif acao == "gerar_lote":
                        cursor.execute("SELECT id, valor_mensalidade FROM alunos WHERE situacao = 'ativo' AND valor_mensalidade > 0;")
                        alunos_ativos = cursor.fetchall()
                        descricao_lote = limpar_campo("descricao_lote")
                        vencimento_lote = limpar_campo("data_vencimento_lote")

                        total_gerado = 0
                        for aluno in alunos_ativos:
                            al_id = aluno[0] if isinstance(aluno, tuple) else aluno['id']
                            al_valor = aluno[1] if isinstance(aluno, tuple) else aluno['valor_mensalidade']
                            cursor.execute(
                                """
                                INSERT INTO financeiro_mensalidades (aluno_id, descricao, valor, data_vencimento, status)
                                VALUES (%s, %s, %s, %s, 'Pendente');
                                """,
                                (al_id, descricao_lote, al_valor, vencimento_lote),
                            )
                            total_gerado += 1

                        conexao.commit()
                        flash(f"✅ Geradas {total_gerado} cobranças em lote!", "success")

                    elif acao == "dar_baixa":
                        data_pag = limpar_campo("data_pagamento") or datetime.now().strftime('%Y-%m-%d')
                        forma_pag = limpar_campo("forma_pagamento") or "Dinheiro"
                        cobranca_id = limpar_campo("cobranca_id")

                        cursor.execute(
                            """
                            UPDATE financeiro_mensalidades 
                            SET status = 'Pago', forma_pagamento = %s, data_pagamento = %s 
                            WHERE id = %s;
                            """,
                            (forma_pag, data_pag, cobranca_id),
                        )
                        conexao.commit()
                        flash("✅ Pagamento registrado com sucesso!", "success")
            except Exception as e:
                conexao.rollback()
                flash(f"❌ Erro na operação: {e}", "danger")
            finally:
                conexao.close()

        origem = request.form.get("origem_aluno_id")
        if origem:
            return redirect(url_for("detalhes_aluno", aluno_id=origem))

        return redirect(url_for("pagina_financeiro"))

    lancamentos, alunos = [], []
    totais = {"recebido": 0.0, "pendente": 0.0, "atrasado": 0.0}

    busca = request.args.get("busca", "").strip()
    status_filtro = request.args.get("status", "").strip()

    conexao = obter_conexao()
    if conexao:
        try:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    UPDATE financeiro_mensalidades 
                    SET status = 'Atrasado' 
                    WHERE status = 'Pendente' AND data_vencimento < CURRENT_DATE;
                    """
                )
                conexao.commit()

                query_lancamentos = """
                    SELECT f.id, f.aluno_id, a.nome_completo, f.descricao, f.valor, f.data_vencimento, 
                           f.data_pagamento, f.status, f.forma_pagamento
                    FROM financeiro_mensalidades f
                    LEFT JOIN alunos a ON f.aluno_id = a.id
                    WHERE 1=1
                """
                params = []

                if busca:
                    query_lancamentos += " AND a.nome_completo ILIKE %s"
                    params.append(f"%{busca}%")

                if status_filtro:
                    query_lancamentos += " AND f.status = %s"
                    params.append(status_filtro)

                query_lancamentos += " ORDER BY f.data_vencimento DESC;"

                cursor.execute(query_lancamentos, params)
                lancamentos = cursor.fetchall()

                cursor.execute(
                    """
                    SELECT 
                        COALESCE(SUM(CASE WHEN status = 'Pago' THEN valor::numeric ELSE 0 END), 0) AS recebido,
                        COALESCE(SUM(CASE WHEN status = 'Pendente' THEN valor::numeric ELSE 0 END), 0) AS pendente,
                        COALESCE(SUM(CASE WHEN status = 'Atrasado' THEN valor::numeric ELSE 0 END), 0) AS atrasado
                    FROM financeiro_mensalidades;
                    """
                )
                resumo = cursor.fetchone()
                if resumo:
                    totais["recebido"] = float(resumo["recebido"])
                    totais["pendente"] = float(resumo["pendente"])
                    totais["atrasado"] = float(resumo["atrasado"])

                cursor.execute("SELECT id, nome_completo, valor_mensalidade FROM alunos ORDER BY nome_completo ASC;")
                alunos = cursor.fetchall()

        except Exception as e:
            print(f"❌ Erro ao carregar dados financeiros: {e}")
        finally:
            conexao.close()

    return render_template(
        "financeiro.html",
        lancamentos=lancamentos,
        alunos=alunos,
        totais=totais,
        busca=busca,
        status=status_filtro,
        data_hoje=datetime.now().strftime('%Y-%m-%d')
    )


# --- ROTA: EXCLUIR COBRANÇA FINANCEIRA ---
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

# --- ROTA: CONFIGURAÇÕES E USUÁRIOS ---
@app.route("/configuracoes", methods=["GET", "POST"])
def pagina_configuracoes():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    conexao = obter_conexao()
    if request.method == "POST":
        acao = request.form.get("acao")
        
        if acao == "salvar_parametros":
            nome_escola = request.form.get("nome_escola")
            ano_letivo = request.form.get("ano_letivo")
            email_contato = request.form.get("email_contato")
            if conexao:
                try:
                    with conexao.cursor() as cursor:
                        cursor.execute(
                            """
                            INSERT INTO configuracoes (id, nome_escola, ano_letivo, email_contato)
                            VALUES (1, %s, %s, %s)
                            ON CONFLICT (id) DO UPDATE 
                            SET nome_escola = EXCLUDED.nome_escola,
                                ano_letivo = EXCLUDED.ano_letivo,
                                email_contato = EXCLUDED.email_contato;
                            """,
                            (nome_escola, ano_letivo, email_contato),
                        )
                        conexao.commit()
                        flash("✅ Parâmetros salvos com sucesso!", "success")
                except Exception as e:
                    conexao.rollback()
                    flash(f"❌ Erro ao salvar parâmetros: {e}", "danger")
                finally:
                    conexao.close()

        elif acao == "cadastrar_usuario":
            nome = request.form.get("nome_usuario")
            email = request.form.get("email_usuario")
            senha = request.form.get("senha_usuario")
            papel = request.form.get("funcao_usuario") or request.form.get("papel_usuario") or "admin"
            if conexao:
                try:
                    with conexao.cursor() as cursor:
                        cursor.execute(
                            """
                            INSERT INTO usuarios (nome, email, senha, papel)
                            VALUES (%s, %s, %s, %s);
                            """,
                            (nome, email, senha, papel),
                        )
                        conexao.commit()
                        flash("✅ Usuário cadastrado com sucesso!", "success")
                except Exception as e:
                    conexao.rollback()
                    flash(f"❌ Erro ao cadastrar usuário: {e}", "danger")
                finally:
                    conexao.close()

        return redirect(url_for("pagina_configuracoes"))

    config = {}
    usuarios = []
    if conexao:
        try:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                try:
                    cursor.execute("SELECT * FROM configuracoes WHERE id = 1;")
                    config = cursor.fetchone() or {}
                except Exception:
                    conexao.rollback()

                cursor.execute("SELECT id, nome, email, papel FROM usuarios ORDER BY nome ASC;")
                usuarios = cursor.fetchall()
        except Exception as e:
            print(f"Erro ao carregar dados de configurações: {e}")
        finally:
            conexao.close()

    return render_template("configuracoes.html", config=config, usuarios=usuarios)


@app.route("/excluir_usuario_sistema/<int:id>", methods=["POST"])
def excluir_usuario_sistema(id):
    if "usuario_id" not in session:
        return redirect(url_for("login"))
    conexao = obter_conexao()
    if conexao:
        try:
            with conexao.cursor() as cursor:
                cursor.execute("DELETE FROM usuarios WHERE id = %s;", (id,))
                conexao.commit()
                flash("✅ Usuário excluído com sucesso!", "success")
        except Exception as e:
            conexao.rollback()
            flash(f"❌ Erro ao excluir usuário: {e}", "danger")
        finally:
            conexao.close()
    return redirect(url_for("pagina_configuracoes"))


if __name__ == "__main__":
    app.run(debug=True, port=5000)