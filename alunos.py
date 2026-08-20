import datetime
from database import obter_conexao
from psycopg2.extras import RealDictCursor


def gerar_proxima_matricula(cursor) -> str:
    """Gera a próxima matrícula no formato AAAANNN (Ex: 2026001).

    Busca o maior sequencial do ano corrente no banco e incrementa 1.
    """
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

    if ultimo_registro:
        # Como o cursor é RealDict, acessamos pela chave 'matricula'
        ultimo_valor = ultimo_registro["matricula"] if isinstance(ultimo_registro, dict) else ultimo_registro[0]
        ultimo_sequencial = int(ultimo_valor[4:])
        novo_sequencial = ultimo_sequencial + 1
    else:
        # Primeiro aluno cadastrado no ano
        novo_sequencial = 1

    # Formata garantindo no mínimo 3 dígitos (001, 002... 250... 1000)
    return f"{ano_atual}{novo_sequencial:03d}"


def cadastrar_aluno(dados_aluno: dict, responsavel_1: dict = None, responsavel_2: dict = None):
    """Cadastra um novo aluno no banco de dados e gera sua matrícula automaticamente.

    Executa em uma transação para garantir consistência entre Aluno e
    Responsáveis.
    """
    conexao = obter_conexao()
    if not conexao:
        raise Exception("Não foi possível estabelecer conexão com o banco de dados.")

    cursor = None
    try:
        # Configurando o cursor para retornar dicionários
        cursor = conexao.cursor(cursor_factory=RealDictCursor)

        # 1. Gerar Matrícula Automática
        matricula = gerar_proxima_matricula(cursor)

        # 2. Inserir Aluno
        sql_aluno = """
            INSERT INTO alunos (
                matricula, nome_completo, cpf, rg, certidao_nascimento, data_nascimento, sexo,
                telefone_principal, telefone_secundario, email,
                cep, rua, numero, bairro, cidade, estado,
                valor_mensalidade, desconto_tipo, desconto_valor
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s
            ) RETURNING id;
        """

        valores_aluno = (
            matricula,
            dados_aluno["nome_completo"],
            dados_aluno.get("cpf"),
            dados_aluno.get("rg"),
            dados_aluno.get("certidao_nascimento"),
            dados_aluno["data_nascimento"],
            dados_aluno.get("sexo"),
            dados_aluno["telefone_principal"],
            dados_aluno.get("telefone_secundario"),
            dados_aluno.get("email"),
            dados_aluno.get("cep"),
            dados_aluno.get("rua"),
            dados_aluno.get("numero"),
            dados_aluno.get("bairro"),
            dados_aluno.get("cidade"),
            dados_aluno.get("estado"),
            dados_aluno.get("valor_mensalidade", 0.00),
            dados_aluno.get("desconto_tipo", "nenhum"),
            dados_aluno.get("desconto_valor", 0.00),
        )

        cursor.execute(sql_aluno, valores_aluno)
        resultado_aluno = cursor.fetchone()
        aluno_id = resultado_aluno["id"] if isinstance(resultado_aluno, dict) else resultado_aluno[0]

        # SQL para inserção de responsáveis
        sql_resp = """
            INSERT INTO responsaveis_aluno (
                aluno_id, tipo_responsavel, nome_completo, cpf, grau_parentesco,
                telefone, local_trabalho, telefone_trabalho
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """

        # 3. Inserir Responsável 1 (Opcional, caso venha preenchido)
        if responsavel_1 and responsavel_1.get("nome_completo"):
            valores_resp1 = (
                aluno_id,
                1,
                responsavel_1["nome_completo"],
                responsavel_1.get("cpf"),
                responsavel_1.get("grau_parentesco"),
                responsavel_1.get("telefone"),
                responsavel_1.get("local_trabalho"),
                responsavel_1.get("telefone_trabalho"),
            )
            cursor.execute(sql_resp, valores_resp1)

        # 4. Inserir Responsável 2 (Opcional)
        if responsavel_2 and responsavel_2.get("nome_completo"):
            valores_resp2 = (
                aluno_id,
                2,
                responsavel_2["nome_completo"],
                responsavel_2.get("cpf"),
                responsavel_2.get("grau_parentesco"),
                responsavel_2.get("telefone"),
                responsavel_2.get("local_trabalho"),
                responsavel_2.get("telefone_trabalho"),
            )
            cursor.execute(sql_resp, valores_resp2)

        conexao.commit()
        print(f"✅ Aluno cadastrado com sucesso! Matrícula gerada: {matricula}")
        return matricula

    except Exception as e:
        if conexao:
            conexao.rollback()
        print(f"❌ Erro ao cadastrar aluno: {e}")
        raise e  # Repassa o erro exato para o app.py capturar e mostrar no flash

    finally:
        if cursor:
            cursor.close()
        if conexao:
            conexao.close()


def listar_alunos():
    """Retorna uma lista com todos os alunos cadastrados usando dicionários."""
    conexao = obter_conexao()
    if not conexao:
        return []

    try:
        with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT id, matricula, nome_completo, situacao FROM alunos ORDER BY id DESC;")
            alunos = cursor.fetchall()
            return alunos
    except Exception as e:
        print(f"❌ Erro ao listar alunos: {e}")
        return []
    finally:
        conexao.close()


def atualizar_responsavel(resp_id, dados):
    """Atualiza os dados de um responsável existente."""
    conexao = obter_conexao()
    if not conexao:
        raise Exception("Não foi possível conectar ao banco de dados.")
    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                UPDATE responsaveis_aluno 
                SET nome_completo = %s, 
                    grau_parentesco = %s, 
                    telefone = %s, 
                    email = %s, 
                    local_trabalho = %s, 
                    telefone_trabalho = %s
                WHERE id = %s;
            """, (
                dados.get("nome_completo"),
                dados.get("grau_parentesco"),
                dados.get("telefone"),
                dados.get("email"),
                dados.get("local_trabalho"),
                dados.get("telefone_trabalho"),
                resp_id
            ))
            conexao.commit()
    except Exception as e:
        conexao.rollback()
        raise e
    finally:
        conexao.close()


def deletar_responsavel(resp_id):
    """Remove um responsável do banco de dados pelo ID."""
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


# --- TESTE PRÁTICO ---
if __name__ == "__main__":
    print("\n--- Testando Cadastro de Aluno ---")
    
    aluno_teste = {
        "nome_completo": "Lucas Gabriel Silva",
        "data_nascimento": "2018-05-14",
        "sexo": "M",
        "telefone_principal": "21999998888",
        "valor_mensalidade": 650.00,
        "desconto_tipo": "percentual",
        "desconto_valor": 10.00
    }

    resp1_teste = {
        "nome_completo": "Mariana Silva",
        "cpf": "123.456.789-00",
        "grau_parentesco": "Mãe",
        "telefone": "21988887777"
    }

    cadastrar_aluno(aluno_teste, resp1_teste)
    
    print("\nAlunos no banco:")
    for a in listar_alunos():
        print(f"ID: {a['id']} | Matrícula: {a['matricula']} | Nome: {a['nome_completo']} | Status: {a['situacao']}")