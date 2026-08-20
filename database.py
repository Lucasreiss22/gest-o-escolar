import psycopg2

# Configurações de Conexão
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "gestao_escolar"
DB_USER = "postgres"
DB_PASSWORD = "123456"  # <--- Altere para sua senha do Postgres


def obter_conexao():
    """Abre uma conexão com o banco de dados gestao_escolar."""
    try:
        conexao = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
        )
        return conexao
    except Exception as erro:
        print(f"❌ Erro ao conectar ao PostgreSQL: {erro}")
        return None


def criar_estrutura_inicial():
    """Cria os ENUMs e todas as tabelas do sistema."""
    script_sql = """
    -- 1. Tipos Enumerados (ENUMs)
    DO $$ BEGIN
        CREATE TYPE perfil_acesso AS ENUM ('admin', 'direcao', 'secretaria', 'professor', 'financeiro', 'estoque');
    EXCEPTION
        WHEN duplicate_object THEN null;
    END $$;

    DO $$ BEGIN
        CREATE TYPE situacao_aluno AS ENUM ('ativo', 'transferido', 'trancado', 'concluido');
    EXCEPTION
        WHEN duplicate_object THEN null;
    END $$;

    DO $$ BEGIN
        CREATE TYPE tipo_desconto AS ENUM ('nenhum', 'percentual', 'valor_fixo', 'bolsa');
    EXCEPTION
        WHEN duplicate_object THEN null;
    END $$;

    -- 2. Tabela de Usuários / Autenticação
    CREATE TABLE IF NOT EXISTS usuarios (
        id SERIAL PRIMARY KEY,
        nome_completo VARCHAR(150) NOT NULL,
        cpf VARCHAR(14) UNIQUE NOT NULL,
        email VARCHAR(150) UNIQUE NOT NULL,
        senha_hash VARCHAR(255) NOT NULL,
        perfil perfil_acesso NOT NULL DEFAULT 'secretaria',
        ativo BOOLEAN DEFAULT TRUE,
        criado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- 3. Tabela de Alunos
    CREATE TABLE IF NOT EXISTS alunos (
        id SERIAL PRIMARY KEY,
        matricula VARCHAR(10) UNIQUE NOT NULL,
        nome_completo VARCHAR(150) NOT NULL,
        cpf VARCHAR(14) UNIQUE,
        rg VARCHAR(20),
        certidao_nascimento VARCHAR(50),
        data_nascimento DATE NOT NULL,
        sexo CHAR(1),
        foto_url VARCHAR(255),
        
        -- Contatos
        telefone_principal VARCHAR(20) NOT NULL,
        telefone_secundario VARCHAR(20),
        email VARCHAR(150),
        
        -- Endereço
        cep VARCHAR(9),
        rua VARCHAR(150),
        numero VARCHAR(20),
        bairro VARCHAR(100),
        cidade VARCHAR(100),
        estado CHAR(2),
        
        -- Acadêmico & Financeiro Base
        data_matricula DATE DEFAULT CURRENT_DATE,
        situacao situacao_aluno DEFAULT 'ativo',
        valor_mensalidade NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
        desconto_tipo tipo_desconto DEFAULT 'nenhum',
        desconto_valor NUMERIC(10, 2) DEFAULT 0.00,
        
        criado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- 4. Tabela de Responsáveis do Aluno
    CREATE TABLE IF NOT EXISTS responsaveis_aluno (
        id SERIAL PRIMARY KEY,
        aluno_id INT REFERENCES alunos(id) ON DELETE CASCADE,
        tipo_responsavel SMALLINT CHECK (tipo_responsavel IN (1, 2)),
        nome_completo VARCHAR(150) NOT NULL,
        cpf VARCHAR(14) NOT NULL,
        grau_parentesco VARCHAR(50) NOT NULL,
        telefone VARCHAR(20) NOT NULL,
        email VARCHAR(150),
        local_trabalho VARCHAR(150),
        telefone_trabalho VARCHAR(20)
    );

    -- 5. Tabela de Funcionários / Professores
    CREATE TABLE IF NOT EXISTS funcionarios (
        id SERIAL PRIMARY KEY,
        usuario_id INT REFERENCES usuarios(id) ON DELETE SET NULL,
        nome_completo VARCHAR(150) NOT NULL,
        cpf VARCHAR(14) UNIQUE NOT NULL,
        data_nascimento DATE NOT NULL,
        cargo VARCHAR(50) NOT NULL,
        telefone VARCHAR(20) NOT NULL,
        email VARCHAR(150),
        formacao VARCHAR(150),
        especialidade VARCHAR(150),
        data_contratacao DATE DEFAULT CURRENT_DATE,
        ativo BOOLEAN DEFAULT TRUE
    );

    -- 6. Tabela de Salas
    CREATE TABLE IF NOT EXISTS salas (
        id SERIAL PRIMARY KEY,
        nome VARCHAR(50) NOT NULL,
        capacidade INT NOT NULL,
        turno VARCHAR(20) NOT NULL,
        recursos TEXT
    );

    -- 7. Tabela de Disciplinas
    CREATE TABLE IF NOT EXISTS disciplinas (
        id SERIAL PRIMARY KEY,
        codigo VARCHAR(20) UNIQUE NOT NULL,
        nome VARCHAR(100) NOT NULL,
        carga_horaria INT NOT NULL
    );

    -- 8. Tabela de Turmas
    CREATE TABLE IF NOT EXISTS turmas (
        id SERIAL PRIMARY KEY,
        nome VARCHAR(100) NOT NULL,
        ano_letivo INT NOT NULL,
        turno VARCHAR(20) NOT NULL,
        sala_id INT REFERENCES salas(id) ON DELETE SET NULL,
        professor_responsavel_id INT REFERENCES funcionarios(id) ON DELETE SET NULL
    );

    -- 9. Tabela de Junção: Alunos Matriculados em Turmas
    CREATE TABLE IF NOT EXISTS turma_alunos (
        id SERIAL PRIMARY KEY,
        turma_id INT REFERENCES turmas(id) ON DELETE CASCADE,
        aluno_id INT REFERENCES alunos(id) ON DELETE CASCADE,
        data_entrou DATE DEFAULT CURRENT_DATE,
        UNIQUE(turma_id, aluno_id)
    );
    """

    conexao = obter_conexao()
    if conexao:
        try:
            cursor = conexao.cursor()
            cursor.execute(script_sql)
            conexao.commit()
            print("✅ Estrutura completa do banco de dados (Pedagógico + Alunos) atualizada com sucesso!")
            cursor.close()
            conexao.close()
        except Exception as e:
            print(f"❌ Erro ao criar tabelas: {e}")


# --- FUNÇÕES DE ATUALIZAÇÃO E EXCLUSÃO DE RESPONSÁVEIS ---

def atualizar_responsavel(resp_id, dados):
    """Atualiza os dados de um responsável existente na tabela responsaveis_aluno."""
    conexao = obter_conexao()
    if not conexao:
        raise Exception("Não foi possível conectar ao banco de dados.")
    
    cursor = conexao.cursor()
    try:
        cursor.execute("""
            UPDATE responsaveis_aluno 
            SET nome_completo = %s, 
                grau_parentesco = %s, 
                telefone = %s, 
                email = %s, 
                local_trabalho = %s, 
                telefone_trabalho = %s
            WHERE id = %s
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
        cursor.close()
        conexao.close()


def deletar_responsavel(resp_id):
    """Remove um responsável da tabela responsaveis_aluno pelo ID."""
    conexao = obter_conexao()
    if not conexao:
        raise Exception("Não foi possível conectar ao banco de dados.")
        
    cursor = conexao.cursor()
    try:
        cursor.execute("DELETE FROM responsaveis_aluno WHERE id = %s", (resp_id,))
        conexao.commit()
    except Exception as e:
        conexao.rollback()
        raise e
    finally:
        cursor.close()
        conexao.close()


if __name__ == "__main__":
    criar_estrutura_inicial()