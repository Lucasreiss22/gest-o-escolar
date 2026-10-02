from io import BytesIO
from pathlib import Path

from fpdf import FPDF

from tributacao import br_money, nome_regime


FONTES = {
    "": [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path(r"C:\Windows\Fonts\arial.ttf"),
    ],
    "B": [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path(r"C:\Windows\Fonts\arialbd.ttf"),
    ],
}


class _ProvaPDF(FPDF):
    def __init__(self):
        super().__init__(format="A4")
        self.set_auto_page_break(auto=True, margin=12)
        self.set_margins(12, 10, 12)
        fonte_ok = False
        for estilo, caminhos in FONTES.items():
            for caminho in caminhos:
                if caminho.exists():
                    self.add_font("Relatorio", estilo, str(caminho))
                    fonte_ok = True
                    break
        self.fonte = "Relatorio" if fonte_ok else "Helvetica"

    def header(self):
        return

    def footer(self):
        return


def _tamanho_imagem_questao(pdf, foto):
    """(largura, altura) em mm. Página vinda de PDF usa a largura da folha; foto fica menor."""
    dados = (foto or (None,))[0]
    if not dados:
        return None
    pagina_pdf = len(foto) > 2 and bool(foto[2])
    try:
        from PIL import Image

        with Image.open(BytesIO(dados)) as img:
            larg_px, alt_px = img.size
    except Exception:
        return None
    proporcao = alt_px / float(larg_px or 1)
    if pagina_pdf:
        largura_max = pdf.epw - 4
        altura_max = pdf.page_break_trigger - pdf.t_margin - 4
    else:
        largura_max, altura_max = 120, 95
    largura = min(largura_max, pdf.epw - 4)
    altura = largura * proporcao
    if altura > altura_max:
        altura = altura_max
        largura = altura / proporcao
    return largura, altura


def _imagem_questao(pdf, foto):
    """Imagem da pergunta, proporcional e sem passar do fim da página."""
    tamanho = _tamanho_imagem_questao(pdf, foto)
    if not tamanho:
        return
    largura, altura = tamanho
    dados, mime = foto[0], (foto[1] if len(foto) > 1 else "")
    try:
        if pdf.get_y() + altura + 1 > pdf.page_break_trigger:
            pdf.add_page()
        arquivo = BytesIO(dados)
        arquivo.name = "foto.png" if "png" in (mime or "").lower() else "foto.jpg"
        topo = pdf.get_y() + 1
        pdf.image(arquivo, x=14, y=topo, w=largura, h=altura)
        pdf.set_y(topo + altura + 2)
    except Exception:
        return


def _altura_questao(pdf, questao, texto):
    """Altura aproximada da pergunta inteira (imagens + enunciado + resposta)."""
    altura = 0.0
    for foto in questao.get("fotos") or []:
        tamanho = _tamanho_imagem_questao(pdf, foto)
        if tamanho:
            altura += tamanho[1] + 3
    pdf.set_font(pdf.fonte, "B", 11)
    try:
        altura += pdf.multi_cell(0, 6, texto, dry_run=True, output="HEIGHT")
    except Exception:
        altura += 6 * (1 + len(texto) // 90)
    if (questao.get("tipo") or "") == "multipla":
        altura += 6 * len([a for a in (questao.get("alternativas") or []) if str(a or "").strip()])
    else:
        altura += ALTURA_LINHA_RESPOSTA * max(1, int(questao.get("linhas") or 5)) + 3
    return altura


ALTURA_LINHA_RESPOSTA = 9


def _espaco_resposta(pdf, linhas, com_linhas=True):
    """Área da resposta discursiva: pauta (linhas para escrever reto) ou espaço em branco."""
    linhas = max(1, int(linhas or 1))
    inicio_x, fim_x = 16, pdf.w - pdf.r_margin
    y = pdf.get_y() + 1
    pdf.set_draw_color(150, 150, 150)
    pdf.set_line_width(0.3)
    for _ in range(linhas):
        if y + ALTURA_LINHA_RESPOSTA > pdf.page_break_trigger:
            pdf.add_page()
            y = pdf.get_y()
        y += ALTURA_LINHA_RESPOSTA
        if com_linhas:
            pdf.line(inicio_x, y, fim_x, y)
    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(0.2)
    pdf.set_y(y + 2)


def _data_hora_prova(data_aplicacao, horario):
    """Texto "dd/mm/aaaa" e "HH:MM" para o cabeçalho da prova (vazio quando não informado)."""
    data_txt = ""
    if data_aplicacao:
        if hasattr(data_aplicacao, "strftime"):
            data_txt = data_aplicacao.strftime("%d/%m/%Y")
        else:
            partes = str(data_aplicacao)[:10].split("-")
            data_txt = "/".join(reversed(partes)) if len(partes) == 3 else str(data_aplicacao)
    hora_txt = ""
    if horario:
        hora_txt = horario.strftime("%H:%M") if hasattr(horario, "strftime") else str(horario)[:5]
    return data_txt, hora_txt


def pdf_prova(
    escola, turma, titulo, materia, questoes, logo=None, com_gabarito=False, tarja="",
    data_aplicacao=None, horario=None, professor=None,
):
    """Prova para o aluno preencher. O cabeçalho não tem borda."""
    pdf = _ProvaPDF()
    pdf.add_page()
    try:
        pdf.set_font(pdf.fonte, "", 12)
    except Exception:
        pdf.fonte = "Helvetica"
        pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(20, 20, 20)
    topo = pdf.get_y()
    texto_x = 12
    if logo and logo[0]:
        arquivo = BytesIO(logo[0])
        mime = (logo[1] or "").lower()
        arquivo.name = "logo.png" if "png" in mime else "logo.jpg"
        try:
            pdf.image(arquivo, x=12, y=topo, w=16)
            texto_x = 32
        except Exception:
            texto_x = 12
    pdf.set_xy(texto_x, topo)
    pdf.cell(0, 6, "Nome: ________________________________", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(texto_x)
    pdf.cell(0, 6, "Matrícula: ________________________", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(texto_x)
    data_txt, hora_txt = _data_hora_prova(data_aplicacao, horario)
    linha_data = f"Data: {data_txt}" if data_txt else "Data: ________________________________"
    if hora_txt:
        linha_data += f"    Horário: {hora_txt}"
    pdf.cell(0, 6, linha_data, new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(texto_x)
    pdf.cell(0, 6, f"Turma: {turma or '—'}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(texto_x)
    pdf.cell(0, 6, "Nota: ________", new_x="LMARGIN", new_y="NEXT")
    if pdf.get_y() < topo + 30:
        pdf.set_y(topo + 30)
    tarja = (tarja or "").strip()
    if tarja:
        pdf.ln(2)
        pdf.set_x(12)
        pdf.set_font(pdf.fonte, "B", 11)
        pdf.multi_cell(0, 6, tarja, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(pdf.fonte, "", 12)
    pdf.ln(3)
    pdf.set_x(12)
    pdf.set_font(pdf.fonte, "B", 14)
    pdf.multi_cell(0, 7, titulo or "Prova", new_x="LMARGIN", new_y="NEXT")
    if materia or escola:
        pdf.set_font(pdf.fonte, "", 11)
        pdf.set_x(12)
        pdf.multi_cell(0, 6, " · ".join(parte for parte in [escola, materia] if parte), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    materias = {(q.get("materia") or "").strip() for q in (questoes or [])} - {""}
    separar_materias = len(materias) > 1
    materia_atual = None
    for indice, questao in enumerate(questoes or [], start=1):
        materia_q = (questao.get("materia") or "").strip()
        novo_bloco = separar_materias and materia_q and materia_q != materia_atual
        texto_q = f"{indice}. {questao.get('enunciado') or ''}"
        necessario = _altura_questao(pdf, questao, texto_q) + (12 if novo_bloco else 0)
        cabe_numa_pagina = necessario <= pdf.page_break_trigger - pdf.t_margin
        if cabe_numa_pagina and pdf.get_y() + necessario > pdf.page_break_trigger:
            pdf.add_page()
        elif novo_bloco and pdf.get_y() > pdf.page_break_trigger - 40:
            pdf.add_page()
        if novo_bloco:
            materia_atual = materia_q
            pdf.ln(2)
            pdf.set_x(12)
            pdf.set_font(pdf.fonte, "B", 12)
            pdf.set_fill_color(235, 241, 250)
            pdf.cell(0, 8, materia_q, fill=True, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
        for foto in questao.get("fotos") or []:
            _imagem_questao(pdf, foto)
        pdf.set_x(12)
        pdf.set_font(pdf.fonte, "B", 11)
        pdf.multi_cell(0, 6, texto_q, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(pdf.fonte, "", 11)
        if (questao.get("tipo") or "") == "multipla":
            for letra, texto in zip("ABCDE", questao.get("alternativas") or []):
                if not str(texto or "").strip():
                    continue
                pdf.set_x(16)
                pdf.multi_cell(0, 6, f"{letra}) {texto}", new_x="LMARGIN", new_y="NEXT")
        else:
            _espaco_resposta(
                pdf,
                int(questao.get("linhas") or 5),
                questao.get("com_linhas") is not False,
            )
        if com_gabarito and (questao.get("resposta") or "").strip():
            pdf.set_x(16)
            pdf.set_font(pdf.fonte, "B", 10)
            pdf.multi_cell(0, 6, f"Resposta: {questao.get('resposta')}", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font(pdf.fonte, "", 11)
        pdf.ln(5)
    if not com_gabarito:
        _assinaturas_prova(pdf, professor)
    return _saida(pdf)


def _assinaturas_prova(pdf, professor=None):
    """Assinatura do aluno ao entregar e do professor após corrigir e lançar a nota."""
    altura_bloco = 46
    pagina_nova = pdf.get_y() + altura_bloco > pdf.page_break_trigger
    if pagina_nova:
        pdf.add_page()
    esquerda = pdf.l_margin
    meio = 10
    largura = (pdf.epw - meio) / 2
    direita = esquerda + largura + meio

    if not pagina_nova:
        pdf.ln(4)
        pdf.set_draw_color(150, 150, 150)
        pdf.set_line_width(0.2)
        pdf.line(esquerda, pdf.get_y(), esquerda + pdf.epw, pdf.get_y())
    pdf.ln(18)
    y_linha = pdf.get_y()
    pdf.set_draw_color(40, 40, 40)
    pdf.set_line_width(0.3)
    pdf.line(esquerda, y_linha, esquerda + largura, y_linha)
    pdf.line(direita, y_linha, direita + largura, y_linha)
    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(0.2)

    pdf.set_text_color(40, 40, 40)
    pdf.set_font(pdf.fonte, "", 10)
    pdf.set_xy(esquerda, y_linha + 1)
    pdf.cell(largura, 5, "Assinatura do(a) aluno(a)", align="C")
    pdf.set_xy(direita, y_linha + 1)
    pdf.cell(largura, 5, "Assinatura do(a) professor(a)", align="C")

    pdf.set_font(pdf.fonte, "", 9)
    pdf.set_text_color(90, 90, 90)
    pdf.set_xy(esquerda, y_linha + 6)
    pdf.cell(largura, 5, "Ao entregar a prova", align="C")
    pdf.set_xy(direita, y_linha + 6)
    nome = (professor or "").strip()
    pdf.cell(largura, 5, f"Prof.(a) {nome}" if nome else "Após corrigir e lançar a nota", align="C")

    pdf.set_font(pdf.fonte, "", 10)
    pdf.set_text_color(40, 40, 40)
    pdf.set_xy(direita, y_linha + 13)
    pdf.cell(largura, 6, "Nota: ________     Data da correção: ____/____/______", align="C")
    pdf.set_text_color(20, 20, 20)
    pdf.set_y(y_linha + 20)


class RelatorioPDF(FPDF):
    def __init__(self, titulo):
        super().__init__(format="A4")
        self.titulo_cabecalho = titulo
        self.set_auto_page_break(auto=True, margin=18)
        fonte_ok = False
        for estilo, caminhos in FONTES.items():
            for caminho in caminhos:
                if caminho.exists():
                    self.add_font("Relatorio", estilo, str(caminho))
                    fonte_ok = True
                    break
        self.fonte = "Relatorio" if fonte_ok else "Helvetica"

    def header(self):
        try:
            self.set_font(self.fonte, "B", 13)
        except Exception:
            self.set_font("Helvetica", "B", 13)
            self.fonte = "Helvetica"
        self.set_text_color(30, 58, 95)
        self.cell(0, 8, self.titulo_cabecalho, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(59, 130, 246)
        self.set_line_width(0.6)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(6)

    def footer(self):
        self.set_y(-15)
        self.set_font(self.fonte, "", 8)
        self.set_text_color(120, 120, 120)
        self.cell(
            0,
            8,
            f"Documento gerado pelo sistema de Gestão Escolar — página {self.page_no()}",
            align="C",
        )

    def secao(self, texto):
        self.set_x(self.l_margin)
        self.set_font(self.fonte, "B", 11)
        self.set_text_color(30, 58, 95)
        self.cell(0, 8, texto, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(40, 40, 40)

    def paragrafo(self, texto, tamanho=10):
        self.set_x(self.l_margin)
        self.set_font(self.fonte, "", tamanho)
        self.multi_cell(
            0, 5.4, "" if texto is None else str(texto),
            align="L", new_x="LMARGIN", new_y="NEXT", wrapmode="CHAR",
        )
        self.ln(1)

    def _coube(self, texto, largura):
        texto = "" if texto is None else str(texto)
        limite = max(float(largura) - 1.6, 4)
        if self.get_string_width(texto) <= limite:
            return texto
        while texto and self.get_string_width(texto + "…") > limite:
            texto = texto[:-1]
        return (texto + "…") if texto else ""

    def linha(self, rotulo, valor, negrito=False, tamanho=10):
        self.set_font(self.fonte, "B" if negrito else "", tamanho)
        rotulo = "" if rotulo is None else str(rotulo)
        valor = "" if valor is None else str(valor)
        self.set_x(self.l_margin)
        if self.get_y() > 272:
            self.add_page()
            self.set_x(self.l_margin)
        largura = self.epw
        largura_valor = min(70, max(32, self.get_string_width(valor) + 3))
        if largura_valor > largura - 20:
            largura_valor = max(largura - 20, 20)
        largura_rotulo = largura - largura_valor
        cabe = (
            largura_rotulo > 8
            and self.get_string_width(rotulo) <= largura_rotulo - 1
            and self.get_string_width(valor) <= largura_valor - 1
        )
        if cabe:
            self.cell(largura_rotulo, 6, rotulo)
            self.cell(largura_valor, 6, valor, align="R", new_x="LMARGIN", new_y="NEXT")
            return
        if rotulo:
            self.set_x(self.l_margin)
            self.multi_cell(
                0, 5.4, rotulo,
                align="L", new_x="LMARGIN", new_y="NEXT", wrapmode="CHAR",
            )
        if valor:
            self.set_x(self.l_margin)
            self.set_font(self.fonte, "B", tamanho)
            self.multi_cell(
                0, 5.4, valor,
                align="R", new_x="LMARGIN", new_y="NEXT", wrapmode="CHAR",
            )

    def tabela(self, cabecalhos, linhas, larguras=None):
        if not larguras:
            larguras = [self.epw / len(cabecalhos)] * len(cabecalhos)
        self.set_x(self.l_margin)
        self.set_font(self.fonte, "B", 8)
        self.set_fill_color(30, 58, 95)
        self.set_text_color(255, 255, 255)
        for i, titulo in enumerate(cabecalhos):
            self.cell(larguras[i], 7, self._coube(titulo, larguras[i]), border=1, fill=True)
        self.ln()
        self.set_text_color(40, 40, 40)
        self.set_font(self.fonte, "", 8)
        fill = False
        for linha in linhas:
            if self.get_y() > 270:
                self.add_page()
                self.set_font(self.fonte, "", 8)
            self.set_x(self.l_margin)
            self.set_fill_color(243, 246, 251)
            for i, celula in enumerate(linha):
                self.cell(larguras[i], 6, self._coube(celula, larguras[i]), border=1, fill=fill)
            self.ln()
            fill = not fill
        self.ln(2)


def _saida(pdf):
    buffer = BytesIO()
    pdf.output(buffer)
    buffer.seek(0)
    return buffer


def _brl(valor):
    return br_money(valor)


def _data_br(valor):
    if hasattr(valor, "strftime"):
        return valor.strftime("%d/%m/%Y")
    texto = str(valor or "").strip()
    if len(texto) >= 10 and texto[4] == "-" and texto[7] == "-":
        ano, mes, dia = texto[:10].split("-")
        return f"{dia}/{mes}/{ano}"
    return texto or "—"


def _anexar_titulos_base(pdf, titulos, regime_apuracao, base_oficial=None):
    if titulos is None:
        return
    pdf.secao("De onde veio a base do mês")
    if (regime_apuracao or "") == "caixa":
        pdf.paragrafo(
            "Regime de caixa: entram as mensalidades cuja data da baixa cai neste mês. "
            "O vencimento pode ser de outro mês. Título emitido e ainda sem baixa fica de fora."
        )
    else:
        pdf.paragrafo(
            "Regime de competência: entram as mensalidades com vencimento neste mês, pagas ou em aberto. "
            "Canceladas ficam de fora."
        )
    linhas = []
    total = 0.0
    total_mora = 0.0
    for item in titulos:
        valor = float(item.get("valor") or 0)
        mora = float(item.get("juros_valor") or 0) + float(item.get("multa_valor") or 0)
        total += valor
        total_mora += mora
        linhas.append([
            (item.get("nome_completo") or "Aluno")[:18],
            (item.get("descricao") or "—")[:20],
            _data_br(item.get("data_vencimento")),
            _data_br(item.get("data_pagamento")) if item.get("data_pagamento") else "—",
            _brl(valor),
            _brl(mora) if mora else "—",
        ])
    if linhas:
        pdf.tabela(
            ["Aluno", "Descrição", "Vencimento", "Baixa", "Mensalidade", "Juros+multa"],
            linhas,
            [36, 40, 26, 26, 31, 31],
        )
    else:
        pdf.paragrafo("Nenhuma mensalidade compõe a base deste mês.")
    pdf.linha("Soma das mensalidades", _brl(total), negrito=True)
    if total_mora:
        pdf.linha("Juros e multa por atraso destes títulos", _brl(total_mora))
        pdf.paragrafo(
            "Juros e multa aparecem à parte: o tratamento fiscal deles segue a apuração do regime "
            "(veja o quadro de tributos acima).",
            tamanho=9,
        )
    if base_oficial is not None and abs(float(base_oficial) - total) > 0.05:
        pdf.paragrafo(
            "A apuração usa "
            + _brl(base_oficial)
            + " porque esta competência tem lançamento manual ou de planilha, que substitui a soma automática."
        )


def _pagina_resultado(pdf, titulo, subtitulo, linhas, nota):
    pdf.titulo_cabecalho = titulo
    pdf.add_page()
    pdf.paragrafo(subtitulo)
    for rotulo, valor, negrito in linhas:
        pdf.linha(rotulo, _brl(valor), negrito=negrito)
    if nota:
        pdf.ln(2)
        pdf.paragrafo(nota)


def _quadro_linhas(apuracao):
    return ((apuracao or {}).get("quadro") or {}).get("linhas") or []


def pdf_calculo_rbt12(escola, mes_label, apuracao, regime_apuracao="competencia"):
    ap = apuracao or {}
    caixa = (regime_apuracao or ap.get("regime_apuracao") or "") == "caixa"
    pdf = RelatorioPDF("Cálculo da RBT12")
    pdf.add_page()
    pdf.paragrafo(f"{escola} · {mes_label}")
    pdf.paragrafo(
        "A Lei Complementar 123/2006 manda somar a receita bruta dos 12 meses anteriores. "
        "Essa soma é a RBT12. O mês da apuração não entra nela: ele só serve de base para o DAS. "
        "A Resolução CGSN 140/2018 detalha essa conta."
    )
    if caixa:
        pdf.paragrafo("No regime de caixa, a soma usa só o que teve baixa. O que não foi pago fica fora.")
    else:
        pdf.paragrafo("No regime de competência, a soma usa o vencimento, pago ou não.")
    soma = 0.0
    linhas = []
    for linha in _quadro_linhas(ap):
        valor = float(linha.get("receita_bruta") or 0)
        entra = bool(linha.get("entra_rbt12"))
        if entra:
            soma += valor
        linhas.append([
            linha.get("rotulo") or linha.get("competencia") or "",
            _brl(valor),
            "Sim" if entra else "Não",
            _brl(soma) if entra else "—",
        ])
    if linhas:
        pdf.tabela(["Competência", "Receita", "Entra", "Soma até aqui"], linhas, [40, 42, 24, 48])
    else:
        pdf.paragrafo("Nenhuma competência lançada na janela.")
    pdf.linha("Soma dos meses que entram", _brl(ap.get("rbt_acumulado")), negrito=True)
    pdf.linha("Meses considerados", ap.get("meses_atividade") or 0)
    if ap.get("annualizado"):
        meses = ap.get("meses_atividade") or 1
        pdf.paragrafo(
            f"Ainda não há 12 meses. A lei manda annualizar: "
            f"({_brl(ap.get('rbt_acumulado'))} ÷ {meses}) × 12 = {_brl(ap.get('rbt12'))}."
        )
    else:
        pdf.paragrafo("Há 12 meses na janela, então a RBT12 é a própria soma. Não há annualização.")
    pdf.linha("RBT12", _brl(ap.get("rbt12")), negrito=True)
    return _saida(pdf)


def _folhas_da_competencia(folhas, competencia):
    return [item for item in (folhas or []) if item.get("competencia") == competencia]


def _encargos_do_mes(pdf, itens):
    chaves = (
        ("Salário e demais valores brutos", "bruto"),
        ("FGTS 8%", "fgts"),
        ("Provisão de 13º", "provisao_13"),
        ("Férias com 1/3", "ferias_terco"),
        ("FGTS sobre 13º e férias", "reflexos_fgts"),
        ("INSS patronal", "inss_patronal"),
        ("RAT", "rat"),
        ("Sistema S", "sistema_s"),
    )
    algum = False
    for rotulo, chave in chaves:
        total = sum(float(item.get(chave) or 0) for item in itens or [])
        if total:
            pdf.linha(rotulo, _brl(total))
            algum = True
    if not algum:
        pdf.paragrafo("Não há lançamento de folha aberto neste mês para detalhar cada encargo.")
    pdf.paragrafo(
        "No Simples Nacional, INSS patronal, RAT e Sistema S não entram de novo na folha: "
        "eles já estão dentro do DAS. Entram na FS12 o que foi pago de salário, 13º, férias com 1/3 e FGTS."
    )


def pdf_calculo_fs12(escola, mes_label, apuracao, regime_apuracao="competencia", folhas=None, itens_mes=None, totais_mes=None):
    ap = apuracao or {}
    quadro = ap.get("quadro") or {}
    pdf = RelatorioPDF("Folha e encargos dos 12 meses")
    pdf.add_page()
    pdf.paragrafo(f"{escola} · {mes_label}")
    pdf.paragrafo(
        "A FS12 soma a folha e os encargos dos mesmos 12 meses que entram na RBT12. "
        "Cada mês abaixo mostra quem foi pago e o custo da escola, que é o salário mais os encargos."
    )
    soma = 0.0
    for linha in _quadro_linhas(ap):
        if not linha.get("entra_rbt12"):
            continue
        valor = float(linha.get("folha_encargos") or 0)
        soma += valor
        pdf.secao(linha.get("rotulo") or linha.get("competencia") or "Mês")
        pessoas = _folhas_da_competencia(folhas, linha.get("competencia"))
        if pessoas:
            tabela = []
            for pessoa in pessoas:
                tabela.append([
                    (pessoa.get("nome_completo") or "Colaborador")[:32],
                    _brl(pessoa.get("bruto")),
                    _brl(pessoa.get("encargos")),
                    _brl(pessoa.get("custo_escola")),
                ])
            pdf.tabela(["Colaborador", "Bruto", "Encargos", "Custo pago"], tabela, [62, 36, 40, 40])
        else:
            pdf.paragrafo("Este mês não tem a folha aberta por colaborador. Entra o total gravado na competência.")
        pdf.linha("Pago neste mês", _brl(valor), negrito=True)
        pdf.linha("Soma da folha até aqui", _brl(soma))
    pdf.linha("Soma dos 12 meses", _brl(ap.get("fs_acumulado")), negrito=True)
    if ap.get("annualizado"):
        meses = ap.get("meses_atividade") or 1
        pdf.paragrafo(
            f"Ainda não há 12 meses. FS12 = ({_brl(ap.get('fs_acumulado'))} ÷ {meses}) × 12 = {_brl(ap.get('fs12'))}."
        )
    pdf.linha("Folha e encargos (FS12)", _brl(ap.get("fs12")), negrito=True)

    apuracao_mes = quadro.get("linha_apuracao") or {}
    pdf.add_page()
    _titulo_folha(pdf, "Folha paga no mês da apuração")
    pdf.paragrafo(
        "Este mês não entra na FS12. Ele aparece aqui para mostrar o que foi pago de folha e de encargo agora."
    )
    pdf.linha("Total do mês", _brl(apuracao_mes.get("folha_encargos")), negrito=True)
    if itens_mes:
        tabela = []
        for pessoa in itens_mes:
            tabela.append([
                (pessoa.get("nome_completo") or "Colaborador")[:32],
                _brl(pessoa.get("bruto")),
                _brl(pessoa.get("encargos")),
                _brl(pessoa.get("custo_escola")),
            ])
        pdf.tabela(["Colaborador", "Bruto", "Encargos", "Custo pago"], tabela, [62, 36, 40, 40])
        pdf.secao("Encargos que compõem esse custo")
        _encargos_do_mes(pdf, itens_mes)
        if totais_mes:
            pdf.linha("Custo total da escola neste mês", _brl(totais_mes.get("custo_escola")), negrito=True)
    else:
        pdf.paragrafo("Não há colaboradores ativos para abrir os encargos deste mês.")
    return _saida(pdf)


def pdf_calculo_fator_r(escola, mes_label, apuracao, regime_apuracao="competencia"):
    ap = apuracao or {}
    fator = float(ap.get("fator_r_pct") or 0)
    anexo = ap.get("anexo") or "-"
    fs = float(ap.get("fs12") or 0)
    rbt = float(ap.get("rbt12") or 0)
    pdf = RelatorioPDF("Cálculo do Fator R")
    pdf.add_page()
    pdf.paragrafo(f"{escola} · {mes_label}")
    pdf.paragrafo(
        "O Fator R é a folha dos 12 meses anteriores dividida pela receita bruta dos mesmos 12 meses. "
        "A Lei Complementar 123/2006 usa 28% como corte. Igual ou acima, a escola de educação fica no Anexo III. "
        "Abaixo, fica no Anexo V. A Resolução CGSN 140/2018 descreve essa divisão. "
        "O mês da apuração não entra nela."
    )
    linhas = []
    for linha in _quadro_linhas(ap):
        linhas.append([
            linha.get("rotulo") or linha.get("competencia") or "",
            _brl(linha.get("receita_bruta")),
            _brl(linha.get("folha_encargos")),
            "Sim" if linha.get("entra_rbt12") else "Não",
        ])
    if linhas:
        pdf.tabela(["Competência", "Receita (RBT12)", "Folha (FS12)", "Entra"], linhas, [40, 48, 48, 24])
    pdf.linha("Soma da receita (RBT12)", _brl(rbt), negrito=True)
    pdf.linha("Soma da folha (FS12)", _brl(fs), negrito=True)
    if rbt:
        razao = fs / rbt
        pdf.linha("Divisão", f"{_brl(fs)} ÷ {_brl(rbt)}")
        pdf.linha("Resultado da divisão", f"{razao:.6f}")
        pdf.linha("Em percentual", f"{razao * 100:.2f}%", negrito=True)
        pdf.paragrafo(
            f"{_brl(fs)} dividido por {_brl(rbt)} dá {razao:.6f}. "
            f"Multiplicado por 100, isso é {razao * 100:.2f}%. Essa é a origem do Fator R."
        )
    else:
        pdf.paragrafo("A RBT12 está zerada, então o Fator R não tem como ser dividido.")
    pdf.linha("Fator R usado na apuração", f"{fator:.2f}%", negrito=True)
    if fator >= 28:
        pdf.paragrafo(f"{fator:.2f}% alcança 28%. Por isso o anexo é o III.")
    else:
        pdf.paragrafo(f"{fator:.2f}% não alcança 28%. Por isso o anexo é o V.")
    pdf.linha("Anexo", anexo, negrito=True)
    return _saida(pdf)


def pdf_extrato_pgdas(
    escola, mes_label, apuracao, regime_apuracao="competencia",
    pendentes=None, atrasados=None, mes_filtro="",
):
    ap = apuracao or {}
    quadro = ap.get("quadro") or {}
    caixa = (regime_apuracao or ap.get("regime_apuracao") or "") == "caixa"
    anexo = ap.get("anexo") or "-"
    aliq_nom = float(ap.get("aliquota_nominal") or 0) * 100
    aliq_ef = float(ap.get("aliquota_efetiva_pct") or 0)
    fator = float(ap.get("fator_r_pct") or 0)
    rbt = float(ap.get("rbt12") or 0)
    fs = float(ap.get("fs12") or 0)
    receita = float(ap.get("receita_mes") or 0)
    deducao = float(ap.get("parcela_deduzir") or 0)
    pdf = RelatorioPDF("Extrato PGDAS")
    pdf.add_page()
    pdf.paragrafo(f"{escola} · {mes_label}")
    pdf.paragrafo(
        "Memória completa da apuração do Simples Nacional, no formato do PGDAS. "
        "Segue a Lei Complementar 123/2006 e a Resolução CGSN 140/2018: "
        "soma da receita e da folha dos 12 meses anteriores, Fator R, anexo, alíquota efetiva e o DAS a pagar. "
        "Não é o documento oficial da Receita Federal."
    )
    if caixa:
        pdf.linha("Regime de apuração", "Regime de caixa", negrito=True)
        pdf.paragrafo(
            "A receita é a que teve baixa. O que não foi pago aparece no fim deste extrato "
            "e fica fora da base do DAS e da RBT12 até o pagamento."
        )
    else:
        pdf.linha("Regime de apuração", "Regime de competência", negrito=True)
        pdf.paragrafo(
            "A receita do mês soma o que venceu nele: pago, pendente e atrasado. "
            "O que não foi pago entra na base do DAS."
        )
    pdf.linha("Tipo de receita", f"Serviços de educação — Anexo {anexo}", negrito=True)
    pdf.linha("DAS a pagar neste mês", _brl(ap.get("das")), negrito=True)

    pdf.secao("Base do DAS neste mês")
    pdf.linha("Receita do mês de apuração", _brl(receita), negrito=True)
    pdf.paragrafo("Este valor calcula o DAS e não entra na RBT12.")
    apuracao_mes = quadro.get("linha_apuracao") or {}
    if apuracao_mes:
        pdf.linha("Folha deste mês", _brl(apuracao_mes.get("folha_encargos")))
        if apuracao_mes.get("origem"):
            pdf.linha("Origem da base", str(apuracao_mes.get("origem")))

    pdf.secao("RBT12")
    pdf.paragrafo("Soma da receita dos 12 meses anteriores. O mês de apuração fica de fora.")
    linhas = []
    for linha in quadro.get("linhas") or []:
        linhas.append([
            linha.get("rotulo") or linha.get("competencia") or "",
            _brl(linha.get("receita_bruta")),
            _brl(linha.get("folha_encargos")),
            "Sim" if linha.get("entra_rbt12") else "Não",
            (linha.get("origem") or "—")[:14],
        ])
    if linhas:
        pdf.tabela(
            ["Competência", "Receita", "Folha", "Entra", "Origem"],
            linhas,
            [34, 38, 38, 22, 32],
        )
    pdf.linha("Soma da receita que entra", _brl(ap.get("rbt_acumulado")))
    pdf.linha("Meses considerados", ap.get("meses_atividade") or 0)
    if ap.get("annualizado"):
        meses = ap.get("meses_atividade") or 1
        pdf.paragrafo(
            f"Menos de 12 meses. RBT12 = ({_brl(ap.get('rbt_acumulado'))} ÷ {meses}) × 12 = {_brl(rbt)}."
        )
    pdf.linha("RBT12", _brl(rbt), negrito=True)

    pdf.secao("Folha e encargos")
    pdf.linha("Soma da folha que entra", _brl(ap.get("fs_acumulado")))
    if ap.get("annualizado"):
        meses = ap.get("meses_atividade") or 1
        pdf.paragrafo(
            f"FS12 = ({_brl(ap.get('fs_acumulado'))} ÷ {meses}) × 12 = {_brl(fs)}."
        )
    pdf.linha("Folha e encargos (FS12)", _brl(fs), negrito=True)

    pdf.secao("Fator R e anexo")
    if rbt:
        razao = fs / rbt
        pdf.linha("Divisão", f"{_brl(fs)} ÷ {_brl(rbt)} = {razao:.6f}")
        pdf.paragrafo(
            f"A folha {_brl(fs)} dividida pela receita {_brl(rbt)} dá {razao:.6f}, "
            f"ou {razao * 100:.2f}%. Essa conta é o Fator R."
        )
    pdf.linha("Fator R", f"{fator:.2f}%", negrito=True)
    if fator >= 28:
        pdf.paragrafo(f"{fator:.2f}% alcança 28%. Pela Lei Complementar 123/2006, o anexo é o III.")
    else:
        pdf.paragrafo(f"{fator:.2f}% ficou abaixo de 28%. Pela Lei Complementar 123/2006, o anexo é o V.")
    pdf.linha("Anexo", anexo, negrito=True)

    pdf.secao("Como o DAS foi calculado")
    pdf.linha("Faixa", ap.get("faixa") or "-")
    pdf.linha("Alíquota nominal", f"{aliq_nom:.2f}%")
    pdf.linha("Parcela a deduzir", _brl(deducao))
    pdf.paragrafo(
        f"Alíquota efetiva = (({_brl(rbt)} × {aliq_nom:.2f}%) − {_brl(deducao)}) ÷ {_brl(rbt)} = {aliq_ef:.4f}%."
    )
    pdf.paragrafo(f"DAS = {_brl(receita)} × {aliq_ef:.4f}% = {_brl(ap.get('das'))}.")
    pdf.linha("DAS a pagar neste mês", _brl(ap.get("das")), negrito=True)

    if caixa:
        nao_pagos, anteriores = _separar_nao_pagos(pendentes, atrasados, mes_filtro)
        total_fora = sum(float(item.get("valor") or 0) for item in nao_pagos)
        total_anteriores = sum(float(item.get("valor") or 0) for item in anteriores)
        pdf.secao("O que não entrou no cálculo da DAS")
        pdf.linha("Não calculado no período", _brl(total_fora), negrito=True)
        pdf.paragrafo("Não entrou no cálculo da DAS devido ao regime de caixa.")
        if total_anteriores:
            pdf.linha("Parcelas anteriores também fora", _brl(total_anteriores))
    return _saida(pdf)


def pdf_simples_nacional(escola, mes_label, regime, apuracao, funcionarios, receitas_mes, dre=None, titulos=None, regime_apuracao="competencia"):
    ap = apuracao or {}
    quadro = ap.get("quadro") or {}
    pdf = RelatorioPDF("Memória de cálculo — Simples Nacional")
    pdf.add_page()
    pdf.paragrafo(f"{escola} · apuração de {mes_label} · {nome_regime(regime)}")
    pdf.paragrafo(
        "A RBT12 soma a receita bruta dos 12 meses anteriores ao mês de apuração. "
        "O mês vigente não entra nessa soma: ele é a base do DAS. "
        "Mês anterior ao primeiro lançamento do sistema fica de fora quando sai da janela."
    )

    pdf.secao("RBT12 — receita dos 12 meses anteriores")
    linhas_rbt = []
    for linha in quadro.get("linhas") or []:
        linhas_rbt.append([
            linha.get("rotulo") or linha.get("competencia") or "",
            "Sim" if linha.get("entra_rbt12") else "Não",
            _brl(linha.get("receita_bruta")),
        ])
    if linhas_rbt:
        pdf.tabela(["Competência", "Entra", "Receita bruta"], linhas_rbt, [55, 30, 70])
    pdf.linha("Soma dos meses que entram", _brl(ap.get("rbt_acumulado")))
    pdf.linha("Meses considerados", ap.get("meses_atividade") or 0)
    if ap.get("annualizado"):
        pdf.paragrafo("Menos de 12 meses na janela: o valor foi annualizado (soma ÷ meses × 12).")
    pdf.linha("RBT12 usada na faixa", _brl(ap.get("rbt12")), negrito=True)

    pdf.secao("FS12 — folha e encargos dos mesmos meses")
    linhas_fs = []
    for linha in quadro.get("linhas") or []:
        if not linha.get("entra_rbt12"):
            continue
        linhas_fs.append([
            linha.get("rotulo") or linha.get("competencia") or "",
            _brl(linha.get("folha_encargos")),
        ])
    if linhas_fs:
        pdf.tabela(["Competência", "Folha e encargos"], linhas_fs, [80, 70])
    pdf.linha("Soma da folha", _brl(ap.get("fs_acumulado")))
    pdf.linha("FS12", _brl(ap.get("fs12")), negrito=True)

    pdf.secao("Fator R")
    pdf.linha("Fórmula", "FS12 ÷ RBT12")
    pdf.linha("Cálculo", f"{_brl(ap.get('fs12'))} ÷ {_brl(ap.get('rbt12'))}")
    pdf.linha("Fator R", f"{float(ap.get('fator_r_pct') or 0):.2f}%", negrito=True)
    pdf.linha("Anexo", f"{ap.get('anexo') or '-'} (Anexo III se Fator R ≥ 28%)")

    pdf.secao("DAS do mês")
    aliq_nom = float(ap.get("aliquota_nominal") or 0) * 100
    pdf.linha("Receita bruta do mês de apuração", _brl(ap.get("receita_mes")))
    pdf.linha("Faixa", ap.get("faixa") or "-")
    pdf.linha("Alíquota nominal", f"{aliq_nom:.2f}%")
    pdf.linha("Parcela a deduzir", _brl(ap.get("parcela_deduzir")))
    pdf.paragrafo("Alíquota efetiva = ((RBT12 × alíquota nominal) − parcela a deduzir) ÷ RBT12")
    pdf.linha("Alíquota efetiva", f"{float(ap.get('aliquota_efetiva_pct') or 0):.4f}%")
    pdf.paragrafo("DAS = receita bruta do mês × alíquota efetiva")
    pdf.linha("DAS", _brl(ap.get("das")), negrito=True)
    mora = ap.get("mora") or {}
    mora_total = float(mora.get("total") or ap.get("acrescimos_mora") or 0)
    pdf.secao("Juros e multa por atraso recebidos no mês")
    pdf.linha("Juros recebidos", _brl(mora.get("juros")))
    pdf.linha("Multa recebida", _brl(mora.get("multa")))
    pdf.linha("Total de acréscimos", _brl(mora_total), negrito=True)
    pdf.paragrafo(
        "No Simples Nacional, juros, multa e encargos cobrados pelo atraso não compõem a receita bruta "
        "(Resolução CGSN 140/2018, art. 2º, § 5º, II). Por isso entram no caixa e no resultado, "
        "mas não aumentam a base do DAS nem a RBT12.",
        tamanho=9,
    )
    _anexar_titulos_base(pdf, titulos, regime_apuracao or ap.get("regime_apuracao"), ap.get("receita_mes"))
    if dre:
        receita = float(dre.get("receita") or 0)
        das = float(dre.get("das") or 0)
        folha = float(dre.get("folha") or 0)
        compras = float(dre.get("compras") or 0)
        servicos = float(dre.get("servicos") or 0)
        apos_das = receita + mora_total - das
        resultado = apos_das - folha - compras - servicos
        _pagina_resultado(
            pdf,
            "DASN — demonstrativo simplificado",
            f"{escola} · {mes_label} · Simples Nacional",
            [
                ("(+) Receita bruta de serviços", receita, False),
                ("(+) Juros e multa por atraso (fora do DAS)", mora_total, False),
                ("(−) DAS", das, False),
                ("(=) Receita após o DAS", apos_das, True),
                ("(−) Folha e encargos", folha, False),
                ("(−) Compras e custos fixos", compras, False),
                ("(−) Serviços contratados", servicos, False),
                ("(=) Resultado do período", resultado, True),
            ],
            "DRE simplificada, sem plano de contas. O DAS substitui PIS, COFINS, IRPJ, CSLL e ISS. "
            "Não substitui a declaração entregue à Receita.",
        )
    return _saida(pdf)


def pdf_lucro_real(escola, mes_label, regime, totais, recebidos, pendentes, atrasados, folha, pis_cofins=None, titulos=None, regime_apuracao="competencia"):
    pdf = RelatorioPDF("Apuração — Lucro Real")
    pdf.add_page()
    pdf.paragrafo(f"{escola} · {mes_label} · {nome_regime(regime)}")
    ap = pis_cofins or {}
    receita = float(ap.get("receita_mes") or 0)
    mora = float(ap.get("acrescimos_mora") or 0)
    base = float(ap.get("base") or (receita + mora))
    pdf.paragrafo(
        "PIS e COFINS não cumulativos incidem sobre a receita do mês, incluindo juros e multa "
        "por atraso recebidos (STJ, Tema 1.237): PIS 1,65% e COFINS 7,6%."
    )
    pdf.linha("Receita bruta do mês", _brl(receita))
    pdf.linha("Juros e multa por atraso recebidos", _brl(mora))
    pdf.linha("Base de PIS/COFINS", _brl(base), negrito=True)
    pdf.linha("PIS 1,65%", _brl(ap.get("pis")))
    pdf.linha("COFINS 7,6%", _brl(ap.get("cofins")))
    pdf.linha("PIS + COFINS", _brl(ap.get("total")), negrito=True)
    pdf.paragrafo(
        f"Conta: {_brl(base)} × 1,65% = {_brl(ap.get('pis'))}. "
        f"{_brl(base)} × 7,6% = {_brl(ap.get('cofins'))}."
    )
    _anexar_titulos_base(pdf, titulos, regime_apuracao, receita)
    tot = totais or {}
    receita_card = float(tot.get("recebido") or 0)
    folha_valor = float(tot.get("folha_pagamento") or 0)
    compras = float(tot.get("custos_compras") or 0)
    servicos = float(tot.get("custos_servicos") or 0)
    _pagina_resultado(
        pdf,
        "DRE simplificada — Lucro Real",
        f"{escola} · {mes_label}",
        [
            ("(+) Recebido nas mensalidades do vencimento", receita_card, False),
            ("(−) Folha e encargos", folha_valor, False),
            ("(−) Compras e custos fixos", compras, False),
            ("(−) Serviços contratados", servicos, False),
            ("(=) Caixa restante do cartão", receita_card - folha_valor - compras - servicos, True),
        ],
        "DRE simplificada, sem plano de contas. O PIS e a COFINS estão na apuração e não entram nesta subtração do caixa.",
    )
    return _saida(pdf)


def pdf_lucro_presumido(escola, mes_label, regime, apuracao, totais, recebidos, titulos=None, regime_apuracao="competencia"):
    ap = apuracao or {}
    tot = totais or {}
    pdf = RelatorioPDF("Apuração — Lucro Presumido")
    pdf.add_page()
    pdf.paragrafo(f"{escola} · {mes_label}")
    mora = float(ap.get("acrescimos_mora") or 0)
    pdf.linha("Receita bruta do mês", _brl(ap.get("receita_mes")))
    pdf.linha("Juros e multa por atraso recebidos", _brl(mora))
    pdf.linha("Base de PIS/COFINS (receita + juros/multa)", _brl(ap.get("base_pis_cofins")))
    pdf.linha("PIS (0,65%)", _brl(ap.get("pis")))
    pdf.linha("COFINS (3%)", _brl(ap.get("cofins")))
    pdf.linha("ISS estimado (5% da mensalidade)", _brl(ap.get("iss")))
    pdf.linha("32% da receita de serviços", _brl(ap.get("base_servicos")))
    pdf.linha("(+) Juros e multa (100%)", _brl(mora))
    pdf.linha("Base de IRPJ/CSLL", _brl(ap.get("base_presumida")), negrito=True)
    pdf.linha("CSLL (9% da base)", _brl(ap.get("csll")))
    pdf.linha("IRPJ (15% da base)", _brl(ap.get("irpj")))
    if ap.get("aplica_adicional_irpj"):
        pdf.linha("Adicional de IRPJ (10%)", _brl(ap.get("irpj_adicional")))
    pdf.linha("Total de tributos", _brl(ap.get("tributos")), negrito=True)
    pdf.paragrafo(
        "PIS = (receita + juros/multa) × 0,65%. COFINS = (receita + juros/multa) × 3% (STJ, Tema 1.237). "
        "ISS estimado = mensalidade × 5% (juros de mora não são preço do serviço). "
        "IRPJ e CSLL: 32% da receita de serviços educacionais + 100% dos juros e multa recebidos, "
        "que não sofrem presunção (Lei 9.430/96, art. 25, II). IRPJ 15% e CSLL 9% dessa base. "
        "O adicional de 10% de IRPJ só entra se a base do trimestre passar de R$ 60.000, "
        "e o mês mostra um terço desse adicional."
    )
    _anexar_titulos_base(pdf, titulos, regime_apuracao, ap.get("receita_mes"))

    receita = float(ap.get("receita_mes") or 0)
    tributos = float(ap.get("tributos") or 0)
    folha = float(tot.get("folha_pagamento") or ap.get("folha_total") or 0)
    compras = float(tot.get("custos_compras") or 0)
    servicos = float(tot.get("custos_servicos") or 0)
    apos_tributos = receita + mora - tributos
    resultado = apos_tributos - folha - compras - servicos
    _pagina_resultado(
        pdf,
        "DRE simplificada — Lucro Presumido",
        f"{escola} · {mes_label}",
        [
            ("(+) Receita bruta de serviços", receita, False),
            ("(+) Juros e multa por atraso", mora, False),
            ("(−) PIS, COFINS, ISS, IRPJ e CSLL", tributos, False),
            ("(=) Resultado após tributos", apos_tributos, True),
            ("(−) Folha e encargos", folha, False),
            ("(−) Compras e custos fixos", compras, False),
            ("(−) Serviços contratados", servicos, False),
            ("(=) Resultado do período", resultado, True),
        ],
        "DRE simplificada, sem plano de contas. IRPJ e CSLL usam a presunção de 32% sobre a receita de serviços educacionais.",
    )
    return _saida(pdf)


def pdf_custos(escola, mes_label, custos, resumo):
    pdf = RelatorioPDF("Relatório de custos")
    pdf.add_page()
    pdf.paragrafo(f"{escola} · {mes_label}")
    resumo = resumo or {}
    pdf.linha("Compras e custos fixos", _brl(resumo.get("compras")))
    pdf.linha("Serviços contratados", _brl(resumo.get("servicos")))
    pdf.linha("Total do mês", _brl(resumo.get("custos")), negrito=True)
    pdf.ln(3)
    pdf.secao("Lançamentos")
    rotulo_tipo = {
        "avista": "À vista",
        "recorrente": "Recorrente",
        "parcelado": "Parcelado",
        "servico": "Serviço",
    }
    rotulo_forma = {
        "dinheiro": "Pix",
        "cartao": "Cartão",
        "boleto": "Boleto",
        "financiamento": "Financiamento",
    }
    if not custos:
        pdf.paragrafo("Nenhum custo neste mês.")
        return _saida(pdf)
    for item in custos:
        data = item.get("data_custo") or item.get("data_inicio") or ""
        if hasattr(data, "strftime"):
            data = data.strftime("%d/%m/%Y")
        else:
            data = str(data)[:10]
        tipo = rotulo_tipo.get(item.get("tipo") or "", "À vista")
        forma = rotulo_forma.get(item.get("forma") or "", item.get("forma") or "")
        extra = " · ".join(parte for parte in (
            tipo,
            (item.get("categoria") or "").strip(),
            forma,
            (item.get("prestador") or "").strip(),
            data,
        ) if parte)
        nome = (item.get("descricao") or "Custo")[:70]
        pdf.linha(nome, _brl(item.get("valor")))
        if extra:
            pdf.set_font(pdf.fonte, "", 8)
            pdf.set_text_color(100, 116, 139)
            pdf.cell(0, 4.5, extra[:110], new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(40, 40, 40)
    return _saida(pdf)


def pdf_boletim(escola, aluno, notas, faltas_resumo, turmas=None):
    pdf = RelatorioPDF("Boletim escolar")
    pdf.add_page()
    pdf.paragrafo(escola or "Gestão Escolar")
    pdf.linha("Aluno", (aluno or {}).get("nome_completo") or "-")
    pdf.linha("Matrícula", (aluno or {}).get("matricula") or "-")
    if turmas:
        nomes = ", ".join((t.get("nome") or "") for t in turmas)
        pdf.linha("Turmas", nomes)
    pdf.linha("Presenças", (faltas_resumo or {}).get("presente") or 0)
    pdf.linha("Faltas", (faltas_resumo or {}).get("falta") or 0)
    linhas = []
    for n in notas or []:
        linhas.append([
            n.get("materia") or n.get("titulo_avaliacao") or "-",
            n.get("trimestre") or "-",
            n.get("nota") or "-",
        ])
    if linhas:
        pdf.tabela(["Matéria / prova", "Bim.", "Nota"], linhas, [90, 30, 40])
    else:
        pdf.paragrafo("Sem notas lançadas.")
    return _saida(pdf)


def pdf_ficha_pedagogica(
    escola,
    aluno,
    turmas=None,
    notas=None,
    faltas=None,
    faltas_resumo=None,
    modo="simplificado",
):
    """Ficha pedagógica sem dados sensíveis de cadastro (CPF, endereço, responsáveis)."""
    completo = (modo or "simplificado").strip().lower() == "completo"
    titulo = "Ficha pedagógica completa" if completo else "Ficha pedagógica simplificada"
    pdf = RelatorioPDF(titulo)
    pdf.add_page()
    pdf.paragrafo(escola or "Gestão Escolar")
    pdf.linha("Aluno", (aluno or {}).get("nome_completo") or "—")
    pdf.linha("Matrícula", (aluno or {}).get("matricula") or "—")
    pdf.linha("Status", (aluno or {}).get("status") or "—")
    if turmas:
        nomes = ", ".join(
            (t.get("nome") or t.get("nome_turma") or "").strip()
            for t in turmas
            if (t.get("nome") or t.get("nome_turma"))
        )
        pdf.linha("Turmas", nomes or "—")
    resumo = faltas_resumo or {}
    pdf.linha("Presenças", resumo.get("presente") or 0)
    pdf.linha("Faltas", resumo.get("falta") or 0)
    pdf.linha("Justificadas", resumo.get("justificada") or 0)

    _secao_se_couber(pdf, "Notas e avaliações")
    linhas_notas = []
    for n in notas or []:
        data_n = n.get("data_aplicacao")
        if hasattr(data_n, "strftime"):
            data_n = data_n.strftime("%d/%m/%Y")
        linhas_notas.append([
            str(n.get("materia") or "—")[:40],
            str(n.get("titulo_avaliacao") or n.get("titulo") or "—")[:36],
            str(n.get("trimestre") or "—"),
            str(n.get("nota") if n.get("nota") is not None else "—"),
            str(data_n or "—")[:10] if completo else "",
        ])
    if linhas_notas:
        if completo:
            pdf.tabela(
                ["Matéria", "Prova", "Bim.", "Nota", "Data"],
                [[a, b, c, d, e] for a, b, c, d, e in linhas_notas],
                [42, 48, 18, 22, 30],
            )
        else:
            # Resumo: últimas 12
            reduzidas = [[a, b, c, d] for a, b, c, d, _e in linhas_notas[:12]]
            pdf.tabela(["Matéria", "Prova", "Bim.", "Nota"], reduzidas, [50, 55, 22, 30])
            if len(linhas_notas) > 12:
                pdf.paragrafo(f"… e mais {len(linhas_notas) - 12} registro(s). Use a ficha completa.", tamanho=9)
    else:
        pdf.paragrafo("Sem notas lançadas.")

    if completo:
        _secao_se_couber(pdf, "Frequência recente")
        linhas_f = []
        for f in (faltas or [])[:40]:
            data_f = f.get("data_aula")
            if hasattr(data_f, "strftime"):
                data_f = data_f.strftime("%d/%m/%Y")
            linhas_f.append([
                str(data_f or "—"),
                _rotulo_status_chamada(f.get("status")),
                str(f.get("disciplina") or "—")[:50],
            ])
        if linhas_f:
            pdf.tabela(["Data", "Status", "Disciplina"], linhas_f, [35, 35, 90])
        else:
            pdf.paragrafo("Sem registros de frequência.")

        if turmas:
            _secao_se_couber(pdf, "Turmas vinculadas")
            linhas_t = []
            for t in turmas:
                linhas_t.append([
                    str(t.get("nome") or t.get("nome_turma") or "—"),
                    str(t.get("ano_letivo") or "—"),
                    str(t.get("turno") or "—"),
                ])
            pdf.tabela(["Turma", "Ano", "Turno"], linhas_t, [80, 35, 45])
    else:
        pdf.paragrafo(
            "Versão simplificada: identificação, turmas e resumo de notas/frequência. "
            "Para histórico detalhado, gere a ficha completa.",
            tamanho=9,
        )
    return _saida(pdf)


def _hora(valor):
    if hasattr(valor, "strftime"):
        return valor.strftime("%H:%M")
    texto = str(valor or "").strip()
    return texto[:5] if texto else "—"


def _rotulo_tipo_evento(tipo):
    mapa = {
        "geral": "Evento",
        "feriado": "Feriado",
        "prova": "Prova",
        "semana_prova": "Semana de provas",
        "rotina": "Rotina",
    }
    return mapa.get((tipo or "").strip().lower(), tipo or "Evento")


def _rotulo_status_chamada(status):
    mapa = {"presente": "Presente", "falta": "Falta", "justificada": "Justificada"}
    return mapa.get((status or "").strip().lower(), status or "—")


def _abrangencia_rotina(row):
    periodo = (row.get("periodo") or "dia").strip().lower()
    data = _data_br(row.get("data_evento"))
    if periodo == "semana":
        return f"Semana de {data}"
    if periodo == "mes":
        return f"Mês de {data[3:]}" if len(data) >= 10 else f"Mês {data}"
    return f"Dia {data}"


def _secao_se_couber(pdf, titulo):
    if pdf.get_y() > 250:
        pdf.add_page()
    pdf.secao(titulo)


def _detalhes(pdf, itens, rotulo):
    textos = []
    for item in itens or []:
        descricao = (item.get("descricao") or "").strip()
        if not descricao:
            continue
        textos.append(f"{rotulo(item)} — {descricao}")
    if not textos:
        return
    pdf.paragrafo("Detalhes")
    for texto in textos:
        pdf.paragrafo(texto, tamanho=9)


def pdf_historico_periodo(
    escola, periodo_label, contexto,
    incluir_chamada=True, incluir_eventos=True, incluir_rotina=True, incluir_provas=True,
    chamada=None, eventos=None, rotinas=None, provas=None, resumo_chamada=None,
    aviso_rotina="", titulo="Histórico do período",
):
    from datetime import datetime as _dt

    pdf = RelatorioPDF(titulo)
    pdf.add_page()
    pdf.paragrafo(f"{escola or 'Gestão Escolar'} · {periodo_label}")
    pdf.paragrafo(contexto or "Escola")
    pdf.paragrafo(f"Emitido em {_dt.now().strftime('%d/%m/%Y às %H:%M')}.")
    pdf.paragrafo(
        "Este relatório reúne as informações do período escolhido. "
        "Cada bloco abaixo traz o resumo e a lista correspondente."
    )
    pdf.secao("Resumo do período")
    if incluir_eventos:
        pdf.linha("Eventos da escola", len(eventos or []))
    if incluir_provas:
        pdf.linha("Provas", len(provas or []))
    if incluir_rotina:
        pdf.linha("Rotinas do professor", len(rotinas or []))
    if incluir_chamada:
        r = resumo_chamada or {}
        pdf.linha("Presenças", r.get("presente") or 0)
        pdf.linha("Faltas", r.get("falta") or 0)
        pdf.linha("Faltas justificadas", r.get("justificada") or 0)
        pdf.linha("Lançamentos de chamada", len(chamada or []))

    ordem = 0

    def _titulo(bloco):
        nonlocal ordem
        ordem += 1
        return f"{ordem}. {bloco}"

    if incluir_eventos:
        _secao_se_couber(pdf, _titulo("Eventos da escola"))
        linhas = []
        for row in eventos or []:
            linhas.append([
                _data_br(row.get("data_evento")),
                _hora(row.get("horario")),
                _rotulo_tipo_evento(row.get("tipo")),
                row.get("titulo") or "—",
                row.get("turma_nome") or "Escola",
            ])
        if linhas:
            pdf.tabela(["Data", "Horário", "Tipo", "Título", "Turma"], linhas, [28, 22, 36, 64, 40])
            _detalhes(pdf, eventos, lambda row: f"{_data_br(row.get('data_evento'))} · {row.get('titulo') or 'Evento'}")
        else:
            pdf.paragrafo("Nenhum evento da escola neste período.")

    if incluir_provas:
        _secao_se_couber(pdf, _titulo("Provas"))
        linhas = []
        for row in provas or []:
            linhas.append([
                _data_br(row.get("data_prova")),
                _hora(row.get("horario")),
                row.get("materia") or "—",
                row.get("titulo") or "—",
                row.get("turma_nome") or "—",
            ])
        if linhas:
            pdf.tabela(["Data", "Horário", "Disciplina", "Prova", "Turma"], linhas, [28, 22, 36, 64, 40])
            _detalhes(pdf, provas, lambda row: f"{_data_br(row.get('data_prova'))} · {row.get('titulo') or 'Prova'}")
        else:
            pdf.paragrafo("Nenhuma prova neste período.")

    if incluir_rotina:
        _secao_se_couber(pdf, _titulo("Rotina do professor"))
        if aviso_rotina:
            pdf.paragrafo(aviso_rotina)
        linhas = []
        for row in rotinas or []:
            linhas.append([
                _abrangencia_rotina(row),
                row.get("professor_nome") or "—",
                row.get("titulo") or "—",
            ])
        if linhas:
            pdf.tabela(["Quando", "Professor", "Rotina"], linhas, [48, 52, 90])
            _detalhes(pdf, rotinas, lambda row: f"{_abrangencia_rotina(row)} · {row.get('titulo') or 'Rotina'}")
        elif not aviso_rotina:
            pdf.paragrafo("Nenhuma rotina neste período.")

    if incluir_chamada:
        if pdf.get_y() > 180:
            pdf.add_page()
        pdf.secao(_titulo("Chamada"))
        linhas = []
        for row in chamada or []:
            linhas.append([
                _data_br(row.get("data_aula")),
                row.get("nome_completo") or "—",
                row.get("turma_nome") or "—",
                row.get("disciplina") or "—",
                _rotulo_status_chamada(row.get("status")),
            ])
        if linhas:
            pdf.tabela(["Data", "Aluno", "Turma", "Disciplina", "Situação"], linhas, [28, 58, 36, 36, 32])
        else:
            pdf.paragrafo("Nenhum lançamento de chamada neste período.")
    return _saida(pdf)


def pdf_lista_alunos(escola, alunos, termo=""):
    pdf = RelatorioPDF("Alunos")
    pdf.add_page()
    pdf.paragrafo(escola or "Gestão Escolar")
    if termo:
        pdf.paragrafo(f"Pesquisa: {termo}")
    ativos = sum(1 for item in alunos or [] if (item.get("status") or "ativo") != "inativo")
    pdf.secao("Resumo")
    pdf.linha("Alunos nesta lista", len(alunos or []))
    pdf.linha("Ativos", ativos)
    pdf.linha("Inativos", len(alunos or []) - ativos)
    pdf.secao("Cadastro")
    linhas = []
    for item in alunos or []:
        linhas.append([
            item.get("matricula") or "—",
            item.get("nome_completo") or "—",
            item.get("turma_nome") or "—",
            "Inativo" if (item.get("status") or "") == "inativo" else "Ativo",
            item.get("telefone_principal") or "—",
        ])
    if linhas:
        pdf.tabela(["Matrícula", "Aluno", "Turma", "Situação", "Telefone"], linhas, [32, 62, 40, 24, 32])
    else:
        pdf.paragrafo("Nenhum aluno neste filtro.")
    return _saida(pdf)


def pdf_lista_equipe(escola, pessoas):
    pdf = RelatorioPDF("Equipe")
    pdf.add_page()
    pdf.paragrafo(escola or "Gestão Escolar")
    pdf.secao("Resumo")
    pdf.linha("Pessoas", len(pessoas or []))
    pdf.secao("Equipe")
    linhas = []
    for item in pessoas or []:
        linhas.append([
            item.get("nome_completo") or "—",
            item.get("cargo") or item.get("papel") or "—",
            item.get("disciplina") or "—",
            item.get("turmas_lecionadas") or "—",
            item.get("telefone") or "—",
        ])
    if linhas:
        pdf.tabela(["Nome", "Cargo", "Disciplina", "Turmas", "Telefone"], linhas, [48, 36, 32, 42, 32])
    else:
        pdf.paragrafo("Nenhuma pessoa neste filtro.")
    return _saida(pdf)


def pdf_turmas(escola, turmas):
    pdf = RelatorioPDF("Turmas")
    pdf.add_page()
    pdf.paragrafo(escola or "Gestão Escolar")
    pdf.secao("Resumo")
    pdf.linha("Turmas", len(turmas or []))
    pdf.linha("Alunos vinculados", sum(len(item.get("alunos") or []) for item in turmas or []))
    if not turmas:
        pdf.paragrafo("Nenhuma turma cadastrada.")
        return _saida(pdf)
    for turma in turmas:
        _secao_se_couber(pdf, turma.get("nome") or "Turma")
        pdf.linha("Ano letivo", turma.get("ano_letivo") or "—")
        pdf.linha("Turno", turma.get("turno") or "—")
        pdf.linha("Professor responsável", turma.get("professor") or "—")
        alunos = turma.get("alunos") or []
        pdf.linha("Alunos", len(alunos))
        linhas = [[item.get("matricula") or "—", item.get("nome") or "—"] for item in alunos]
        if linhas:
            pdf.tabela(["Matrícula", "Aluno"], linhas, [40, 150])
        else:
            pdf.paragrafo("Nenhum aluno vinculado.")
    return _saida(pdf)


def pdf_notas_fiscais(escola, mes_label, faturado, grupos):
    pdf = RelatorioPDF("Notas fiscais")
    pdf.add_page()
    pdf.paragrafo(f"{escola or 'Gestão Escolar'} · competência {mes_label}")
    pdf.secao("Resumo")
    total = sum(len(grupo.get("notas") or []) for grupo in grupos or [])
    pdf.linha("Notas nesta lista", total)
    pdf.linha("Faturamento fiscal do mês", _brl(faturado), negrito=True)
    pdf.paragrafo("Entram no faturamento só as notas faturadas. Cancelada e substituída não entram de novo.")
    if not grupos:
        pdf.paragrafo("Nenhuma nota neste filtro.")
        return _saida(pdf)
    for grupo in grupos:
        nome = grupo.get("aluno_nome") or "Sem aluno"
        if grupo.get("matricula"):
            nome = f"{nome} · {grupo.get('matricula')}"
        _secao_se_couber(pdf, nome)
        linhas = []
        for nota in grupo.get("notas") or []:
            vinculo = "Válida" if nota.get("status") == "FATURADA" else (nota.get("status") or "—")
            if nota.get("status") == "SUBSTITUIDA":
                vinculo = f"Substituída por {nota.get('substituta_numero') or '—'}"
            elif nota.get("substituida_numero"):
                vinculo = f"Substitui {nota.get('substituida_numero')}"
            linhas.append([
                nota.get("status") or "—",
                nota.get("numero_nfse") or "—",
                nota.get("periodo_competencia_original") or nota.get("periodo_competencia") or "—",
                _brl(nota.get("valor")),
                vinculo,
            ])
        if linhas:
            pdf.tabela(["Situação", "Número", "Competência", "Valor", "Vínculo"], linhas, [28, 28, 32, 32, 70])
    return _saida(pdf)


def pdf_auditoria(escola, registros):
    pdf = RelatorioPDF("Auditoria")
    pdf.add_page()
    pdf.paragrafo(escola or "Gestão Escolar")
    pdf.secao("Resumo")
    pdf.linha("Registros", len(registros or []))
    pdf.secao("Movimentos")
    linhas = []
    for item in registros or []:
        quem = item.get("usuario_nome") or "—"
        login = item.get("login") or item.get("usuario_login") or item.get("usuario_email") or ""
        if login:
            quem = f"{quem} ({login})"
        detalhe = item.get("detalhe_texto") or ""
        if not detalhe and item.get("mudancas"):
            partes = []
            for m in item["mudancas"][:8]:
                partes.append(f"{m.get('campo')}: {m.get('antes')} → {m.get('depois')}")
            detalhe = " · ".join(partes)
        resumo = item.get("resumo") or "—"
        if detalhe:
            resumo = f"{resumo} | {detalhe}"[:180]
        linhas.append([
            item.get("quando") or _data_br(item.get("criado_em")),
            quem[:40],
            item.get("tipo_rotulo") or item.get("tipo") or "—",
            item.get("modulo") or "—",
            resumo,
        ])
    if linhas:
        pdf.tabela(["Quando", "Quem (login)", "Tipo", "Módulo", "Resumo / alterações"], linhas, [28, 42, 24, 24, 72])
    else:
        pdf.paragrafo("Nenhum movimento neste filtro.")
    return _saida(pdf)


def pdf_pasta_professor(escola, professor, arquivos, provas):
    pdf = RelatorioPDF("Pasta do professor")
    pdf.add_page()
    pdf.paragrafo(f"{escola or 'Gestão Escolar'} · {professor or 'Professor'}")
    pdf.secao("Resumo")
    pdf.linha("Arquivos PDF", len(arquivos or []))
    pdf.linha("Provas criadas", len(provas or []))
    pdf.secao("Arquivos")
    rotulos = {"prova_feita": "Prova feita", "prova_aplicar": "Prova a aplicar"}
    linhas = []
    for item in arquivos or []:
        linhas.append([
            rotulos.get(item.get("tipo"), item.get("tipo") or "—"),
            item.get("titulo") or "—",
            item.get("turma_nome") or "—",
        ])
    if linhas:
        pdf.tabela(["Tipo", "Título", "Turma"], linhas, [40, 90, 60])
    else:
        pdf.paragrafo("Nenhum PDF guardado.")
    pdf.secao("Provas criadas no sistema")
    linhas = [[item.get("titulo") or "—", item.get("materia") or "—", item.get("turma_nome") or "—"] for item in provas or []]
    if linhas:
        pdf.tabela(["Prova", "Disciplina", "Turma"], linhas, [80, 55, 55])
    else:
        pdf.paragrafo("Nenhuma prova criada.")
    return _saida(pdf)


def pdf_notas_prova(escola, prova, quadro, filtro="todos", logo=None):
    """Notas de todos os alunos da turma numa prova, com turma, professor e quem está sem nota."""
    from datetime import datetime

    pdf = RelatorioPDF("Notas da prova")
    pdf.add_page()
    if logo and logo[0]:
        arquivo = BytesIO(logo[0])
        arquivo.name = "logo.png" if "png" in (logo[1] or "").lower() else "logo.jpg"
        try:
            pdf.image(arquivo, x=pdf.w - pdf.r_margin - 18, y=pdf.t_margin, w=18)
        except Exception:
            pass
    pdf.paragrafo(escola or "Gestão Escolar")

    data_txt, hora_txt = _data_hora_prova(prova.get("data_aplicacao"), prova.get("horario"))
    pdf.secao("Prova")
    pdf.linha("Prova", prova.get("titulo") or "—")
    pdf.linha("Matéria(s)", prova.get("materia") or "—")
    pdf.linha("Turma", prova.get("turma_nome") or "—")
    pdf.linha("Professor(a) que aplicou", prova.get("professor_nome") or "—")
    pdf.linha("Data de aplicação", f"{data_txt or '—'}{f' às {hora_txt}' if hora_txt else ''}")

    linhas_quadro = quadro.get("quadro") or []
    com_nota = sum(1 for linha in linhas_quadro if linha.get("nota_item"))
    pdf.secao("Resumo")
    pdf.linha("Alunos", len(linhas_quadro))
    pdf.linha("Com nota lançada", com_nota)
    pdf.linha("Sem nota lançada", quadro.get("qtd_sem_nota") or 0, negrito=bool(quadro.get("qtd_sem_nota")))
    if quadro.get("media"):
        pdf.linha("Média da turma", quadro["media"])
        pdf.linha("Maior nota", quadro.get("maior") or "—")
        pdf.linha("Menor nota", quadro.get("menor") or "—")

    if filtro == "com":
        selecionadas = [linha for linha in linhas_quadro if linha.get("nota_item")]
        pdf.secao("Alunos com nota")
    elif filtro == "sem":
        selecionadas = [linha for linha in linhas_quadro if not linha.get("nota_item")]
        pdf.secao("Alunos sem nota")
    else:
        selecionadas = linhas_quadro
        pdf.secao("Notas de todos os alunos")

    tabela, alteradas = [], []
    for numero, linha in enumerate(selecionadas, start=1):
        item = linha.get("nota_item")
        agenda = linha.get("agenda") or {}
        data_aluno = _data_br(agenda.get("data_aplicacao")) if agenda.get("data_aplicacao") else (data_txt or "—")
        if agenda.get("data_original") and agenda.get("data_aplicacao") and str(agenda["data_original"]) != str(agenda["data_aplicacao"]):
            data_aluno += " *"
            alteradas.append(
                f"{linha.get('nome_completo')}: {_data_br(agenda['data_original'])} para {_data_br(agenda['data_aplicacao'])}"
                + (f" — {agenda['justificativa']}" if agenda.get("justificativa") else "")
            )
        if linha.get("fora_da_turma"):
            situacao = "Saiu da turma"
        else:
            situacao = "Lançada" if item else "NÃO LANÇADA"
        tabela.append([
            numero,
            linha.get("nome_completo") or "—",
            linha.get("matricula") or "—",
            data_aluno,
            item.get("nota") if item else "—",
            situacao,
        ])
    if tabela:
        pdf.tabela(["Nº", "Aluno", "Matrícula", "Data da prova", "Nota", "Situação"], tabela, [10, 72, 28, 26, 18, 36])
    else:
        pdf.paragrafo({
            "com": "Nenhuma nota lançada ainda.",
            "sem": "Todos os alunos já têm nota nesta prova.",
        }.get(filtro, "Nenhum aluno nesta turma."))
    if alteradas:
        pdf.paragrafo("* Data alterada só para o aluno:", tamanho=8)
        for texto in alteradas:
            pdf.paragrafo(texto, tamanho=8)

    if pdf.get_y() > 245:
        pdf.add_page()
    pdf.ln(14)
    pdf.set_font(pdf.fonte, "", 10)
    pdf.set_text_color(40, 40, 40)
    pdf.cell(0, 5, "_____________________________________________", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, f"Professor(a) {prova.get('professor_nome') or ''}".strip(), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font(pdf.fonte, "", 8)
    pdf.set_text_color(120, 120, 120)
    try:
        from zoneinfo import ZoneInfo
        agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    except Exception:
        agora = datetime.now()
    pdf.cell(0, 5, f"Gerado em {agora.strftime('%d/%m/%Y %H:%M')}", align="C", new_x="LMARGIN", new_y="NEXT")
    return _saida(pdf)


def pdf_folha_pagamento(escola, mes_label, regime, itens, totais):
    pdf = RelatorioPDF("Folha de pagamento")
    pdf.add_page()
    pdf.paragrafo(f"{escola} · {mes_label} · {nome_regime(regime)}")
    linhas = []
    for item in itens or []:
        linhas.append([
            (item.get("nome_completo") or "")[:28],
            (item.get("rotulo_contrato") or "")[:16],
            _brl(item.get("bruto")),
            _brl(item.get("liquido")),
            _brl(item.get("custo_escola")),
        ])
    if linhas:
        pdf.tabela(["Colaborador", "Contrato", "Bruto", "Líquido", "Custo"], linhas, [50, 38, 34, 34, 34])
    pdf.linha("Custo total da escola", _brl((totais or {}).get("custo_escola")), negrito=True)
    pdf.paragrafo(
        "O cartão Folha e encargos é a soma do custo da escola. "
        "Esse custo junta o que se paga ao colaborador e os encargos da escola. "
        "O líquido sozinho não é o valor do cartão."
    )
    for item in itens or []:
        pdf.secao((item.get("nome_completo") or "Colaborador")[:80])
        pdf.linha("Contrato", (item.get("rotulo_contrato") or item.get("tipo_contrato") or "—")[:40])
        if item.get("observacao"):
            pdf.paragrafo(item.get("observacao"))
        for rotulo, chave in (
            ("Salário ou valor das horas", "salario"),
            ("DSR", "dsr"),
            ("Hora extra 50%", "adicional_he_50"),
            ("Hora extra 100%", "adicional_he_100"),
            ("DSR sobre horas extras", "dsr_he"),
            ("Bruto", "bruto"),
            ("INSS do colaborador", "inss_funcionario"),
            ("IRRF", "irrf"),
            ("PIS retido", "pis"),
            ("COFINS retido", "cofins"),
            ("CSLL retido", "csll"),
            ("ISS retido", "iss"),
            ("Líquido", "liquido"),
            ("FGTS", "fgts"),
            ("Provisão de 13º", "provisao_13"),
            ("Férias + 1/3", "ferias_terco"),
            ("INSS patronal", "inss_patronal"),
            ("RAT", "rat"),
            ("Sistema S", "sistema_s"),
            ("Encargos da escola", "encargos"),
        ):
            valor = float(item.get(chave) or 0)
            if valor:
                pdf.linha(rotulo, _brl(valor))
        pdf.linha("Custo deste colaborador", _brl(item.get("custo_escola")), negrito=True)
    pdf.linha("Soma do cartão", _brl((totais or {}).get("custo_escola")), negrito=True)
    return _saida(pdf)


def pdf_composicao_mensalidades(escola, mes_label, titulo, explicacao, itens, total):
    pdf = RelatorioPDF(titulo)
    pdf.add_page()
    pdf.paragrafo(f"{escola} · {mes_label}")
    pdf.paragrafo(explicacao)
    linhas = []
    for item in itens or []:
        linhas.append([
            (item.get("nome_completo") or "Aluno")[:18],
            (item.get("descricao") or "—")[:20],
            _data_br(item.get("data_vencimento")),
            _data_br(item.get("data_pagamento")) if item.get("data_pagamento") else "—",
            (item.get("forma_pagamento") or "—")[:12],
            _brl(item.get("valor")),
        ])
    if linhas:
        pdf.tabela(
            ["Aluno", "Descrição", "Vencimento", "Data da baixa", "Forma", "Valor"],
            linhas,
            [36, 40, 28, 32, 26, 28],
        )
    else:
        pdf.paragrafo("Nenhum lançamento compõe este valor.")
    pdf.linha("Total do cartão", _brl(total), negrito=True)
    pdf.paragrafo(f"{len(linhas)} lançamento(s). A soma destas linhas é o valor exibido no cartão.")
    return _saida(pdf)


def pdf_composicao_custos(escola, mes_label, titulo, explicacao, itens, total):
    pdf = RelatorioPDF(titulo)
    pdf.add_page()
    pdf.paragrafo(f"{escola} · {mes_label}")
    pdf.paragrafo(explicacao)
    if not itens:
        pdf.paragrafo("Nenhum lançamento compõe este valor.")
    for item in itens or []:
        pdf.linha((item.get("descricao") or "Custo")[:70], _brl(item.get("valor")))
        if item.get("porque"):
            pdf.set_x(pdf.l_margin)
            pdf.set_font(pdf.fonte, "", 8)
            pdf.set_text_color(100, 116, 139)
            pdf.multi_cell(
                0, 4.5, str(item.get("porque"))[:240],
                align="L", new_x="LMARGIN", new_y="NEXT", wrapmode="CHAR",
            )
            pdf.set_text_color(40, 40, 40)
            pdf.ln(1)
    pdf.linha("Total do cartão", _brl(total), negrito=True)
    return _saida(pdf)


def pdf_caixa_restante(escola, mes_label, partes, total, regime_apuracao):
    pdf = RelatorioPDF("Caixa restante")
    pdf.add_page()
    pdf.paragrafo(f"{escola} · {mes_label}")
    pdf.paragrafo(
        "Este número é a conta do cartão: recebido nas mensalidades do vencimento, "
        "menos folha, tributos, compras e serviços. Não é uma DRE. "
        "A DRE continua simplificada porque a escola não usa plano de contas."
    )
    if (regime_apuracao or "") == "caixa":
        pdf.paragrafo(
            "Os tributos desta conta seguem o regime de caixa: a base é a data da baixa. "
            "O recebido do cartão continua sendo as mensalidades deste vencimento que já foram quitadas."
        )
    else:
        pdf.paragrafo(
            "Os tributos desta conta seguem o regime de competência: a base é o vencimento do mês."
        )
    for rotulo, valor in partes:
        pdf.linha(rotulo, _brl(valor))
    pdf.linha("(=) Caixa restante", _brl(total), negrito=True)
    pdf.paragrafo("Cada parcela tem o relatório completo no cartão correspondente.")
    return _saida(pdf)


def pdf_regime_apuracao(escola, mes_label, regime_apuracao, regime_tributario):
    pdf = RelatorioPDF("Regime de apuração")
    pdf.add_page()
    pdf.paragrafo(f"{escola} · {mes_label} · {nome_regime(regime_tributario)}")
    if (regime_apuracao or "") == "caixa":
        pdf.secao("Regime de caixa")
        pdf.paragrafo(
            "A escola optou pelo regime de caixa. O imposto do mês usa a data da baixa: "
            "o valor entra quando foi pago, não quando venceu."
        )
        pdf.paragrafo(
            "O cartão Pago no mês lista essas baixas, mesmo que o vencimento seja de outro mês. "
            "Mensalidade emitida e sem baixa não entra na base do imposto."
        )
        pdf.paragrafo(
            "O cartão Total recebido é outra conta: mensalidades deste vencimento que já receberam baixa. "
            "Ele alimenta o caixa restante. O imposto, no regime de caixa, usa o cartão Pago no mês."
        )
    else:
        pdf.secao("Regime de competência")
        pdf.paragrafo(
            "A escola está no regime de competência. O imposto usa o vencimento da mensalidade, "
            "tenha sido paga ou não."
        )
        pdf.paragrafo(
            "A data da baixa registra quando o dinheiro entrou, mas não muda o mês do imposto "
            "enquanto o regime continuar sendo o de competência."
        )
    return _saida(pdf)


def _total_recebido_item(item):
    return (
        float(item.get("valor") or 0)
        + float(item.get("juros_valor") or 0)
        + float(item.get("multa_valor") or 0)
    )


def _mes_vencimento(item):
    valor = item.get("data_vencimento")
    if hasattr(valor, "strftime"):
        return valor.strftime("%Y-%m")
    texto = str(valor or "")
    if len(texto) >= 7 and texto[4] == "-":
        return texto[:7]
    return ""


def _separar_nao_pagos(pendentes, atrasados, mes_filtro):
    do_mes = list(pendentes or [])
    anteriores = []
    for item in atrasados or []:
        if mes_filtro and _mes_vencimento(item) == mes_filtro:
            do_mes.append(item)
        else:
            anteriores.append(item)
    return do_mes, anteriores


def _titulo_folha(pdf, texto):
    pdf.set_x(pdf.l_margin)
    pdf.set_font(pdf.fonte, "B", 14)
    pdf.set_text_color(30, 58, 95)
    pdf.multi_cell(0, 8, texto, align="L", new_x="LMARGIN", new_y="NEXT", wrapmode="CHAR")
    pdf.set_text_color(40, 40, 40)
    pdf.ln(1)


def _total_destaque(pdf, rotulo, valor):
    pdf.set_x(pdf.l_margin)
    pdf.set_font(pdf.fonte, "B", 12)
    pdf.set_text_color(30, 58, 95)
    pdf.cell(pdf.epw * 0.62, 10, rotulo)
    pdf.set_font(pdf.fonte, "B", 14)
    pdf.cell(pdf.epw * 0.38, 10, valor, align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(40, 40, 40)


def _nome_aluno(pdf, item, tamanho, fundo):
    if pdf.get_y() > 215:
        pdf.add_page()
    pdf.set_x(pdf.l_margin)
    pdf.set_fill_color(*fundo)
    pdf.set_font(pdf.fonte, "B", tamanho)
    pdf.set_text_color(30, 58, 95)
    pdf.multi_cell(
        0, 8, item.get("nome_completo") or "Aluno",
        align="L", fill=True, new_x="LMARGIN", new_y="NEXT", wrapmode="CHAR",
    )
    pdf.set_text_color(40, 40, 40)
    pdf.ln(1)


def _ficha_nao_pago(pdf, item, caixa, tamanho=10):
    _nome_aluno(pdf, item, 12, (254, 242, 242))
    parcela = item.get("parcela_contrato")
    juros_pct = float(item.get("juros_percentual") or 0)
    juros_valor = float(item.get("juros_valor") or 0)
    multa_valor = float(item.get("multa_valor") or 0)
    pdf.linha("Matrícula", item.get("matricula") or "—", tamanho=tamanho)
    if parcela:
        pdf.linha("Parcela", str(parcela), tamanho=tamanho)
    pdf.linha("Descrição", (item.get("descricao") or "Mensalidade").strip(), tamanho=tamanho)
    pdf.linha("Vencimento", _data_br(item.get("data_vencimento")), tamanho=tamanho)
    pdf.linha("Situação", item.get("status") or "Sem baixa", tamanho=tamanho)
    pdf.linha("Mensalidade", _brl(item.get("valor")), negrito=True, tamanho=tamanho)
    if juros_pct or juros_valor:
        pdf.linha("Juros", f"{juros_pct:g}% = {_brl(juros_valor)}", tamanho=tamanho)
        pdf.paragrafo(
            "Há juros lançados nesta parcela, mas sem baixa eles não entram na apuração.",
            tamanho=tamanho,
        )
    else:
        pdf.linha("Juros", "R$ 0,00", tamanho=tamanho)
        pdf.paragrafo(
            "Sem baixa: juros não foram lançados nesta mensalidade e não entram na apuração.",
            tamanho=tamanho,
        )
    if multa_valor:
        pdf.linha("Multa", _brl(multa_valor), tamanho=tamanho)
        pdf.paragrafo(
            "Há multa lançada nesta parcela, mas sem baixa ela não entra na apuração.",
            tamanho=tamanho,
        )
    else:
        pdf.linha("Multa", "R$ 0,00", tamanho=tamanho)
        pdf.paragrafo(
            "Sem baixa: multa não foi lançada nesta mensalidade e não entra na apuração.",
            tamanho=tamanho,
        )
    if caixa:
        pdf.linha("Apuração", "Fora da base do regime de caixa", negrito=True, tamanho=tamanho)
    else:
        pdf.linha("Apuração", "Entra pelo vencimento, mesmo sem baixa", negrito=True, tamanho=tamanho)
    pdf.ln(3)


def _ficha_pago(pdf, item, caixa):
    entrou = _total_recebido_item(item)
    _nome_aluno(pdf, item, 14, (236, 253, 243))
    parcela = item.get("parcela_contrato")
    juros_pct = float(item.get("juros_percentual") or 0)
    juros_valor = float(item.get("juros_valor") or 0)
    multa_valor = float(item.get("multa_valor") or 0)
    pdf.linha("Matrícula", item.get("matricula") or "—", tamanho=11)
    if parcela:
        pdf.linha("Parcela", str(parcela), tamanho=11)
    pdf.linha("Descrição", (item.get("descricao") or "Mensalidade").strip(), tamanho=11)
    pdf.linha("Vencimento", _data_br(item.get("data_vencimento")), tamanho=11)
    pdf.linha("Data da baixa", _data_br(item.get("data_pagamento")), tamanho=11)
    if item.get("forma_pagamento"):
        pdf.linha("Forma", str(item.get("forma_pagamento")), tamanho=11)
    pdf.linha("Mensalidade", _brl(item.get("valor")), tamanho=11)
    if juros_pct or juros_valor:
        pdf.linha("Juros", f"{juros_pct:g}% = {_brl(juros_valor)}", tamanho=11)
        pdf.paragrafo("Este juros entrou na base porque a baixa é deste mês.", tamanho=11)
    else:
        pdf.linha("Juros", "R$ 0,00", tamanho=11)
        pdf.paragrafo("Não houve juros nesta baixa.", tamanho=11)
    if multa_valor:
        pdf.linha("Multa", _brl(multa_valor), tamanho=11)
        pdf.paragrafo("Esta multa entrou na base porque a baixa é deste mês.", tamanho=11)
    else:
        pdf.linha("Multa", "R$ 0,00", tamanho=11)
        pdf.paragrafo("Não houve multa nesta baixa.", tamanho=11)
    pdf.linha("Total que entrou", _brl(entrou), negrito=True, tamanho=12)
    if caixa:
        pdf.linha("Apuração", "Entrou na base do regime de caixa", negrito=True, tamanho=11)
    else:
        pdf.linha("Apuração", "A competência usa o vencimento, não esta baixa", negrito=True, tamanho=11)
    pdf.ln(4)


def pdf_regime_detalhado(
    escola, mes_label, regime_apuracao, regime_tributario,
    recebidos, pendentes, atrasados, mes_filtro="", parte="",
):
    caixa = (regime_apuracao or "") == "caixa"
    parte = (parte or "").strip()
    nao_pagos, anteriores = _separar_nao_pagos(pendentes, atrasados, mes_filtro)
    total_pago = sum(_total_recebido_item(item) for item in (recebidos or []))
    total_nao_pago = sum(float(item.get("valor") or 0) for item in nao_pagos)
    total_anteriores = sum(float(item.get("valor") or 0) for item in anteriores)
    titulo = "Regime de caixa" if caixa else "Regime de competência"
    if parte == "pago":
        titulo += " — pagos"
    elif parte == "nao_pago":
        titulo += " — não pagos"

    pdf = RelatorioPDF(titulo)
    pdf.add_page()
    pdf.paragrafo(f"{escola} · {mes_label} · {nome_regime(regime_tributario)}")
    _total_destaque(pdf, "Total pago no mês", _brl(total_pago))
    _total_destaque(pdf, "Total não pago no mês", _brl(total_nao_pago))
    pdf.ln(2)
    if caixa:
        pdf.paragrafo(
            "O total pago é o que teve baixa neste mês, com juros e multa quando houver. "
            "Esse valor entra na apuração do regime de caixa. "
            "O total não pago vence neste mês e não teve baixa, então ficou fora da apuração."
        )
    else:
        pdf.paragrafo(
            "O total pago é o que teve baixa neste mês. "
            "O total não pago vence neste mês e ainda não teve baixa. "
            "No regime de competência, os dois entram pelo vencimento."
        )
    if anteriores:
        pdf.linha("Parcelas anteriores sem baixa", _brl(total_anteriores), negrito=True)
        if parte == "pago":
            pdf.paragrafo("O detalhe dessas parcelas está no PDF de quem não pagou.")
        else:
            pdf.paragrafo("Elas aparecem nas folhas de quem não pagou.")
    if parte == "pago":
        pdf.paragrafo("A folha seguinte lista só os alunos que tiveram baixa neste mês.")
    elif parte == "nao_pago":
        pdf.paragrafo("A folha seguinte lista só os alunos que ficaram sem baixa.")
    else:
        pdf.paragrafo("A folha seguinte lista os alunos sem baixa. A outra folha lista os alunos que pagaram neste mês.")

    if parte != "pago":
        pdf.add_page()
        _titulo_folha(pdf, "Não pagos neste mês")
        if caixa:
            pdf.paragrafo(
                "Estes alunos vencem neste mês e não tiveram baixa. "
                "O valor não entrou na apuração do regime de caixa. "
                "Em cada mensalidade está a apuração de juros e de multa."
            )
        else:
            pdf.paragrafo(
                "Estes alunos vencem neste mês e não tiveram baixa. "
                "Em cada mensalidade está a apuração de juros e de multa."
            )
        if not nao_pagos:
            pdf.paragrafo("Nenhuma mensalidade deste mês ficou sem baixa.")
        for item in nao_pagos:
            _ficha_nao_pago(pdf, item, caixa)
        if nao_pagos:
            pdf.linha("Total não pago no mês", _brl(total_nao_pago), negrito=True, tamanho=12)

        if anteriores:
            pdf.ln(2)
            pdf.secao("Parcelas anteriores ainda sem baixa")
            pdf.paragrafo(
                "Venceram antes deste mês e continuam sem pagamento. "
                + (
                    "Ficam fora da apuração até a baixa, com juros e multa se forem lançados nesse dia."
                    if caixa else
                    "No regime de competência, já entraram no mês do vencimento."
                )
            )
            for item in anteriores:
                _ficha_nao_pago(pdf, item, caixa)
            pdf.linha("Total de parcelas anteriores", _brl(total_anteriores), negrito=True, tamanho=12)

    if parte != "nao_pago":
        pdf.add_page()
        _titulo_folha(pdf, "Pagos neste mês")
        pdf.paragrafo(
            "Estes alunos tiveram baixa neste mês. "
            + (
                "O total de cada um, com juros e multa, entrou na apuração do regime de caixa."
                if caixa else
                "A data da baixa mostra quando o dinheiro entrou. No regime de competência, o imposto segue o vencimento."
            )
        )
        if not recebidos:
            pdf.paragrafo("Nenhuma baixa neste mês.")
        for item in recebidos or []:
            _ficha_pago(pdf, item, caixa)
        pdf.linha("Total pago no mês", _brl(total_pago), negrito=True, tamanho=12)
    return _saida(pdf)


def pdf_contracheque(escola, mes_label, item):
    pdf = RelatorioPDF("Contra-cheque")
    pdf.add_page()
    pdf.paragrafo(f"{escola} · {mes_label}")
    pdf.linha("Colaborador", (item or {}).get("nome_completo") or "-")
    pdf.linha("Cargo", (item or {}).get("cargo") or "-")
    pdf.linha("Contrato", (item or {}).get("rotulo_contrato") or "-")
    if (item or {}).get("dia_pagamento"):
        pdf.linha("Dia de pagamento", str(item.get("dia_pagamento")))
    if (item or {}).get("adicional_he_50"):
        pdf.linha(
            "Hora extra 50% (dia útil)",
            f"{item.get('horas_extras') or 0:g} h × {_brl(item.get('valor_hora_extra'))} = {_brl(item.get('adicional_he_50'))}",
        )
    if (item or {}).get("adicional_he_100"):
        pdf.linha(
            "Hora extra 100% (domingo/feriado)",
            f"{item.get('horas_extras_100') or 0:g} h × {_brl(item.get('valor_hora_extra_100'))} = {_brl(item.get('adicional_he_100'))}",
        )
    if (item or {}).get("dsr_he"):
        pdf.linha("DSR sobre horas extras", _brl(item.get("dsr_he")))
    if (item or {}).get("adicional_he") and not (item or {}).get("adicional_he_50") and not (item or {}).get("adicional_he_100"):
        pdf.linha(
            "Horas extras",
            f"{item.get('horas_extras') or 0:g} h × {_brl(item.get('valor_hora_extra'))} = {_brl(item.get('adicional_he'))}",
        )
    pdf.linha("Bruto", _brl((item or {}).get("bruto")), negrito=True)
    pdf.linha("INSS", _brl((item or {}).get("inss_funcionario")))
    pdf.linha("IRRF", _brl((item or {}).get("irrf")))
    if (item or {}).get("desconto_faltas"):
        pdf.linha("Faltas não justificadas", _brl(item.get("desconto_faltas")))
    if (item or {}).get("desconto_dsr_faltas"):
        pdf.linha("DSR por faltas", _brl(item.get("desconto_dsr_faltas")))
    pdf.linha("Líquido", _brl((item or {}).get("liquido")), negrito=True)
    if (item or {}).get("observacao"):
        pdf.paragrafo(item.get("observacao"))
    return _saida(pdf)


def pdf_ponto(escola, colaborador, periodo_rotulo, registros, faltas=None, atestados=None, resumo=None):
    pdf = RelatorioPDF("Relatório de ponto")
    pdf.add_page()
    pdf.paragrafo(f"{escola or 'Gestão Escolar'} · {colaborador or 'Colaborador'}")
    pdf.linha("Período", periodo_rotulo or "—")
    if resumo:
        pdf.secao("Resumo do período")
        pdf.linha("Jornada esperada/dia", resumo.get("jornada_fmt") or "—")
        pdf.linha("Horas positivas", resumo.get("positivo_fmt") or "0h00")
        pdf.linha("Horas negativas", resumo.get("negativo_fmt") or "0h00")
        pdf.linha("Saldo líquido (banco)", resumo.get("liquido_fmt") or "0h00", negrito=True)
        pdf.linha("Total presença (entrada→saída)", resumo.get("presenca_fmt") or "—")
        pdf.linha("Total em café", resumo.get("cafe_fmt") or "—")
        pdf.linha("Total em almoço", resumo.get("almoco_fmt") or "—")
        pdf.linha("Total horas trabalhadas", resumo.get("trabalhado_fmt") or "—")

    pdf.secao("Batidas detalhadas")
    linhas = []
    for item in registros or []:
        data = item.get("data_ref")
        if hasattr(data, "strftime"):
            data = data.strftime("%d/%m/%Y")
        linhas.append([
            data or "—",
            item.get("entrada") or "—",
            item.get("cafe_ida") or "—",
            item.get("cafe_volta") or "—",
            item.get("cafe_dur_fmt") or "—",
            item.get("almoco") or "—",
            item.get("almoco_volta") or item.get("cafe") or "—",
            item.get("almoco_dur_fmt") or "—",
            item.get("saida") or "—",
        ])
    if linhas:
        pdf.tabela(
            ["Data", "Entrada", "Café↓", "Café↑", "Café", "Almoço↓", "Almoço↑", "Almoço", "Saída"],
            linhas,
            [20, 18, 16, 16, 16, 18, 18, 18, 18],
        )
    else:
        pdf.paragrafo("Nenhuma batida neste período.")

    pdf.secao("Presença e banco de horas por dia")
    linhas = []
    for item in registros or []:
        data = item.get("data_ref")
        if hasattr(data, "strftime"):
            data = data.strftime("%d/%m/%Y")
        linhas.append([
            data or "—",
            item.get("presenca_fmt") or "—",
            item.get("trabalhado_fmt") or "—",
            item.get("esperado_fmt") or "—",
            item.get("saldo_fmt") or "—",
            (f"+{item.get('excesso_cafe_min')}m" if item.get("excesso_cafe_min") else "—"),
            (f"+{item.get('excesso_almoco_min')}m" if item.get("excesso_almoco_min") else "—"),
        ])
    if linhas:
        pdf.tabela(
            ["Data", "Presença", "Trabalhado", "Esperado", "Saldo", "+Café", "+Almoço"],
            linhas,
            [24, 24, 26, 24, 24, 20, 22],
        )
    else:
        pdf.paragrafo("Sem dias fechados (entrada e saída) neste período.")

    pdf.paragrafo(
        "Presença = saída − entrada. Trabalhado = presença − tempo de café − tempo de almoço. "
        "Saldo = trabalhado − jornada do dia. +Café/+Almoço = minutos além do prazo."
    )

    pdf.secao("Faltas e justificativas")
    linhas = []
    for item in faltas or []:
        data = item.get("data_ref")
        if hasattr(data, "strftime"):
            data = data.strftime("%d/%m/%Y")
        tipo = "Não justificada" if item.get("tipo") == "nao_justificada" else "Justificada"
        desc = "Sim" if item.get("descontar") and item.get("status") == "confirmada" and item.get("tipo") == "nao_justificada" else "Não"
        linhas.append([data or "—", tipo, item.get("status") or "—", desc, (item.get("motivo") or "—")[:40]])
    if linhas:
        pdf.tabela(["Data", "Tipo", "Status", "Desconto", "Motivo"], linhas, [28, 32, 28, 24, 50])
    else:
        pdf.paragrafo("Nenhuma falta neste período.")
    pdf.secao("Atestados")
    linhas = []
    for item in atestados or []:
        ini = item.get("data_inicio") or item.get("criado_em")
        fim = item.get("data_fim")
        if hasattr(ini, "strftime"):
            ini = ini.strftime("%d/%m/%Y")
        if hasattr(fim, "strftime"):
            fim = fim.strftime("%d/%m/%Y")
        periodo = f"{ini or '—'}" + (f" a {fim}" if fim else "")
        linhas.append([periodo, item.get("titulo") or "Atestado", item.get("status") or "—"])
    if linhas:
        pdf.tabela(["Período", "Título", "Status"], linhas, [50, 80, 40])
    else:
        pdf.paragrafo("Nenhum atestado neste período.")
    pdf.paragrafo(
        "Falta não justificada confirmada com desconto: dia + DSR da semana (Lei 605/1949). "
        "Atestado aprovado gera falta justificada sem desconto."
    )
    return _saida(pdf)


def pdf_cobranca_mensalidade(escola, cobranca, aluno=None):
    pdf = RelatorioPDF("Cobrança de mensalidade")
    pdf.add_page()
    pdf.paragrafo(escola or "Gestão Escolar")
    nome = (aluno or {}).get("nome_completo") or cobranca.get("nome_completo") or "Aluno"
    pdf.linha("Aluno", nome)
    if (aluno or {}).get("matricula"):
        pdf.linha("Matrícula", aluno.get("matricula"))
    pdf.linha("Descrição", cobranca.get("descricao") or "Mensalidade")
    venc = cobranca.get("data_vencimento")
    if hasattr(venc, "strftime"):
        venc = venc.strftime("%d/%m/%Y")
    pdf.linha("Vencimento", venc or "-")
    valor = float(cobranca.get("valor") or 0)
    juros_pct = float(cobranca.get("juros_percentual") or 0)
    juros = float(cobranca.get("juros_valor") or 0)
    multa = float(cobranca.get("multa_valor") or 0)
    pdf.linha("Valor da mensalidade", br_money(valor), negrito=not (juros or multa))
    if juros or multa:
        pdf.linha("Juros por atraso", f"{juros_pct:g}% = {br_money(juros)}" if juros_pct else br_money(juros))
        pdf.linha("Multa por atraso", br_money(multa))
        pdf.linha("Total com acréscimos", br_money(valor + juros + multa), negrito=True)
    pdf.linha("Status", cobranca.get("status") or "Pendente")
    pago = cobranca.get("data_pagamento")
    if pago:
        pdf.linha("Data da baixa", pago.strftime("%d/%m/%Y") if hasattr(pago, "strftime") else str(pago)[:10])
        if cobranca.get("forma_pagamento"):
            pdf.linha("Forma de pagamento", cobranca.get("forma_pagamento"))
    pdf.paragrafo("Aviso de cobrança da mensalidade. Confirme o pagamento com a secretaria.")
    return _saida(pdf)


def _linha_rescisao_calc(pdf, calculo):
    """Memória de cálculo completa de uma rescisão."""
    c = calculo or {}
    pdf.linha("Tipo", c.get("rotulo_tipo") or c.get("tipo_rescisao") or "-")
    pdf.linha("Aviso prévio", c.get("rotulo_aviso") or c.get("aviso_modalidade") or "-")
    pdf.linha("Admissão", c.get("data_admissao") or "-")
    pdf.linha("Desligamento", c.get("data_desligamento") or "-")
    pdf.linha("Salário de referência", _brl(c.get("salario_mensal")))
    pdf.ln(2)
    pdf.secao("Verbas")
    pdf.linha(f"Saldo de salário ({c.get('dias_trabalhados_mes') or 0} dias)", _brl(c.get("saldo_salario")))
    pdf.linha(f"Aviso prévio ({c.get('dias_aviso') or 0} dias)", _brl(c.get("aviso_indenizado")))
    if float(c.get("aviso_desconto") or 0) > 0:
        pdf.linha("Desconto aviso não cumprido", f"- {_brl(c.get('aviso_desconto'))}")
    pdf.linha(f"13º proporcional ({c.get('avos_13') or 0}/12)", _brl(c.get("decimo_terceiro")))
    pdf.linha("Férias vencidas", _brl(c.get("ferias_vencidas")))
    pdf.linha("1/3 férias vencidas", _brl(c.get("terco_ferias_vencidas")))
    pdf.linha(f"Férias proporcionais ({c.get('avos_ferias_proporcionais') or 0}/12)", _brl(c.get("ferias_proporcionais")))
    pdf.linha("1/3 férias proporcionais", _brl(c.get("terco_ferias_proporcionais")))
    if float(c.get("outros_proventos") or 0) > 0:
        pdf.linha("Outros proventos", _brl(c.get("outros_proventos")))
    if float(c.get("multa_art_477") or 0) > 0:
        pdf.linha("Multa Art. 477 § 8º (atraso)", _brl(c.get("multa_art_477")))
    pdf.ln(2)
    pdf.secao("Descontos do trabalhador")
    tem_detalhe = "inss_mensal" in c
    if tem_detalhe:
        pdf.linha(f"INSS sobre saldo (base {_brl(c.get('base_inss_mensal'))})", f"- {_brl(c.get('inss_mensal'))}")
        pdf.linha("INSS sobre 13º (à parte)", f"- {_brl(c.get('inss_13'))}")
        pdf.linha("IRRF sobre saldo", f"- {_brl(c.get('irrf_mensal'))}")
        pdf.linha("IRRF sobre 13º (exclusivo)", f"- {_brl(c.get('irrf_13'))}")
    else:
        pdf.linha("INSS (estimativa)", f"- {_brl(c.get('inss'))}")
        pdf.linha("IRRF (estimativa)", f"- {_brl(c.get('irrf'))}")
    if float(c.get("outros_descontos") or 0) > 0:
        pdf.linha("Outros descontos", f"- {_brl(c.get('outros_descontos'))}")
    pdf.ln(2)
    pdf.secao("Encargos da escola")
    aliq = float(c.get("aliquota_fgts") or 0) * 100
    aliq_m = float(c.get("aliquota_multa_fgts") or 0) * 100
    pdf.linha(f"FGTS do mês ({aliq:.1f}%)", _brl(c.get("fgts_mes")))
    pdf.linha(f"Multa FGTS ({aliq_m:.0f}%)", _brl(c.get("multa_fgts")))
    if float(c.get("inss_patronal") or 0) > 0:
        aliq_p = float(c.get("aliquota_patronal") or 0) * 100
        pdf.linha(f"INSS patronal + RAT + terceiros ({aliq_p:.1f}%)", _brl(c.get("inss_patronal")))
    elif tem_detalhe:
        pdf.linha("INSS patronal", "incluído no DAS (Simples)")
    pdf.ln(2)
    pdf.secao("Totais")
    pdf.linha("Proventos", _brl(c.get("proventos")))
    pdf.linha("Descontos", _brl(c.get("descontos")))
    pdf.linha("Líquido ao trabalhador", _brl(c.get("total_liquido")), negrito=True)
    pdf.linha("Custo total da escola", _brl(c.get("custo_empregador")), negrito=True)
    if float(c.get("saque_fgts_percentual") or 0) > 0:
        pct = float(c.get("saque_fgts_percentual")) * 100
        pdf.linha(f"Saque do FGTS ({pct:.0f}% + multa)", f"≈ {_brl(c.get('saque_fgts_estimado'))}")
    if tem_detalhe:
        pdf.linha("Seguro-desemprego", "Tem direito" if c.get("seguro_desemprego") else "Não tem direito")
    if c.get("data_limite_pagamento"):
        pdf.paragrafo(
            f"Prazo Art. 477 §6º CLT: quitação até {c.get('data_limite_pagamento')}."
            + (" Atenção: pagamento em atraso." if c.get("pagamento_atrasado") else "")
        )
    if tem_detalhe:
        pdf.secao("Incidência por verba")
        pdf.tabela(
            ["Verba", "INSS", "IRRF", "FGTS"],
            [
                ["Saldo de salário", "Sim", "Sim", "Sim"],
                ["13º proporcional", "Sim*", "Sim (exclusivo)", "Sim"],
                ["Aviso prévio indenizado", "Não", "Não", "Sim"],
                ["Férias indenizadas + 1/3", "Não", "Não", "Não"],
                ["Multa FGTS / Art. 477", "Não", "Não", "Não"],
            ],
            [70, 35, 45, 30],
        )
        pdf.paragrafo(
            "* A parte do 13º gerada só pela projeção do aviso indenizado não tem INSS. "
            "Bases: Lei 8.212/91, art. 28, § 9º; Súmulas 305 TST, 125 e 386 STJ; STJ Tema 478.",
            tamanho=9,
        )
    obrigacoes = c.get("obrigacoes") or []
    if obrigacoes:
        pdf.secao("Prazos de pagamento e recolhimento")
        pdf.tabela(
            ["Obrigação", "Prazo"],
            [[str(o.get("item"))[:70], _data_br(o.get("prazo"))] for o in obrigacoes],
            [140, 40],
        )
    pdf.paragrafo(
        "Custo da escola = líquido + INSS + IRRF retidos + FGTS do mês + multa FGTS"
        + (" + cota patronal" if float(c.get("inss_patronal") or 0) > 0 else "")
        + ". A multa e o FGTS vão à conta vinculada; o líquido é pago ao trabalhador. "
        "Valores estimados sem dependentes de IR; confira com a contabilidade."
    )


def pdf_rescisao(escola, pessoa, calculo, rescisao_id=None):
    pdf = RelatorioPDF("Rescisão contratual — memória de cálculo")
    pdf.add_page()
    pdf.paragrafo(escola or "Gestão Escolar")
    if rescisao_id:
        pdf.linha("Rescisão nº", str(rescisao_id))
    pdf.linha("Colaborador", (pessoa or {}).get("nome_completo") or "-")
    if (pessoa or {}).get("cpf"):
        pdf.linha("CPF", pessoa.get("cpf"))
    if (pessoa or {}).get("cargo"):
        pdf.linha("Cargo", pessoa.get("cargo"))
    pdf.ln(2)
    _linha_rescisao_calc(pdf, calculo)
    return _saida(pdf)


def pdf_rescisoes_mes(escola, mes_label, itens, total_custo):
    """Relatório mensal: cada rescisão com memória de cálculo e custo da escola."""
    pdf = RelatorioPDF("Custos por rescisão")
    pdf.add_page()
    pdf.paragrafo(f"{escola or 'Gestão Escolar'} · {mes_label}")
    pdf.linha("Total de custos por rescisão no mês", _brl(total_custo), negrito=True)
    pdf.paragrafo(
        "Cada rescisão abaixo traz a memória de cálculo completa. "
        "O valor entra em Financeiro como custo com categoria Rescisão."
    )
    if not itens:
        pdf.paragrafo("Nenhuma rescisão neste mês.")
        return _saida(pdf)
    for item in itens:
        pdf.ln(3)
        pdf.secao((item.get("nome_completo") or "Colaborador")[:80])
        if item.get("id"):
            pdf.linha("Rescisão nº", str(item.get("id")))
        if item.get("data_desligamento"):
            data = item["data_desligamento"]
            if hasattr(data, "strftime"):
                data = data.strftime("%d/%m/%Y")
            pdf.linha("Desligamento", str(data)[:10])
        pdf.linha("Custo lançado no Financeiro", _brl(item.get("custo_empregador") or item.get("total_liquido")))
        calc = item.get("detalhes") or {}
        if isinstance(calc, str):
            try:
                import json
                calc = json.loads(calc)
            except Exception:
                calc = {}
        if calc:
            _linha_rescisao_calc(pdf, calc)
        else:
            pdf.linha("Líquido registrado", _brl(item.get("total_liquido")))
            pdf.linha("Multa FGTS", _brl(item.get("multa_fgts")))
            pdf.linha("FGTS mês", _brl(item.get("fgts_mes")))
    return _saida(pdf)
