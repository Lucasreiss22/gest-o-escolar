"""Rede de escolas: matriz, filial ou unidade independente.

Matriz e filiais são estabelecimentos da mesma empresa, ou seja, têm a mesma raiz de CNPJ (8 primeiros números).
O vínculo fica em `plataforma_escolas` (tipo_unidade, matriz_id); o banco de cada unidade é o schema dela (db_nome).
"""

from empresa import so_digitos

TIPOS_UNIDADE = (
    ("independente", "Independente (nem matriz nem filial)"),
    ("matriz", "Matriz"),
    ("filial", "Filial"),
)


def normalizar_tipo_unidade(valor):
    valor = (valor or "").strip().lower()
    return valor if valor in dict(TIPOS_UNIDADE) else "independente"


def raiz_cnpj(cnpj):
    digitos = so_digitos(cnpj)
    return digitos[:8] if len(digitos) == 14 else ""


def _id(valor):
    try:
        return int(valor) if valor not in (None, "") else None
    except (TypeError, ValueError):
        return None


def filiais_da(escola_id, escolas):
    return [e for e in escolas or [] if _id(e.get("matriz_id")) == _id(escola_id) and e.get("tipo_unidade") == "filial"]


def matrizes_possiveis(escola, escolas):
    """Matrizes com a mesma raiz de CNPJ (a escola nunca vê as demais clientes da plataforma)."""
    raiz = raiz_cnpj((escola or {}).get("cnpj"))
    if not raiz:
        return []
    return [
        e for e in escolas or []
        if e.get("tipo_unidade") == "matriz" and _id(e.get("id")) != _id(escola.get("id")) and raiz_cnpj(e.get("cnpj")) == raiz
    ]


def validar_unidade(escola, tipo, matriz_id, escolas):
    """Devolve (tipo, matriz_id) válidos ou levanta ValueError com a explicação."""
    tipo = normalizar_tipo_unidade(tipo)
    matriz_id = _id(matriz_id)
    escola = escola or {}
    filiais = filiais_da(escola.get("id"), escolas)
    if tipo != "matriz" and filiais:
        nomes = ", ".join(f.get("nome") or f"#{f.get('id')}" for f in filiais)
        raise ValueError(f"Esta escola é matriz de {nomes}. Desvincule as filiais antes de mudar a classificação.")
    if tipo == "independente":
        return tipo, None
    if not raiz_cnpj(escola.get("cnpj")):
        raise ValueError("Informe o CNPJ da escola nos dados da empresa antes de classificá-la como matriz ou filial.")
    if tipo == "matriz":
        return tipo, None
    if not matriz_id:
        raise ValueError("Escolha a matriz desta filial.")
    matriz = next((e for e in escolas or [] if _id(e.get("id")) == matriz_id), None)
    if not matriz or matriz_id == _id(escola.get("id")):
        raise ValueError("Matriz não encontrada.")
    if matriz.get("tipo_unidade") != "matriz":
        raise ValueError(f"{matriz.get('nome')} não está classificada como matriz.")
    if raiz_cnpj(matriz.get("cnpj")) != raiz_cnpj(escola.get("cnpj")):
        raise ValueError(
            "Matriz e filial precisam ter a mesma raiz de CNPJ (os 8 primeiros números). "
            "Escolas com CNPJ diferente são independentes."
        )
    return tipo, matriz_id


def resumo_unidade(escola, escolas):
    """Dados para a tela: classificação atual, matriz, filiais e opções de matriz."""
    escola = escola or {}
    tipo = normalizar_tipo_unidade(escola.get("tipo_unidade"))
    matriz = next((e for e in escolas or [] if _id(e.get("id")) == _id(escola.get("matriz_id"))), None)
    return {
        "escola_id": escola.get("id"),
        "tipo": tipo,
        "matriz_id": _id(escola.get("matriz_id")) if tipo == "filial" else None,
        "matriz_nome": (matriz or {}).get("nome") if tipo == "filial" else None,
        "filiais": [{"id": f.get("id"), "nome": f.get("nome")} for f in filiais_da(escola.get("id"), escolas)],
        "opcoes_matriz": [{"id": m.get("id"), "nome": m.get("nome")} for m in matrizes_possiveis(escola, escolas)],
        "db_nome": escola.get("db_nome"),
        "tem_cnpj": bool(raiz_cnpj(escola.get("cnpj"))),
    }
