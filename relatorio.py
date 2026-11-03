"""Gera o PDF do mês com o resumo de todas as faturas."""
import re
from collections import defaultdict

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing, Rect, String

from categorias import PAGAMENTO, SALDO_ANTERIOR

AZUL = colors.HexColor("#2c4d8f")
CINZA = colors.HexColor("#f2f4f8")
CINZA_TEXTO = colors.HexColor("#5f6673")

estilos = getSampleStyleSheet()
TITULO = ParagraphStyle("titulo", parent=estilos["Title"], textColor=AZUL, fontSize=20, spaceAfter=4)
SUBTITULO = ParagraphStyle("sub", parent=estilos["Normal"], textColor=CINZA_TEXTO, alignment=1)
SECAO = ParagraphStyle("secao", parent=estilos["Heading2"], textColor=AZUL, spaceBefore=14, spaceAfter=6)
PEQUENO = ParagraphStyle("pequeno", parent=estilos["Normal"], fontSize=8, textColor=CINZA_TEXTO)
DESTAQUE = ParagraphStyle("destaque", parent=estilos["Normal"], fontSize=13, leading=18)
DIREITA = ParagraphStyle("direita", parent=estilos["Normal"], alignment=TA_RIGHT)


def reais(valor: float) -> str:
    """1774.15 -> 'R$ 1.774,15'"""
    texto = f"{abs(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"- R$ {texto}" if valor < 0 else f"R$ {texto}"


def tabela(linhas, larguras, total=False, direita_desde=1):
    """Monta uma tabela com cabeçalho azul e linhas zebradas.
    direita_desde: a partir de qual coluna os textos ficam alinhados à direita (valores)."""
    t = Table(linhas, colWidths=larguras, hAlign="LEFT")
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (direita_desde, 0), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, CINZA]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if total:  
        estilo += [
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("LINEABOVE", (0, -1), (-1, -1), 1, AZUL),
            ("BACKGROUND", (0, -1), (-1, -1), colors.white),
        ]
    t.setStyle(TableStyle(estilo))
    return t


# Uma cor para cada cartão, parecida com a do app do banco
CORES_DOS_BANCOS = {
    "Nubank": colors.HexColor("#8a05be"),
    "Mercado Pago": colors.HexColor("#009ee3"),
    "Banese": colors.HexColor("#1f8a5b"),
}


def porcentagens_inteiras(valores):
    """Arredonda as porcentagens de um jeito que a soma dá sempre 100%.
    Ex.: 59,4 + 22,3 + 18,2 arredondados dariam 59 + 22 + 18 = 99%; aqui quem
    perdeu mais no arredondamento (o 59,4) ganha o ponto que falta."""
    total = sum(valores)
    exatas = [v * 100 / total for v in valores]
    inteiras = [int(p) for p in exatas]
    faltam = 100 - sum(inteiras)
    for i in sorted(range(len(exatas)), key=lambda i: -(exatas[i] - inteiras[i]))[:faltam]:
        inteiras[i] += 1
    return inteiras


def grafico_por_cartao(por_banco, bancos):
    """Gráfico de pizza com a porcentagem que cada cartão representa no total,
    e ao lado a legenda com o nome, a porcentagem e o valor."""
    total = sum(por_banco[b] for b in bancos)
    if total <= 0:
        return None
    desenho = Drawing(17 * cm, 6 * cm)

    pizza = Pie()
    pizza.x, pizza.y = 0.5 * cm, 0.3 * cm
    pizza.width = pizza.height = 5.4 * cm
    pizza.data = [por_banco[b] for b in bancos]
    porcentagem = dict(zip(bancos, porcentagens_inteiras([por_banco[b] for b in bancos])))
    pizza.labels = [f"{porcentagem[b]}%" for b in bancos]
    pizza.simpleLabels = 1
    pizza.sideLabels = 0
    pizza.startAngle = 90
    pizza.direction = "clockwise"
    pizza.slices.strokeColor = colors.white
    pizza.slices.strokeWidth = 2
    pizza.slices.fontName = "Helvetica-Bold"
    pizza.slices.fontSize = 11
    pizza.slices.fontColor = colors.white
    pizza.slices.labelRadius = 0.65
    for i, banco in enumerate(bancos):
        pizza.slices[i].fillColor = CORES_DOS_BANCOS.get(banco, AZUL)
    desenho.add(pizza)

    # Legenda: quadradinho da cor, nome do cartão, porcentagem e valor
    y = 4.6 * cm
    for banco in bancos:
        cor = CORES_DOS_BANCOS.get(banco, AZUL)
        desenho.add(Rect(7.5 * cm, y, 0.45 * cm, 0.45 * cm, fillColor=cor, strokeColor=None))
        desenho.add(String(8.3 * cm, y + 0.08 * cm, banco, fontName="Helvetica-Bold", fontSize=12))
        desenho.add(String(12.3 * cm, y + 0.08 * cm, f"{porcentagem[banco]}%",
                           fontName="Helvetica-Bold", fontSize=12, fillColor=cor))
        desenho.add(String(16.8 * cm, y + 0.08 * cm, reais(por_banco[banco]),
                           fontName="Helvetica", fontSize=12, textAnchor="end"))
        y -= 1.3 * cm
    return desenho


def eh_gasto(lanc):
    return lanc["categoria"] not in (PAGAMENTO, SALDO_ANTERIOR)


def gerar_pdf(caminho, titulo_mes, lancamentos, bancos, conferencias=None):
    conferencias = conferencias or {}
    doc = SimpleDocTemplate(
        str(caminho), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=1.8 * cm, bottomMargin=1.8 * cm, title=f"Gastos - {titulo_mes}",
    )
    gastos = [l for l in lancamentos if eh_gasto(l)]
    partes = [Paragraph("Controle de gastos", TITULO), Paragraph(titulo_mes, SUBTITULO), Spacer(1, 14)]

    # ===== resumo geral =====
    total_geral = sum(l["valor"] for l in gastos)
    partes.append(Paragraph(f"Total gasto nos cartões: <b>{reais(total_geral)}</b>", DESTAQUE))
    por_banco = defaultdict(float)
    for l in gastos:
        por_banco[l["banco"]] += l["valor"]
    if len(bancos) == 1:
        partes.append(Paragraph(f"{bancos[0]}: {reais(por_banco[bancos[0]])}", estilos["Normal"]))

    grafico = grafico_por_cartao(por_banco, bancos)
    if grafico and len(bancos) > 1:
        partes.append(Paragraph("Quanto cada cartão gastou", SECAO))
        partes.append(grafico)

    partes.append(Paragraph("Gastos por categoria", SECAO))
    soma = defaultdict(lambda: defaultdict(float))
    for l in gastos:
        soma[l["categoria"]][l["banco"]] += l["valor"]
    categorias = sorted(soma, key=lambda c: -sum(soma[c].values()))
    linhas = [["Categoria", *bancos, "Total"]]
    for cat in categorias:
        linhas.append([cat, *[reais(soma[cat][b]) if soma[cat][b] else "-" for b in bancos],
                       reais(sum(soma[cat].values()))])
    linhas.append(["Total", *[reais(por_banco[b]) for b in bancos], reais(total_geral)])
    largura_banco = (17 * cm - 4.5 * cm - 3 * cm) / max(len(bancos), 1)
    partes.append(tabela(linhas, [4.5 * cm, *[largura_banco] * len(bancos), 3 * cm], total=True))

    # Parcelas que continuam nos próximos meses
    em_aberto = [l for l in gastos if l["parcela"] and l["parcela"][0] < l["parcela"][1]]
    if em_aberto:
        partes.append(Paragraph("Parcelas que continuam", SECAO))
        linhas = [["Compra", "Banco", "Parcela", "Valor", "Ainda falta"]]
        falta_total = 0.0
        for l in sorted(em_aberto, key=lambda l: -l["valor"]):
            atual, total = l["parcela"]
            falta = (total - atual) * l["valor"]
            falta_total += falta
            compra = re.sub(r"\s*-\s*(Parcela\s*)?\d+/\d+\s*$", "", l["descricao"], flags=re.I)[:28]
            linhas.append([compra, l["banco"], f"{atual}/{total}", reais(l["valor"]), reais(falta)])
        linhas.append(["Total que ainda vem", "", "", "", reais(falta_total)])
        partes.append(tabela(linhas, [5.5 * cm, 3 * cm, 2 * cm, 3 * cm, 3.5 * cm], total=True, direita_desde=2))

    # ===== uma página por banco =====
    for banco in bancos:
        do_banco = [l for l in lancamentos if l["banco"] == banco]
        gastos_banco = [l for l in do_banco if eh_gasto(l)]
        partes += [PageBreak(), Paragraph(banco, TITULO), Paragraph(titulo_mes, SUBTITULO), Spacer(1, 12)]
        partes.append(Paragraph(f"Gastos na fatura: <b>{reais(por_banco[banco])}</b>", DESTAQUE))
        conf = conferencias.get(banco)

        por_cat = defaultdict(lambda: [0.0, 0])
        for l in gastos_banco:
            por_cat[l["categoria"]][0] += l["valor"]
            if not l.get("ajuste"):  # o ajuste muda o valor, mas não é uma compra
                por_cat[l["categoria"]][1] += 1
        linhas = [["Categoria", "Compras", "Valor"]]
        for cat, (valor, qtd) in sorted(por_cat.items(), key=lambda i: -i[1][0]):
            linhas.append([cat, str(qtd), reais(valor)])
        compras = sum(1 for l in gastos_banco if not l.get("ajuste"))
        linhas.append(["Total", str(compras), reais(por_banco[banco])])
        partes.append(Spacer(1, 6))
        partes.append(tabela(linhas, [8 * cm, 3 * cm, 4 * cm], total=True))

        # Movimentação: saldo anterior e pagamentos (não são gastos, mas mudam o valor da fatura)
        anterior = sum(l["valor"] for l in do_banco if l["categoria"] == SALDO_ANTERIOR)
        pagos = sum(l["valor"] for l in do_banco if l["categoria"] == PAGAMENTO)
        # Se você informou o valor real da fatura, este quadro não é necessário 
        if (anterior or pagos) and not conf:
            partes.append(Paragraph("Movimentação da fatura", SECAO))
            linhas = [["", "Valor"],
                      ["Saldo do mês anterior", reais(anterior)],
                      ["Gastos desta fatura", reais(por_banco[banco])],
                      ["Pagamentos feitos", reais(pagos)],
                      ["Resultado", reais(anterior + por_banco[banco] + pagos)]]
            partes.append(tabela(linhas, [8 * cm, 4 * cm], total=True))
            partes.append(Paragraph(
                "Resultado negativo quer dizer que foi pago mais do que o devido (crédito para a próxima fatura).",
                PEQUENO,
            ))

        # Lista completa, para conferir
        partes.append(Paragraph("Lançamentos", SECAO))
        linhas = [["Data", "Descrição", "Categoria", "Valor"]]
        for l in sorted(do_banco, key=lambda l: l["data"]):
            linhas.append([l["data"].strftime("%d/%m"), l["descricao"][:50], l["categoria"], reais(l["valor"])])
        t = tabela(linhas, [1.4 * cm, 8.6 * cm, 3.4 * cm, 3.6 * cm], direita_desde=3)
        t.setStyle(TableStyle([("FONTSIZE", (0, 1), (-1, -1), 8)]))
        partes.append(t)

    # Categorias criadas automaticamente (para virar regra no regras.csv)
        novas = sorted({l["loja"] for l in gastos if not l["tem_regra"]})
    if novas:
        partes.append(KeepTogether([
            Paragraph("Lojas que foram para Comida sem regra", SECAO),
            Paragraph(
                "Estas lojas não combinaram com nenhuma regra e foram para Comida (o mais comum): "
                + ", ".join(novas) + ".",
                PEQUENO,
            ),
        ]))

    doc.build(partes)
