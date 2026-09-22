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
    "calendario_escolar": "calendario",
    "cadastrar_evento": "calendario",
    "pagina_configuracoes": "configuracoes",
    "excluir_usuario_sistema": "usuarios",
    "gerenciar_usuarios": "usuarios",
    "contracheque": "contracheque",
    "pdf_contracheque_rota": "contracheque",
    "enviar_contracheques_mes": "financeiro",
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


def pode_modulo(papel, modulo):
    papel_n = normalizar_papel(papel)
    permitidos = MODULOS.get(modulo, PAPEIS_TOTAIS)
    return papel_n in permitidos


def pode_endpoint(papel, endpoint):
    if not endpoint:
        return True
    modulo = ENDPOINTS.get(endpoint)
    if not modulo:
        return True
    return pode_modulo(papel, modulo)


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
