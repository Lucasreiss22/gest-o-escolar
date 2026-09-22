import datetime
from database import obter_conexao
from psycopg2.extras import RealDictCursor


def gerar_proxima_matricula(cursor) -> str:
    """Gera a próxima matrícula no formato AAAANNN (Ex: 2026001)."""
    ano_atual = datetime.datetime.now().year

    query = """
        SELECT matricula
        FROM alunos
        WHERE matricula LIKE %s
        ORDER BY matricula DESC
        LIMIT 1;
    """
    cursor.execute(query, (f"{ano_atual}%",))
    ultimo_registro = cursor.fetchone()

    novo_sequencial = 1
    if ultimo_registro:
        ultimo_valor = ultimo_registro["matricula"] if isinstance(ultimo_registro, dict) else ultimo_registro[0]
        texto = str(ultimo_valor or "")
        if len(texto) >= 5:
            try:
                novo_sequencial = int(texto[4:]) + 1
            except ValueError:
                novo_sequencial = 1

    return f"{ano_atual}{novo_sequencial:03d}"


def cadastrar_aluno(dados_aluno: dict, responsavel_1: dict = None, responsavel_2: dict = None):
    """Cadastra um novo aluno no banco de dados e gera sua matrícula automaticamente."""
    from database import garantir_tabelas_folha, garantir_tabelas_pedagogicas
    garantir_tabelas_folha()
    garantir_tabelas_pedagogicas()

    conexao = obter_conexao()
    if not conexao:
        raise Exception("Não foi possível estabelecer conexão com o banco de dados.")

    cursor = None
    try:
        cursor = conexao.cursor(cursor_factory=RealDictCursor)
        matricula = gerar_proxima_matricula(cursor)

        sexo_bruto = (dados_aluno.get("sexo") or "").strip()
        sexo = sexo_bruto[:1].upper() if sexo_bruto else None
        if sexo_bruto.lower().startswith("fem"):
            sexo = "F"
        elif sexo_bruto.lower().startswith("masc"):
            sexo = "M"
        estado = (dados_aluno.get("estado") or "")[:2].upper() or None

        sql_aluno = """
            INSERT INTO alunos (
                matricula, nome_completo, cpf, rg, certidao_nascimento, data_nascimento, sexo,
                telefone_principal, telefone_secundario, email,
                cep, rua, numero, bairro, cidade, estado,
                valor_mensalidade, desconto_tipo, desconto_valor, status,
                contrato_meses, contrato_inicio, turnos_mensalidade, foto_url
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, 'ativo',
                %s, %s, %s, %s
            ) RETURNING id;
        """

        valores_aluno = (
            matricula,
            dados_aluno["nome_completo"],
            dados_aluno.get("cpf"),
            dados_aluno.get("rg"),
            dados_aluno.get("certidao_nascimento"),
            dados_aluno["data_nascimento"],
            sexo,
            dados_aluno["telefone_principal"],
            dados_aluno.get("telefone_secundario"),
            dados_aluno.get("email"),
            dados_aluno.get("cep"),
            dados_aluno.get("rua"),
            dados_aluno.get("numero"),
            dados_aluno.get("bairro"),
            dados_aluno.get("cidade"),
            estado,
            dados_aluno.get("valor_mensalidade", 0.00),
            dados_aluno.get("desconto_tipo") or "nenhum",
            dados_aluno.get("desconto_valor", 0.00),
            dados_aluno.get("contrato_meses") or 12,
            dados_aluno.get("contrato_inicio") or None,
            dados_aluno.get("turnos_mensalidade") or "manha",
            dados_aluno.get("foto_url"),
        )

        cursor.execute(sql_aluno, valores_aluno)
        resultado_aluno = cursor.fetchone()
        aluno_id = resultado_aluno["id"] if isinstance(resultado_aluno, dict) else resultado_aluno[0]

        turma_id = dados_aluno.get("turma_id")
        if turma_id:
            cursor.execute("""
                INSERT INTO turma_alunos (turma_id, aluno_id)
                VALUES (%s, %s)
                ON CONFLICT (turma_id, aluno_id) DO NOTHING;
            """, (turma_id, aluno_id))

        sql_resp = """
            INSERT INTO responsaveis_aluno (
                aluno_id, tipo_responsavel, nome_completo, cpf, grau_parentesco,
                telefone, email, local_trabalho, telefone_trabalho, foto_url
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """

        if responsavel_1 and responsavel_1.get("nome_completo"):
            cursor.execute(sql_resp, (
                aluno_id, 1,
                responsavel_1["nome_completo"],
                responsavel_1.get("cpf"),
                responsavel_1.get("grau_parentesco"),
                responsavel_1.get("telefone"),
                responsavel_1.get("email"),
                responsavel_1.get("local_trabalho"),
                responsavel_1.get("telefone_trabalho"),
                responsavel_1.get("foto_url"),
            ))

        if responsavel_2 and responsavel_2.get("nome_completo"):
            cursor.execute(sql_resp, (
                aluno_id, 2,
                responsavel_2["nome_completo"],
                responsavel_2.get("cpf"),
                responsavel_2.get("grau_parentesco"),
                responsavel_2.get("telefone"),
                responsavel_2.get("email"),
                responsavel_2.get("local_trabalho"),
                responsavel_2.get("telefone_trabalho"),
                responsavel_2.get("foto_url"),
            ))

        conexao.commit()
        return matricula

    except Exception as e:
        if conexao:
            conexao.rollback()
        raise e
    finally:
        if cursor:
            cursor.close()
        if conexao:
            conexao.close()


def listar_alunos(termo: str = None):
    """Retorna uma lista de alunos com turmas agrupadas, permitindo busca por nome, CPF ou matrícula."""
    conexao = obter_conexao()
    if not conexao:
        return []

    try:
        with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
            if termo:
                filtro = f"%{termo}%"
                cursor.execute(
                    """
                    SELECT
                        a.id,
                        a.matricula,
                        a.nome_completo,
                        a.email,
                        a.telefone_principal,
                        a.cidade,
                        a.rua,
                        a.foto_url,
                        a.turnos_mensalidade,
                        COALESCE(NULLIF(a.status, ''), 'ativo') AS status,
                        STRING_AGG(t.nome, ', ') AS turma_nome
                    FROM alunos a
                    LEFT JOIN turma_alunos ta ON ta.aluno_id = a.id
                    LEFT JOIN turmas t ON t.id = ta.turma_id
                    WHERE a.nome_completo ILIKE %s
                       OR COALESCE(a.matricula, '') ILIKE %s
                       OR CAST(a.id AS TEXT) ILIKE %s
                    GROUP BY a.id, a.matricula, a.nome_completo, a.email, a.telefone_principal, a.status,
                             a.cidade, a.rua, a.foto_url, a.turnos_mensalidade
                    ORDER BY a.id DESC;
                    """,
                    (filtro, filtro, filtro),
                )
            else:
                cursor.execute(
                    """
                    SELECT
                        a.id,
                        a.matricula,
                        a.nome_completo,
                        a.email,
                        a.telefone_principal,
                        a.cidade,
                        a.rua,
                        a.foto_url,
                        a.turnos_mensalidade,
                        COALESCE(NULLIF(a.status, ''), 'ativo') AS status,
                        STRING_AGG(t.nome, ', ') AS turma_nome
                    FROM alunos a
                    LEFT JOIN turma_alunos ta ON ta.aluno_id = a.id
                    LEFT JOIN turmas t ON t.id = ta.turma_id
                    GROUP BY a.id, a.matricula, a.nome_completo, a.email, a.telefone_principal, a.status,
                             a.cidade, a.rua, a.foto_url, a.turnos_mensalidade
                    ORDER BY a.id DESC;
                    """
                )
            return cursor.fetchall()
    except Exception as e:
        try:
            print(f"Erro ao listar/buscar alunos: {e}")
        except Exception:
            pass
        return []
    finally:
        conexao.close()


def atualizar_responsavel(resp_id, dados):
    """Atualiza as informações de cadastro de um responsável legal."""
    conexao = obter_conexao()
    if not conexao:
        raise Exception("Não foi possível conectar ao banco de dados.")
    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                UPDATE responsaveis_aluno 
                SET nome_completo = %s, cpf = %s, grau_parentesco = %s, 
                    telefone = %s, email = %s, local_trabalho = %s, telefone_trabalho = %s,
                    foto_url = COALESCE(%s, foto_url)
                WHERE id = %s;
            """, (
                dados.get("nome_completo"), dados.get("cpf"), dados.get("grau_parentesco"),
                dados.get("telefone"), dados.get("email"), dados.get("local_trabalho"),
                dados.get("telefone_trabalho"), dados.get("foto_url"), resp_id
            ))
            conexao.commit()
    except Exception as e:
        conexao.rollback()
        raise e
    finally:
        conexao.close()


def deletar_responsavel(resp_id):
    """Remove um responsável legal vinculado ao aluno."""
    conexao = obter_conexao()
    if not conexao:
        raise Exception("Não foi possível conectar ao banco de dados.")
    try:
        with conexao.cursor() as cursor:
            cursor.execute("DELETE FROM responsaveis_aluno WHERE id = %s;", (resp_id,))
            conexao.commit()
    except Exception as e:
        conexao.rollback()
        raise e
    finally:
        conexao.close()