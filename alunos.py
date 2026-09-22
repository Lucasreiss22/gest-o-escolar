import datetime
import re
from database import obter_conexao
from psycopg2.extras import RealDictCursor
from simples_nacional import _linhas_arquivo, parse_moeda_livre


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


def _sexo_normalizado(sexo_bruto):
    texto = (sexo_bruto or "").strip()
    if not texto:
        return None
    if texto.lower().startswith("fem"):
        return "F"
    if texto.lower().startswith("masc"):
        return "M"
    return texto[:1].upper()


def _turno_planilha(texto):
    bruto = (texto or "").strip().lower().replace("ã", "a").replace("é", "e").replace("í", "i")
    tokens = [parte.strip() for parte in re.split(r"[,;/|]+", bruto) if parte.strip()]
    achados = []
    for token in tokens:
        if token in ("manha", "matutino"):
            codigo = "manha"
        elif token in ("tarde", "vespertino"):
            codigo = "tarde"
        elif token in ("noite", "noturno"):
            codigo = "noite"
        elif token in ("hibrido", "hibrida", "integral"):
            codigo = "hibrido"
        else:
            continue
        if codigo not in achados:
            achados.append(codigo)
    if not achados:
        return "manha"
    conjunto = set(achados)
    if "hibrido" in conjunto or conjunto == {"manha", "tarde"}:
        return "hibrido"
    if conjunto == {"tarde", "noite"}:
        return "tarde_noite"
    if len(achados) > 1:
        return "hibrido"
    return achados[0]


def _vazio_para_nulo(valor):
    texto = str(valor or "").strip()
    return texto or None


def _so_digitos(valor):
    return re.sub(r"\D", "", str(valor or ""))


def _mapa_turmas(cursor):
    cursor.execute("SELECT id, nome FROM turmas")
    mapa = {}
    for row in cursor.fetchall() or []:
        nome = str((row["nome"] if isinstance(row, dict) else row[1]) or "").strip().lower()
        tid = row["id"] if isinstance(row, dict) else row[0]
        if nome:
            mapa[nome] = tid
    return mapa


def _ids_turmas(texto, mapa):
    mapa = mapa or {}
    achados = []
    faltando = []
    for parte in re.split(r"[,;/|]+", str(texto or "")):
        chave = parte.strip().lower()
        if not chave:
            continue
        candidatos = [chave, chave.lstrip("0") or "0", chave.zfill(2)]
        tid = None
        for cand in candidatos:
            if cand in mapa:
                tid = mapa[cand]
                break
        if tid is None:
            digitos = _so_digitos(chave)
            for nome, valor in mapa.items():
                if digitos and _so_digitos(nome) == digitos:
                    tid = valor
                    break
        if tid and tid not in achados:
            achados.append(tid)
        elif tid is None:
            faltando.append(parte.strip())
    return achados, faltando


def _vincular_turma_id(cursor, turma_id, aluno_id):
    cursor.execute(
        """
        INSERT INTO turma_alunos (turma_id, aluno_id)
        VALUES (%s, %s)
        ON CONFLICT (turma_id, aluno_id) DO NOTHING
        """,
        (turma_id, aluno_id),
    )


def _vincular_turmas_texto(cursor, aluno_id, texto, mapa):
    ids, faltando = _ids_turmas(texto, mapa)
    for turma_id in ids:
        _vincular_turma_id(cursor, turma_id, aluno_id)
    return faltando


def _salvar_responsavel(cursor, aluno_id, tipo, responsavel):
    if not responsavel or not responsavel.get("nome_completo"):
        return
    cursor.execute(
        "SELECT id FROM responsaveis_aluno WHERE aluno_id = %s AND tipo_responsavel = %s LIMIT 1",
        (aluno_id, tipo),
    )
    existente = cursor.fetchone()
    valores = (
        responsavel["nome_completo"],
        _vazio_para_nulo(responsavel.get("cpf")) or "nao informado",
        responsavel.get("grau_parentesco") or "responsável",
        responsavel.get("telefone") or "(00) 0000-0000",
        _vazio_para_nulo(responsavel.get("email")),
        _vazio_para_nulo(responsavel.get("local_trabalho")),
        _vazio_para_nulo(responsavel.get("telefone_trabalho")),
    )
    if existente:
        resp_id = existente["id"] if isinstance(existente, dict) else existente[0]
        cursor.execute(
            """
            UPDATE responsaveis_aluno
            SET nome_completo = %s, cpf = %s, grau_parentesco = %s, telefone = %s, email = %s,
                local_trabalho = %s, telefone_trabalho = %s
            WHERE id = %s
            """,
            valores + (resp_id,),
        )
        return
    cursor.execute(
        """
        INSERT INTO responsaveis_aluno (
            aluno_id, tipo_responsavel, nome_completo, cpf, grau_parentesco,
            telefone, email, local_trabalho, telefone_trabalho, foto_url
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (aluno_id, tipo) + valores + (responsavel.get("foto_url"),),
    )


def _atualizar_aluno_planilha(cursor, aluno_id, dados_aluno, responsavel_1=None, responsavel_2=None):
    sexo = _sexo_normalizado(dados_aluno.get("sexo"))
    estado = (dados_aluno.get("estado") or "")[:2].upper() or None
    cursor.execute(
        """
        UPDATE alunos SET
            nome_completo = %s, rg = %s, data_nascimento = %s, sexo = %s,
            telefone_principal = %s, email = %s, cep = %s, rua = %s, numero = %s,
            bairro = %s, cidade = %s, estado = %s, valor_mensalidade = %s,
            contrato_meses = %s, contrato_inicio = COALESCE(%s::date, contrato_inicio),
            turnos_mensalidade = %s
        WHERE id = %s
        """,
        (
            dados_aluno["nome_completo"],
            _vazio_para_nulo(dados_aluno.get("rg")),
            dados_aluno.get("data_nascimento") or "2000-01-01",
            sexo,
            dados_aluno.get("telefone_principal") or "(00) 0000-0000",
            _vazio_para_nulo(dados_aluno.get("email")),
            _vazio_para_nulo(dados_aluno.get("cep")),
            _vazio_para_nulo(dados_aluno.get("rua")),
            _vazio_para_nulo(dados_aluno.get("numero")),
            _vazio_para_nulo(dados_aluno.get("bairro")),
            _vazio_para_nulo(dados_aluno.get("cidade")),
            estado,
            dados_aluno.get("valor_mensalidade", 0) or 0,
            dados_aluno.get("contrato_meses") or 12,
            dados_aluno.get("contrato_inicio") or None,
            dados_aluno.get("turnos_mensalidade") or "manha",
            aluno_id,
        ),
    )
    faltando = _vincular_turmas_texto(cursor, aluno_id, dados_aluno.get("turma_nome"), dados_aluno.get("_mapa_turmas"))
    _salvar_responsavel(cursor, aluno_id, 1, responsavel_1)
    _salvar_responsavel(cursor, aluno_id, 2, responsavel_2)
    return faltando


def _inserir_aluno(cursor, dados_aluno: dict, responsavel_1: dict = None, responsavel_2: dict = None):
    matricula = dados_aluno.get("matricula") or gerar_proxima_matricula(cursor)
    sexo = _sexo_normalizado(dados_aluno.get("sexo"))
    estado = (dados_aluno.get("estado") or "")[:2].upper() or None
    turma_id = dados_aluno.get("turma_id")

    cursor.execute(
        """
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
        """,
        (
            matricula,
            dados_aluno["nome_completo"],
            _vazio_para_nulo(dados_aluno.get("cpf")),
            _vazio_para_nulo(dados_aluno.get("rg")),
            _vazio_para_nulo(dados_aluno.get("certidao_nascimento")),
            dados_aluno.get("data_nascimento") or "2000-01-01",
            sexo,
            dados_aluno.get("telefone_principal") or "(00) 0000-0000",
            _vazio_para_nulo(dados_aluno.get("telefone_secundario")),
            _vazio_para_nulo(dados_aluno.get("email")),
            _vazio_para_nulo(dados_aluno.get("cep")),
            _vazio_para_nulo(dados_aluno.get("rua")),
            _vazio_para_nulo(dados_aluno.get("numero")),
            _vazio_para_nulo(dados_aluno.get("bairro")),
            _vazio_para_nulo(dados_aluno.get("cidade")),
            estado,
            dados_aluno.get("valor_mensalidade", 0.00) or 0,
            dados_aluno.get("desconto_tipo") or "nenhum",
            dados_aluno.get("desconto_valor", 0.00) or 0,
            dados_aluno.get("contrato_meses") or 12,
            dados_aluno.get("contrato_inicio") or None,
            dados_aluno.get("turnos_mensalidade") or "manha",
            dados_aluno.get("foto_url"),
        ),
    )
    resultado_aluno = cursor.fetchone()
    aluno_id = resultado_aluno["id"] if isinstance(resultado_aluno, dict) else resultado_aluno[0]

    if turma_id:
        _vincular_turma_id(cursor, turma_id, aluno_id)
    _vincular_turmas_texto(cursor, aluno_id, dados_aluno.get("turma_nome"), dados_aluno.get("_mapa_turmas"))
    _salvar_responsavel(cursor, aluno_id, 1, responsavel_1)
    _salvar_responsavel(cursor, aluno_id, 2, responsavel_2)
    return matricula, aluno_id


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
        matricula, _aluno_id = _inserir_aluno(cursor, dados_aluno, responsavel_1, responsavel_2)
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


def _celula(row, idx):
    if idx is None or idx >= len(row):
        return ""
    valor = row[idx]
    if valor is None:
        return ""
    if hasattr(valor, "strftime"):
        return valor.strftime("%Y-%m-%d")
    return str(valor).strip()


def _indice_coluna(cabecalho, *chaves):
    for chave in chaves:
        for i, nome in enumerate(cabecalho):
            if nome == chave:
                return i
    for chave in chaves:
        if len(chave) < 5:
            continue
        for i, nome in enumerate(cabecalho):
            if chave in nome:
                return i
    return None


def parse_data_livre(texto):
    if texto is None or str(texto).strip() == "":
        return None
    if hasattr(texto, "strftime"):
        return texto.strftime("%Y-%m-%d")
    s = str(texto).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.datetime.strptime(s[:10], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def importar_planilha_alunos(arquivo):
    linhas = _linhas_arquivo(arquivo)
    if not linhas:
        return []
    cab = [str(c or "").strip().lower().lstrip("\ufeff") for c in linhas[0]]
    col = {
        "nome": _indice_coluna(cab, "nome_completo", "nome do aluno", "aluno", "nome"),
        "nascimento": _indice_coluna(cab, "data_nascimento", "nascimento", "dt_nasc"),
        "cpf": _indice_coluna(cab, "cpf"),
        "rg": _indice_coluna(cab, "rg"),
        "sexo": _indice_coluna(cab, "sexo", "genero", "gênero"),
        "telefone": _indice_coluna(cab, "telefone_principal", "telefone", "celular", "whatsapp"),
        "email": _indice_coluna(cab, "email", "e-mail"),
        "cep": _indice_coluna(cab, "cep"),
        "rua": _indice_coluna(cab, "logradouro", "endereco", "endereço", "rua"),
        "numero": _indice_coluna(cab, "numero", "número"),
        "bairro": _indice_coluna(cab, "bairro"),
        "cidade": _indice_coluna(cab, "cidade"),
        "estado": _indice_coluna(cab, "estado", "uf"),
        "mensalidade": _indice_coluna(cab, "mensalidade", "valor_mensalidade", "valor"),
        "turno": _indice_coluna(cab, "turno", "turnos"),
        "contrato_meses": _indice_coluna(cab, "contrato_meses", "meses", "duracao", "duração"),
        "contrato_inicio": _indice_coluna(cab, "contrato_inicio", "inicio_contrato", "início"),
        "turma": _indice_coluna(cab, "turma", "serie", "série"),
        "resp1_nome": _indice_coluna(cab, "resp1_nome", "responsavel", "responsável", "mae", "mãe"),
        "resp1_cpf": _indice_coluna(cab, "resp1_cpf"),
        "resp1_parentesco": _indice_coluna(cab, "resp1_parentesco", "parentesco"),
        "resp1_telefone": _indice_coluna(cab, "resp1_telefone"),
        "resp1_email": _indice_coluna(cab, "resp1_email", "email_responsavel", "e-mail do responsável"),
    }
    if col["nome"] is None:
        raise ValueError("A planilha precisa de uma coluna de nome do aluno (nome ou nome_completo).")

    itens = []
    for row in linhas[1:]:
        if not row or not any(str(c).strip() for c in row if c is not None):
            continue
        nome = _celula(row, col["nome"])
        if not nome:
            continue
        itens.append({
            "aluno": {
                "nome_completo": nome,
                "cpf": _celula(row, col["cpf"]),
                "rg": _celula(row, col["rg"]),
                "data_nascimento": parse_data_livre(_celula(row, col["nascimento"])) or "2000-01-01",
                "sexo": _celula(row, col["sexo"]),
                "telefone_principal": _celula(row, col["telefone"]) or "(00) 0000-0000",
                "email": _celula(row, col["email"]),
                "cep": _celula(row, col["cep"]),
                "rua": _celula(row, col["rua"]),
                "numero": _celula(row, col["numero"]),
                "bairro": _celula(row, col["bairro"]),
                "cidade": _celula(row, col["cidade"]),
                "estado": _celula(row, col["estado"]),
                "valor_mensalidade": parse_moeda_livre(_celula(row, col["mensalidade"])),
                "contrato_meses": int(float(_celula(row, col["contrato_meses"]) or 12)),
                "contrato_inicio": parse_data_livre(_celula(row, col["contrato_inicio"])),
                "turnos_mensalidade": _turno_planilha(_celula(row, col["turno"])),
                "turma_nome": _celula(row, col["turma"]),
            },
            "resp1": {
                "nome_completo": _celula(row, col["resp1_nome"]),
                "cpf": _celula(row, col["resp1_cpf"]),
                "grau_parentesco": _celula(row, col["resp1_parentesco"]) or "responsável",
                "telefone": _celula(row, col["resp1_telefone"]),
                "email": _celula(row, col["resp1_email"]),
            } if _celula(row, col["resp1_nome"]) else None,
        })
    return itens


def _proximas_matriculas(cursor, quantidade):
    if quantidade <= 0:
        return []
    ano_atual = datetime.datetime.now().year
    cursor.execute(
        "SELECT matricula FROM alunos WHERE matricula LIKE %s ORDER BY matricula DESC LIMIT 1",
        (f"{ano_atual}%",),
    )
    ultimo = cursor.fetchone()
    sequencia = 1
    if ultimo:
        texto = str((ultimo["matricula"] if isinstance(ultimo, dict) else ultimo[0]) or "")
        if len(texto) >= 5:
            try:
                sequencia = int(texto[4:]) + 1
            except ValueError:
                sequencia = 1
    return [f"{ano_atual}{sequencia + i:03d}" for i in range(quantidade)]


def cadastrar_alunos_lote(itens):
    from database import garantir_tabelas_folha, garantir_tabelas_pedagogicas
    garantir_tabelas_folha()
    garantir_tabelas_pedagogicas()
    conexao = obter_conexao()
    if not conexao:
        raise Exception("Não foi possível estabelecer conexão com o banco de dados.")
    ok, erros, avisos = [], [], []
    cursor = None
    try:
        cursor = conexao.cursor(cursor_factory=RealDictCursor)
        mapa = _mapa_turmas(cursor)
        cursor.execute("SELECT id, matricula, cpf FROM alunos WHERE COALESCE(cpf, '') <> ''")
        por_cpf = {}
        for row in cursor.fetchall() or []:
            chave = _so_digitos(row["cpf"] if isinstance(row, dict) else row[2])
            if chave:
                por_cpf[chave] = row
        novos = 0
        for item in itens:
            dados = item.get("aluno") or {}
            if _so_digitos(dados.get("cpf")) not in por_cpf:
                novos += 1
        matriculas = _proximas_matriculas(cursor, novos)
        ponteiro = 0
        for i, item in enumerate(itens, start=2):
            dados = dict(item.get("aluno") or {})
            nome = (dados.get("nome_completo") or "").strip()
            if not nome:
                erros.append(f"Linha {i}: sem nome do aluno.")
                continue
            dados["_mapa_turmas"] = mapa
            try:
                cursor.execute("SAVEPOINT aluno_lote")
                existente = por_cpf.get(_so_digitos(dados.get("cpf")))
                if existente:
                    aluno_id = existente["id"] if isinstance(existente, dict) else existente[0]
                    matricula = existente["matricula"] if isinstance(existente, dict) else existente[1]
                    faltando = _atualizar_aluno_planilha(cursor, aluno_id, dados, item.get("resp1"), item.get("resp2"))
                    atualizado = True
                else:
                    dados["matricula"] = matriculas[ponteiro]
                    ponteiro += 1
                    matricula, aluno_id = _inserir_aluno(cursor, dados, item.get("resp1"), item.get("resp2"))
                    faltando = []
                    _, faltando = _ids_turmas(dados.get("turma_nome"), mapa)
                    atualizado = False
                    if _so_digitos(dados.get("cpf")):
                        por_cpf[_so_digitos(dados.get("cpf"))] = {"id": aluno_id, "matricula": matricula, "cpf": dados.get("cpf")}
                cursor.execute("RELEASE SAVEPOINT aluno_lote")
                if faltando:
                    avisos.append(f"Linha {i} ({nome}): turma não encontrada ({', '.join(faltando)}).")
                ok.append({
                    "matricula": matricula,
                    "aluno_id": aluno_id,
                    "aluno": dados,
                    "atualizado": atualizado,
                })
            except Exception as e:
                cursor.execute("ROLLBACK TO SAVEPOINT aluno_lote")
                erros.append(f"Linha {i} ({nome}): {e}")
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        if cursor:
            cursor.close()
        conexao.close()
    return ok, erros, avisos


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