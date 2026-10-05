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
    "rescisao": PAPEIS_TOTAIS | {"financeiro"},
    "auditoria": {"admin", "administrador", "direcao", "supervisor"},
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
    "sala_professor_editar": "pedagogico",
    "prova_pdf": "pedagogico",
    "prova_notas_pdf": "pedagogico",
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
    "relatorio_dre": "financeiro",
    "lucro_real_ajuste_salvar": "financeiro",
    "lucro_real_ajuste_excluir": "financeiro",
    "relatorio_cartao_financeiro": "financeiro",
    "relatorio_pdf_folha": "financeiro",
    "relatorio_pdf_custos": "financeiro",
    "relatorio_pdf_rescisoes": "financeiro",
    "rescisao_pdf": "rescisao",
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
    "ficha_pedagogica_pdf": "pedagogico",
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
    "fechar_competencia_folha": "financeiro",
    "reabrir_competencia_folha": "financeiro",
    "ponto": "ponto",
    "ponto_gestao": "ponto",
    "ponto_relatorio_pdf": "ponto",
    "atestado_ponto": "ponto",
    "pagina_rescisao": "rescisao",
    "rescisao_calcular": "rescisao",
    "rescisao_confirmar": "rescisao",
    "rescisao_recontratar": "rescisao",
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
    """Papel vazio ou desconhecido cai no perfil mais restrito (funcionário), nunca em admin."""
    bruto = (papel or "").strip().lower()
    mapa = {
        "administrador": "admin",
        "plataforma": "admin",
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
    } else "funcionario")


AREAS_ACESSO = [
    ("dashboard", "Painel"),
    ("alunos", "Alunos"),
    ("pedagogico", "Pedagógico — visão, chamada e notas"),
    ("pedagogico_cadastro", "Pedagógico — turmas, matérias e matrículas"),
    ("professores", "Equipe"),
    ("financeiro", "Financeiro"),
    ("calendario", "Calendário / chamada"),
    ("contracheque", "Contra-cheque"),
    ("ponto", "Ponto (bater e ver)"),
    ("rescisao", "Rescisão contratual"),
    ("configuracoes", "Configurações"),
    ("usuarios", "Usuários e permissões"),
    ("auditoria", "Auditoria"),
    ("nfse", "Notas fiscais (NFS-e)"),
]

# Agrupa a matriz de permissões na tela de configurações
AREAS_GRUPOS = [
    ("Menu e painel", ["dashboard"]),
    ("Alunos e pedagógico", ["alunos", "pedagogico", "pedagogico_cadastro", "calendario"]),
    ("Equipe e ponto", ["professores", "ponto", "contracheque", "rescisao"]),
    ("Financeiro e notas", ["financeiro", "nfse"]),
    ("Administração", ["configuracoes", "usuarios", "auditoria"]),
]

ACOES_ACESSO = ("acessar", "ver", "alterar", "excluir")

ACOES_ROTULO = {
    "acessar": "Acessar aba",
    "ver": "Ver / consultar",
    "alterar": "Alterar / incluir",
    "excluir": "Excluir",
}

ACOES_HINT = {
    "acessar": "Mostra a tela no menu e permite abrir a aba.",
    "ver": "Consulta dados sem editar (listas, painéis, detalhes).",
    "alterar": "Cria e edita registros nessa tela.",
    "excluir": "Apaga registros ou desfaz vínculos nessa tela.",
}

# Sub-ações finas (Alunos, Pedagógico e aprovação de ponto)
SUBACOES = {
    "alunos": (
        ("pdf", "Gerar PDF cadastral / lista"),
    ),
    "pedagogico": (
        ("notas", "Lançar / ajustar notas"),
        ("chamada", "Marcar presença e faltas"),
        ("boletim", "Gerar boletim PDF"),
        ("ficha", "Gerar ficha pedagógica PDF"),
    ),
    "ponto": (
        ("aprovar_retroativo", "Aprovar ponto retroativo e correções"),
    ),
}

SUBACOES_ROTULO = {
    area: {codigo: rotulo for codigo, rotulo in itens}
    for area, itens in SUBACOES.items()
}

SUBACOES_HINT = {
    "pdf": "Lista de alunos ou ficha cadastral pela aba Alunos.",
    "notas": "Incluir e ajustar notas e provas no pedagógico.",
    "chamada": "Registrar presença, falta ou justificativa.",
    "boletim": "Baixar ou enviar o boletim em PDF.",
    "ficha": "Ficha pedagógica simplificada ou completa (sem cadastro sensível).",
    "aprovar_retroativo": (
        "Aprova ou rejeita batidas de dias anteriores e correções de ponto. "
        "Sem essa permissão o pedido não entra no ponto nem no contra-cheque."
    ),
}

TELAS_PLANO = [
    ("alunos", "Alunos"),
    ("pedagogico", "Pedagógico (visão geral)"),
    ("pedagogico_cadastro", "Função: turmas e matrículas"),
    ("professores", "Equipe"),
    ("financeiro", "Financeiro"),
    ("nfse", "Função: notas fiscais (NFS-e)"),
    ("calendario", "Calendário / chamada"),
    ("contracheque", "Contra-cheque"),
    ("ponto", "Ponto"),
    ("rescisao", "Rescisão / recontratação"),
    ("auditoria", "Auditoria"),
]

MODULO_PARA_TELA = {
    "dashboard": None,
    "configuracoes": None,
    "usuarios": None,
    "alunos": "alunos",
    "pedagogico": "pedagogico",
    "pedagogico_cadastro": "pedagogico_cadastro",
    "professores": "professores",
    "financeiro": "financeiro",
    "calendario": "calendario",
    "contracheque": "contracheque",
    "ponto": "ponto",
    "nfse": "nfse",
    "auditoria": "auditoria",
    "rescisao": "rescisao",
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
        ["alunos", "pedagogico", "pedagogico_cadastro", "professores", "calendario"],
    ),
    (
        "completo",
        "Completo",
        "Todas as telas e funções do sistema.",
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
    "ficha_pedagogica_pdf": "pedagogico",
    "ajustar_contracheque": "contracheque",
    "pagina_notas_fiscais": "nfse",
    "nfse_emitir": "nfse",
    "nfse_cancelar": "nfse",
    "nfse_substituir": "nfse",
    "nfse_consultar": "nfse",
    "nfse_lote": "nfse",
    "nfse_xml": "nfse",
    "nfse_danfse": "nfse",
    "pagina_auditoria": "auditoria",
    "relatorio_auditoria_pdf": "auditoria",
    "ponto": "ponto",
    "ponto_gestao": "ponto",
    "pagina_rescisao": "rescisao",
    "rescisao_recontratar": "rescisao",
}

_POST_SO_LEITURA = {
    "pdf_contracheque_rota",
    "relatorio_pdf_consulta",
    "relatorio_tributario",
    "relatorio_pdf_custos",
    "relatorio_pdf_rescisoes",
    "rescisao_pdf",
    "boletim_pdf",
    "ficha_pedagogica_pdf",
}

_ENDPOINTS_EXCLUIR = {
    "excluir_aluno_rota": "alunos",
    "excluir_professor": "professores",
    "excluir_turma": "pedagogico_cadastro",
    "excluir_financeiro": "financeiro",
    "lucro_real_ajuste_excluir": "financeiro",
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

# (endpoint, acao_form ou "") -> (sub_acao, modulo)
_SUBACAO_REQ = {
    ("adicionar_nota", ""): ("notas", "pedagogico"),
    ("ajustar_prova_aluno", ""): ("notas", "pedagogico"),
    ("anexar_boletim", ""): ("boletim", "pedagogico"),
    ("boletim_pdf", ""): ("boletim", "pedagogico"),
    ("ficha_pedagogica_pdf", ""): ("ficha", "pedagogico"),
    ("relatorio_alunos_pdf", ""): ("pdf", "alunos"),
    ("lancar_frequencia_aluno", ""): ("chamada", "pedagogico"),
    ("pagina_pedagogico", "marcar_presenca"): ("chamada", "pedagogico"),
    ("pagina_pedagogico", "marcar_presenca_aluno"): ("chamada", "pedagogico"),
    ("pagina_pedagogico", "marcar_presenca_turma"): ("chamada", "pedagogico"),
    ("pagina_pedagogico", "marcar_presenca_lote"): ("chamada", "pedagogico"),
    ("pagina_pedagogico", "lancar_frequencia"): ("chamada", "pedagogico"),
    ("pagina_pedagogico", "adicionar_nota"): ("notas", "pedagogico"),
    ("pagina_pedagogico", "ajustar_nota"): ("notas", "pedagogico"),
    ("calendario_escolar", "marcar_presenca"): ("chamada", "pedagogico"),
    ("calendario_escolar", "lancar_frequencia"): ("chamada", "pedagogico"),
    ("ponto", "aprovar_ponto_retroativo"): ("aprovar_retroativo", "ponto"),
    ("ponto", "rejeitar_ponto_retroativo"): ("aprovar_retroativo", "ponto"),
    ("ponto", "solicitar_correcao_ponto"): ("aprovar_retroativo", "ponto"),
}


def pode_modulo(papel, modulo):
    papel_n = normalizar_papel(papel)
    permitidos = MODULOS.get(modulo, PAPEIS_TOTAIS)
    return papel_n in permitidos


def _subs_padrao(area, papel_n, entra):
    """Defaults das sub-ações por área/papel."""
    itens = SUBACOES.get(area) or ()
    if not itens:
        return {}
    if not entra:
        return {codigo: False for codigo, _r in itens}
    # Professor: pedagógico completo nas sub-ações; sem alunos.pdf
    if area == "pedagogico":
        ligar = entra  # quem acessa pedagógico por padrão pode notas/chamada/pdfs
        if papel_n == "funcionario":
            ligar = False
        return {codigo: ligar for codigo, _r in itens}
    if area == "alunos":
        # PDF cadastral: secretaria e gestão
        ligar = papel_n in {"admin", "supervisor", "financeiro", "direcao", "secretaria"}
        return {codigo: ligar for codigo, _r in itens}
    if area == "ponto":
        # Admin e secretaria aprovam por padrão. Os demais recebem o flag na matriz.
        aprova = papel_n in {"admin", "secretaria"}
        return {codigo: aprova for codigo, _r in itens}
    return {codigo: False for codigo, _r in itens}


def permissoes_padrao(papel):
    papel_n = normalizar_papel(papel)
    mapa = {}
    for area, _rotulo in AREAS_ACESSO:
        entra = papel_n == "admin" or pode_modulo(papel_n, area)
        altera = entra
        if area == "contracheque" and papel_n in {"professor", "funcionario", "secretaria"}:
            altera = False
        if area == "auditoria":
            altera = False
        gestao = papel_n in {"admin", "supervisor", "financeiro", "direcao"}
        mapa[area] = {
            "acessar": entra,
            "ver": entra,
            "alterar": altera and area not in {"auditoria", "dashboard"},
            "excluir": altera and gestao and area not in {"auditoria", "dashboard", "contracheque"},
        }
        if area == "dashboard":
            mapa[area]["alterar"] = False
            mapa[area]["excluir"] = False
        mapa[area].update(_subs_padrao(area, papel_n, entra))
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


def _chaves_area(area):
    chaves = list(ACOES_ACESSO)
    for codigo, _rotulo in SUBACOES.get(area) or ():
        chaves.append(codigo)
    return chaves


def permissoes_efetivas(papel, salvo=None):
    base = permissoes_padrao(papel)
    dados = ler_permissoes(salvo)
    if not dados:
        return base
    for area, _rotulo in AREAS_ACESSO:
        item = dados.get(area) or {}
        for chave in _chaves_area(area):
            if chave in item:
                base[area][chave] = bool(item[chave])
        # Cascade: alterar/excluir ⇒ ver+acessar; ver ⇒ acessar.
        # Acessar sozinho NÃO implica ver.
        if base[area].get("excluir") or base[area].get("alterar"):
            base[area]["ver"] = True
            base[area]["acessar"] = True
        elif base[area].get("ver"):
            base[area]["acessar"] = True
        # Sub-ações exigem ver
        for codigo, _r in SUBACOES.get(area) or ():
            if base[area].get(codigo) and not base[area].get("ver"):
                base[area][codigo] = False
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
        return bool(bloco.get("ver"))
    if acao in (SUBACOES_ROTULO.get(modulo) or {}):
        return bool(bloco.get("ver") and bloco.get(acao))
    # acessar: só o flag acessar (menu / abrir aba)
    return bool(bloco.get("acessar"))


def pode_subacao(papel, modulo, sub, salvo=None):
    """Consulta uma sub-ação fina (notas, chamada, boletim, ficha, pdf…)."""
    if normalizar_papel(papel) == "admin":
        return True
    bloco = permissoes_efetivas(papel, salvo).get(modulo) or {}
    if not bloco.get("ver"):
        return False
    return bool(bloco.get(sub))


def pode_endpoint(papel, endpoint):
    if not endpoint:
        return True
    modulo = ENDPOINTS.get(endpoint)
    if not modulo:
        return True
    return pode_modulo(papel, modulo)


def classificar_requisicao(endpoint, metodo, acao_form=None):
    """
    Retorna (acao, modulo).
    Para sub-ações, acao é o código da sub (notas, chamada, …).
    GET de conteúdo sensível (boletim/ficha) também usa sub-ação.
    """
    chave = (endpoint or "", acao_form or "")
    if chave in _SUBACAO_REQ:
        sub, modulo = _SUBACAO_REQ[chave]
        return sub, modulo
    if endpoint in _SUBACAO_REQ:
        sub, modulo = _SUBACAO_REQ[(endpoint, "")]
        return sub, modulo
    metodo_u = (metodo or "GET").upper()
    if metodo_u == "POST" and endpoint not in _POST_SO_LEITURA:
        if endpoint in _ENDPOINTS_EXCLUIR:
            return "excluir", _ENDPOINTS_EXCLUIR[endpoint]
        if chave in _FORM_EXCLUIR:
            return "excluir", _FORM_EXCLUIR[chave]
        if chave in _FORM_CADASTRO:
            return "alterar", _FORM_CADASTRO[chave]
        return "alterar", ENDPOINTS.get(endpoint)
    # GET: abrir aba = acessar; conteúdo de consulta é checado na view com pode_ver
    return "acessar", ENDPOINTS.get(endpoint)


def modulo_no_plano(modulo, telas):
    if not isinstance(telas, (list, tuple, set)):
        return True
    tela = MODULO_PARA_TELA.get(modulo)
    if tela is None:
        return True
    if tela in telas:
        return True
    if tela.startswith("pedagogico") and "pedagogico" in telas:
        return True
    if tela == "nfse" and "financeiro" in telas:
        return True
    if tela == "rescisao" and ("professores" in telas or "financeiro" in telas):
        return True
    return False


_SALA_PROFESSOR = {
    "sala_professor",
    "sala_professor_nova",
    "sala_professor_enviar_pdf",
    "sala_professor_detalhe",
    "sala_professor_editar",
    "prova_pdf",
    "prova_notas_pdf",
    "arquivo_professor",
    "pasta_professor_pdf",
}


def endpoint_no_plano(endpoint, telas, acao_form=None):
    if not isinstance(telas, (list, tuple, set)):
        return True
    if endpoint in _SALA_PROFESSOR:
        return "pedagogico" in telas or "pedagogico_cadastro" in telas
    if endpoint == "detalhes_aluno":
        return "alunos" in telas or "pedagogico" in telas
    if endpoint == "ficha_pedagogica_pdf":
        return "pedagogico" in telas
    # Usa as mesmas regras/fallbacks de modulo_no_plano (ex.: rescisão com equipe/financeiro)
    if endpoint in _TELA_EXTRA:
        return modulo_no_plano(_TELA_EXTRA[endpoint], telas)
    _tipo, modulo = classificar_requisicao(endpoint, "GET", acao_form)
    if not modulo:
        return True
    return modulo_no_plano(modulo, telas)


def pode_requisicao(papel, endpoint, metodo, salvo=None, acao_form=None):
    if not endpoint:
        return True
    # Tela Pedagógico é uma só: visão OU cadastro de turmas basta para abrir
    if endpoint == "pagina_pedagogico" and (metodo or "GET").upper() == "GET":
        return (
            pode_acao(papel, "pedagogico", "acessar", salvo)
            or pode_acao(papel, "pedagogico_cadastro", "acessar", salvo)
        )
    # Minhas provas: área própria do professor (provas e notas das turmas dele)
    if endpoint in _SALA_PROFESSOR:
        return (
            normalizar_papel(papel) == "professor"
            or pode_acao(papel, "pedagogico", "acessar", salvo)
            or pode_acao(papel, "pedagogico_cadastro", "acessar", salvo)
        )
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
            "Jovem aprendiz",
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
