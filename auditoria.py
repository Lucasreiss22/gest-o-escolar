"""Registro do que foi incluído, alterado ou excluído no sistema."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from database import obter_conexao_nova
from permissoes import AREAS_ACESSO, ENDPOINTS
from psycopg2.extras import RealDictCursor

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
    ("email", "E-mail / login"),
    ("email_admin", "E-mail"),
    ("email_contato", "E-mail de contato"),
    ("descricao", "Descrição"),
    ("descricao_custo", "Descrição"),
    ("valor", "Valor"),
    ("valor_mensalidade", "Mensalidade"),
    ("valor_hora", "Valor hora"),
    ("status", "Status"),
    ("data_nascimento", "Data de nascimento"),
    ("data_vencimento", "Vencimento"),
    ("data_pagamento", "Pagamento"),
    ("data_ref", "Data de referência"),
    ("data_inicio", "Data início"),
    ("data_fim", "Data fim"),
    ("data_aplicacao", "Data da prova"),
    ("data_evento", "Data do evento"),
    ("contrato_inicio", "Início do contrato"),
    ("pacote", "Pacote"),
    ("mes", "Mês"),
    ("aluno_id", "Aluno (id)"),
    ("escola_id", "Escola (id)"),
    ("turma_id", "Turma (id)"),
    ("funcionario_id", "Colaborador (id)"),
    ("usuario_id", "Usuário (id)"),
    ("cpf", "CPF"),
    ("telefone", "Telefone"),
    ("celular", "Celular"),
    ("endereco", "Endereço"),
    ("cidade", "Cidade"),
    ("bairro", "Bairro"),
    ("papel", "Perfil"),
    ("cargo", "Cargo"),
    ("tipo", "Tipo"),
    ("tipo_contrato", "Tipo de contrato"),
    ("matricula", "Matrícula"),
    ("observacao", "Observação"),
    ("motivo", "Motivo"),
    ("justificativa", "Justificativa"),
    ("ponto_minutos_cafe", "Café (min)"),
    ("ponto_minutos_almoco", "Almoço (min)"),
    ("ponto_jornada_minutos", "Jornada (min)"),
    ("horario", "Horário"),
    ("entrada", "Entrada"),
    ("saida", "Saída"),
    ("almoco", "Almoço"),
    ("cafe_ida", "Café (ida)"),
    ("cafe_volta", "Café (volta)"),
    ("almoco_volta", "Almoço (volta)"),
    ("decisao", "Decisão"),
    ("descontar", "Descontar"),
    ("desconto_tipo", "Tipo de desconto"),
    ("desconto_valor", "Valor do desconto"),
    ("competencia", "Competência"),
    ("regime", "Regime"),
    ("turno", "Turno"),
    ("ano_letivo", "Ano letivo"),
    ("etapa", "Etapa"),
    ("categoria", "Categoria"),
    ("permissoes", "Permissões"),
)

_SENSIVEL = ("senha", "password", "secret", "token", "codigo", "arquivo", "foto")

_ROTULOS = {
    # Alunos
    "cadastrar_aluno": "Incluiu aluno",
    "cadastrar_aluno_simples": "Incluiu aluno",
    "cadastrar_aluno_rota": "Incluiu aluno",
    "importar_alunos": "Importou alunos",
    "importar_alunos_simples": "Importou alunos",
    "editar_aluno": "Alterou aluno",
    "ajustar_mensalidades_abertas": "Ajustou mensalidades em aberto ao desconto do aluno",
    "excluir_aluno_rota": "Excluiu aluno",
    "excluir_alunos": "Excluiu aluno",
    "deletar_responsavel": "Excluiu responsável",
    "deletar_autorizado": "Excluiu pessoa autorizada",
    "editar_autorizado": "Alterou pessoa autorizada",
    "nao_autorizar_busca": "Bloqueou autorização de busca",
    "adicionar_responsavel": "Incluiu responsável",
    "salvar_responsavel": "Alterou responsável",
    "editar_responsavel": "Alterou responsável",
    "adicionar_autorizado": "Incluiu pessoa autorizada",
    "enviar_autorizacao_busca": "Enviou autorização de busca",
    # Pedagógico / turmas
    "criar_turma": "Incluiu turma",
    "nova_turma": "Incluiu turma",
    "excluir_turma": "Excluiu turma",
    "desvincular_aluno": "Tirou aluno da turma",
    "desvincular": "Tirou aluno da turma",
    "vincular": "Vinculou aluno à turma",
    "vincular_aluno": "Vinculou aluno à turma",
    "incluir_aluno": "Incluiu aluno na turma",
    "criar_disciplina": "Incluiu matéria",
    "criar_disciplina_turma": "Incluiu matéria na turma",
    "editar_disciplina": "Alterou matéria",
    "excluir_disciplina": "Excluiu matéria",
    "excluir_disciplina_turma": "Removeu matéria da turma",
    "desativar_disciplina": "Desativou matéria",
    "ativar_disciplina": "Ativou matéria",
    "vincular_disciplina": "Vinculou matéria à turma",
    "criar_prova_turma": "Criou prova da turma",
    "lancar_frequencia": "Lançou frequência",
    "lancar_frequencia_aluno": "Lançou frequência",
    "adicionar_nota": "Incluiu nota",
    "ajustar_prova_aluno": "Ajustou prova do aluno",
    "ficha_pedagogica_pdf": "Gerou ficha pedagógica",
    "boletim_pdf": "Gerou boletim",
    "sala_professor_enviar_pdf": "Enviou PDF da sala do professor",
    # Equipe
    "cadastrar_professor": "Incluiu colaborador",
    "excluir_professor": "Excluiu colaborador",
    "editar_professor": "Alterou colaborador",
    "salvar_tempos_funcionario": "Alterou tempos de ponto",
    # Financeiro
    "criar_cobranca": "Gerou cobrança",
    "editar_cobranca": "Alterou cobrança",
    "excluir_financeiro": "Excluiu registro financeiro",
    "dar_baixa": "Deu baixa na cobrança",
    "dar_baixa_lote": "Deu baixa em lote",
    "tirar_baixa": "Retirou a baixa da cobrança",
    "tirar_baixa_lote": "Retirou a baixa em lote",
    "criar_custo": "Incluiu custo",
    "excluir_custo": "Excluiu custo",
    "importar_custos": "Importou custos",
    "enviar_memoria_simples": "Enviou memória do Simples",
    "enviar_contracheques_mes": "Enviou contra-cheques do mês",
    "ajustar_contracheque": "Ajustou contra-cheque",
    # Calendário
    "cadastrar_evento": "Incluiu evento no calendário",
    "editar_evento": "Alterou evento do calendário",
    "excluir_evento": "Excluiu evento do calendário",
    # Ponto
    "bater_ponto": "Registrou batida de ponto",
    "solicitar_ponto_retroativo": "Pediu ponto retroativo",
    "solicitar_correcao_ponto": "Pediu correção de ponto",
    "aprovar_ponto_retroativo": "Aprovou ponto retroativo",
    "rejeitar_ponto_retroativo": "Rejeitou ponto retroativo",
    "cancelar_ponto_retroativo": "Cancelou ponto retroativo",
    "confirmar_atestado": "Confirmou atestado",
    "confirmar_falta": "Confirmou falta",
    "lancar_falta": "Lançou falta",
    "enviar_atestado": "Enviou atestado",
    "rejeitar_atestado": "Rejeitou atestado",
    # Usuários / permissões / config
    "salvar_acesso": "Alterou permissões de usuário",
    "excluir_usuario_sistema": "Excluiu usuário do painel",
    "excluir": "Excluiu registro",
    "salvar_logo": "Alterou logo / mensagem",
    "salvar_config": "Alterou configurações",
    "salvar_escola": "Alterou dados da escola",
    "redefinir_senha": "Redefiniu senha",
    # Plataforma
    "criar_escola": "Incluiu escola",
    "definir_pacote": "Alterou o pacote da escola",
    "salvar_pacote": "Alterou pacote",
    "salvar_cobranca_escola": "Alterou o desconto da escola",
    "gerar_assinaturas": "Gerou assinaturas do mês",
    "atualizar_abertas": "Atualizou assinaturas em aberto",
    "excluir_cobranca": "Excluiu assinatura",
    "salvar_google": "Alterou o envio de e-mail",
    "pausar_escola": "Pausou escola",
    "reativar_escola": "Reativou escola",
    "excluir_escola": "Excluiu escola",
    # NFS-e
    "salvar_nfse": "Alterou a nota fiscal",
    "salvar_nfse_plataforma": "Alterou a nota fiscal da plataforma",
    "emitir_nfse_plataforma": "Emitiu NFS-e da licença",
    "cancelar_nfse_plataforma": "Cancelou NFS-e da licença",
    "substituir_nfse_plataforma": "Substituiu NFS-e da licença",
    "nfse_emitir": "Emitiu NFS-e",
    "nfse_cancelar": "Cancelou NFS-e",
    "nfse_substituir": "Substituiu NFS-e",
    "nfse_lote": "Emitiu NFS-e em lote",
    "nfse_consultar": "Consultou NFS-e",
}

# Rótulos de tela alinhados às permissões (AREAS_ACESSO)
_ROTULO_AREA = {codigo: rotulo for codigo, rotulo in AREAS_ACESSO}
_ROTULO_AREA.update(
    {
        "dashboard": "Painel",
        "alunos": "Alunos",
        "pedagogico": "Pedagógico — visão, chamada e notas",
        "pedagogico_cadastro": "Pedagógico — turmas, matérias e matrículas",
        "professores": "Equipe",
        "financeiro": "Financeiro",
        "calendario": "Calendário / chamada",
        "contracheque": "Contra-cheque",
        "ponto": "Ponto",
        "configuracoes": "Configurações",
        "usuarios": "Usuários e permissões",
        "auditoria": "Auditoria",
        "nfse": "Notas fiscais (NFS-e)",
    }
)

# Endpoints extras (plataforma / fora do ENDPOINTS)
_MODULOS_EXTRA = {
    "plataforma_escolas": "Plataforma",
    "dashboard": "Painel",
    "login": "Acesso",
    "logout": "Acesso",
    "Usuários e permissões": "Usuários e permissões",
}

_MODULOS = {
    endpoint: _ROTULO_AREA.get(area, area.replace("_", " ").capitalize())
    for endpoint, area in ENDPOINTS.items()
}
_MODULOS.update(_MODULOS_EXTRA)

_TIPOS = {
    "inclusao": "Inclusão",
    "alteracao": "Alteração",
    "exclusao": "Exclusão",
}

_IGNORAR_FORM = {
    "acao",
    "csrf_token",
    "auditoria_antes",
    "form_login",
    "permanecer_logado",
    "senha",
    "senha2",
    "password",
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
            cursor.execute(
                "ALTER TABLE plataforma_auditoria ADD COLUMN IF NOT EXISTS usuario_login VARCHAR(150)"
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


def _fmt_valor(valor):
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "Sim" if valor else "Não"
    if isinstance(valor, (list, tuple)):
        partes = [_fmt_valor(v) for v in valor if _fmt_valor(v)]
        return ", ".join(partes)
    if isinstance(valor, datetime):
        return valor.strftime("%d/%m/%Y %H:%M")
    texto = str(valor).strip()
    if not texto or texto.lower() in {"none", "null", "undefined"}:
        return ""
    # YYYY-MM-DD → BR
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", texto):
        a, m, d = texto.split("-")
        return f"{d}/{m}/{a}"
    # YYYY-MM-DDTHH:MM
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?", texto):
        data, hora = texto.replace("T", " ").split(" ", 1)
        a, m, d = data.split("-")
        return f"{d}/{m}/{a} {hora[:5]}"
    return texto[:200]


def _pegar(origem, chave):
    if origem is None:
        return ""
    if hasattr(origem, "getlist"):
        valores = [_fmt_valor(item) for item in origem.getlist(chave)]
        return ", ".join(v for v in valores if v)
    if hasattr(origem, "get"):
        return _fmt_valor(origem.get(chave))
    return ""


def _mapa_antes(origem):
    antes = {}
    if origem is None:
        return antes
    raw = ""
    if hasattr(origem, "get"):
        raw = origem.get("auditoria_antes") or ""
    if raw:
        try:
            payload = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(payload, dict):
                for chave, valor in payload.items():
                    if not _sensivel(chave):
                        antes[chave] = _fmt_valor(valor)
        except Exception:
            pass
    chaves = []
    if hasattr(origem, "keys"):
        chaves = list(origem.keys())
    elif hasattr(origem, "getlist"):
        try:
            chaves = list(origem.keys())
        except Exception:
            chaves = []
    for chave in chaves:
        if not chave or _sensivel(chave):
            continue
        chave_s = str(chave)
        if chave_s.endswith("_antes"):
            base = chave_s[:-6]
            antes[base] = _pegar(origem, chave_s)
        elif chave_s.startswith("antes_"):
            base = chave_s[6:]
            antes[base] = _pegar(origem, chave_s)
    return antes


def classificar_movimento(endpoint, acao):
    bruto = f"{acao or ''} {endpoint or ''}".lower()
    if any(p in bruto for p in ("excluir", "deletar", "apagar", "remover", "desvincular", "rejeit")):
        tipo = "exclusao"
    elif any(
        p in bruto
        for p in ("criar", "cadastr", "inclu", "adicion", "import", "gerar", "anex", "lancar", "registrar", "enviar", "bater")
    ):
        tipo = "inclusao"
    else:
        tipo = "alteracao"
    rotulo = _ROTULOS.get((acao or "").strip()) or _ROTULOS.get(endpoint or "")
    if not rotulo:
        rotulo = {"inclusao": "Incluiu registro", "alteracao": "Alterou registro", "exclusao": "Excluiu registro"}[tipo]
    return tipo, rotulo


def montar_mudancas(formulario, arquivos=None, antes=None):
    """Monta lista {campo, antes, depois} a partir do formulário e do mapa anterior."""
    origem = formulario or {}
    antes_map = dict(antes or {})
    antes_map.update(_mapa_antes(origem))
    mudancas = []
    vistos = set()

    def _add(chave, rotulo, depois, valor_antes=None):
        if chave in vistos or _sensivel(chave):
            return
        depois_f = _fmt_valor(depois)
        antes_f = _fmt_valor(valor_antes if valor_antes is not None else antes_map.get(chave))
        if not depois_f and not antes_f:
            return
        if depois_f == antes_f:
            return
        vistos.add(chave)
        mudancas.append(
            {
                "campo": rotulo,
                "antes": antes_f or "—",
                "depois": depois_f or "—",
            }
        )

    for chave, rotulo in _CAMPOS:
        _add(chave, rotulo, _pegar(origem, chave))

    # Campos extras do formulário (não sensíveis)
    chaves_extra = []
    if hasattr(origem, "keys"):
        try:
            chaves_extra = list(origem.keys())
        except Exception:
            chaves_extra = []
    for chave in chaves_extra:
        chave_s = str(chave)
        if chave_s in vistos or chave_s in _IGNORAR_FORM or _sensivel(chave_s):
            continue
        if chave_s.endswith("_antes") or chave_s.startswith("antes_"):
            continue
        if chave_s.startswith("auditoria_"):
            continue
        rotulo = chave_s.replace("_", " ").strip().capitalize()
        _add(chave_s, rotulo, _pegar(origem, chave_s))

    if arquivos:
        for chave, arquivo in arquivos.items():
            nome = getattr(arquivo, "filename", "") or ""
            if nome:
                mudancas.append({"campo": "Arquivo", "antes": "—", "depois": nome[:120]})

    return mudancas


def montar_detalhe(formulario, arquivos=None, antes=None):
    mudancas = montar_mudancas(formulario, arquivos, antes)
    linhas = []
    for item in mudancas:
        if item["antes"] not in ("", "—") and item["depois"] not in ("", "—"):
            linhas.append(f"{item['campo']}: de {item['antes']} → para {item['depois']}")
        elif item["depois"] not in ("", "—"):
            linhas.append(f"{item['campo']}: {item['depois']}")
        elif item["antes"] not in ("", "—"):
            linhas.append(f"{item['campo']}: removido (era {item['antes']})")
    payload = {
        "mudancas": mudancas,
        "texto": " · ".join(linhas)[:4000],
    }
    return json.dumps(payload, ensure_ascii=False)[:8000]


def diff_dicts(antes, depois):
    """Gera JSON de detalhe comparando dois dicionários (uso explícito nas rotas)."""
    mudancas = []
    chaves = set((antes or {}).keys()) | set((depois or {}).keys())
    mapa_rotulo = {k: r for k, r in _CAMPOS}
    for chave in sorted(chaves):
        if _sensivel(chave) or chave in _IGNORAR_FORM:
            continue
        a = _fmt_valor((antes or {}).get(chave))
        d = _fmt_valor((depois or {}).get(chave))
        if a == d:
            continue
        mudancas.append(
            {
                "campo": mapa_rotulo.get(chave, chave.replace("_", " ").capitalize()),
                "antes": a or "—",
                "depois": d or "—",
            }
        )
    linhas = []
    for item in mudancas:
        if item["antes"] != "—" and item["depois"] != "—":
            linhas.append(f"{item['campo']}: de {item['antes']} → para {item['depois']}")
        elif item["depois"] != "—":
            linhas.append(f"{item['campo']}: {item['depois']}")
        else:
            linhas.append(f"{item['campo']}: removido (era {item['antes']})")
    return json.dumps({"mudancas": mudancas, "texto": " · ".join(linhas)[:4000]}, ensure_ascii=False)[:8000]


def registrar_auditoria(
    escola_id,
    escola_nome,
    usuario_nome,
    usuario_email,
    tipo,
    modulo,
    resumo,
    detalhe="",
    usuario_login=None,
):
    if tipo not in _TIPOS:
        tipo = "alteracao"
    garantir_auditoria()
    login = (usuario_login or usuario_email or "")[:150] or None
    conexao = obter_conexao_nova()
    if not conexao:
        return
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO plataforma_auditoria
                    (escola_id, escola_nome, usuario_nome, usuario_email, usuario_login,
                     tipo, modulo, resumo, detalhe)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    escola_id or None,
                    (escola_nome or "")[:180] or None,
                    (usuario_nome or "")[:150] or None,
                    (usuario_email or "")[:150] or None,
                    login,
                    tipo,
                    (modulo or "")[:80] or None,
                    (resumo or "Alterou registro")[:400],
                    (detalhe or "")[:8000] or None,
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


def _parse_detalhe(bruto):
    mudancas = []
    texto = ""
    if not bruto:
        return mudancas, texto
    if isinstance(bruto, dict):
        mudancas = bruto.get("mudancas") or []
        texto = bruto.get("texto") or ""
        return mudancas, texto
    raw = str(bruto).strip()
    if raw.startswith("{"):
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                mudancas = payload.get("mudancas") or []
                texto = payload.get("texto") or ""
                return mudancas, texto
        except Exception:
            pass
    return [], raw


def listar_auditoria(escola_id=None, tipo="", busca="", limite=_LIMITE, modulo=""):
    garantir_auditoria()
    tipo = (tipo or "").strip().lower()
    if tipo not in _TIPOS:
        tipo = ""
    busca = (busca or "").strip()
    modulo = (modulo or "").strip()
    limite = max(1, min(int(limite or _LIMITE), 500))
    filtros = []
    params = []
    if escola_id:
        filtros.append("escola_id = %s")
        params.append(int(escola_id))
    if tipo:
        filtros.append("tipo = %s")
        params.append(tipo)
    if modulo:
        filtros.append("modulo ILIKE %s")
        params.append(modulo)
    if busca:
        filtros.append(
            """
            (resumo ILIKE %s OR detalhe ILIKE %s OR usuario_nome ILIKE %s
             OR usuario_email ILIKE %s OR COALESCE(usuario_login, '') ILIKE %s
             OR escola_nome ILIKE %s OR modulo ILIKE %s)
            """
        )
        like = f"%{busca}%"
        params.extend([like, like, like, like, like, like, like])
    where = f"WHERE {' AND '.join(filtros)}" if filtros else ""
    conexao = obter_conexao_nova()
    if not conexao:
        return []
    try:
        with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                f"""
                SELECT id, criado_em, escola_id, escola_nome, usuario_nome, usuario_email,
                       COALESCE(usuario_login, usuario_email) AS usuario_login,
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
                mudancas, texto = _parse_detalhe(item.get("detalhe"))
                item["mudancas"] = mudancas
                item["detalhe_texto"] = texto or (item.get("detalhe") or "")
                item["login"] = item.get("usuario_login") or item.get("usuario_email") or ""
                linhas.append(item)
            return linhas
    finally:
        conexao.close()


def modulos_auditoria(escola_id=None):
    """Lista de telas já registradas na auditoria (para filtro)."""
    garantir_auditoria()
    conexao = obter_conexao_nova()
    if not conexao:
        return list(_ROTULO_AREA.values())
    try:
        with conexao.cursor() as cursor:
            if escola_id:
                cursor.execute(
                    """
                    SELECT DISTINCT modulo FROM plataforma_auditoria
                    WHERE escola_id = %s AND modulo IS NOT NULL AND modulo <> ''
                    ORDER BY modulo
                    """,
                    (int(escola_id),),
                )
            else:
                cursor.execute(
                    """
                    SELECT DISTINCT modulo FROM plataforma_auditoria
                    WHERE modulo IS NOT NULL AND modulo <> ''
                    ORDER BY modulo
                    """
                )
            encontrados = []
            for row in cursor.fetchall() or []:
                valor = row.get("modulo") if isinstance(row, dict) else (row[0] if row else None)
                if valor:
                    encontrados.append(valor)
    finally:
        conexao.close()
    base = list(_ROTULO_AREA.values()) + ["Plataforma", "Sistema"]
    unidos = []
    vistos = set()
    for nome in encontrados + base:
        if nome and nome not in vistos:
            vistos.add(nome)
            unidos.append(nome)
    return unidos


def modulo_da_rota(endpoint):
    if not endpoint:
        return "Sistema"
    if endpoint in _MODULOS:
        return _MODULOS[endpoint]
    # fallback: tenta pelo mapa de áreas
    area = ENDPOINTS.get(endpoint)
    if area:
        return _ROTULO_AREA.get(area, area.replace("_", " ").capitalize())
    return "Sistema"
