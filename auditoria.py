"""Registro do que foi incluído, alterado ou excluído no sistema."""

from datetime import datetime, timedelta, timezone

from database import obter_conexao_nova

_FUSO = timezone(timedelta(hours=-3))
_LIMITE = 300

_CAMPOS = (
    ("nome_completo", "Nome"),
    ("nome", "Nome"),
    ("aluno_nome", "Aluno"),
    ("nome_turma", "Turma"),
    ("turma_nome", "Turma"),
    ("nome_disciplina", "Matéria"),
    ("titulo", "Título"),
    ("titulo_prova", "Prova"),
    ("email", "E-mail"),
    ("email_admin", "E-mail"),
    ("descricao", "Descrição"),
    ("descricao_custo", "Descrição"),
    ("valor", "Valor"),
    ("valor_mensalidade", "Mensalidade"),
    ("status", "Status"),
    ("data_vencimento", "Vencimento"),
    ("data_pagamento", "Pagamento"),
    ("contrato_inicio", "Início"),
    ("pacote", "Pacote"),
    ("mes", "Mês"),
    ("aluno_id", "Aluno"),
    ("escola_id", "Escola"),
)

_SENSIVEL = ("senha", "password", "secret", "token", "codigo")

_ROTULOS = {
    "criar_cobranca": "Gerou cobrança",
    "editar_cobranca": "Alterou cobrança",
    "dar_baixa": "Deu baixa na cobrança",
    "dar_baixa_lote": "Deu baixa em lote",
    "tirar_baixa": "Retirou a baixa da cobrança",
    "tirar_baixa_lote": "Retirou a baixa em lote",
    "cadastrar_aluno": "Incluiu aluno",
    "cadastrar_aluno_simples": "Incluiu aluno",
    "importar_alunos": "Importou alunos",
    "importar_alunos_simples": "Importou alunos",
    "editar_aluno": "Alterou aluno",
    "excluir_aluno_rota": "Excluiu aluno",
    "deletar_responsavel": "Excluiu responsável",
    "deletar_autorizado": "Excluiu pessoa autorizada",
    "adicionar_responsavel": "Incluiu responsável",
    "salvar_responsavel": "Alterou responsável",
    "criar_turma": "Incluiu turma",
    "nova_turma": "Incluiu turma",
    "excluir_turma": "Excluiu turma",
    "desvincular_aluno": "Tirou aluno da turma",
    "vincular": "Vinculou aluno à turma",
    "criar_disciplina": "Incluiu matéria",
    "excluir_disciplina": "Excluiu matéria",
    "lancar_frequencia": "Lançou frequência",
    "adicionar_nota": "Incluiu nota",
    "anexar_boletim": "Anexou boletim",
    "criar_custo": "Incluiu custo",
    "excluir_custo": "Excluiu custo",
    "importar_custos": "Importou custos",
    "criar_escola": "Incluiu escola",
    "definir_pacote": "Alterou o pacote da escola",
    "salvar_pacote": "Alterou pacote",
    "salvar_cobranca_escola": "Alterou o desconto da escola",
    "gerar_assinaturas": "Gerou assinaturas do mês",
    "atualizar_abertas": "Atualizou assinaturas em aberto",
    "excluir_cobranca": "Excluiu assinatura",
    "redefinir_senha": "Redefiniu senha",
    "salvar_google": "Alterou o envio de e-mail",
    "pausar_escola": "Pausou escola",
    "reativar_escola": "Reativou escola",
    "excluir_escola": "Excluiu escola",
    "salvar_nfse": "Alterou a nota fiscal",
    "salvar_nfse_plataforma": "Alterou a nota fiscal da plataforma",
    "emitir_nfse_plataforma": "Emitiu NFS-e da licença",
    "cancelar_nfse_plataforma": "Cancelou NFS-e da licença",
    "substituir_nfse_plataforma": "Substituiu NFS-e da licença",
    "nfse_emitir": "Emitiu NFS-e",
    "nfse_cancelar": "Cancelou NFS-e",
    "nfse_substituir": "Substituiu NFS-e",
    "nfse_lote": "Emitiu NFS-e em lote",
}

_MODULOS = {
    "pagina_alunos": "Alunos",
    "detalhes_aluno": "Alunos",
    "salvar_responsavel": "Alunos",
    "adicionar_responsavel": "Alunos",
    "excluir_aluno_rota": "Alunos",
    "pagina_financeiro": "Financeiro",
    "excluir_financeiro": "Financeiro",
    "pagina_professores": "Equipe",
    "cadastrar_professor": "Equipe",
    "excluir_professor": "Equipe",
    "detalhes_professor": "Equipe",
    "pagina_pedagogico": "Pedagógico",
    "excluir_turma": "Pedagógico",
    "aluno_vincular_turma": "Pedagógico",
    "lancar_frequencia_aluno": "Pedagógico",
    "calendario_escolar": "Calendário",
    "cadastrar_evento": "Calendário",
    "pagina_configuracoes": "Configurações",
    "gerenciar_usuarios": "Usuários",
    "excluir_usuario_sistema": "Usuários",
    "contracheque": "Contra-cheque",
    "ajustar_contracheque": "Contra-cheque",
    "plataforma_escolas": "Plataforma",
    "pagina_notas_fiscais": "Notas fiscais",
    "nfse_emitir": "Notas fiscais",
    "nfse_cancelar": "Notas fiscais",
    "nfse_substituir": "Notas fiscais",
    "nfse_consultar": "Notas fiscais",
    "nfse_lote": "Notas fiscais",
}

_TIPOS = {
    "inclusao": "Inclusão",
    "alteracao": "Alteração",
    "exclusao": "Exclusão",
}


def garantir_auditoria():
    conexao = obter_conexao_nova()
    if not conexao:
        return
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS plataforma_auditoria (
                    id SERIAL PRIMARY KEY,
                    criado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    escola_id INT,
                    escola_nome VARCHAR(180),
                    usuario_nome VARCHAR(150),
                    usuario_email VARCHAR(150),
                    tipo VARCHAR(20) NOT NULL,
                    modulo VARCHAR(80),
                    resumo VARCHAR(400) NOT NULL,
                    detalhe TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS plataforma_auditoria_quando
                ON plataforma_auditoria (criado_em DESC)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS plataforma_auditoria_escola
                ON plataforma_auditoria (escola_id, criado_em DESC)
                """
            )
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()


def _sensivel(chave):
    texto = (chave or "").lower()
    return any(parte in texto for parte in _SENSIVEL)


def classificar_movimento(endpoint, acao):
    bruto = f"{acao or ''} {endpoint or ''}".lower()
    if any(p in bruto for p in ("excluir", "deletar", "apagar", "remover", "desvincular")):
        tipo = "exclusao"
    elif any(p in bruto for p in ("criar", "cadastr", "inclu", "adicion", "import", "gerar", "anex", "lancar", "registrar")):
        tipo = "inclusao"
    else:
        tipo = "alteracao"
    rotulo = _ROTULOS.get((acao or "").strip()) or _ROTULOS.get(endpoint or "")
    if not rotulo:
        rotulo = {"inclusao": "Incluiu registro", "alteracao": "Alterou registro", "exclusao": "Excluiu registro"}[tipo]
    return tipo, rotulo


def montar_detalhe(formulario, arquivos=None):
    partes = []
    vistos = set()
    origem = formulario or {}
    for chave, rotulo in _CAMPOS:
        if chave in vistos or _sensivel(chave):
            continue
        valor = ""
        if hasattr(origem, "getlist"):
            valores = [str(item).strip() for item in origem.getlist(chave) if str(item).strip()]
            valor = ", ".join(valores)
        else:
            valor = str(origem.get(chave) or "").strip()
        if not valor or valor.lower() in {"none", "selecione o aluno..."}:
            continue
        vistos.add(chave)
        partes.append(f"{rotulo}: {valor[:160]}")
    if arquivos:
        for chave, arquivo in arquivos.items():
            nome = getattr(arquivo, "filename", "") or ""
            if nome:
                partes.append(f"Arquivo: {nome[:120]}")
    return " · ".join(partes)[:1500]


def registrar_auditoria(escola_id, escola_nome, usuario_nome, usuario_email, tipo, modulo, resumo, detalhe=""):
    if tipo not in _TIPOS:
        tipo = "alteracao"
    garantir_auditoria()
    conexao = obter_conexao_nova()
    if not conexao:
        return
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO plataforma_auditoria
                    (escola_id, escola_nome, usuario_nome, usuario_email, tipo, modulo, resumo, detalhe)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    escola_id or None,
                    (escola_nome or "")[:180] or None,
                    (usuario_nome or "")[:150] or None,
                    (usuario_email or "")[:150] or None,
                    tipo,
                    (modulo or "")[:80] or None,
                    (resumo or "Alterou registro")[:400],
                    (detalhe or "")[:1500] or None,
                ),
            )
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()


def _quando(valor):
    if not valor:
        return ""
    if not isinstance(valor, datetime):
        return str(valor)
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(_FUSO).strftime("%d/%m/%Y %H:%M")


def listar_auditoria(escola_id=None, tipo="", busca="", limite=_LIMITE):
    garantir_auditoria()
    tipo = (tipo or "").strip().lower()
    if tipo not in _TIPOS:
        tipo = ""
    busca = (busca or "").strip()
    limite = max(1, min(int(limite or _LIMITE), 500))
    filtros = []
    params = []
    if escola_id:
        filtros.append("escola_id = %s")
        params.append(int(escola_id))
    if tipo:
        filtros.append("tipo = %s")
        params.append(tipo)
    if busca:
        filtros.append(
            "(resumo ILIKE %s OR detalhe ILIKE %s OR usuario_nome ILIKE %s OR usuario_email ILIKE %s OR escola_nome ILIKE %s OR modulo ILIKE %s)"
        )
        like = f"%{busca}%"
        params.extend([like, like, like, like, like, like])
    where = f"WHERE {' AND '.join(filtros)}" if filtros else ""
    conexao = obter_conexao_nova()
    if not conexao:
        return []
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, criado_em, escola_id, escola_nome, usuario_nome, usuario_email,
                       tipo, modulo, resumo, detalhe
                FROM plataforma_auditoria
                {where}
                ORDER BY criado_em DESC, id DESC
                LIMIT %s
                """,
                params + [limite],
            )
            linhas = []
            for row in cursor.fetchall() or []:
                item = dict(row)
                item["quando"] = _quando(item.get("criado_em"))
                item["tipo_rotulo"] = _TIPOS.get(item.get("tipo"), "Alteração")
                linhas.append(item)
            return linhas
    finally:
        conexao.close()


def modulo_da_rota(endpoint):
    return _MODULOS.get(endpoint or "", "Sistema")
