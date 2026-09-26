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
    "ponto": PAPEIS_TOTAIS | {"professor", "funcionario", "secretaria"},
    "auditoria": {"admin"},
    "nfse": {"admin", "financeiro"},
}

ENDPOINTS = {
    "dashboard": "dashboard",
    "pagina_alunos": "alunos",
    "relatorio_alunos_pdf": "alunos",
    "cadastrar_aluno": "alunos",
    "cadastrar_aluno_rota": "alunos",
    "detalhes_aluno": "pedagogico",
    "editar_aluno": "alunos",
    "salvar_responsavel": "alunos",
    "adicionar_responsavel": "alunos",
    "excluir_aluno_rota": "alunos",
    "lancar_frequencia_aluno": "pedagogico",
    "pagina_professores": "professores",
    "relatorio_equipe_pdf": "professores",
    "sala_professor": "pedagogico",
    "sala_professor_nova": "pedagogico",
    "sala_professor_enviar_pdf": "pedagogico",
    "sala_professor_detalhe": "pedagogico",
    "prova_pdf": "pedagogico",
    "arquivo_professor": "pedagogico",
    "pasta_professor_pdf": "pedagogico",
    "relatorio_turmas_pdf": "pedagogico",
    "cadastrar_professor": "professores",
    "excluir_professor": "professores",
    "detalhes_professor": "professores",
    "pagina_pedagogico": "pedagogico",
    "excluir_turma": "pedagogico_cadastro",
    "pagina_financeiro": "financeiro",
    "excluir_financeiro": "financeiro",
    "relatorio_tributario": "financeiro",
    "relatorio_cartao_financeiro": "financeiro",
    "relatorio_pdf_folha": "financeiro",
    "relatorio_pdf_custos": "financeiro",
    "calendario_escolar": "calendario",
    "cadastrar_evento": "calendario",
    "relatorio_pdf_consulta": "calendario",
    "relatorio_pdf_periodo": "calendario",
    "pagina_configuracoes": "configuracoes",
    "excluir_usuario_sistema": "usuarios",
    "gerenciar_usuarios": "usuarios",
    "adicionar_autorizado": "alunos",
    "enviar_autorizacao_busca": "alunos",
    "adicionar_nota": "pedagogico",
    "boletim_pdf": "pedagogico",
    "anexar_boletim": "pedagogico",
    "ajustar_prova_aluno": "pedagogico",
    "modelo_alunos_csv": "alunos",
    "cobranca_pdf": "financeiro",
    "cobranca_email": "financeiro",
    "memoria_simples_pdf": "financeiro",
    "extrato_pgdas_pdf": "financeiro",
    "enviar_memoria_simples": "financeiro",
    "modelo_custos_csv": "financeiro",
    "modelo_simples_csv": "financeiro",
    "modelo_alunos_financeiro_csv": "financeiro",
    "ajustar_contracheque": "contracheque",
    "contracheque": "contracheque",
    "pdf_contracheque_rota": "contracheque",
    "enviar_contracheques_mes": "financeiro",
    "ponto": "ponto",
    "atestado_ponto": "ponto",
    "aluno_vincular_turma": "pedagogico_cadastro",
    "pagina_auditoria": "auditoria",
    "relatorio_auditoria_pdf": "auditoria",
    "pagina_notas_fiscais": "nfse",
    "nfse_emitir": "nfse",
    "nfse_cancelar": "nfse",
    "nfse_substituir": "nfse",
    "nfse_consultar": "nfse",
    "nfse_lote": "nfse",
    "nfse_xml": "nfse",
    "nfse_danfse": "nfse",
    "relatorio_nfse_pdf": "nfse",
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
    ("alunos", "Alunos (cadastro e exclusão)"),
    ("pedagogico", "Pedagógico (turmas, chamada e notas)"),
    ("pedagogico_cadastro", "Turmas e matrículas"),
    ("professores", "Equipe"),
    ("financeiro", "Financeiro"),
    ("calendario", "Calendário"),
    ("contracheque", "Contra-cheque"),
    ("ponto", "Ponto"),
    ("configuracoes", "Configurações"),
    ("usuarios", "Usuários e permissões"),
    ("nfse", "Notas fiscais"),
]

ACOES_ACESSO = ("acessar", "ver", "alterar", "excluir")

TELAS_PLANO = [
    ("alunos", "Alunos"),
    ("pedagogico", "Pedagógico"),
    ("professores", "Equipe"),
    ("financeiro", "Financeiro"),
    ("calendario", "Calendário"),
    ("contracheque", "Contra-cheque"),
]

MODULO_PARA_TELA = {
    "dashboard": None,
    "configuracoes": None,
    "usuarios": None,
    "alunos": "alunos",
    "pedagogico": "pedagogico",
    "pedagogico_cadastro": "pedagogico",
    "professores": "professores",
    "financeiro": "financeiro",
    "calendario": "calendario",
    "contracheque": "contracheque",
    "ponto": None,
    "nfse": "financeiro",
}

PACOTES_INICIAIS = [
    (
        "financeiro",
        "Financeiro",
        "Mensalidades, custos, tributos e contra-cheque.",
        ["financeiro", "contracheque"],
    ),
    (
        "pedagogico",
        "Pedagógico",
        "Alunos, turmas, chamada, equipe e calendário.",
        ["alunos", "pedagogico", "professores", "calendario"],
    ),
    (
        "completo",
        "Completo",
        "Todas as telas do sistema.",
        [codigo for codigo, _rotulo in TELAS_PLANO],
    ),
]

_TELA_EXTRA = {
    "cobranca_pdf": "financeiro",
    "cobranca_email": "financeiro",
    "memoria_simples_pdf": "financeiro",
    "extrato_pgdas_pdf": "financeiro",
    "enviar_memoria_simples": "financeiro",
    "modelo_custos_csv": "financeiro",
    "modelo_simples_csv": "financeiro",
    "modelo_alunos_financeiro_csv": "financeiro",
    "modelo_alunos_csv": "alunos",
    "adicionar_nota": "pedagogico",
    "boletim_pdf": "pedagogico",
    "anexar_boletim": "pedagogico",
    "ajustar_contracheque": "contracheque",
    "pagina_notas_fiscais": "financeiro",
    "nfse_emitir": "financeiro",
    "nfse_cancelar": "financeiro",
    "nfse_substituir": "financeiro",
    "nfse_consultar": "financeiro",
    "nfse_lote": "financeiro",
    "nfse_xml": "financeiro",
    "nfse_danfse": "financeiro",
}

_POST_SO_LEITURA = {"pdf_contracheque_rota", "relatorio_pdf_consulta", "relatorio_tributario", "relatorio_pdf_custos"}

_ENDPOINTS_EXCLUIR = {
    "excluir_aluno_rota": "alunos",
    "excluir_professor": "professores",
    "excluir_turma": "pedagogico_cadastro",
    "excluir_financeiro": "financeiro",
    "excluir_usuario_sistema": "usuarios",
}

_FORM_EXCLUIR = {
    ("pagina_alunos", "excluir_alunos"): "alunos",
    ("pagina_alunos", "deletar_autorizado"): "alunos",
    ("salvar_responsavel", "deletar_responsavel"): "alunos",
    ("pagina_pedagogico", "excluir_disciplina"): "pedagogico_cadastro",
    ("pagina_pedagogico", "excluir_disciplina_turma"): "pedagogico_cadastro",
    ("pagina_pedagogico", "desvincular_aluno"): "pedagogico_cadastro",
    ("aluno_vincular_turma", "desvincular"): "pedagogico_cadastro",
    ("gerenciar_usuarios", "excluir"): "usuarios",
}

_FORM_CADASTRO = {
    ("pagina_alunos", "editar_aluno"): "alunos",
    ("pagina_alunos", "editar_autorizado"): "alunos",
    ("pagina_alunos", "nao_autorizar_busca"): "alunos",
    ("pagina_alunos", "cadastrar_aluno"): "alunos",
    ("pagina_alunos", "importar_alunos"): "alunos",
    ("salvar_responsavel", "editar_responsavel"): "alunos",
    ("pagina_pedagogico", "criar_turma"): "pedagogico_cadastro",
    ("pagina_pedagogico", "nova_turma"): "pedagogico_cadastro",
    ("pagina_pedagogico", "vincular_aluno"): "pedagogico_cadastro",
    ("pagina_pedagogico", "incluir_aluno"): "pedagogico_cadastro",
    ("pagina_pedagogico", "criar_disciplina"): "pedagogico_cadastro",
    ("pagina_pedagogico", "criar_disciplina_turma"): "pedagogico_cadastro",
    ("pagina_pedagogico", "editar_disciplina"): "pedagogico_cadastro",
    ("pagina_pedagogico", "desativar_disciplina"): "pedagogico_cadastro",
    ("pagina_pedagogico", "ativar_disciplina"): "pedagogico_cadastro",
    ("pagina_pedagogico", "vincular_disciplina"): "pedagogico_cadastro",
    ("pagina_pedagogico", "criar_prova_turma"): "pedagogico_cadastro",
    ("aluno_vincular_turma", "vincular"): "pedagogico_cadastro",
}


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
        gestao = papel_n in {"admin", "supervisor", "financeiro", "direcao"}
        mapa[area] = {
            "acessar": entra,
            "ver": entra,
            "alterar": altera,
            "excluir": altera and gestao,
        }
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
        if base[area].get("excluir") or base[area]["alterar"]:
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
    if acao == "excluir":
        return bool(bloco.get("excluir"))
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


def classificar_requisicao(endpoint, metodo, acao_form=None):
    if (metodo or "GET").upper() == "POST" and endpoint not in _POST_SO_LEITURA:
        if endpoint in _ENDPOINTS_EXCLUIR:
            return "excluir", _ENDPOINTS_EXCLUIR[endpoint]
        chave = (endpoint, acao_form or "")
        if chave in _FORM_EXCLUIR:
            return "excluir", _FORM_EXCLUIR[chave]
        if chave in _FORM_CADASTRO:
            return "alterar", _FORM_CADASTRO[chave]
        return "alterar", ENDPOINTS.get(endpoint)
    return "acessar", ENDPOINTS.get(endpoint)


def modulo_no_plano(modulo, telas):
    if not isinstance(telas, (list, tuple, set)):
        return True
    tela = MODULO_PARA_TELA.get(modulo)
    if tela is None:
        return True
    return tela in telas


def endpoint_no_plano(endpoint, telas, acao_form=None):
    if not isinstance(telas, (list, tuple, set)):
        return True
    if endpoint == "detalhes_aluno":
        return "alunos" in telas or "pedagogico" in telas
    if endpoint in _TELA_EXTRA:
        return _TELA_EXTRA[endpoint] in telas
    _tipo, modulo = classificar_requisicao(endpoint, "GET", acao_form)
    if not modulo:
        return True
    return modulo_no_plano(modulo, telas)


def pode_requisicao(papel, endpoint, metodo, salvo=None, acao_form=None):
    if not endpoint:
        return True
    acao, modulo = classificar_requisicao(endpoint, metodo, acao_form)
    if not modulo:
        return True
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
