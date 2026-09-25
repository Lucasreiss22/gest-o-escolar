"""Emissão de NFS-e pela API da Focus NFe.

O token e o certificado A1 ficam no banco da escola ou da plataforma.
Nenhuma nota sai sem esses dados gravados no servidor. A Focus autentica
cada chamada com o token da empresa; o certificado A1 fica vinculado a
essa empresa na Focus e também fica guardado aqui.
"""

import time
from datetime import datetime, timedelta, timezone

STATUS_FATURADA = "FATURADA"
STATUS_CANCELADA = "CANCELADA"
STATUS_SUBSTITUIDA = "SUBSTITUIDA"
STATUS_PENDENTE = "PENDENTE"
STATUS_ERRO = "ERRO"
STATUS_NOTA = (
    STATUS_FATURADA,
    STATUS_CANCELADA,
    STATUS_SUBSTITUIDA,
    STATUS_PENDENTE,
    STATUS_ERRO,
)

URLS = {
    "homologacao": "https://homologacao.focusnfe.com.br/v2/nfse",
    "producao": "https://api.focusnfe.com.br/v2/nfse",
}

_FUSO = timezone(timedelta(hours=-3))
_FOCUS_STATUS = {
    "autorizado": STATUS_FATURADA,
    "cancelado": STATUS_CANCELADA,
    "erro_autorizacao": STATUS_ERRO,
    "erro": STATUS_ERRO,
    "processando_autorizacao": STATUS_PENDENTE,
    "substituido": STATUS_SUBSTITUIDA,
}

_MESES = (
    "",
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)


def agora_local():
    return datetime.now(_FUSO)


def apenas_digitos(valor):
    return "".join(caractere for caractere in str(valor or "") if caractere.isdigit())


def limpar_token(token):
    texto = (token or "").replace("\n", "").replace("\r", "").replace("\t", "")
    texto = texto.strip().strip('"').strip("'").strip()
    baixo = texto.lower()
    for prefixo in ("bearer ", "token ", "basic "):
        if baixo.startswith(prefixo):
            texto = texto[len(prefixo):].strip()
            break
    if texto.lower().startswith("token:"):
        texto = texto.split(":", 1)[1].strip()
    texto = texto.strip().strip('"').strip("'").strip()
    return "".join(texto.split())


def mascarar_token(token):
    texto = limpar_token(token)
    if not texto:
        return ""
    if len(texto) <= 4:
        return "••••"
    return "••••" + texto[-4:]


def token_recusado(mensagem, codigo=None):
    texto = (mensagem or "").lower()
    if "access token" in texto or "token inválido" in texto or "token invalido" in texto:
        return True
    return int(codigo or 0) in {401, 403} and "token" in texto


def periodo_de(data):
    if not data:
        return ""
    if isinstance(data, str):
        texto = data.strip()
        if len(texto) >= 7 and texto[4] == "-":
            return texto[:7]
        return ""
    return data.strftime("%Y-%m")


def rotulo_periodo(periodo):
    texto = (periodo or "").strip()
    if len(texto) < 7 or texto[4] != "-":
        return texto
    ano = texto[:4]
    mes = int(texto[5:7] or 0)
    if mes < 1 or mes > 12:
        return texto
    return f"{_MESES[mes]}/{ano}"


def substituicao_retroativa(data_emissao, data_substituicao):
    origem = periodo_de(data_emissao)
    destino = periodo_de(data_substituicao)
    if not origem or not destino:
        return False
    return destino > origem


def texto_tarja(data_substituicao, periodo_original):
    quando = data_substituicao
    if hasattr(quando, "strftime"):
        quando = quando.strftime("%d/%m/%Y")
    else:
        quando = str(quando or "")[:10]
    return (
        "Atenção: Esta nota foi substituída em um período posterior "
        f"({quando}). Para fins tributários e de apuração de faturamento, "
        "o valor desta receita pertence e compõe o período original de emissão "
        f"({rotulo_periodo(periodo_original)})."
    )


def tp_ret_pis_cofins(pis, cofins, csll):
    """Tipo de retenção da NFS-e nacional.

    0 não retido. 1 PIS/COFINS retidos. 3 PIS/COFINS/CSLL retidos juntos.
    """
    tem_unificada = float(pis or 0) > 0 or float(cofins or 0) > 0
    tem_csll = float(csll or 0) > 0
    if tem_unificada and tem_csll:
        return 3
    if tem_unificada:
        return 1
    return 0


def opcao_simples(regime_tributario, escolhida=None):
    bruto = (escolhida or "").strip()
    if bruto in {"1", "2", "3"}:
        return bruto
    if (regime_tributario or "") == "simples_nacional":
        return "3"
    return "1"


def pode_emitir_mensalidade(regime, status, data_pagamento):
    regime_norm = (regime or "competencia").strip().lower()
    situacao = (status or "").strip().lower()
    if situacao in {"cancelado", "cancelada"}:
        return False, "Mensalidade cancelada não gera NFS-e."
    if regime_norm == "caixa":
        if situacao != "pago":
            return False, "No regime de caixa a NFS-e só sai para mensalidade paga."
        if not data_pagamento:
            return False, "Informe a data de pagamento antes de emitir a NFS-e."
    return True, ""


def valor_da_nota(regime, valor, juros, multa, status):
    base = round(float(valor or 0), 2)
    situacao = (status or "").strip().lower()
    if (regime or "") == "caixa" or situacao == "pago":
        return round(base + float(juros or 0) + float(multa or 0), 2)
    return base


def competencia_da_mensalidade(regime, data_vencimento, data_pagamento, status):
    if (regime or "") == "caixa" and (status or "").strip().lower() == "pago" and data_pagamento:
        return periodo_de(data_pagamento)
    return periodo_de(data_vencimento)


def competencia_fiscal(nota):
    """Competência em que o valor da nota entra no faturamento.

    Nota cancelada ou já substituída não entra de novo. A substituta
    retroativa permanece no mês da nota original.
    """
    if (nota.get("status") or "") != STATUS_FATURADA:
        return ""
    return (nota.get("periodo_competencia_original") or periodo_de(nota.get("data_emissao")) or "")


def valor_na_competencia(notas, competencia):
    total = 0.0
    for nota in notas or []:
        if competencia_fiscal(nota) == competencia:
            total += float(nota.get("valor") or 0)
    return round(total, 2)


def _decimal(valor):
    return round(float(valor or 0), 2)


def montar_payload(prestador, tomador, servico, substituida=None, data_emissao=None):
    quando = data_emissao or agora_local()
    if hasattr(quando, "strftime"):
        emissao = quando.strftime("%Y-%m-%dT%H:%M:%S-03:00")
    else:
        emissao = str(quando)
    pis = _decimal(servico.get("valor_pis"))
    cofins = _decimal(servico.get("valor_cofins"))
    csll = _decimal(servico.get("valor_csll"))
    ir = _decimal(servico.get("valor_ir"))
    corpo_servico = {
        "aliquota": _decimal(servico.get("aliquota") if servico.get("aliquota") is not None else 2),
        "discriminacao": servico.get("discriminacao") or "Prestação de serviços.",
        "iss_retido": bool(servico.get("iss_retido")),
        "item_lista_servico": servico.get("item_lista_servico") or "08.01",
        "codigo_tributacao_municipio": servico.get("codigo_tributacao_municipio") or "0801",
        "valor_servicos": _decimal(servico.get("valor_servicos")),
        "valor_deducoes": _decimal(servico.get("valor_deducoes")),
        "valor_pis": pis,
        "valor_cofins": cofins,
        "valor_inss": _decimal(servico.get("valor_inss")),
        "valor_ir": ir,
        "valor_csll": csll,
        "tpRetPISCOFINS": int(servico.get("tpRetPISCOFINS") if servico.get("tpRetPISCOFINS") is not None else tp_ret_pis_cofins(pis, cofins, csll)),
        "reforma_tributaria": {
            "vIBS": _decimal((servico.get("reforma_tributaria") or {}).get("vIBS")),
            "vCBS": _decimal((servico.get("reforma_tributaria") or {}).get("vCBS")),
            "pIBS": _decimal((servico.get("reforma_tributaria") or {}).get("pIBS")),
            "pCBS": _decimal((servico.get("reforma_tributaria") or {}).get("pCBS")),
        },
    }
    beneficio = (servico.get("cBeneficio") or "").strip()
    if beneficio:
        corpo_servico["cBeneficio"] = beneficio
    payload = {
        "data_emissao": emissao,
        "prestador": {
            "cnpj": apenas_digitos(prestador.get("cnpj")),
            "inscricao_municipal": (prestador.get("inscricao_municipal") or "").strip(),
            "codigo_opcao_simples_nacional": str(prestador.get("codigo_opcao_simples_nacional") or "1"),
        },
        "tomador": {
            "razao_social": (tomador.get("razao_social") or "").strip(),
            "email": (tomador.get("email") or "").strip(),
            "endereco": {
                "logradouro": (tomador.get("logradouro") or "").strip(),
                "numero": (tomador.get("numero") or "S/N").strip() or "S/N",
                "bairro": (tomador.get("bairro") or "").strip(),
                "codigo_municipio": apenas_digitos(tomador.get("codigo_municipio")),
                "uf": (tomador.get("uf") or "").strip().upper()[:2],
                "cep": apenas_digitos(tomador.get("cep")),
            },
        },
        "servico": corpo_servico,
    }
    documento = apenas_digitos(tomador.get("documento") or tomador.get("cpf") or tomador.get("cnpj"))
    if len(documento) > 11:
        payload["tomador"]["cnpj"] = documento
    else:
        payload["tomador"]["cpf"] = documento
    if substituida and (substituida.get("numero_nfse") or substituida.get("chave") or substituida.get("codigo_verificacao")):
        vinculo = {
            "numero": str(substituida.get("numero_nfse") or ""),
            "codigo_verificacao": str(substituida.get("codigo_verificacao") or ""),
            "chave": str(substituida.get("chave") or ""),
        }
        payload["nfse_substituida"] = vinculo
        if vinculo["numero"]:
            payload["numero_nfse_substituida"] = vinculo["numero"]
    return payload


def url_base(ambiente):
    return URLS["producao" if (ambiente or "") == "producao" else "homologacao"]


def _host_focus(ambiente):
    if (ambiente or "") == "producao":
        return "https://api.focusnfe.com.br"
    return "https://homologacao.focusnfe.com.br"


def _mensagem_focus(corpo):
    if not isinstance(corpo, dict):
        return str(corpo or "")[:500]
    erros = corpo.get("erros") or corpo.get("errors") or []
    textos = []
    if isinstance(erros, list):
        for item in erros:
            if isinstance(item, dict):
                textos.append(str(item.get("mensagem") or item.get("message") or item))
            else:
                textos.append(str(item))
    elif erros:
        textos.append(str(erros))
    base = str(corpo.get("mensagem") or corpo.get("message") or "")
    junto = " ".join(parte for parte in [base, *textos] if parte).strip()
    return (junto or str(corpo))[:800]


def interpretar_resposta(codigo, corpo):
    dados = corpo if isinstance(corpo, dict) else {}
    status_api = str(dados.get("status") or "").strip().lower()
    status = _FOCUS_STATUS.get(status_api)
    if status is None:
        status = STATUS_ERRO if int(codigo or 0) >= 400 else STATUS_PENDENTE
    return {
        "status": status,
        "numero_nfse": str(dados.get("numero") or dados.get("numero_nfse") or "")[:40],
        "codigo_verificacao": str(dados.get("codigo_verificacao") or "")[:80],
        "chave": str(dados.get("chave_nfe") or dados.get("chave_nfse") or dados.get("chave") or "")[:80],
        "url_pdf": str(
            dados.get("caminho_danfe")
            or dados.get("url_danfse")
            or dados.get("url")
            or ""
        )[:500],
        "xml_caminho": str(
            dados.get("caminho_xml_nota_fiscal")
            or dados.get("caminho_xml")
            or ""
        )[:500],
        "mensagem": "" if status in {STATUS_FATURADA, STATUS_CANCELADA, STATUS_PENDENTE} else _mensagem_focus(dados),
    }


def cliente_focus(metodo, url, token, payload=None):
    import requests

    auth = ((token or "").strip(), "")
    if metodo == "POST":
        resposta = requests.post(url, json=payload, auth=auth, timeout=40)
    elif metodo == "DELETE":
        resposta = requests.delete(url, json=payload, auth=auth, timeout=40)
    else:
        resposta = requests.get(url, auth=auth, timeout=40)
    try:
        corpo = resposta.json()
    except Exception:
        corpo = {"mensagem": (resposta.text or "")[:500]}
    return resposta.status_code, corpo


def _emitir_uma_vez(token, ambiente, ref, payload, cliente, tentativas):
    base = url_base(ambiente)
    codigo, corpo = cliente("POST", f"{base}?ref={ref}", token, payload)
    lido = interpretar_resposta(codigo, corpo)
    espera = 0
    while lido["status"] == STATUS_PENDENTE and espera < tentativas and not token_recusado(lido.get("mensagem"), codigo):
        time.sleep(1.2)
        codigo, corpo = cliente("GET", f"{base}/{ref}", token, None)
        lido = interpretar_resposta(codigo, corpo)
        espera += 1
    return lido


def token_aceito(token, ambiente, cliente=None):
    cliente = cliente or cliente_focus
    try:
        codigo, corpo = cliente("GET", f"{url_base(ambiente)}/sonda-gestaoescolar", token, None)
    except Exception:
        return None
    mensagem = _mensagem_focus(corpo) if isinstance(corpo, dict) else str(corpo or "")
    if token_recusado(mensagem, codigo):
        return False
    if int(codigo or 0) in {401, 403}:
        return False
    return True


def ambiente_do_token(token, preferido="homologacao", cliente=None):
    token = limpar_token(token)
    if not token:
        return None, "Cole o token da Focus. Ele fica só no servidor."
    preferido = "producao" if preferido == "producao" else "homologacao"
    hom = token_aceito(token, "homologacao", cliente)
    pro = token_aceito(token, "producao", cliente)
    if hom is None and pro is None:
        return preferido, "Não foi possível consultar a Focus agora. O token foi salvo."
    if preferido == "producao" and pro:
        return "producao", "A Focus aceitou o token na produção."
    if hom:
        return "homologacao", "A Focus aceitou o token na homologação."
    if pro:
        return "producao", "Esse token não vale na homologação. Ele vale na produção, e o ambiente foi ajustado."
    return None, (
        "A Focus recusou o token na homologação e na produção. "
        "Abra o painel da Focus, copie o token de novo e cole sem espaço, aspas ou a palavra Token na frente."
    )


def emitir_focus(token, ambiente, ref, payload, cliente=None, tentativas=4):
    cliente = cliente or cliente_focus
    token = limpar_token(token)
    lido = _emitir_uma_vez(token, ambiente, ref, payload, cliente, tentativas)
    if token_recusado(lido.get("mensagem")):
        outro = "producao" if (ambiente or "") != "producao" else "homologacao"
        lido2 = _emitir_uma_vez(token, outro, ref, payload, cliente, tentativas)
        if not token_recusado(lido2.get("mensagem")):
            lido2["ambiente_corrigido"] = outro
            return lido2
        lido["mensagem"] = (
            "A Focus recusou o token na homologação e na produção. "
            "Em Configurações, cole de novo o token do painel da Focus, sem espaço, aspas ou a palavra Token na frente."
        )
    return lido


def consultar_focus(token, ambiente, ref, cliente=None):
    cliente = cliente or cliente_focus
    codigo, corpo = cliente("GET", f"{url_base(ambiente)}/{ref}", token, None)
    return interpretar_resposta(codigo, corpo)


def cancelar_focus(token, ambiente, ref, justificativa, cliente=None):
    cliente = cliente or cliente_focus
    codigo, corpo = cliente(
        "DELETE",
        f"{url_base(ambiente)}/{ref}",
        token,
        {"justificativa": justificativa},
    )
    lido = interpretar_resposta(codigo, corpo)
    if int(codigo or 0) < 400 and lido["status"] == STATUS_PENDENTE:
        lido["status"] = STATUS_CANCELADA
    return lido


def garantir_tabela_escola(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS notas_fiscais (
            id SERIAL PRIMARY KEY,
            aluno_id INT,
            mensalidade_id INT,
            ref VARCHAR(60) UNIQUE,
            numero_nfse VARCHAR(40),
            codigo_verificacao VARCHAR(80),
            chave VARCHAR(80),
            status VARCHAR(20) NOT NULL DEFAULT 'PENDENTE',
            nota_substituida_id INT,
            nota_substituta_id INT,
            data_emissao TIMESTAMP,
            data_cancelamento TIMESTAMP,
            data_substituicao TIMESTAMP,
            periodo_competencia VARCHAR(7),
            periodo_competencia_original VARCHAR(7),
            exibir_tarja_faturamento_retroativo BOOLEAN DEFAULT FALSE,
            valor NUMERIC(12,2) DEFAULT 0,
            tomador_nome VARCHAR(180),
            tomador_documento VARCHAR(20),
            mensagem_erro TEXT,
            url_pdf TEXT,
            xml_caminho TEXT,
            justificativa TEXT,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notas_mensalidade ON notas_fiscais (mensalidade_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notas_aluno ON notas_fiscais (aluno_id)")


def garantir_tabela_plataforma(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS plataforma_nfse (
            id INT PRIMARY KEY DEFAULT 1,
            token TEXT,
            ambiente VARCHAR(20) DEFAULT 'homologacao',
            cnpj VARCHAR(20),
            inscricao_municipal VARCHAR(40),
            codigo_municipio VARCHAR(10),
            regime_tributario VARCHAR(40) DEFAULT 'lucro_presumido',
            regime_apuracao VARCHAR(20) DEFAULT 'competencia',
            item_lista VARCHAR(10) DEFAULT '01.05',
            codigo_tributacao VARCHAR(20) DEFAULT '0105',
            aliquota NUMERIC(6,2) DEFAULT 2,
            opcao_simples VARCHAR(2) DEFAULT '1',
            c_beneficio VARCHAR(20),
            p_ibs NUMERIC(8,4) DEFAULT 0,
            p_cbs NUMERIC(8,4) DEFAULT 0,
            certificado_pfx BYTEA,
            certificado_nome VARCHAR(180),
            certificado_senha VARCHAR(255),
            logradouro VARCHAR(150),
            numero VARCHAR(20),
            bairro VARCHAR(100),
            uf CHAR(2),
            cep VARCHAR(9)
        )
        """
    )
    cursor.execute("INSERT INTO plataforma_nfse (id) VALUES (1) ON CONFLICT (id) DO NOTHING")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS plataforma_notas_fiscais (
            id SERIAL PRIMARY KEY,
            escola_id INT,
            cobranca_id INT,
            ref VARCHAR(60) UNIQUE,
            numero_nfse VARCHAR(40),
            codigo_verificacao VARCHAR(80),
            chave VARCHAR(80),
            status VARCHAR(20) NOT NULL DEFAULT 'PENDENTE',
            nota_substituida_id INT,
            nota_substituta_id INT,
            data_emissao TIMESTAMP,
            data_cancelamento TIMESTAMP,
            data_substituicao TIMESTAMP,
            periodo_competencia VARCHAR(7),
            periodo_competencia_original VARCHAR(7),
            exibir_tarja_faturamento_retroativo BOOLEAN DEFAULT FALSE,
            valor NUMERIC(12,2) DEFAULT 0,
            tomador_nome VARCHAR(180),
            tomador_documento VARCHAR(20),
            mensagem_erro TEXT,
            url_pdf TEXT,
            xml_caminho TEXT,
            justificativa TEXT,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _aplicar_leitura(nota, lido, quando):
    nota_status = lido["status"]
    if nota.get("status") == STATUS_SUBSTITUIDA and nota_status == STATUS_FATURADA:
        nota_status = STATUS_SUBSTITUIDA
    campos = {
        "status": nota_status,
        "numero_nfse": lido.get("numero_nfse") or nota.get("numero_nfse"),
        "codigo_verificacao": lido.get("codigo_verificacao") or nota.get("codigo_verificacao"),
        "chave": lido.get("chave") or nota.get("chave"),
        "url_pdf": lido.get("url_pdf") or nota.get("url_pdf"),
        "xml_caminho": lido.get("xml_caminho") or nota.get("xml_caminho"),
        "mensagem_erro": lido.get("mensagem") or "",
    }
    if nota_status == STATUS_CANCELADA:
        campos["data_cancelamento"] = quando
    return campos


def _gravar_nota(cursor, tabela, nota_id, campos):
    partes = []
    valores = []
    for coluna, valor in campos.items():
        partes.append(f"{coluna} = %s")
        valores.append(valor)
    valores.append(nota_id)
    cursor.execute(f"UPDATE {tabela} SET {', '.join(partes)} WHERE id = %s", valores)


def _cfg_escola(cursor):
    garantir_tabela_escola(cursor)
    cursor.execute("SELECT * FROM configuracoes WHERE id = 1")
    cfg = cursor.fetchone() or {}
    if not isinstance(cfg, dict):
        return {}
    return cfg


def _gravar_ambiente(cursor, ambiente, plataforma=False):
    if plataforma:
        cursor.execute("UPDATE plataforma_nfse SET ambiente = %s WHERE id = 1", (ambiente,))
    else:
        cursor.execute("UPDATE configuracoes SET nfse_ambiente = %s WHERE id = 1", (ambiente,))
    _commit(cursor)


def _aviso_ambiente(lido):
    ambiente = lido.get("ambiente_corrigido")
    if not ambiente:
        return ""
    nome = "produção" if ambiente == "producao" else "homologação"
    return f" O ambiente foi ajustado para {nome}, porque o token não valia no outro."


def _exigir_credencial(cfg):
    token = limpar_token(cfg.get("nfse_token") or cfg.get("token"))
    if not token:
        raise ValueError("Informe o token da Focus em Configurações, no bloco da nota fiscal.")
    cnpj = apenas_digitos(cfg.get("nfse_cnpj") or cfg.get("cnpj"))
    if len(cnpj) != 14:
        raise ValueError("Informe o CNPJ do prestador com 14 números.")
    im = (cfg.get("nfse_inscricao_municipal") or cfg.get("inscricao_municipal") or "").strip()
    if not im:
        raise ValueError("Informe a inscrição municipal do prestador.")
    if not apenas_digitos(cfg.get("nfse_codigo_municipio") or cfg.get("codigo_municipio")):
        raise ValueError("Informe o código IBGE do município.")
    return token


def _reforma(cfg, valor):
    p_ibs = float(cfg.get("nfse_p_ibs") if cfg.get("nfse_p_ibs") is not None else cfg.get("p_ibs") or 0)
    p_cbs = float(cfg.get("nfse_p_cbs") if cfg.get("nfse_p_cbs") is not None else cfg.get("p_cbs") or 0)
    return {
        "vIBS": round(valor * p_ibs / 100, 2),
        "vCBS": round(valor * p_cbs / 100, 2),
        "pIBS": p_ibs,
        "pCBS": p_cbs,
    }


def _prestador_de(cfg):
    return {
        "cnpj": cfg.get("nfse_cnpj") or cfg.get("cnpj"),
        "inscricao_municipal": cfg.get("nfse_inscricao_municipal") or cfg.get("inscricao_municipal"),
        "codigo_opcao_simples_nacional": opcao_simples(
            cfg.get("regime_tributario"),
            cfg.get("nfse_opcao_simples") or cfg.get("opcao_simples"),
        ),
    }


def _servico_de(cfg, valor, discriminacao, item_padrao, codigo_padrao):
    pis = float(cfg.get("nfse_valor_pis") or 0)
    cofins = float(cfg.get("nfse_valor_cofins") or 0)
    csll = float(cfg.get("nfse_valor_csll") or 0)
    ir = float(cfg.get("nfse_valor_ir") or 0)
    return {
        "aliquota": cfg.get("nfse_aliquota") if cfg.get("nfse_aliquota") is not None else cfg.get("aliquota") or 2,
        "discriminacao": discriminacao,
        "iss_retido": bool(cfg.get("nfse_iss_retido")),
        "item_lista_servico": cfg.get("nfse_item_lista") or cfg.get("item_lista") or item_padrao,
        "codigo_tributacao_municipio": cfg.get("nfse_codigo_tributacao") or cfg.get("codigo_tributacao") or codigo_padrao,
        "valor_servicos": valor,
        "valor_pis": pis,
        "valor_cofins": cofins,
        "valor_csll": csll,
        "valor_ir": ir,
        "tpRetPISCOFINS": tp_ret_pis_cofins(pis, cofins, csll),
        "cBeneficio": cfg.get("nfse_c_beneficio") or cfg.get("c_beneficio") or "",
        "reforma_tributaria": _reforma(cfg, valor),
    }


def _id_linha(row):
    if isinstance(row, dict):
        return row.get("id")
    return row[0]


def _buscar_tomador_aluno(cursor, aluno_id, codigo_municipio):
    cursor.execute("SELECT * FROM alunos WHERE id = %s", (aluno_id,))
    aluno = cursor.fetchone() or {}
    cursor.execute(
        """
        SELECT nome_completo, cpf, email
        FROM responsaveis_aluno
        WHERE aluno_id = %s AND COALESCE(cpf, '') <> ''
        ORDER BY id
        LIMIT 1
        """,
        (aluno_id,),
    )
    responsavel = cursor.fetchone() or {}
    documento = apenas_digitos((responsavel or {}).get("cpf") or aluno.get("cpf"))
    nome = ((responsavel or {}).get("nome_completo") or aluno.get("nome_completo") or "").strip()
    if len(documento) != 11 and len(documento) != 14:
        raise ValueError("Cadastre o CPF do responsável ou do aluno antes de emitir a NFS-e.")
    if not nome:
        raise ValueError("Cadastre o nome do tomador antes de emitir a NFS-e.")
    return {
        "documento": documento,
        "razao_social": nome,
        "email": (responsavel or {}).get("email") or aluno.get("email") or "",
        "logradouro": aluno.get("rua") or "",
        "numero": aluno.get("numero") or "S/N",
        "bairro": aluno.get("bairro") or "",
        "codigo_municipio": codigo_municipio,
        "uf": aluno.get("estado") or "",
        "cep": aluno.get("cep") or "",
    }


def _nota_ativa_mensalidade(cursor, mensalidade_id):
    cursor.execute(
        """
        SELECT * FROM notas_fiscais
        WHERE mensalidade_id = %s AND status IN ('FATURADA', 'PENDENTE')
        ORDER BY id DESC
        LIMIT 1
        """,
        (mensalidade_id,),
    )
    return cursor.fetchone()


def _commit(cursor):
    conexao = getattr(cursor, "connection", None)
    if conexao is not None:
        conexao.commit()


def _chamar_focus(cursor, tabela, nota_id, funcao):
    try:
        return funcao()
    except Exception as erro:
        if isinstance(erro, ValueError):
            raise
        _gravar_nota(
            cursor,
            tabela,
            nota_id,
            {"status": STATUS_ERRO, "mensagem_erro": "Falha de comunicação com a Focus."},
        )
        _commit(cursor)
        raise ValueError("Não foi possível falar com a Focus. A nota ficou registrada com erro.") from erro


def emitir_mensalidade(cursor, mensalidade_id, cliente=None):
    cfg = _cfg_escola(cursor)
    token = _exigir_credencial(cfg)
    regime = (cfg.get("regime_apuracao") or "competencia").strip().lower()
    cursor.execute("SELECT * FROM financeiro_mensalidades WHERE id = %s", (mensalidade_id,))
    mensalidade = cursor.fetchone()
    if not mensalidade:
        raise ValueError("Mensalidade não encontrada.")
    ativa = _nota_ativa_mensalidade(cursor, mensalidade_id)
    if ativa and ativa.get("status") == STATUS_FATURADA:
        raise ValueError("Esta mensalidade já tem NFS-e faturada. Cancele ou substitua essa nota.")
    if ativa and ativa.get("status") == STATUS_PENDENTE:
        return consultar_nota(cursor, ativa["id"], "notas_fiscais", cliente)
    ok, motivo = pode_emitir_mensalidade(regime, mensalidade.get("status"), mensalidade.get("data_pagamento"))
    if not ok:
        raise ValueError(motivo)
    valor = valor_da_nota(
        regime,
        mensalidade.get("valor"),
        mensalidade.get("juros_valor"),
        mensalidade.get("multa_valor"),
        mensalidade.get("status"),
    )
    if valor <= 0:
        raise ValueError("A mensalidade precisa ter valor maior que zero.")
    competencia = competencia_da_mensalidade(
        regime,
        mensalidade.get("data_vencimento"),
        mensalidade.get("data_pagamento"),
        mensalidade.get("status"),
    )
    tomador = _buscar_tomador_aluno(cursor, mensalidade.get("aluno_id"), cfg.get("nfse_codigo_municipio"))
    mes_ano = competencia[5:7] + "/" + competencia[:4] if len(competencia) >= 7 else ""
    servico = _servico_de(
        cfg,
        valor,
        f"Prestação de serviços educacionais referente à mensalidade escolar. Competência: {mes_ano}.",
        "08.01",
        "0801",
    )
    quando = agora_local()
    ref = f"m{mensalidade_id}t{int(quando.timestamp())}"
    cursor.execute(
        """
        INSERT INTO notas_fiscais (
            aluno_id, mensalidade_id, ref, status, data_emissao,
            periodo_competencia, periodo_competencia_original, valor,
            tomador_nome, tomador_documento
        ) VALUES (%s, %s, %s, 'PENDENTE', %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            mensalidade.get("aluno_id"),
            mensalidade_id,
            ref,
            quando,
            competencia,
            competencia,
            valor,
            tomador["razao_social"],
            tomador["documento"],
        ),
    )
    nota_id = _id_linha(cursor.fetchone())
    _commit(cursor)
    payload = montar_payload(_prestador_de(cfg), tomador, servico, data_emissao=quando)
    lido = _chamar_focus(
        cursor,
        "notas_fiscais",
        nota_id,
        lambda: emitir_focus(token, cfg.get("nfse_ambiente"), ref, payload, cliente),
    )
    _gravar_nota(cursor, "notas_fiscais", nota_id, _aplicar_leitura({"status": STATUS_PENDENTE}, lido, quando))
    if lido.get("ambiente_corrigido"):
        _gravar_ambiente(cursor, lido["ambiente_corrigido"])
    else:
        _commit(cursor)
    aviso = _aviso_ambiente(lido)
    if lido["status"] == STATUS_ERRO:
        raise ValueError(lido["mensagem"] or "A Focus recusou a NFS-e.")
    if lido["status"] == STATUS_PENDENTE:
        return "NFS-e enviada e ainda pendente de autorização. Atualize o status para baixar o XML e a DANFSe." + aviso
    return (
        f"NFS-e faturada{(' nº ' + lido['numero_nfse']) if lido.get('numero_nfse') else ''}. "
        "O XML e a DANFSe estão na nota." + aviso
    )


def consultar_nota(cursor, nota_id, tabela, cliente=None):
    cursor.execute(f"SELECT * FROM {tabela} WHERE id = %s", (nota_id,))
    nota = cursor.fetchone()
    if not nota:
        raise ValueError("Nota fiscal não encontrada.")
    if tabela == "notas_fiscais":
        cfg = _cfg_escola(cursor)
        token = _exigir_credencial(cfg)
        ambiente = cfg.get("nfse_ambiente")
    else:
        cfg = _cfg_plataforma(cursor)
        token = _exigir_credencial(cfg)
        ambiente = cfg.get("ambiente")
    lido = consultar_focus(token, ambiente, nota.get("ref"), cliente)
    quando = agora_local()
    _gravar_nota(cursor, tabela, nota_id, _aplicar_leitura(nota, lido, quando))
    if lido["status"] == STATUS_FATURADA and nota.get("nota_substituida_id") and nota.get("status") != STATUS_FATURADA:
        retro = (nota.get("periodo_competencia") or "") > (nota.get("periodo_competencia_original") or "9999")
        _gravar_nota(
            cursor,
            tabela,
            nota_id,
            {"exibir_tarja_faturamento_retroativo": retro},
        )
        _gravar_nota(
            cursor,
            tabela,
            nota.get("nota_substituida_id"),
            {
                "status": STATUS_SUBSTITUIDA,
                "nota_substituta_id": nota_id,
                "data_substituicao": quando,
                "exibir_tarja_faturamento_retroativo": retro,
                "mensagem_erro": "",
            },
        )
    _commit(cursor)
    return "Status da NFS-e atualizado."


def cancelar_nota(cursor, nota_id, tabela, justificativa, cliente=None):
    texto = (justificativa or "").strip()
    if len(texto) < 15:
        raise ValueError("A justificativa do cancelamento precisa ter pelo menos 15 caracteres.")
    cursor.execute(f"SELECT * FROM {tabela} WHERE id = %s", (nota_id,))
    nota = cursor.fetchone()
    if not nota:
        raise ValueError("Nota fiscal não encontrada.")
    if nota.get("status") != STATUS_FATURADA:
        raise ValueError("Só uma NFS-e faturada pode ser cancelada.")
    if tabela == "notas_fiscais":
        cfg = _cfg_escola(cursor)
        token = _exigir_credencial(cfg)
        ambiente = cfg.get("nfse_ambiente")
    else:
        cfg = _cfg_plataforma(cursor)
        token = _exigir_credencial(cfg)
        ambiente = cfg.get("ambiente")
    lido = cancelar_focus(token, ambiente, nota.get("ref"), texto, cliente)
    if lido["status"] != STATUS_CANCELADA:
        _gravar_nota(cursor, tabela, nota_id, {"mensagem_erro": lido.get("mensagem") or "Cancelamento recusado."})
        _commit(cursor)
        raise ValueError(lido.get("mensagem") or "A Focus não homologou o cancelamento.")
    quando = agora_local()
    _gravar_nota(
        cursor,
        tabela,
        nota_id,
        {
            "status": STATUS_CANCELADA,
            "data_cancelamento": quando,
            "justificativa": texto,
            "mensagem_erro": "",
        },
    )
    _commit(cursor)
    return "NFS-e cancelada. O valor deixa de compor o faturamento."


def substituir_nota(cursor, nota_id, tabela, cliente=None, contexto=None):
    cursor.execute(f"SELECT * FROM {tabela} WHERE id = %s", (nota_id,))
    antiga = cursor.fetchone()
    if not antiga:
        raise ValueError("Nota fiscal não encontrada.")
    if antiga.get("status") != STATUS_FATURADA:
        raise ValueError("Só uma NFS-e faturada pode ser substituída.")
    quando = agora_local()
    retro = substituicao_retroativa(antiga.get("data_emissao"), quando)
    periodo_original = antiga.get("periodo_competencia_original") or periodo_de(antiga.get("data_emissao"))
    if tabela == "notas_fiscais":
        return _substituir_mensalidade(cursor, antiga, quando, retro, periodo_original, cliente)
    return _substituir_plataforma(cursor, antiga, quando, retro, periodo_original, cliente, contexto or {})


def _substituir_mensalidade(cursor, antiga, quando, retro, periodo_original, cliente):
    cfg = _cfg_escola(cursor)
    token = _exigir_credencial(cfg)
    cursor.execute("SELECT * FROM financeiro_mensalidades WHERE id = %s", (antiga.get("mensalidade_id"),))
    mensalidade = cursor.fetchone()
    if not mensalidade:
        raise ValueError("Mensalidade da nota não encontrada.")
    regime = (cfg.get("regime_apuracao") or "competencia").strip().lower()
    valor = float(antiga.get("valor") or 0) or valor_da_nota(
        regime,
        mensalidade.get("valor"),
        mensalidade.get("juros_valor"),
        mensalidade.get("multa_valor"),
        mensalidade.get("status"),
    )
    tomador = _buscar_tomador_aluno(cursor, antiga.get("aluno_id") or mensalidade.get("aluno_id"), cfg.get("nfse_codigo_municipio"))
    competencia_emissao = periodo_de(quando)
    fiscal = periodo_original if retro else competencia_emissao
    mes_ano = fiscal[5:7] + "/" + fiscal[:4] if len(fiscal) >= 7 else ""
    servico = _servico_de(
        cfg,
        valor,
        f"Prestação de serviços educacionais referente à mensalidade escolar. Competência: {mes_ano}. Nota substituta.",
        "08.01",
        "0801",
    )
    ref = f"s{antiga['id']}t{int(quando.timestamp())}"
    cursor.execute(
        """
        INSERT INTO notas_fiscais (
            aluno_id, mensalidade_id, ref, status, nota_substituida_id, data_emissao,
            periodo_competencia, periodo_competencia_original,
            exibir_tarja_faturamento_retroativo, valor, tomador_nome, tomador_documento
        ) VALUES (%s, %s, %s, 'PENDENTE', %s, %s, %s, %s, FALSE, %s, %s, %s)
        RETURNING id
        """,
        (
            antiga.get("aluno_id"),
            antiga.get("mensalidade_id"),
            ref,
            antiga["id"],
            quando,
            competencia_emissao,
            fiscal,
            valor,
            tomador["razao_social"],
            tomador["documento"],
        ),
    )
    nova_id = _id_linha(cursor.fetchone())
    _commit(cursor)
    payload = montar_payload(_prestador_de(cfg), tomador, servico, substituida=antiga, data_emissao=quando)
    lido = _chamar_focus(
        cursor,
        "notas_fiscais",
        nova_id,
        lambda: emitir_focus(token, cfg.get("nfse_ambiente"), ref, payload, cliente),
    )
    _finalizar_substituicao(cursor, "notas_fiscais", antiga, nova_id, lido, quando, retro)
    if lido["status"] == STATUS_ERRO:
        raise ValueError(lido["mensagem"] or "A Focus recusou a nota substituta.")
    if lido["status"] == STATUS_PENDENTE:
        return "Nota substituta enviada e ainda pendente. A nota original continua faturada até a autorização."
    return "NFS-e substituída. A nova nota aponta a nota original."


def _finalizar_substituicao(cursor, tabela, antiga, nova_id, lido, quando, retro):
    campos_nova = _aplicar_leitura({"status": STATUS_PENDENTE}, lido, quando)
    if lido["status"] == STATUS_FATURADA:
        campos_nova["exibir_tarja_faturamento_retroativo"] = retro
    _gravar_nota(cursor, tabela, nova_id, campos_nova)
    if lido["status"] == STATUS_FATURADA:
        _gravar_nota(
            cursor,
            tabela,
            antiga["id"],
            {
                "status": STATUS_SUBSTITUIDA,
                "nota_substituta_id": nova_id,
                "data_substituicao": quando,
                "exibir_tarja_faturamento_retroativo": retro,
                "mensagem_erro": "",
            },
        )
    _commit(cursor)


def anexar_ultima_nota(cursor, linhas, chave="id"):
    ids = [linha.get(chave) for linha in linhas or [] if linha.get(chave)]
    if not ids:
        return
    garantir_tabela_escola(cursor)
    cursor.execute(
        """
        SELECT DISTINCT ON (mensalidade_id) *
        FROM notas_fiscais
        WHERE mensalidade_id = ANY(%s)
        ORDER BY mensalidade_id, id DESC
        """,
        (ids,),
    )
    por_mensalidade = {nota["mensalidade_id"]: _enriquecer(nota) for nota in cursor.fetchall() or []}
    for linha in linhas:
        linha["nfse"] = por_mensalidade.get(linha.get(chave))


def _enriquecer(nota):
    if not nota:
        return None
    item = dict(nota)
    if item.get("exibir_tarja_faturamento_retroativo"):
        item["tarja"] = texto_tarja(
            item.get("data_substituicao") or item.get("data_emissao"),
            item.get("periodo_competencia_original"),
        )
    return item


def listar_notas_escola(cursor, status=None, aluno_id=None):
    garantir_tabela_escola(cursor)
    sql = """
        SELECT n.*,
               a.nome_completo AS aluno_nome,
               a.matricula,
               s.numero_nfse AS substituta_numero,
               s.status AS substituta_status,
               o.numero_nfse AS substituida_numero,
               o.status AS substituida_status,
               o.data_emissao AS substituida_emissao
        FROM notas_fiscais n
        LEFT JOIN alunos a ON a.id = n.aluno_id
        LEFT JOIN notas_fiscais s ON s.id = n.nota_substituta_id
        LEFT JOIN notas_fiscais o ON o.id = n.nota_substituida_id
        WHERE 1=1
    """
    params = []
    if status in STATUS_NOTA:
        sql += " AND n.status = %s"
        params.append(status)
    if aluno_id:
        sql += " AND n.aluno_id = %s"
        params.append(aluno_id)
    sql += " ORDER BY a.nome_completo NULLS LAST, n.id DESC"
    cursor.execute(sql, params)
    grupos = []
    indice = {}
    for bruta in cursor.fetchall() or []:
        nota = _enriquecer(bruta)
        chave = nota.get("aluno_id") or 0
        if chave not in indice:
            indice[chave] = {
                "aluno_id": nota.get("aluno_id"),
                "aluno_nome": nota.get("aluno_nome") or "Sem aluno",
                "matricula": nota.get("matricula") or "",
                "notas": [],
            }
            grupos.append(indice[chave])
        indice[chave]["notas"].append(nota)
    return grupos


def faturamento_das_notas(cursor, competencia):
    garantir_tabela_escola(cursor)
    cursor.execute("SELECT * FROM notas_fiscais")
    notas = [dict(item) for item in cursor.fetchall() or []]
    return valor_na_competencia(notas, competencia)


def listar_alunos_nfse(cursor):
    cursor.execute(
        """
        SELECT a.id, a.nome_completo, a.matricula, a.cpf,
               (
                   SELECT t.nome FROM turma_alunos ta
                   JOIN turmas t ON t.id = ta.turma_id
                   WHERE ta.aluno_id = a.id
                   ORDER BY ta.turma_id DESC
                   LIMIT 1
               ) AS turma_nome
        FROM alunos a
        ORDER BY a.nome_completo
        """
    )
    return cursor.fetchall() or []


def listar_mensalidades_emissao(cursor, aluno_id):
    if not aluno_id:
        return []
    garantir_tabela_escola(cursor)
    cursor.execute(
        """
        SELECT f.id, f.descricao, f.valor, f.data_vencimento, f.data_pagamento, f.status,
               n.id AS nota_id, n.status AS nota_status, n.numero_nfse
        FROM financeiro_mensalidades f
        LEFT JOIN LATERAL (
            SELECT id, status, numero_nfse
            FROM notas_fiscais
            WHERE mensalidade_id = f.id
            ORDER BY id DESC
            LIMIT 1
        ) n ON TRUE
        WHERE f.aluno_id = %s
        ORDER BY f.data_vencimento DESC
        """,
        (aluno_id,),
    )
    return cursor.fetchall() or []


def _baixar_focus(token, ambiente, caminho):
    import requests

    if not caminho:
        raise ValueError("A Focus ainda não devolveu este arquivo. Atualize o status da nota.")
    texto = str(caminho)
    if texto.startswith("http://") or texto.startswith("https://"):
        url = texto
    else:
        url = _host_focus(ambiente) + (texto if texto.startswith("/") else "/" + texto)
    resposta = requests.get(url, auth=((token or "").strip(), ""), timeout=40)
    if resposta.status_code >= 400 and texto.startswith("http"):
        resposta = requests.get(url, timeout=40)
    if resposta.status_code >= 400 or not resposta.content:
        raise ValueError("A Focus não entregou o arquivo desta nota.")
    mime = (resposta.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    return resposta.content, mime


def documento_da_nota(cursor, nota_id, tipo):
    cursor.execute("SELECT * FROM notas_fiscais WHERE id = %s", (nota_id,))
    nota = cursor.fetchone()
    if not nota:
        raise ValueError("Nota fiscal não encontrada.")
    if nota.get("status") not in {STATUS_FATURADA, STATUS_CANCELADA, STATUS_SUBSTITUIDA}:
        raise ValueError("O XML e a DANFSe ficam disponíveis depois que a nota é autorizada.")
    campo = "xml_caminho" if tipo == "xml" else "url_pdf"
    if not nota.get(campo):
        consultar_nota(cursor, nota_id, "notas_fiscais")
        cursor.execute("SELECT * FROM notas_fiscais WHERE id = %s", (nota_id,))
        nota = cursor.fetchone()
    cfg = _cfg_escola(cursor)
    token = _exigir_credencial(cfg)
    conteudo, mime = _baixar_focus(token, cfg.get("nfse_ambiente"), nota.get(campo))
    numero = nota.get("numero_nfse") or nota_id
    if tipo == "xml":
        return conteudo, "application/xml", f"nfse_{numero}.xml"
    if "html" in mime or conteudo[:80].lstrip().lower().startswith(b"<!doctype") or conteudo[:20].lstrip().startswith(b"<"):
        return conteudo, "text/html", f"danfse_{numero}.html"
    return conteudo, "application/pdf", f"danfse_{numero}.pdf"


def salvar_config_escola(cursor, form, arquivo):
    atual = _cfg_escola(cursor)
    token = limpar_token(form.get("nfse_token")) or limpar_token(atual.get("nfse_token"))
    senha = (form.get("nfse_certificado_senha") or "").strip() or (atual.get("nfse_certificado_senha") or "")
    pfx = atual.get("nfse_certificado_pfx")
    nome_arquivo = atual.get("nfse_certificado_nome") or ""
    if arquivo and getattr(arquivo, "filename", ""):
        nome = arquivo.filename.lower()
        if not nome.endswith((".pfx", ".p12")):
            raise ValueError("O certificado A1 precisa ser um arquivo .pfx ou .p12.")
        conteudo = arquivo.read()
        if not conteudo:
            raise ValueError("O arquivo do certificado veio vazio.")
        if len(conteudo) > 5 * 1024 * 1024:
            raise ValueError("O certificado passou de 5 MB.")
        if not senha:
            raise ValueError("Informe a senha do certificado A1.")
        pfx = conteudo
        nome_arquivo = arquivo.filename[:180]
    ambiente = "producao" if (form.get("nfse_ambiente") or "") == "producao" else "homologacao"
    aceito = True
    aviso = "O token fica só no servidor."
    if token:
        ajustado, aviso = ambiente_do_token(token, ambiente)
        if ajustado:
            ambiente = ajustado
        else:
            aceito = False
    item = (form.get("nfse_item_lista") or "08.01").strip()[:10]
    dados = (
        token,
        ambiente,
        apenas_digitos(form.get("nfse_cnpj"))[:20],
        (form.get("nfse_inscricao_municipal") or "").strip()[:40],
        apenas_digitos(form.get("nfse_codigo_municipio"))[:10],
        item,
        (form.get("nfse_codigo_tributacao") or "0801").strip()[:20],
        _decimal(form.get("nfse_aliquota") or 2),
        opcao_simples(form.get("regime_tributario") or atual.get("regime_tributario"), form.get("nfse_opcao_simples")),
        (form.get("nfse_c_beneficio") or "").strip()[:20],
        _decimal(form.get("nfse_p_ibs") or 0),
        _decimal(form.get("nfse_p_cbs") or 0),
        pfx,
        nome_arquivo,
        senha,
    )
    cursor.execute("SELECT id FROM configuracoes WHERE id = 1")
    if cursor.fetchone():
        cursor.execute(
            """
            UPDATE configuracoes SET
                nfse_token = %s,
                nfse_ambiente = %s,
                nfse_cnpj = %s,
                nfse_inscricao_municipal = %s,
                nfse_codigo_municipio = %s,
                nfse_item_lista = %s,
                nfse_codigo_tributacao = %s,
                nfse_aliquota = %s,
                nfse_opcao_simples = %s,
                nfse_c_beneficio = %s,
                nfse_p_ibs = %s,
                nfse_p_cbs = %s,
                nfse_certificado_pfx = %s,
                nfse_certificado_nome = %s,
                nfse_certificado_senha = %s
            WHERE id = 1
            """,
            dados,
        )
    else:
        cursor.execute(
            """
            INSERT INTO configuracoes (
                id, nfse_token, nfse_ambiente, nfse_cnpj, nfse_inscricao_municipal,
                nfse_codigo_municipio, nfse_item_lista, nfse_codigo_tributacao, nfse_aliquota,
                nfse_opcao_simples, nfse_c_beneficio, nfse_p_ibs, nfse_p_cbs,
                nfse_certificado_pfx, nfse_certificado_nome, nfse_certificado_senha
            ) VALUES (1, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            dados,
        )
    return aceito, aviso


def preparar_config_tela(config):
    item = dict(config or {})
    item["nfse_tem_certificado"] = bool(item.get("nfse_certificado_pfx"))
    item["nfse_token_mascarado"] = mascarar_token(item.get("nfse_token"))
    item.pop("nfse_token", None)
    item.pop("nfse_certificado_senha", None)
    item.pop("nfse_certificado_pfx", None)
    return item


def _cfg_plataforma(cursor):
    garantir_tabela_plataforma(cursor)
    cursor.execute(
        """
        SELECT id, token, ambiente, cnpj, inscricao_municipal, codigo_municipio,
               regime_tributario, regime_apuracao, item_lista, codigo_tributacao, aliquota,
               opcao_simples, c_beneficio, p_ibs, p_cbs, certificado_nome,
               (certificado_pfx IS NOT NULL) AS tem_certificado,
               logradouro, numero, bairro, uf, cep
        FROM plataforma_nfse WHERE id = 1
        """
    )
    return cursor.fetchone() or {}


def ler_config_plataforma_tela(cursor):
    cfg = dict(_cfg_plataforma(cursor) or {})
    cfg["token_mascarado"] = mascarar_token(cfg.get("token"))
    cfg.pop("token", None)
    return cfg


def salvar_config_plataforma(cursor, form, arquivo):
    garantir_tabela_plataforma(cursor)
    cursor.execute("SELECT token, certificado_pfx, certificado_nome, certificado_senha FROM plataforma_nfse WHERE id = 1")
    atual = cursor.fetchone() or {}
    token = limpar_token(form.get("nfse_token")) or limpar_token(atual.get("token"))
    senha = (form.get("nfse_certificado_senha") or "").strip() or (atual.get("certificado_senha") or "")
    pfx = atual.get("certificado_pfx")
    nome_arquivo = atual.get("certificado_nome") or ""
    if arquivo and getattr(arquivo, "filename", ""):
        nome = arquivo.filename.lower()
        if not nome.endswith((".pfx", ".p12")):
            raise ValueError("O certificado A1 precisa ser um arquivo .pfx ou .p12.")
        conteudo = arquivo.read()
        if not conteudo:
            raise ValueError("O arquivo do certificado veio vazio.")
        if len(conteudo) > 5 * 1024 * 1024:
            raise ValueError("O certificado passou de 5 MB.")
        if not senha:
            raise ValueError("Informe a senha do certificado A1.")
        pfx = conteudo
        nome_arquivo = arquivo.filename[:180]
    item = (form.get("item_lista") or "01.05").strip()
    if item not in {"01.05", "01.07"}:
        item = "01.05"
    codigo = "0107" if item == "01.07" else "0105"
    cursor.execute(
        """
        UPDATE plataforma_nfse SET
            token = %s,
            ambiente = %s,
            cnpj = %s,
            inscricao_municipal = %s,
            codigo_municipio = %s,
            regime_tributario = %s,
            regime_apuracao = %s,
            item_lista = %s,
            codigo_tributacao = %s,
            aliquota = %s,
            opcao_simples = %s,
            c_beneficio = %s,
            p_ibs = %s,
            p_cbs = %s,
            certificado_pfx = %s,
            certificado_nome = %s,
            certificado_senha = %s,
            logradouro = %s,
            numero = %s,
            bairro = %s,
            uf = %s,
            cep = %s
        WHERE id = 1
        """,
        (
            token,
            "producao" if (form.get("nfse_ambiente") or "") == "producao" else "homologacao",
            apenas_digitos(form.get("nfse_cnpj"))[:20],
            (form.get("nfse_inscricao_municipal") or "").strip()[:40],
            apenas_digitos(form.get("nfse_codigo_municipio"))[:10],
            form.get("regime_tributario") or "lucro_presumido",
            "caixa" if (form.get("regime_apuracao") or "") == "caixa" else "competencia",
            item,
            codigo,
            _decimal(form.get("nfse_aliquota") or 2),
            opcao_simples(form.get("regime_tributario"), form.get("nfse_opcao_simples")),
            (form.get("nfse_c_beneficio") or "").strip()[:20],
            _decimal(form.get("nfse_p_ibs") or 0),
            _decimal(form.get("nfse_p_cbs") or 0),
            pfx,
            nome_arquivo,
            senha,
            (form.get("logradouro") or "").strip()[:150],
            (form.get("numero") or "").strip()[:20],
            (form.get("bairro") or "").strip()[:100],
            (form.get("uf") or "").strip().upper()[:2],
            apenas_digitos(form.get("cep"))[:9],
        ),
    )


def salvar_tomador_escola(cursor, escola_id, form):
    cursor.execute(
        """
        UPDATE plataforma_escolas SET
            cnpj = %s,
            nfse_email = %s,
            nfse_logradouro = %s,
            nfse_numero = %s,
            nfse_bairro = %s,
            nfse_codigo_municipio = %s,
            nfse_uf = %s,
            nfse_cep = %s
        WHERE id = %s
        """,
        (
            apenas_digitos(form.get("cnpj"))[:20],
            (form.get("nfse_email") or "").strip()[:150],
            (form.get("logradouro") or "").strip()[:150],
            (form.get("numero") or "").strip()[:20],
            (form.get("bairro") or "").strip()[:100],
            apenas_digitos(form.get("codigo_municipio"))[:10],
            (form.get("uf") or "").strip().upper()[:2],
            apenas_digitos(form.get("cep"))[:9],
            escola_id,
        ),
    )


def _tomador_escola(escola, cfg):
    documento = apenas_digitos(escola.get("cnpj"))
    if len(documento) != 14:
        raise ValueError(f"Cadastre o CNPJ de {escola.get('nome') or 'a escola'} antes de emitir.")
    return {
        "documento": documento,
        "razao_social": escola.get("nome") or "",
        "email": escola.get("nfse_email") or escola.get("email_admin") or "",
        "logradouro": escola.get("nfse_logradouro") or cfg.get("logradouro") or "",
        "numero": escola.get("nfse_numero") or "S/N",
        "bairro": escola.get("nfse_bairro") or cfg.get("bairro") or "",
        "codigo_municipio": escola.get("nfse_codigo_municipio") or cfg.get("codigo_municipio") or "",
        "uf": escola.get("nfse_uf") or cfg.get("uf") or "",
        "cep": escola.get("nfse_cep") or cfg.get("cep") or "",
    }


def emitir_cobranca_plataforma(cursor, cobranca_id, cliente=None):
    cfg = dict(_cfg_plataforma_completo(cursor))
    token = _exigir_credencial(cfg)
    cursor.execute(
        """
        SELECT c.*, e.nome, e.email_admin, e.cnpj, e.nfse_email, e.nfse_logradouro,
               e.nfse_numero, e.nfse_bairro, e.nfse_codigo_municipio, e.nfse_uf, e.nfse_cep
        FROM plataforma_cobrancas c
        JOIN plataforma_escolas e ON e.id = c.escola_id
        WHERE c.id = %s
        """,
        (cobranca_id,),
    )
    cobranca = cursor.fetchone()
    if not cobranca:
        raise ValueError("Assinatura não encontrada.")
    cursor.execute(
        """
        SELECT * FROM plataforma_notas_fiscais
        WHERE cobranca_id = %s AND status IN ('FATURADA', 'PENDENTE')
        ORDER BY id DESC LIMIT 1
        """,
        (cobranca_id,),
    )
    ativa = cursor.fetchone()
    if ativa and ativa.get("status") == STATUS_FATURADA:
        raise ValueError("Esta assinatura já tem NFS-e faturada.")
    if ativa and ativa.get("status") == STATUS_PENDENTE:
        return consultar_nota(cursor, ativa["id"], "plataforma_notas_fiscais", cliente)
    regime = (cfg.get("regime_apuracao") or "competencia").strip().lower()
    ok, motivo = pode_emitir_mensalidade(regime, cobranca.get("status"), cobranca.get("data_pagamento"))
    if not ok:
        raise ValueError(motivo)
    valor = valor_da_nota(regime, cobranca.get("valor"), cobranca.get("juros_valor"), cobranca.get("multa_valor"), cobranca.get("status"))
    if valor <= 0:
        raise ValueError("A assinatura precisa ter valor maior que zero.")
    competencia = competencia_da_mensalidade(regime, cobranca.get("data_vencimento"), cobranca.get("data_pagamento"), cobranca.get("status"))
    tomador = _tomador_escola(cobranca, cfg)
    mes_ano = competencia[5:7] + "/" + competencia[:4] if len(competencia) >= 7 else ""
    item = cfg.get("item_lista") or "01.05"
    servico = _servico_de(
        cfg,
        valor,
        f"Licenciamento de software de gestão escolar. Competência: {mes_ano}.",
        item,
        cfg.get("codigo_tributacao") or "0105",
    )
    quando = agora_local()
    ref = f"p{cobranca_id}t{int(quando.timestamp())}"
    cursor.execute(
        """
        INSERT INTO plataforma_notas_fiscais (
            escola_id, cobranca_id, ref, status, data_emissao,
            periodo_competencia, periodo_competencia_original, valor,
            tomador_nome, tomador_documento
        ) VALUES (%s, %s, %s, 'PENDENTE', %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            cobranca.get("escola_id"),
            cobranca_id,
            ref,
            quando,
            competencia,
            competencia,
            valor,
            tomador["razao_social"],
            tomador["documento"],
        ),
    )
    nota_id = _id_linha(cursor.fetchone())
    _commit(cursor)
    payload = montar_payload(_prestador_de(cfg), tomador, servico, data_emissao=quando)
    lido = _chamar_focus(
        cursor,
        "plataforma_notas_fiscais",
        nota_id,
        lambda: emitir_focus(token, cfg.get("ambiente"), ref, payload, cliente),
    )
    _gravar_nota(cursor, "plataforma_notas_fiscais", nota_id, _aplicar_leitura({"status": STATUS_PENDENTE}, lido, quando))
    if lido.get("ambiente_corrigido"):
        _gravar_ambiente(cursor, lido["ambiente_corrigido"], plataforma=True)
    else:
        _commit(cursor)
    aviso = _aviso_ambiente(lido)
    if lido["status"] == STATUS_ERRO:
        raise ValueError(lido["mensagem"] or "A Focus recusou a NFS-e.")
    if lido["status"] == STATUS_PENDENTE:
        return "NFS-e da licença enviada e ainda pendente de autorização." + aviso
    return f"NFS-e da licença faturada{(' nº ' + lido['numero_nfse']) if lido.get('numero_nfse') else ''}." + aviso


def _cfg_plataforma_completo(cursor):
    garantir_tabela_plataforma(cursor)
    cursor.execute("SELECT * FROM plataforma_nfse WHERE id = 1")
    cfg = cursor.fetchone() or {}
    cfg = dict(cfg)
    cfg["nfse_token"] = cfg.get("token")
    cfg["nfse_cnpj"] = cfg.get("cnpj")
    cfg["nfse_inscricao_municipal"] = cfg.get("inscricao_municipal")
    cfg["nfse_codigo_municipio"] = cfg.get("codigo_municipio")
    cfg["nfse_ambiente"] = cfg.get("ambiente")
    cfg["nfse_aliquota"] = cfg.get("aliquota")
    cfg["nfse_item_lista"] = cfg.get("item_lista")
    cfg["nfse_codigo_tributacao"] = cfg.get("codigo_tributacao")
    cfg["nfse_opcao_simples"] = cfg.get("opcao_simples")
    cfg["nfse_c_beneficio"] = cfg.get("c_beneficio")
    cfg["nfse_p_ibs"] = cfg.get("p_ibs")
    cfg["nfse_p_cbs"] = cfg.get("p_cbs")
    return cfg


def _substituir_plataforma(cursor, antiga, quando, retro, periodo_original, cliente, contexto):
    cfg = _cfg_plataforma_completo(cursor)
    token = _exigir_credencial(cfg)
    cursor.execute(
        """
        SELECT c.*, e.nome, e.email_admin, e.cnpj, e.nfse_email, e.nfse_logradouro,
               e.nfse_numero, e.nfse_bairro, e.nfse_codigo_municipio, e.nfse_uf, e.nfse_cep
        FROM plataforma_cobrancas c
        JOIN plataforma_escolas e ON e.id = c.escola_id
        WHERE c.id = %s
        """,
        (antiga.get("cobranca_id"),),
    )
    cobranca = cursor.fetchone()
    if not cobranca:
        raise ValueError("Assinatura da nota não encontrada.")
    valor = float(antiga.get("valor") or cobranca.get("valor") or 0)
    tomador = _tomador_escola(cobranca, cfg)
    fiscal = periodo_original if retro else periodo_de(quando)
    mes_ano = fiscal[5:7] + "/" + fiscal[:4] if len(fiscal) >= 7 else ""
    servico = _servico_de(
        cfg,
        valor,
        f"Licenciamento de software de gestão escolar. Competência: {mes_ano}. Nota substituta.",
        cfg.get("item_lista") or "01.05",
        cfg.get("codigo_tributacao") or "0105",
    )
    ref = f"ps{antiga['id']}t{int(quando.timestamp())}"
    cursor.execute(
        """
        INSERT INTO plataforma_notas_fiscais (
            escola_id, cobranca_id, ref, status, nota_substituida_id, data_emissao,
            periodo_competencia, periodo_competencia_original,
            exibir_tarja_faturamento_retroativo, valor, tomador_nome, tomador_documento
        ) VALUES (%s, %s, %s, 'PENDENTE', %s, %s, %s, %s, FALSE, %s, %s, %s)
        RETURNING id
        """,
        (
            antiga.get("escola_id"),
            antiga.get("cobranca_id"),
            ref,
            antiga["id"],
            quando,
            periodo_de(quando),
            fiscal,
            valor,
            tomador["razao_social"],
            tomador["documento"],
        ),
    )
    nova_id = _id_linha(cursor.fetchone())
    _commit(cursor)
    payload = montar_payload(_prestador_de(cfg), tomador, servico, substituida=antiga, data_emissao=quando)
    lido = _chamar_focus(
        cursor,
        "plataforma_notas_fiscais",
        nova_id,
        lambda: emitir_focus(token, cfg.get("ambiente"), ref, payload, cliente),
    )
    _finalizar_substituicao(cursor, "plataforma_notas_fiscais", antiga, nova_id, lido, quando, retro)
    if lido["status"] == STATUS_ERRO:
        raise ValueError(lido["mensagem"] or "A Focus recusou a nota substituta.")
    if lido["status"] == STATUS_PENDENTE:
        return "Nota substituta enviada e ainda pendente."
    return "NFS-e da licença substituída."


def listar_notas_plataforma(cursor, status=None):
    garantir_tabela_plataforma(cursor)
    sql = """
        SELECT n.*, e.nome AS escola_nome,
               s.numero_nfse AS substituta_numero,
               o.numero_nfse AS substituida_numero
        FROM plataforma_notas_fiscais n
        LEFT JOIN plataforma_escolas e ON e.id = n.escola_id
        LEFT JOIN plataforma_notas_fiscais s ON s.id = n.nota_substituta_id
        LEFT JOIN plataforma_notas_fiscais o ON o.id = n.nota_substituida_id
        WHERE 1=1
    """
    params = []
    if status in STATUS_NOTA:
        sql += " AND n.status = %s"
        params.append(status)
    sql += " ORDER BY e.nome, n.id DESC"
    cursor.execute(sql, params)
    return [_enriquecer(item) for item in cursor.fetchall() or []]


def listar_cobrancas_plataforma(cursor, mes):
    garantir_tabela_plataforma(cursor)
    cursor.execute(
        """
        SELECT c.id, c.escola_id, c.competencia, c.descricao, c.valor, c.status,
               c.data_vencimento, c.data_pagamento, e.nome AS escola_nome, e.cnpj,
               n.id AS nota_id, n.status AS nota_status, n.numero_nfse,
               n.exibir_tarja_faturamento_retroativo
        FROM plataforma_cobrancas c
        JOIN plataforma_escolas e ON e.id = c.escola_id
        LEFT JOIN LATERAL (
            SELECT id, status, numero_nfse, exibir_tarja_faturamento_retroativo
            FROM plataforma_notas_fiscais
            WHERE cobranca_id = c.id
            ORDER BY id DESC
            LIMIT 1
        ) n ON TRUE
        WHERE c.competencia = %s
        ORDER BY e.nome
        """,
        (mes,),
    )
    return cursor.fetchall() or []
