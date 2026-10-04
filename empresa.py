"""Cadastro da escola como empresa: CNPJ, inscrições, endereço fiscal, responsável legal e contador.

Os dados ficam em `configuracoes` (id = 1) do schema da escola. As colunas `cnpj`, `inscricao_municipal`
e `codigo_municipio` já são o fallback da NFS-e; uma cópia vai para `plataforma_escolas` para a plataforma
cobrar e emitir a nota da licença com a escola como tomadora.
"""

import json
import re
from datetime import date

UFS = (
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB",
    "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
)

PORTES = (
    ("", "Não informado"),
    ("mei", "MEI"),
    ("me", "Microempresa (ME)"),
    ("epp", "Empresa de pequeno porte (EPP)"),
    ("demais", "Demais"),
)

# (campo do formulário, coluna, rótulo, tamanho)
CAMPOS_EMPRESA = (
    ("razao_social", "razao_social", "Razão social", 180),
    ("nome_fantasia", "nome_fantasia", "Nome fantasia", 180),
    ("cnpj", "cnpj", "CNPJ", 20),
    ("inscricao_estadual", "inscricao_estadual", "Inscrição estadual", 30),
    ("inscricao_municipal", "inscricao_municipal", "Inscrição municipal", 40),
    ("cnae_principal", "cnae_principal", "CNAE principal", 12),
    ("codigo_inep", "codigo_inep", "Código INEP", 12),
    ("data_abertura", "data_abertura", "Data de abertura", None),
    ("porte", "porte_empresa", "Porte", 10),
    ("telefone_empresa", "telefone_empresa", "Telefone", 30),
    ("cep", "cep", "CEP", 9),
    ("logradouro", "logradouro", "Logradouro", 150),
    ("numero", "numero", "Número", 20),
    ("complemento", "complemento", "Complemento", 80),
    ("bairro", "bairro", "Bairro", 100),
    ("cidade", "cidade", "Cidade", 100),
    ("estado", "uf", "UF", 2),
    ("codigo_municipio", "codigo_municipio", "Código IBGE do município", 10),
    ("responsavel_nome", "responsavel_nome", "Responsável legal", 150),
    ("responsavel_cpf", "responsavel_cpf", "CPF do responsável", 14),
    ("responsavel_cargo", "responsavel_cargo", "Cargo do responsável", 80),
    ("contador_nome", "contador_nome", "Contador / escritório", 150),
    ("contador_crc", "contador_crc", "CRC do contador", 30),
    ("contador_email", "contador_email", "E-mail do contador", 150),
    ("contador_telefone", "contador_telefone", "Telefone do contador", 30),
)

COLUNAS_EMPRESA = tuple(coluna for _campo, coluna, _rotulo, _tam in CAMPOS_EMPRESA)
_RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def so_digitos(valor):
    return "".join(c for c in str(valor or "") if c.isdigit())


def cnpj_valido(valor):
    d = so_digitos(valor)
    if len(d) != 14 or d == d[0] * 14:
        return False
    for tamanho in (12, 13):
        pesos = list(range(tamanho - 7, 1, -1)) + list(range(9, 1, -1))
        soma = sum(int(n) * p for n, p in zip(d[:tamanho], pesos))
        dv = 11 - soma % 11
        if (0 if dv >= 10 else dv) != int(d[tamanho]):
            return False
    return True


def cpf_valido(valor):
    d = so_digitos(valor)
    if len(d) != 11 or d == d[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(n) * p for n, p in zip(d[:tamanho], range(tamanho + 1, 1, -1)))
        dv = (soma * 10) % 11
        if (0 if dv == 10 else dv) != int(d[tamanho]):
            return False
    return True


def formatar_cnpj(valor):
    d = so_digitos(valor)
    if len(d) != 14:
        return (valor or "").strip()
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def formatar_cpf(valor):
    d = so_digitos(valor)
    if len(d) != 11:
        return (valor or "").strip()
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def formatar_cep(valor):
    d = so_digitos(valor)
    return f"{d[:5]}-{d[5:]}" if len(d) == 8 else (valor or "").strip()


def dados_empresa_do_form(form):
    """Lê e valida os campos. Devolve (dados por coluna, lista de erros). Campos vazios ficam None."""
    dados, erros = {}, []
    for campo, coluna, rotulo, tamanho in CAMPOS_EMPRESA:
        bruto = (form.get(campo) or "").strip()
        dados[coluna] = bruto[:tamanho] if (bruto and tamanho) else (bruto or None)

    if dados["cnpj"]:
        if not cnpj_valido(dados["cnpj"]):
            erros.append("CNPJ inválido: confira os 14 números.")
        dados["cnpj"] = so_digitos(dados["cnpj"])
    ie = dados["inscricao_estadual"]
    if ie and ie.upper() not in ("ISENTO", "ISENTA"):
        dados["inscricao_estadual"] = so_digitos(ie) or None
        if not dados["inscricao_estadual"]:
            erros.append("Inscrição estadual: use só números ou ISENTO.")
    elif ie:
        dados["inscricao_estadual"] = "ISENTO"
    if dados["cnae_principal"]:
        cnae = so_digitos(dados["cnae_principal"])
        if len(cnae) != 7:
            erros.append("CNAE principal tem 7 números (ex.: 8513-9/00).")
        dados["cnae_principal"] = cnae
    if dados["codigo_inep"]:
        inep = so_digitos(dados["codigo_inep"])
        if len(inep) != 8:
            erros.append("Código INEP da escola tem 8 números.")
        dados["codigo_inep"] = inep
    if dados["data_abertura"]:
        try:
            abertura = date.fromisoformat(dados["data_abertura"][:10])
            if abertura > date.today():
                erros.append("Data de abertura não pode ser futura.")
            dados["data_abertura"] = abertura.isoformat()
        except ValueError:
            erros.append("Data de abertura inválida.")
            dados["data_abertura"] = None
    if dados["porte_empresa"] and dados["porte_empresa"] not in dict(PORTES):
        dados["porte_empresa"] = None
    if dados["cep"]:
        cep = so_digitos(dados["cep"])
        if len(cep) != 8:
            erros.append("CEP tem 8 números.")
        dados["cep"] = cep
    if dados["uf"]:
        dados["uf"] = dados["uf"].upper()
        if dados["uf"] not in UFS:
            erros.append("UF inválida.")
    if dados["codigo_municipio"]:
        ibge = so_digitos(dados["codigo_municipio"])
        if len(ibge) != 7:
            erros.append("Código IBGE do município tem 7 números (o CEP preenche sozinho).")
        dados["codigo_municipio"] = ibge
    if dados["responsavel_cpf"]:
        if not cpf_valido(dados["responsavel_cpf"]):
            erros.append("CPF do responsável legal inválido.")
        dados["responsavel_cpf"] = so_digitos(dados["responsavel_cpf"])
    if dados["contador_email"]:
        dados["contador_email"] = dados["contador_email"].lower()
        if not _RE_EMAIL.match(dados["contador_email"]):
            erros.append("E-mail do contador inválido.")
    return dados, erros


def tem_dados_empresa(form):
    return any((form.get(campo) or "").strip() for campo, _c, _r, _t in CAMPOS_EMPRESA)


def garantir_colunas_empresa(cursor):
    partes = []
    for _campo, coluna, _rotulo, tamanho in CAMPOS_EMPRESA:
        tipo = "DATE" if coluna == "data_abertura" else f"VARCHAR({tamanho})"
        partes.append(f"ADD COLUMN IF NOT EXISTS {coluna} {tipo}")
    cursor.execute("ALTER TABLE configuracoes " + ", ".join(partes))


def salvar_empresa(cursor, dados, limpar_vazios=False):
    """Grava só os campos preenchidos; campo em branco mantém o valor salvo, a não ser com limpar_vazios."""
    garantir_colunas_empresa(cursor)
    alvo = [c for c in COLUNAS_EMPRESA if limpar_vazios or dados.get(c) not in (None, "")]
    if not alvo:
        return []
    colunas = ", ".join(alvo)
    marcadores = ", ".join(["%s"] * len(alvo))
    atualiza = ", ".join(f"{c} = EXCLUDED.{c}" for c in alvo)
    cursor.execute(
        f"INSERT INTO configuracoes (id, {colunas}) VALUES (1, {marcadores}) "
        f"ON CONFLICT (id) DO UPDATE SET {atualiza}",
        tuple(dados.get(c) for c in alvo),
    )
    return alvo


def ler_empresa(cursor):
    cursor.execute("SELECT * FROM configuracoes WHERE id = 1")
    linha = cursor.fetchone() or {}
    return {c: linha.get(c) for c in COLUNAS_EMPRESA}


def campos_apagados(atual, dados):
    """Rótulos dos campos que tinham valor e vieram em branco."""
    rotulos = {coluna: rotulo for _campo, coluna, rotulo, _t in CAMPOS_EMPRESA}
    return [rotulos[c] for c in COLUNAS_EMPRESA if (atual or {}).get(c) not in (None, "") and dados.get(c) in (None, "")]


def dados_empresa_tela(cfg):
    """Valores formatados para preencher o formulário (chave = nome do campo)."""
    cfg = cfg or {}
    tela = {}
    for campo, coluna, _rotulo, _tam in CAMPOS_EMPRESA:
        valor = cfg.get(coluna)
        if hasattr(valor, "isoformat"):
            valor = valor.isoformat()
        tela[campo] = valor or ""
    tela["cnpj"] = formatar_cnpj(tela["cnpj"])
    tela["responsavel_cpf"] = formatar_cpf(tela["responsavel_cpf"])
    tela["cep"] = formatar_cep(tela["cep"])
    return tela


def empresa_incompleta(cfg):
    """Campos essenciais para folha, tributos e nota que ainda faltam."""
    cfg = cfg or {}
    faltam = []
    for coluna, rotulo in (
        ("razao_social", "razão social"),
        ("cnpj", "CNPJ"),
        ("inscricao_municipal", "inscrição municipal"),
        ("cep", "endereço"),
        ("responsavel_nome", "responsável legal"),
    ):
        if not cfg.get(coluna):
            faltam.append(rotulo)
    return faltam


def copia_para_plataforma(dados):
    """Colunas de plataforma_escolas (tomador da nota da licença) + cópia completa em JSON."""
    copia = {c: (v.isoformat() if hasattr(v, "isoformat") else v) for c, v in dados.items() if c in COLUNAS_EMPRESA}
    return {
        "cnpj": dados.get("cnpj"),
        "nfse_logradouro": dados.get("logradouro"),
        "nfse_numero": dados.get("numero"),
        "nfse_bairro": dados.get("bairro"),
        "nfse_codigo_municipio": dados.get("codigo_municipio"),
        "nfse_uf": dados.get("uf"),
        "nfse_cep": dados.get("cep"),
        "dados_empresa": json.dumps(copia, ensure_ascii=False),
    }
