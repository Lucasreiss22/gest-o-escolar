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
        self.set_font(self.fonte, "B", 11)
        self.set_text_color(30, 58, 95)
        self.cell(0, 8, texto, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(40, 40, 40)

    def paragrafo(self, texto):
        self.set_font(self.fonte, "", 10)
        self.multi_cell(0, 5.4, texto)
        self.ln(1)

    def linha(self, rotulo, valor, negrito=False):
        self.set_font(self.fonte, "B" if negrito else "", 10)
        self.cell(95, 6, rotulo)
        self.cell(0, 6, str(valor), new_x="LMARGIN", new_y="NEXT")

    def tabela(self, cabecalhos, linhas, larguras=None):
        if not larguras:
            larguras = [190 / len(cabecalhos)] * len(cabecalhos)
        self.set_font(self.fonte, "B", 8)
        self.set_fill_color(30, 58, 95)
        self.set_text_color(255, 255, 255)
        for i, titulo in enumerate(cabecalhos):
            self.cell(larguras[i], 7, titulo, border=1, fill=True)
        self.ln()
        self.set_text_color(40, 40, 40)
        self.set_font(self.fonte, "", 8)
        fill = False
        for linha in linhas:
            if self.get_y() > 270:
                self.add_page()
            self.set_fill_color(243, 246, 251)
            for i, celula in enumerate(linha):
                self.cell(larguras[i], 6, str(celula)[:40], border=1, fill=fill)
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


def pdf_simples_nacional(escola, mes_label, regime, apuracao, funcionarios, receitas_mes):
    pdf = RelatorioPDF("Relatório Simples Nacional")
    pdf.add_page()
    pdf.paragrafo(f"{escola} · {mes_label} · {nome_regime(regime)}")
    pdf.linha("Receita do mês", _brl((apuracao or {}).get("receita_mes")))
    pdf.linha("DAS", _brl((apuracao or {}).get("das")), negrito=True)
    return _saida(pdf)


def pdf_lucro_real(escola, mes_label, regime, totais, recebidos, pendentes, atrasados, folha, pis_cofins=None):
    pdf = RelatorioPDF("Relatório Lucro Real")
    pdf.add_page()
    pdf.paragrafo(f"{escola} · {mes_label}")
    pdf.linha("Recebido", _brl((totais or {}).get("recebido")))
    pdf.linha("Folha", _brl((totais or {}).get("folha_pagamento")))
    if pis_cofins:
        pdf.linha("PIS+COFINS", _brl(pis_cofins.get("total")))
    return _saida(pdf)


def pdf_lucro_presumido(escola, mes_label, regime, apuracao, totais, recebidos):
    pdf = RelatorioPDF("Relatório Lucro Presumido")
    pdf.add_page()
    pdf.paragrafo(f"{escola} · {mes_label}")
    pdf.linha("Faturamento", _brl((apuracao or {}).get("receita_mes")))
    pdf.linha("Tributos", _brl((apuracao or {}).get("tributos")), negrito=True)
    pdf.linha("Folha", _brl((apuracao or {}).get("folha_total")))
    pdf.linha("Compras", _brl((totais or {}).get("custos_compras")))
    pdf.linha("Serviços", _brl((totais or {}).get("custos_servicos")))
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
    if (item or {}).get("adicional_he"):
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
