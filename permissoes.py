"""Controle de acesso por perfil de usuário."""

PAPEIS_TOTAIS = {"admin", "administrador", "financeiro", "direcao", "administrativo", "supervisor"}

MODULOS = {
    "dashboard": PAPEIS_TOTAIS | {"secretaria", "professor", "funcionario"},
    "alunos": PAPEIS_TOTAIS | {"secretaria"},
    "professores": PAPEIS_TOTAIS | {"secretaria"},
    "pedagogico": PAPEIS_TOTAIS | {"secretaria", "professor"},
    "pedagogico_cadastro": PAPEIS_TOTAIS | {"secretaria"},
    "financeiro": PAPEIS_TOTAIS,
    "calendario": PAPEIS_TOTAIS | {"secretaria", "professor", "funcionario"},
    "configuracoes": PAPEIS_TOTAIS,
    "usuarios": {"admin", "administrador", "direcao", "supervisor", "financeiro"},
    "contracheque": PAPEIS_TOTAIS | {"professor", "funcionario", "secretaria"},
}

ENDPOINTS = {
    "dashboard": "dashboard",
    "pagina_alunos": "alunos",
    "cadastrar_aluno": "alunos",
    "cadastrar_aluno_rota": "alunos",
    "detalhes_aluno": "pedagogico",
    "editar_aluno": "alunos",
    "salvar_responsavel": "alunos",
    "adicionar_responsavel": "alunos",
    "excluir_aluno_rota": "alunos",
    "lancar_frequencia_aluno": "pedagogico",
    "pagina_professores": "professores",
    "cadastrar_professor": "professores",
    "excluir_professor": "professores",
    "detalhes_professor": "professores",
    "pagina_pedagogico": "pedagogico",
    "excluir_turma": "pedagogico_cadastro",
    "pagina_financeiro": "financeiro",
    "excluir_financeiro": "financeiro",
    "relatorio_tributario": "financeiro",
    "relatorio_pdf_folha": "financeiro",
    "relatorio_pdf_custos": "financeiro",
    "calendario_escolar": "calendario",
    "cadastrar_evento": "calendario",
    "pagina_configuracoes": "configuracoes",
    "excluir_usuario_sistema": "usuarios",
    "gerenciar_usuarios": "usuarios",
    "contracheque": "contracheque",
    "pdf_contracheque_rota": "contracheque",
    "enviar_contracheques_mes": "financeiro",
    "aluno_vincular_turma": "pedagogico_cadastro",
}


def normalizar_papel(papel):
    bruto = (papel or "admin").strip().lower()
    mapa = {
        "administrador": "admin",
        "administrativo": "financeiro",
        "supervisor": "supervisor",
        "supervisor administrativo": "supervisor",
        "direção": "direcao",
        "secretaria": "secretaria",
        "financeiro": "financeiro",
        "professor": "professor",
        "funcionario": "funcionario",
        "funcionário": "funcionario",
        "pai_mae": "funcionario",
        "aluno": "funcionario",
    }
    return mapa.get(bruto, bruto if bruto in {
        "admin", "financeiro", "secretaria", "professor", "funcionario", "direcao", "supervisor"
    } else "admin")


AREAS_ACESSO = [
    ("dashboard", "Painel"),
    ("alunos", "Alunos"),
    ("pedagogico", "Pedagógico (turmas, chamada e notas)"),
    ("pedagogico_cadastro", "Cadastrar turma e matrícula"),
    ("professores", "Equipe"),
    ("financeiro", "Financeiro"),
    ("calendario", "Calendário"),
    ("contracheque", "Contra-cheque"),
    ("configuracoes", "Configurações"),
    ("usuarios", "Usuários e permissões"),
]

ACOES_ACESSO = ("acessar", "ver", "alterar")

_POST_SO_LEITURA = {"pdf_contracheque_rota", "relatorio_pdf_consulta", "relatorio_tributario", "relatorio_pdf_custos"}


def pode_modulo(papel, modulo):
    papel_n = normalizar_papel(papel)
    permitidos = MODULOS.get(modulo, PAPEIS_TOTAIS)
    return papel_n in permitidos


def permissoes_padrao(papel):
    papel_n = normalizar_papel(papel)
    mapa = {}
    for area, _rotulo in AREAS_ACESSO:
        entra = papel_n == "admin" or pode_modulo(papel_n, area)
        altera = entra
        if area == "contracheque" and papel_n in {"professor", "funcionario", "secretaria"}:
            altera = False
        mapa[area] = {"acessar": entra, "ver": entra, "alterar": altera}
    return mapa


def ler_permissoes(bruto):
    if not bruto:
        return None
    if isinstance(bruto, dict):
        return bruto
    try:
        import json
        dados = json.loads(bruto)
        return dados if isinstance(dados, dict) else None
    except Exception:
        return None


def permissoes_efetivas(papel, salvo=None):
    base = permissoes_padrao(papel)
    dados = ler_permissoes(salvo)
    if not dados:
        return base
    for area, _rotulo in AREAS_ACESSO:
        item = dados.get(area) or {}
        for acao in ACOES_ACESSO:
            if acao in item:
                base[area][acao] = bool(item[acao])
        if base[area]["alterar"]:
            base[area]["ver"] = True
            base[area]["acessar"] = True
        elif base[area]["ver"]:
            base[area]["acessar"] = True
    return base


def padroes_por_papel():
    return {papel: permissoes_padrao(papel) for papel in (
        "admin", "supervisor", "financeiro", "direcao", "secretaria", "professor", "funcionario"
    )}


def pode_acao(papel, modulo, acao="acessar", salvo=None):
    if normalizar_papel(papel) == "admin":
        return True
    bloco = permissoes_efetivas(papel, salvo).get(modulo) or {}
    if acao == "alterar":
        return bool(bloco.get("alterar"))
    if acao == "ver":
        return bool(bloco.get("ver") or bloco.get("acessar"))
    return bool(bloco.get("acessar") or bloco.get("ver"))


def pode_endpoint(papel, endpoint):
    if not endpoint:
        return True
    modulo = ENDPOINTS.get(endpoint)
    if not modulo:
        return True
    return pode_modulo(papel, modulo)


def pode_requisicao(papel, endpoint, metodo, salvo=None):
    if not endpoint:
        return True
    modulo = ENDPOINTS.get(endpoint)
    if not modulo:
        return True
    acao = "acessar"
    if (metodo or "GET").upper() == "POST" and endpoint not in _POST_SO_LEITURA:
        acao = "alterar"
    return pode_acao(papel, modulo, acao, salvo)


def rotulo_papel(papel):
    mapa = {
        "admin": "Administrador",
        "financeiro": "Financeiro / Administrativo",
        "supervisor": "Supervisor Administrativo",
        "direcao": "Direção",
        "secretaria": "Secretaria",
        "professor": "Professor",
        "funcionario": "Funcionário",
    }
    return mapa.get(normalizar_papel(papel), papel or "-")


CARGOS_ESCOLA = [
    (
        "Direção e gestão",
        [
            "Diretor(a)",
            "Vice-diretor(a)",
            "Diretor(a) adjunto(a)",
            "Coordenador(a) pedagógico(a)",
            "Coordenador(a) de turno",
            "Coordenador(a) de educação infantil",
            "Supervisor(a) pedagógico(a)",
            "Orientador(a) educacional",
            "Secretário(a) escolar",
            "Auxiliar de secretaria",
            "Administrador(a)",
            "Administrativo",
            "Financeiro",
            "Recursos humanos",
            "Assistente administrativo",
        ],
    ),
    (
        "Docência",
        [
            "Professor(a)",
            "Professor(a) de educação infantil",
            "Professor(a) de ensino fundamental",
            "Professor(a) de educação física",
            "Professor(a) de artes",
            "Professor(a) de música",
            "Professor(a) de inglês",
            "Professor(a) de espanhol",
            "Professor(a) de informática",
            "Professor(a) de reforço",
            "Professor(a) substituto(a)",
            "Auxiliar",
            "Auxiliar de classe",
            "Auxiliar de creche",
            "Monitor(a) de turma",
            "Estagiário(a) docente",
        ],
    ),
    (
        "Apoio pedagógico",
        [
            "Psicopedagogo(a)",
            "Psicólogo(a) escolar",
            "Fonoaudiólogo(a)",
            "Assistente social",
            "Intérprete de Libras",
            "Cuidador(a)",
            "Auxiliar de inclusão",
            "Bibliotecário(a)",
        ],
    ),
    (
        "Alimentação",
        [
            "Nutricionista",
            "Cozinheiro(a)",
            "Auxiliar de cozinha",
            "Merendeiro(a)",
        ],
    ),
    (
        "Operacional e apoio",
        [
            "Porteiro(a)",
            "Recepcionista",
            "Inspetor(a) de alunos",
            "Zelador(a)",
            "Auxiliar de limpeza",
            "Serviços gerais",
            "Motorista",
            "Monitor(a) de transporte",
            "Técnico(a) de informática",
            "Manutenção",
            "Jardineiro(a)",
            "Estagiário(a)",
            "Voluntário(a)",
            "Prestador(a) de serviço",
        ],
    ),
]


def cargos_escola_planos():
    itens = []
    for _grupo, cargos in CARGOS_ESCOLA:
        itens.extend(cargos)
    return itens
