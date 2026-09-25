import re
import psycopg2
import psycopg2.extras
from contextvars import ContextVar
from urllib.parse import unquote, urlparse

from config import carregar_config

_tenant_db = ContextVar("tenant_db", default=None)


def definir_banco_escola(db_nome):
    return _tenant_db.set(db_nome)


def limpar_banco_escola(token):
    _tenant_db.reset(token)


def resetar_tenant():
    _tenant_db.set(None)


def nome_banco_master():
    cfg = carregar_config()
    dsn = (cfg.get("DATABASE_URL") or "").strip()
    if dsn:
        if dsn.startswith("postgres://"):
            dsn = "postgresql://" + dsn[len("postgres://"):]
        caminho = dsn.split("?", 1)[0]
        nome = caminho.rsplit("/", 1)[-1].strip()
        if nome:
            return nome
    return cfg["DB_NAME"]


def _nome_banco_atual(master=False):
    if master:
        return nome_banco_master()
    tenant = _tenant_db.get()
    if tenant:
        return tenant
    try:
        from flask import has_request_context, session
        if has_request_context() and not session.get("super_admin"):
            return session.get("escola_db")
    except Exception:
        pass
    return None


ultimo_erro_pg = ""


def erro_conexao_atual():
    return ultimo_erro_pg


_params_pg = None
_raw_pg = None
_tabelas_ok = set()


class _ConexaoReuso:
    """close() devolve a conexão ao worker em vez de derrubar o SSL com o Supabase."""

    def __init__(self, raw):
        self._raw = raw

    def cursor(self, *args, **kwargs):
        return self._raw.cursor(*args, **kwargs)

    def commit(self):
        return self._raw.commit()

    def rollback(self):
        try:
            return self._raw.rollback()
        except Exception:
            return None

    def close(self):
        try:
            self._raw.rollback()
        except Exception:
            pass

    def set_session(self, *args, **kwargs):
        return self._raw.set_session(*args, **kwargs)

    @property
    def autocommit(self):
        return self._raw.autocommit

    @autocommit.setter
    def autocommit(self, valor):
        self._raw.autocommit = valor

    @property
    def closed(self):
        return self._raw.closed


def _destino_postgres(dsn, dbname, sslmode):
    """Converte host Direct (IPv6) do Supabase para Session pooler (IPv4)."""
    global _params_pg
    if dsn.startswith("postgres://"):
        dsn = "postgresql://" + dsn[len("postgres://"):]
    parsed = urlparse(dsn)
    host = parsed.hostname or ""
    port = parsed.port or 5432
    user = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    ref_alias = {
        "yqkptzxrkfreisydyir": "yqkptzkxrklreisydyir",
    }
    if host.startswith("db.") and host.endswith(".supabase.co"):
        ref = host.split(".")[1]
        ref = ref_alias.get(ref, ref)
        host = "aws-0-sa-east-1.pooler.supabase.com"
        port = 5432
        if user == "postgres" or not user.startswith("postgres."):
            user = f"postgres.{ref}"
    if "yqkptzxrkfreisydyir" in (user or ""):
        user = user.replace("yqkptzxrkfreisydyir", "yqkptzkxrklreisydyir")
    return dict(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
        sslmode=sslmode or "require",
        cursor_factory=psycopg2.extras.RealDictCursor,
        connect_timeout=5,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=3,
    )


def host_postgres_configurado():
    cfg = carregar_config()
    dsn = cfg.get("DATABASE_URL") or ""
    if not dsn:
        return ""
    try:
        params = _destino_postgres(dsn, "postgres", "require")
        return params.get("host") or ""
    except Exception:
        return ""


def _schema_seguro(nome):
    texto = (nome or "").strip()
    if texto == "public" or re.fullmatch(r"[a-z][a-z0-9_]{0,62}", texto):
        return texto
    return ""


def _aplicar_schema(conexao, schema):
    nome = _schema_seguro(schema) or "public"
    with conexao.cursor() as cursor:
        if nome == "public":
            cursor.execute('SET search_path TO public')
        else:
            cursor.execute(f'SET search_path TO "{nome}", public')


def _params_conexao():
    global _params_pg
    if _params_pg:
        return dict(_params_pg)
    cfg = carregar_config()
    dsn = cfg.get("DATABASE_URL") or ""
    master_nome = nome_banco_master()
    if dsn:
        params = _destino_postgres(dsn, master_nome, cfg.get("DB_SSLMODE") or "require")
    else:
        params = dict(
            host=cfg["DB_HOST"],
            port=cfg["DB_PORT"],
            dbname=master_nome,
            user=cfg["DB_USER"],
            password=cfg["DB_PASSWORD"],
            sslmode=cfg.get("DB_SSLMODE") or "prefer",
            cursor_factory=psycopg2.extras.RealDictCursor,
            connect_timeout=5,
        )
    _params_pg = dict(params)
    return dict(params)


def obter_conexao_nova():
    """Conexão solta (CREATE/DROP SCHEMA). Quem chama precisa fechar de verdade."""
    return psycopg2.connect(**_params_conexao())


def obter_conexao(master=False):
    """Reusa uma conexão SSL por worker. Escola só troca o search_path."""
    global ultimo_erro_pg, _raw_pg
    ultimo_erro_pg = ""
    master_nome = nome_banco_master()
    if master:
        schema = "public"
    else:
        schema = _nome_banco_atual(master=False)
        if not schema:
            return None
        if not _schema_seguro(schema):
            print(f"Schema de escola inválido: {schema}")
            return None
    for _tentativa in (1, 2):
        try:
            if _raw_pg is None or _raw_pg.closed:
                _raw_pg = psycopg2.connect(**_params_conexao())
            try:
                _raw_pg.rollback()
            except Exception:
                pass
            _aplicar_schema(_raw_pg, schema)
            return _ConexaoReuso(_raw_pg)
        except Exception as erro:
            ultimo_erro_pg = str(erro)
            try:
                if _raw_pg:
                    _raw_pg.close()
            except Exception:
                pass
            _raw_pg = None
            if _tentativa == 2:
                print(f"Erro ao conectar ao PostgreSQL ({master_nome}/{schema}): {erro}")
                return None
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
            print(f"Erro ao criar tabelas: {e}")


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


def _log_db(msg):
    try:
        print(msg)
    except UnicodeEncodeError:
        print(str(msg).encode("ascii", "replace").decode("ascii"))


def _tabela_existe(cursor, tabela):
    cursor.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = current_schema() AND table_name = %s
        """,
        (tabela,),
    )
    return bool(cursor.fetchone())


def _mapa_colunas(cursor):
    cursor.execute(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = current_schema()
        """
    )
    mapa = {}
    for row in cursor.fetchall() or []:
        tabela = row["table_name"] if isinstance(row, dict) else row[0]
        coluna = row["column_name"] if isinstance(row, dict) else row[1]
        mapa.setdefault(tabela, set()).add(coluna)
    return mapa


def _garantir_coluna(cursor, tabela, coluna, spec, mapa=None):
    if mapa is None:
        if not _tabela_existe(cursor, tabela):
            return
        cursor.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = %s AND column_name = %s
            """,
            (tabela, coluna),
        )
        if cursor.fetchone():
            return
    else:
        if tabela not in mapa or coluna in mapa.get(tabela, ()):
            return
    cursor.execute(f'ALTER TABLE "{tabela}" ADD COLUMN {coluna} {spec}')
    if mapa is not None:
        mapa.setdefault(tabela, set()).add(coluna)


def garantir_tabelas_pedagogicas():
    """Cria tabelas de frequência, boletins anexos e vínculos de disciplina."""
    schema = _nome_banco_atual(master=False)
    if not schema:
        return
    chave = f"{schema}:ped"
    if chave in _tabelas_ok:
        return
    conexao = obter_conexao()
    if not conexao:
        return
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS turmas (
                    id SERIAL PRIMARY KEY,
                    nome VARCHAR(100) NOT NULL,
                    ano_letivo INT,
                    turno VARCHAR(20)
                );
                CREATE TABLE IF NOT EXISTS disciplinas (
                    id SERIAL PRIMARY KEY,
                    codigo VARCHAR(20),
                    nome VARCHAR(100) NOT NULL,
                    carga_horaria INT DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS frequencia (
                    id SERIAL PRIMARY KEY,
                    aluno_id INT REFERENCES alunos(id) ON DELETE CASCADE,
                    turma_id INT REFERENCES turmas(id) ON DELETE SET NULL,
                    data_aula DATE NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'presente',
                    disciplina VARCHAR(100),
                    observacao TEXT,
                    UNIQUE (aluno_id, data_aula)
                );

                CREATE TABLE IF NOT EXISTS boletins_anexos (
                    id SERIAL PRIMARY KEY,
                    aluno_id INT REFERENCES alunos(id) ON DELETE CASCADE,
                    trimestre SMALLINT,
                    descricao VARCHAR(150),
                    arquivo_pdf VARCHAR(255) NOT NULL,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS turma_disciplinas (
                    id SERIAL PRIMARY KEY,
                    turma_id INT REFERENCES turmas(id) ON DELETE CASCADE,
                    disciplina_id INT REFERENCES disciplinas(id) ON DELETE CASCADE,
                    UNIQUE (turma_id, disciplina_id)
                );

                CREATE TABLE IF NOT EXISTS provas_turma (
                    id SERIAL PRIMARY KEY,
                    turma_id INT REFERENCES turmas(id) ON DELETE CASCADE,
                    materia VARCHAR(100),
                    titulo VARCHAR(150) NOT NULL,
                    descricao TEXT,
                    data_prova DATE NOT NULL,
                    horario TIME,
                    trimestre SMALLINT,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS calendario_eventos (
                    id SERIAL PRIMARY KEY,
                    titulo VARCHAR(180),
                    descricao TEXT,
                    data_evento DATE,
                    tipo VARCHAR(40),
                    turma_id INT,
                    professor_id INT,
                    aluno_id INT,
                    horario TIME
                );
                """
            )
            mapa = _mapa_colunas(cursor)
            for tabela, coluna, spec in (
                ("turmas", "professor_responsavel_id", "INT"),
                ("turmas", "sala_id", "INT"),
                ("turmas", "ano_letivo", "INT"),
                ("turmas", "turno", "VARCHAR(20)"),
                ("funcionarios", "especialidade", "VARCHAR(150)"),
                ("funcionarios", "formacao", "VARCHAR(150)"),
                ("funcionarios", "ativo", "BOOLEAN DEFAULT TRUE"),
                ("funcionarios", "data_contratacao", "DATE"),
                ("funcionarios", "data_nascimento", "DATE"),
                ("funcionarios", "telefone", "VARCHAR(20)"),
                ("funcionarios", "salario", "NUMERIC(12,2) DEFAULT 0"),
                ("disciplinas", "tipo_frequencia", "VARCHAR(20) DEFAULT 'semanal'"),
                ("disciplinas", "aulas_semana", "INT DEFAULT 2"),
                ("disciplinas", "minutos_aula", "INT DEFAULT 60"),
                ("disciplinas", "vezes_mes", "INT DEFAULT 1"),
                ("disciplinas", "dias_semana", "VARCHAR(40) DEFAULT ''"),
                ("turma_disciplinas", "tipo_frequencia", "VARCHAR(20) DEFAULT 'semanal'"),
                ("turma_disciplinas", "aulas_semana", "INT DEFAULT 2"),
                ("turma_disciplinas", "minutos_aula", "INT DEFAULT 60"),
                ("turma_disciplinas", "vezes_mes", "INT DEFAULT 1"),
                ("turma_disciplinas", "dias_semana", "VARCHAR(40) DEFAULT ''"),
                ("disciplinas", "grade_json", "TEXT DEFAULT '[]'"),
                ("turma_disciplinas", "grade_json", "TEXT DEFAULT '[]'"),
                ("funcionarios", "foto_url", "VARCHAR(255)"),
            ):
                _garantir_coluna(cursor, tabela, coluna, spec, mapa)
            if "frequencia" in mapa:
                try:
                    cursor.execute("UPDATE frequencia SET disciplina = '' WHERE disciplina IS NULL;")
                except Exception:
                    pass
                cursor.execute(
                    """
                    SELECT 1 FROM pg_constraint WHERE conname = 'frequencia_aluno_dia_disc_key'
                    """
                )
                if not cursor.fetchone():
                    try:
                        cursor.execute(
                            """
                            ALTER TABLE frequencia
                            ADD CONSTRAINT frequencia_aluno_dia_disc_key
                            UNIQUE (aluno_id, data_aula, disciplina)
                            """
                        )
                    except Exception:
                        pass
            conexao.commit()
            _tabelas_ok.add(chave)
    except Exception as e:
        try:
            conexao.rollback()
        except Exception:
            pass
        _log_db(f"Erro ao garantir tabelas pedagogicas: {e}")
    finally:
        conexao.close()


def garantir_tabelas_folha():
    schema = _nome_banco_atual(master=False)
    if not schema:
        return
    chave = f"{schema}:folha:simples"
    if chave in _tabelas_ok:
        return
    conexao = obter_conexao()
    if not conexao:
        return
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS financeiro_custos (
                    id SERIAL PRIMARY KEY,
                    descricao VARCHAR(180) NOT NULL,
                    categoria VARCHAR(80) DEFAULT 'operacional',
                    valor NUMERIC(12,2) NOT NULL DEFAULT 0,
                    data_custo DATE NOT NULL DEFAULT CURRENT_DATE,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS financeiro_mensalidades (
                    id SERIAL PRIMARY KEY,
                    aluno_id INT,
                    descricao VARCHAR(255),
                    valor NUMERIC(12,2) DEFAULT 0,
                    data_vencimento DATE,
                    data_pagamento DATE,
                    forma_pagamento VARCHAR(40),
                    juros_percentual NUMERIC(8,4) DEFAULT 0,
                    juros_valor NUMERIC(12,2) DEFAULT 0,
                    multa_valor NUMERIC(12,2) DEFAULT 0,
                    status VARCHAR(30) DEFAULT 'Pendente',
                    turno VARCHAR(20),
                    parcela_contrato INT
                );
                CREATE TABLE IF NOT EXISTS folha_itens (
                    id SERIAL PRIMARY KEY,
                    funcionario_id INT,
                    competencia VARCHAR(7) NOT NULL,
                    tipo_contrato VARCHAR(30),
                    bruto NUMERIC(12,2) DEFAULT 0,
                    dsr NUMERIC(12,2) DEFAULT 0,
                    inss_funcionario NUMERIC(12,2) DEFAULT 0,
                    irrf NUMERIC(12,2) DEFAULT 0,
                    liquido NUMERIC(12,2) DEFAULT 0,
                    encargos NUMERIC(12,2) DEFAULT 0,
                    custo_escola NUMERIC(12,2) DEFAULT 0,
                    detalhes JSONB,
                    UNIQUE (funcionario_id, competencia)
                );
                CREATE TABLE IF NOT EXISTS folha_envios (
                    id SERIAL PRIMARY KEY,
                    funcionario_id INT,
                    competencia VARCHAR(7) NOT NULL,
                    enviado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (funcionario_id, competencia)
                );
                CREATE TABLE IF NOT EXISTS simples_competencias (
                    competencia VARCHAR(7) PRIMARY KEY,
                    receita_bruta NUMERIC(14,2) DEFAULT 0,
                    folha_encargos NUMERIC(14,2) DEFAULT 0,
                    origem VARCHAR(20) DEFAULT 'manual',
                    observacao VARCHAR(255),
                    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS folha_ajustes (
                    funcionario_id INT NOT NULL,
                    competencia VARCHAR(7) NOT NULL,
                    horas_extras NUMERIC(10,2) DEFAULT 0,
                    horas_extras_100 NUMERIC(10,2) DEFAULT 0,
                    valor_hora_extra NUMERIC(12,2) DEFAULT 0,
                    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (funcionario_id, competencia)
                );
                CREATE TABLE IF NOT EXISTS turma_alunos (
                    turma_id INT,
                    aluno_id INT,
                    UNIQUE (turma_id, aluno_id)
                );
                CREATE TABLE IF NOT EXISTS responsaveis_aluno (
                    id SERIAL PRIMARY KEY,
                    aluno_id INT,
                    tipo_responsavel SMALLINT,
                    nome_completo VARCHAR(150),
                    cpf VARCHAR(14),
                    grau_parentesco VARCHAR(50),
                    telefone VARCHAR(30),
                    email VARCHAR(150),
                    local_trabalho VARCHAR(150),
                    telefone_trabalho VARCHAR(30)
                );
                CREATE TABLE IF NOT EXISTS pessoas_autorizadas (
                    id SERIAL PRIMARY KEY,
                    aluno_id INT,
                    nome_completo VARCHAR(150),
                    cpf VARCHAR(14),
                    telefone VARCHAR(30),
                    vinculo VARCHAR(80),
                    endereco VARCHAR(255),
                    foto_url VARCHAR(255)
                );
                CREATE TABLE IF NOT EXISTS provas_notas (
                    id SERIAL PRIMARY KEY,
                    aluno_id INT,
                    turma_id INT,
                    materia VARCHAR(100),
                    trimestre SMALLINT,
                    titulo_avaliacao VARCHAR(150),
                    nota NUMERIC(6,2),
                    arquivo_pdf VARCHAR(255),
                    data_registro DATE DEFAULT CURRENT_DATE
                );
                """
            )
            mapa = _mapa_colunas(cursor)
            for tabela, coluna, spec in (
                ("funcionarios", "data_nascimento", "DATE"),
                ("funcionarios", "telefone", "VARCHAR(20)"),
                ("funcionarios", "email", "VARCHAR(150)"),
                ("funcionarios", "data_inicio_contrato", "DATE"),
                ("funcionarios", "data_fim_contrato", "DATE"),
                ("funcionarios", "dia_pagamento", "INT DEFAULT 5"),
                ("funcionarios", "horas_extras", "NUMERIC(10,2) DEFAULT 0"),
                ("funcionarios", "horas_extras_100", "NUMERIC(10,2) DEFAULT 0"),
                ("funcionarios", "valor_hora_extra", "NUMERIC(12,2) DEFAULT 0"),
                ("funcionarios", "enviar_contracheque", "BOOLEAN DEFAULT TRUE"),
                ("funcionarios", "salario", "NUMERIC(12,2) DEFAULT 0"),
                ("funcionarios", "tipo_contrato", "VARCHAR(30) DEFAULT 'clt_mensalista'"),
                ("funcionarios", "valor_hora", "NUMERIC(12,2) DEFAULT 0"),
                ("funcionarios", "horas_mes", "NUMERIC(10,2) DEFAULT 0"),
                ("funcionarios", "reter_federal", "BOOLEAN DEFAULT FALSE"),
                ("funcionarios", "reter_iss", "BOOLEAN DEFAULT FALSE"),
                ("funcionarios", "aliquota_iss", "NUMERIC(6,2) DEFAULT 5"),
                ("funcionarios", "usuario_id", "INT"),
                ("funcionarios", "rg", "VARCHAR(30)"),
                ("funcionarios", "cep", "VARCHAR(9)"),
                ("funcionarios", "rua", "VARCHAR(150)"),
                ("funcionarios", "numero", "VARCHAR(20)"),
                ("funcionarios", "bairro", "VARCHAR(100)"),
                ("funcionarios", "cidade", "VARCHAR(100)"),
                ("funcionarios", "estado", "CHAR(2)"),
                ("funcionarios", "banco", "VARCHAR(80)"),
                ("funcionarios", "agencia", "VARCHAR(20)"),
                ("funcionarios", "conta", "VARCHAR(30)"),
                ("funcionarios", "tipo_conta", "VARCHAR(20)"),
                ("funcionarios", "pix", "VARCHAR(120)"),
                ("funcionarios", "pis_nit", "VARCHAR(20)"),
                ("funcionarios", "cnpj", "VARCHAR(20)"),
                ("funcionarios", "cpf", "VARCHAR(14)"),
                ("alunos", "status", "VARCHAR(20) DEFAULT 'ativo'"),
                ("alunos", "situacao", "VARCHAR(20) DEFAULT 'ativo'"),
                ("alunos", "cpf", "VARCHAR(14)"),
                ("alunos", "rg", "VARCHAR(30)"),
                ("alunos", "certidao_nascimento", "VARCHAR(50)"),
                ("alunos", "data_nascimento", "DATE"),
                ("alunos", "sexo", "VARCHAR(20)"),
                ("alunos", "telefone_principal", "VARCHAR(30)"),
                ("alunos", "telefone_secundario", "VARCHAR(30)"),
                ("alunos", "valor_mensalidade", "NUMERIC(12,2) DEFAULT 0"),
                ("alunos", "desconto_tipo", "VARCHAR(20) DEFAULT 'nenhum'"),
                ("alunos", "desconto_valor", "NUMERIC(12,2) DEFAULT 0"),
                ("alunos", "foto_url", "VARCHAR(255)"),
                ("responsaveis_aluno", "foto_url", "VARCHAR(255)"),
                ("funcionarios", "foto_url", "VARCHAR(255)"),
                ("pessoas_autorizadas", "foto_url", "VARCHAR(255)"),
                ("alunos", "cep", "VARCHAR(9)"),
                ("alunos", "rua", "VARCHAR(150)"),
                ("alunos", "numero", "VARCHAR(20)"),
                ("alunos", "bairro", "VARCHAR(100)"),
                ("alunos", "cidade", "VARCHAR(100)"),
                ("alunos", "estado", "CHAR(2)"),
                ("alunos", "contrato_meses", "INT DEFAULT 12"),
                ("alunos", "contrato_inicio", "DATE"),
                ("alunos", "turnos_mensalidade", "VARCHAR(20) DEFAULT 'manha'"),
                ("financeiro_custos", "tipo", "VARCHAR(20) DEFAULT 'avista'"),
                ("financeiro_custos", "forma", "VARCHAR(30) DEFAULT 'dinheiro'"),
                ("financeiro_custos", "parcelas", "INT DEFAULT 1"),
                ("financeiro_custos", "parcela_num", "INT DEFAULT 1"),
                ("financeiro_custos", "grupo_id", "VARCHAR(40)"),
                ("financeiro_custos", "data_inicio", "DATE"),
                ("financeiro_custos", "data_fim", "DATE"),
                ("financeiro_custos", "valor_unitario", "NUMERIC(12,2) DEFAULT 0"),
                ("financeiro_custos", "valor_bruto", "NUMERIC(12,2) DEFAULT 0"),
                ("financeiro_custos", "prestador", "VARCHAR(180)"),
                ("financeiro_custos", "reter_federal", "BOOLEAN DEFAULT FALSE"),
                ("financeiro_custos", "reter_iss", "BOOLEAN DEFAULT FALSE"),
                ("financeiro_custos", "aliquota_iss", "NUMERIC(6,2) DEFAULT 5"),
                ("financeiro_custos", "federal_na_nota", "BOOLEAN DEFAULT TRUE"),
                ("financeiro_custos", "iss_na_nota", "BOOLEAN DEFAULT TRUE"),
                ("financeiro_custos", "irrf", "NUMERIC(12,2) DEFAULT 0"),
                ("financeiro_custos", "pis", "NUMERIC(12,2) DEFAULT 0"),
                ("financeiro_custos", "cofins", "NUMERIC(12,2) DEFAULT 0"),
                ("financeiro_custos", "csll", "NUMERIC(12,2) DEFAULT 0"),
                ("financeiro_custos", "iss", "NUMERIC(12,2) DEFAULT 0"),
                ("financeiro_custos", "ativo", "BOOLEAN DEFAULT TRUE"),
                ("financeiro_mensalidades", "turno", "VARCHAR(20)"),
                ("financeiro_mensalidades", "parcela_contrato", "INT"),
                ("financeiro_mensalidades", "data_pagamento", "DATE"),
                ("financeiro_mensalidades", "forma_pagamento", "VARCHAR(40)"),
                ("financeiro_mensalidades", "aluno_id", "INT"),
                ("financeiro_mensalidades", "descricao", "VARCHAR(255)"),
                ("financeiro_mensalidades", "valor", "NUMERIC(12,2) DEFAULT 0"),
                ("financeiro_mensalidades", "data_vencimento", "DATE"),
                ("financeiro_mensalidades", "status", "VARCHAR(30) DEFAULT 'Pendente'"),
                ("financeiro_mensalidades", "juros_percentual", "NUMERIC(8,4) DEFAULT 0"),
                ("financeiro_mensalidades", "juros_valor", "NUMERIC(12,2) DEFAULT 0"),
                ("financeiro_mensalidades", "multa_valor", "NUMERIC(12,2) DEFAULT 0"),
                ("configuracoes", "regime_apuracao", "VARCHAR(20) DEFAULT 'competencia'"),
                ("configuracoes", "nfse_token", "TEXT"),
                ("configuracoes", "nfse_ambiente", "VARCHAR(20) DEFAULT 'homologacao'"),
                ("configuracoes", "nfse_cnpj", "VARCHAR(20)"),
                ("configuracoes", "nfse_inscricao_municipal", "VARCHAR(40)"),
                ("configuracoes", "nfse_codigo_municipio", "VARCHAR(10)"),
                ("configuracoes", "nfse_item_lista", "VARCHAR(10) DEFAULT '08.01'"),
                ("configuracoes", "nfse_codigo_tributacao", "VARCHAR(20) DEFAULT '0801'"),
                ("configuracoes", "nfse_aliquota", "NUMERIC(6,2) DEFAULT 2"),
                ("configuracoes", "nfse_opcao_simples", "VARCHAR(2)"),
                ("configuracoes", "nfse_c_beneficio", "VARCHAR(20)"),
                ("configuracoes", "nfse_p_ibs", "NUMERIC(8,4) DEFAULT 0"),
                ("configuracoes", "nfse_p_cbs", "NUMERIC(8,4) DEFAULT 0"),
                ("configuracoes", "nfse_certificado_pfx", "BYTEA"),
                ("configuracoes", "nfse_certificado_nome", "VARCHAR(180)"),
                ("configuracoes", "nfse_certificado_senha", "VARCHAR(255)"),
                ("configuracoes", "smtp_host", "VARCHAR(120)"),
                ("configuracoes", "smtp_port", "INT DEFAULT 587"),
                ("configuracoes", "smtp_user", "VARCHAR(150)"),
                ("configuracoes", "smtp_password", "VARCHAR(255)"),
                ("configuracoes", "smtp_from", "VARCHAR(150)"),
                ("configuracoes", "smtp_tls", "BOOLEAN DEFAULT TRUE"),
                ("usuarios", "permissoes", "TEXT"),
            ):
                _garantir_coluna(cursor, tabela, coluna, spec, mapa)
            if "alunos" in mapa:
                try:
                    cursor.execute("ALTER TABLE alunos ALTER COLUMN sexo TYPE VARCHAR(20)")
                except Exception:
                    pass
                if "status" in mapa.get("alunos", ()):
                    cursor.execute(
                        """
                        UPDATE alunos
                        SET status = COALESCE(NULLIF(status, ''), 'ativo')
                        WHERE status IS NULL OR TRIM(status) = ''
                        """
                    )
            from nfse import garantir_tabela_escola
            garantir_tabela_escola(cursor)
            conexao.commit()
            _tabelas_ok.add(chave)
    except Exception as e:
        try:
            conexao.rollback()
        except Exception:
            pass
        _log_db(f"Erro ao garantir tabelas de folha: {e}")
    finally:
        conexao.close()


if __name__ == "__main__":
    criar_estrutura_inicial()
    garantir_tabelas_pedagogicas()
    garantir_tabelas_folha()
