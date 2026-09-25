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

    def paragrafo(self, texto):
        self.set_x(self.l_margin)
        self.set_font(self.fonte, "", 10)
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

    def linha(self, rotulo, valor, negrito=False):
        self.set_font(self.fonte, "B" if negrito else "", 10)
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
            self.set_font(self.fonte, "B", 10)
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
    for item in titulos:
        valor = float(item.get("valor") or 0)
        total += valor
        linhas.append([
            (item.get("nome_completo") or "Aluno")[:18],
            (item.get("descricao") or "—")[:22],
            _data_br(item.get("data_vencimento")),
            _data_br(item.get("data_pagamento")) if item.get("data_pagamento") else "—",
            _brl(valor),
        ])
    if linhas:
        pdf.tabela(
            ["Aluno", "Descrição", "Vencimento", "Data da baixa", "Valor"],
            linhas,
            [40, 48, 32, 36, 34],
        )
    else:
        pdf.paragrafo("Nenhuma mensalidade compõe a base deste mês.")
    pdf.linha("Soma das mensalidades", _brl(total), negrito=True)
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
    _anexar_titulos_base(pdf, titulos, regime_apuracao or ap.get("regime_apuracao"), ap.get("receita_mes"))
    if dre:
        receita = float(dre.get("receita") or 0)
        das = float(dre.get("das") or 0)
        folha = float(dre.get("folha") or 0)
        compras = float(dre.get("compras") or 0)
        servicos = float(dre.get("servicos") or 0)
        apos_das = receita - das
        resultado = apos_das - folha - compras - servicos
        _pagina_resultado(
            pdf,
            "DASN — demonstrativo simplificado",
            f"{escola} · {mes_label} · Simples Nacional",
            [
                ("(+) Receita bruta de serviços", receita, False),
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
    pdf.paragrafo(
        "PIS e COFINS não cumulativos incidem sobre a receita bruta do mês: "
        "PIS 1,65% e COFINS 7,6%."
    )
    pdf.linha("Receita bruta do mês", _brl(receita))
    pdf.linha("PIS 1,65%", _brl(ap.get("pis")))
    pdf.linha("COFINS 7,6%", _brl(ap.get("cofins")))
    pdf.linha("PIS + COFINS", _brl(ap.get("total")), negrito=True)
    pdf.paragrafo(
        f"Conta: {_brl(receita)} × 1,65% = {_brl(ap.get('pis'))}. "
        f"{_brl(receita)} × 7,6% = {_brl(ap.get('cofins'))}."
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
    pdf.linha("Receita bruta do mês", _brl(ap.get("receita_mes")))
    pdf.linha("PIS (0,65%)", _brl(ap.get("pis")))
    pdf.linha("COFINS (3%)", _brl(ap.get("cofins")))
    pdf.linha("ISS estimado (5%)", _brl(ap.get("iss")))
    pdf.linha("Base de IRPJ/CSLL (32%)", _brl(ap.get("base_presumida")))
    pdf.linha("CSLL (9% da base)", _brl(ap.get("csll")))
    pdf.linha("IRPJ (15% da base)", _brl(ap.get("irpj")))
    if ap.get("aplica_adicional_irpj"):
        pdf.linha("Adicional de IRPJ (10%)", _brl(ap.get("irpj_adicional")))
    pdf.linha("Total de tributos", _brl(ap.get("tributos")), negrito=True)
    pdf.paragrafo(
        "PIS = receita × 0,65%. COFINS = receita × 3%. ISS estimado = receita × 5%. "
        "IRPJ e CSLL usam 32% da receita de serviços educacionais: IRPJ 15% dessa base e CSLL 9%. "
        "O adicional de 10% de IRPJ só entra se a base presumida do trimestre passar de R$ 60.000, "
        "e o mês mostra um terço desse adicional."
    )
    _anexar_titulos_base(pdf, titulos, regime_apuracao, ap.get("receita_mes"))

    receita = float(ap.get("receita_mes") or 0)
    tributos = float(ap.get("tributos") or 0)
    folha = float(tot.get("folha_pagamento") or ap.get("folha_total") or 0)
    compras = float(tot.get("custos_compras") or 0)
    servicos = float(tot.get("custos_servicos") or 0)
    apos_tributos = receita - tributos
    resultado = apos_tributos - folha - compras - servicos
    _pagina_resultado(
        pdf,
        "DRE simplificada — Lucro Presumido",
        f"{escola} · {mes_label}",
        [
            ("(+) Receita bruta de serviços", receita, False),
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
        pdf.tabela(["Matéria / prova", "Trim.", "Nota"], linhas, [90, 30, 40])
    else:
        pdf.paragrafo("Sem notas lançadas.")
    return _saida(pdf)


def pdf_historico_periodo(escola, periodo_label, contexto, incluir_chamada=True, incluir_eventos=True, chamada=None, eventos=None, provas=None, resumo_chamada=None):
    pdf = RelatorioPDF("Histórico do período")
    pdf.add_page()
    pdf.paragrafo(f"{escola} · {periodo_label}")
    pdf.paragrafo(contexto or "")
    if incluir_chamada:
        pdf.secao("Chamada")
        r = resumo_chamada or {}
        pdf.linha("Presente", r.get("presente") or 0)
        pdf.linha("Falta", r.get("falta") or 0)
        pdf.linha("Justificada", r.get("justificada") or 0)
        linhas = []
        for row in chamada or []:
            linhas.append([
                str(row.get("data_aula") or "")[:10],
                (row.get("nome_completo") or "")[:28],
                row.get("status") or "",
            ])
        if linhas:
            pdf.tabela(["Data", "Aluno", "Status"], linhas, [35, 100, 40])
    if incluir_eventos:
        pdf.secao("Eventos")
        linhas = []
        for row in eventos or []:
            linhas.append([
                str(row.get("data_evento") or "")[:10],
                (row.get("titulo") or "")[:40],
                (row.get("tipo") or "")[:18],
            ])
        if linhas:
            pdf.tabela(["Data", "Título", "Tipo"], linhas, [35, 110, 40])
        else:
            pdf.paragrafo("Nenhum evento no período.")
        if provas:
            pdf.secao("Provas")
            linhas = [[str(p.get("data_prova") or "")[:10], (p.get("titulo") or "")[:50]] for p in provas]
            pdf.tabela(["Data", "Prova"], linhas, [40, 150])
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


def _rotulo_parcela(item):
    nome = (item.get("nome_completo") or "Aluno").strip()
    parcela = item.get("parcela_contrato")
    if parcela:
        nome = f"{nome} · parcela {parcela}"
    descricao = (item.get("descricao") or "").strip()
    if descricao:
        nome = f"{nome} · {descricao}"
    return nome[:90]


def _total_recebido_item(item):
    return (
        float(item.get("valor") or 0)
        + float(item.get("juros_valor") or 0)
        + float(item.get("multa_valor") or 0)
    )


def pdf_regime_detalhado(escola, mes_label, regime_apuracao, regime_tributario, recebidos, pendentes, atrasados):
    caixa = (regime_apuracao or "") == "caixa"
    pdf = RelatorioPDF("Regime de caixa" if caixa else "Regime de competência")
    pdf.add_page()
    pdf.paragrafo(f"{escola} · {mes_label} · {nome_regime(regime_tributario)}")
    if caixa:
        pdf.paragrafo(
            "No regime de caixa, o imposto do mês usa o que foi recebido, não o que foi emitido. "
            "Entra na base a mensalidade que teve baixa neste mês, mais os juros percentuais e a multa fixa "
            "cobrados nessa baixa. O vencimento pode ser de outro mês. "
            "Parcela emitida e ainda sem baixa, mesmo atrasada, fica fora da base até o pagamento."
        )
        pdf.paragrafo(
            "No Simples Nacional, essa é a opção de apurar pelo recebimento. "
            "No Lucro Presumido, PIS, COFINS, IRPJ e CSLL deste mês usam a mesma base recebida. "
            "A DRE continua simplificada, sem plano de contas."
        )
    else:
        pdf.paragrafo(
            "No regime de competência, a mensalidade entra no imposto pelo vencimento, paga ou não. "
            "A data da baixa não muda esse mês. Juros e multa só existem depois da baixa e aparecem "
            "no lançamento pago, somados ao que entrou na conta."
        )

    pdf.secao("O que foi pago e entrou neste mês")
    if caixa:
        pdf.paragrafo("Cada linha abaixo teve baixa neste mês. Por isso entra na base do regime de caixa.")
    else:
        pdf.paragrafo("Baixas deste mês. No regime de competência, a mensalidade já entrou pelo vencimento.")
    total_pago = 0.0
    if not recebidos:
        pdf.paragrafo("Nenhuma baixa neste mês.")
    for item in recebidos or []:
        entrou = _total_recebido_item(item)
        total_pago += entrou
        pdf.linha(_rotulo_parcela(item), _brl(entrou), negrito=True)
        juros_pct = float(item.get("juros_percentual") or 0)
        partes = [
            f"Vencia em {_data_br(item.get('data_vencimento'))}",
            f"baixa em {_data_br(item.get('data_pagamento'))}",
            f"mensalidade {_brl(item.get('valor'))}",
        ]
        if juros_pct or float(item.get("juros_valor") or 0):
            partes.append(f"juros {juros_pct:g}% = {_brl(item.get('juros_valor'))}")
        if float(item.get("multa_valor") or 0):
            partes.append(f"multa fixa {_brl(item.get('multa_valor'))}")
        if item.get("forma_pagamento"):
            partes.append(str(item.get("forma_pagamento")))
        if caixa:
            partes.append("entrou porque a baixa é deste mês")
        pdf.paragrafo(". ".join(partes) + ".")
    pdf.linha("Total que entrou no mês", _brl(total_pago), negrito=True)

    pdf.secao("O que não foi pago")
    pdf.paragrafo(
        "Mensalidades com vencimento neste mês que ainda não venceram e não têm baixa. "
        + ("No regime de caixa, ficam fora do imposto até o pagamento." if caixa else "No regime de competência, já entram pelo vencimento.")
    )
    total_pendente = 0.0
    if not pendentes:
        pdf.paragrafo("Nenhuma mensalidade pendente neste vencimento.")
    for item in pendentes or []:
        valor = float(item.get("valor") or 0)
        total_pendente += valor
        pdf.linha(_rotulo_parcela(item), _brl(valor), negrito=True)
        pdf.paragrafo(
            f"Vence em {_data_br(item.get('data_vencimento'))} e ainda não houve baixa. "
            "Por isso não foi paga."
        )
    pdf.linha("Total pendente do vencimento", _brl(total_pendente), negrito=True)

    pdf.secao("O que está em atraso, inclusive parcelas anteriores")
    pdf.paragrafo(
        "Parcelas com vencimento já passado e sem baixa, deste mês ou de meses anteriores. "
        + (
            "Continuam fora da base do regime de caixa. Entram só no mês em que a baixa for dada, com juros e multa se houver."
            if caixa else
            "No regime de competência, a parcela atrasada já entrou no mês do vencimento. Ela segue em aberto na cobrança."
        )
    )
    total_atraso = 0.0
    if not atrasados:
        pdf.paragrafo("Nenhuma parcela em atraso.")
    for item in atrasados or []:
        valor = float(item.get("valor") or 0)
        total_atraso += valor
        pdf.linha(_rotulo_parcela(item), _brl(valor), negrito=True)
        pdf.paragrafo(
            f"Venceu em {_data_br(item.get('data_vencimento'))} e não há data de baixa. "
            "O atraso é a falta de pagamento dessa parcela."
        )
    pdf.linha("Total em atraso", _brl(total_atraso), negrito=True)
    if caixa:
        pdf.linha("Base do imposto neste mês", _brl(total_pago), negrito=True)
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
    pdf.linha("Líquido", _brl((item or {}).get("liquido")), negrito=True)
    if (item or {}).get("observacao"):
        pdf.paragrafo(item.get("observacao"))
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
    pdf.linha("Valor", br_money(cobranca.get("valor")), negrito=True)
    pdf.linha("Status", cobranca.get("status") or "Pendente")
    pdf.paragrafo("Aviso de cobrança da mensalidade. Confirme o pagamento com a secretaria.")
    return _saida(pdf)
