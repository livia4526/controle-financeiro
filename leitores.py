"""Leitores de fatura: cada banco tem um formato, e cada leitor transforma o arquivo
numa lista de lançamentos no MESMO formato:

    {"data": date, "descricao": str, "valor": float, "banco": str}

Cada leitor devolve (lancamentos, total_da_fatura). O total é o valor impresso na
fatura (quando o arquivo tem essa informação) e vira a sugestão na hora da conferência.

    Nubank        -> CSV exportado pelo app         (Nubank_2026-10-22.csv)
    Mercado Pago  -> PDF da fatura                  (fatura-cartao-mercado-pago-2026-10.pdf)
    Banese        -> print(s) da tela do app        (Banese.jpg, Banese_2.png...)
"""
import csv
import re
from datetime import date
from pathlib import Path

MESES_ABREV = {"JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4, "MAI": 5, "JUN": 6,
               "JUL": 7, "AGO": 8, "SET": 9, "OUT": 10, "NOV": 11, "DEZ": 12}
EXTENSOES_DE_IMAGEM = {".jpg", ".jpeg", ".png"}


def texto_para_valor(texto: str) -> float:
    """'1.774,15' -> 1774.15   '- 20,00' -> -20.0   'R$ 25,21' -> 25.21"""
    limpo = texto.replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
    return float(limpo)


def data_com_ano(dia: int, mes: int, vencimento: date) -> date:
    """A fatura só mostra dia/mês. O ano vem do vencimento: uma compra de dezembro
    numa fatura que vence em janeiro é do ano anterior."""
    ano = vencimento.year - 1 if mes > vencimento.month else vencimento.year
    return date(ano, mes, dia)


# ---------------------------------------------------------------- Nubank (CSV)

def ler_nubank(caminho: Path) -> tuple[list[dict], float | None]:
    """CSV que o Nubank exporta: colunas date,title,amount. Não traz o total da fatura."""
    lancamentos = []
    with open(caminho, encoding="utf-8-sig") as arquivo:
        for linha in csv.DictReader(arquivo):
            lancamentos.append({
                "data": date.fromisoformat(linha["date"]),
                "descricao": linha["title"].strip(),
                "valor": texto_para_valor(linha["amount"]),
                "banco": "Nubank",
            })
    return lancamentos, None


# ---------------------------------------------------------- Mercado Pago (PDF)

LINHA_MP = re.compile(r"^(\d{2})/(\d{2}) (.+?) (-?)R\$ ?([\d.]+,\d{2})$")


def ler_mercado_pago_texto(paginas: list[str]) -> tuple[list[dict], float | None]:
    """Recebe o texto de cada página do PDF e separa os lançamentos.

    Só pega as linhas que estão dentro das tabelas "Data Movimentações Valor"
    e para no "Total" de cada cartão. O resto do PDF (propaganda de parcelamento,
    juros, etc.) é ignorado."""
    texto = "\n".join(paginas)

    achado = re.search(r"Vencimento:?\s*(\d{2})/(\d{2})/(\d{4})", texto) or \
        re.search(r"Vence em.*?\n.*?(\d{2})/(\d{2})/(\d{4})", texto)
    if not achado:
        raise ValueError("Não achei a data de vencimento no PDF do Mercado Pago.")
    vencimento = date(int(achado.group(3)), int(achado.group(2)), int(achado.group(1)))

    total = None
    achado = re.search(r"Total a pagar.*?\n\s*R\$ ?([\d.]+,\d{2})", texto)
    if achado:
        total = texto_para_valor(achado.group(1))

    lancamentos = []
    dentro_da_tabela = False
    for linha in texto.splitlines():
        linha = linha.strip()
        if linha.startswith("Data Movimenta"):
            dentro_da_tabela = True
            continue
        if linha.startswith("Total"):
            dentro_da_tabela = False
            continue
        achado = LINHA_MP.match(linha)
        if not (dentro_da_tabela and achado):
            continue
        dia, mes, descricao, sinal, valor = achado.groups()
        valor = texto_para_valor(valor)
        # O PDF mostra o pagamento como valor positivo, mas ele é um crédito
        if sinal or re.search(r"pagamento d[ae] fatura|estorno", descricao, re.I):
            valor = -valor
        lancamentos.append({
            "data": data_com_ano(int(dia), int(mes), vencimento),
            "descricao": descricao.strip(),
            "valor": valor,
            "banco": "Mercado Pago",
        })
    return lancamentos, total


def ler_mercado_pago(caminho: Path) -> tuple[list[dict], float | None]:
    import pdfplumber  # só é preciso se tiver fatura em PDF

    with pdfplumber.open(caminho) as pdf:
        paginas = [pagina.extract_text() or "" for pagina in pdf.pages]
    return ler_mercado_pago_texto(paginas)


# --------------------------------------------------------- Banese (print/OCR)

def valor_do_ocr(texto: str) -> float | None:
    """'24,48' -> 24.48 | '2448' -> 24.48 (o OCR às vezes come a vírgula) | 'R$' -> None"""
    limpo = texto.replace("R$", "").replace("-", "").replace(" ", "").replace(".", "")
    if re.fullmatch(r"\d+,\d{2}", limpo):
        return float(limpo.replace(",", "."))
    if re.fullmatch(r"\d{3,}", limpo):
        return int(limpo) / 100
    return None


def primeiro_valor(palavras: list[dict]) -> float | None:
    for palavra in palavras:
        valor = valor_do_ocr(palavra["texto"])
        if valor is not None:
            return valor
    return None


def palavras_do_print(caminho: Path) -> list[dict]:
    """Roda o OCR e devolve cada palavra com a posição (x em % da largura)."""
    import pytesseract
    from PIL import Image, ImageOps

    configurar_tesseract(pytesseract)
    imagem = ImageOps.grayscale(Image.open(caminho))
    imagem = imagem.resize((imagem.width * 2, imagem.height * 2), Image.LANCZOS)
    dados = pytesseract.image_to_data(
        imagem, lang="por", config="--psm 11", output_type=pytesseract.Output.DICT
    )
    palavras = []
    for i, texto in enumerate(dados["text"]):
        if texto.strip():
            palavras.append({
                "texto": texto.strip(),
                "x": dados["left"][i] * 100 / imagem.width,
                "y": dados["top"][i] + dados["height"][i] / 2,
            })
    return palavras


class TesseractNaoEncontrado(Exception):
    pass


def configurar_tesseract(pytesseract):
    """No Windows o Tesseract costuma não estar no PATH: procura nas pastas onde o
    instalador costuma colocar."""
    import os
    import shutil

    if shutil.which("tesseract"):
        return
    pastas = [
        Path(r"C:\Program Files\Tesseract-OCR"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Tesseract-OCR",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Tesseract-OCR",
    ]
    for pasta in pastas:
        if (pasta / "tesseract.exe").exists():
            pytesseract.pytesseract.tesseract_cmd = str(pasta / "tesseract.exe")
            return
    raise TesseractNaoEncontrado(
        "Não achei o Tesseract (o programa que lê o print do Banese).\n"
        "  Instale pelo link https://github.com/UB-Mannheim/tesseract/wiki\n"
        "  marcando 'Portuguese' em 'Additional language data', e rode de novo."
    )


def agrupar_em_linhas(palavras: list[dict], tolerancia: float = 14) -> list[list[dict]]:
    """Junta as palavras que estão na mesma altura da tela."""
    linhas: list[list[dict]] = []
    for palavra in sorted(palavras, key=lambda p: p["y"]):
        if linhas and abs(linhas[-1][0]["y"] - palavra["y"]) <= tolerancia:
            linhas[-1].append(palavra)
        else:
            linhas.append([palavra])
    return [sorted(linha, key=lambda p: p["x"]) for linha in linhas]


def ler_banese_palavras(palavras: list[dict]) -> tuple[list[dict], float | None, date | None]:
    """Transforma as palavras do print em lançamentos.

    No app do Banese cada compra ocupa duas linhas:
        17 SET   Elo*maria Souza Lima              R$ 10,00
                 Outros - À Vista
    A data só aparece na primeira compra do dia; as outras usam a data de cima."""
    linhas = agrupar_em_linhas(palavras)
    texto_todo = " ".join(p["texto"] for p in palavras)

    vencimento = None
    achado = re.search(r"Vencimento\s*(\d{2})/(\d{2})/(\d{4})", texto_todo)
    if achado:
        vencimento = date(int(achado.group(3)), int(achado.group(2)), int(achado.group(1)))

    lancamentos = []
    total = None
    dia_mes = None
    for numero, linha in enumerate(linhas):
        direita = [p for p in linha if p["x"] >= 75]
        meio = [p for p in linha if 15 <= p["x"] < 75]
        esquerda = [p for p in linha if p["x"] < 15]
        valor = primeiro_valor(direita)
        if valor is None:
            # "R$ 222,56" no meio do topo da tela: é o total da fatura
            if total is None and not lancamentos and any(p["texto"] == "R$" for p in meio):
                total = primeiro_valor(meio)
            continue

        # Data (ex.: "17 SET") na esquerda; se não tiver, é do mesmo dia da compra de cima
        texto_esquerda = " ".join(p["texto"] for p in esquerda).upper()
        achado = re.search(r"(\d{1,2})\s*(" + "|".join(MESES_ABREV) + ")", texto_esquerda)
        if achado:
            dia_mes = (int(achado.group(1)), MESES_ABREV[achado.group(2)])

        descricao = " ".join(p["texto"] for p in meio).strip(" -|")
        if not descricao or dia_mes is None:
            continue

        if any(p["texto"].startswith("-") for p in direita) or "pagamento" in descricao.lower():
            valor = -valor

        # A linha cinza de baixo traz o tipo que o app dá ("Mercado - À Vista")
        dica = ""
        if numero + 1 < len(linhas):
            dica = " ".join(p["texto"] for p in linhas[numero + 1] if 15 <= p["x"] < 75)

        lancamentos.append({
            "dia_mes": dia_mes, "descricao": descricao, "valor": valor,
            "banco": "Banese", "dica": dica,
        })
    return lancamentos, total, vencimento


def ler_banese(caminhos: list[Path]) -> tuple[list[dict], float | None]:
    """Lê um ou mais prints da fatura do Banese (se a fatura não couber numa tela,
    tire vários prints rolando a tela; as compras repetidas entre um print e outro
    são descartadas)."""
    todos: list[dict] = []
    total = None
    vencimento = None
    for caminho in sorted(caminhos):
        palavras = palavras_do_print(caminho)
        lidos, total_do_print, venc = ler_banese_palavras(palavras)
        total = total or total_do_print
        vencimento = vencimento or venc
        todos += sem_repetir(todos, lidos)

    vencimento = vencimento or date.today()
    for l in todos:
        dia, mes = l.pop("dia_mes")
        l["data"] = data_com_ano(dia, mes, vencimento)
    return todos, total


def sem_repetir(anteriores: list[dict], novos: list[dict]) -> list[dict]:
    """Quando dois prints se sobrepõem, o começo do segundo repete o fim do primeiro."""
    def chave(l):
        return (l["dia_mes"], round(l["valor"], 2))

    for tamanho in range(min(len(anteriores), len(novos)), 0, -1):
        if [chave(l) for l in anteriores[-tamanho:]] == [chave(l) for l in novos[:tamanho]]:
            return novos[tamanho:]
    return novos


# ------------------------------------------------------------------ escolha

def banco_do_arquivo(caminho: Path) -> str | None:
    nome = caminho.name.lower().replace(" ", "").replace("-", "").replace("_", "")
    if nome.startswith("nubank"):
        return "Nubank"
    if "mercadopago" in nome:
        return "Mercado Pago"
    if nome.startswith("banese"):
        return "Banese"
    # Sem o nome do banco: cada banco manda um tipo de arquivo diferente
    extensao = caminho.suffix.lower()
    if extensao == ".csv":
        return "Nubank"
    if extensao == ".pdf":
        return "Mercado Pago"
    if extensao in EXTENSOES_DE_IMAGEM:
        return "Banese"
    return None


def ler_faturas(arquivos: list[Path]) -> tuple[list[dict], dict[str, float]]:
    """Lê todos os arquivos da pasta. Devolve os lançamentos e o total de cada fatura
    (quando o arquivo traz)."""
    lancamentos: list[dict] = []
    totais: dict[str, float] = {}
    prints_do_banese = []
    for caminho in arquivos:
        banco = banco_do_arquivo(caminho)
        extensao = caminho.suffix.lower()
        if banco is None:
            print(f"Ignorando {caminho.name}: não sei de qual banco é.")
            continue
        if banco == "Banese" and extensao in EXTENSOES_DE_IMAGEM:
            prints_do_banese.append(caminho)
            continue
        if banco == "Nubank" and extensao == ".csv":
            lidos, total = ler_nubank(caminho)
        elif banco == "Mercado Pago" and extensao == ".pdf":
            lidos, total = ler_mercado_pago(caminho)
        else:
            print(f"Ignorando {caminho.name}: formato não esperado para {banco}.")
            continue
        print(f"{caminho.name}: {len(lidos)} lançamentos")
        lancamentos += lidos
        if total is not None:
            totais[banco] = total

    if prints_do_banese:
        try:
            lidos, total = ler_banese(prints_do_banese)
        except TesseractNaoEncontrado as erro:
            print(f"\nATENÇÃO: o print do Banese ficou de fora. {erro}\n")
            return lancamentos, totais
        nomes = ", ".join(p.name for p in prints_do_banese)
        print(f"{nomes}: {len(lidos)} lançamentos lidos do print")
        lancamentos += lidos
        if total is not None:
            totais["Banese"] = total
    return lancamentos, totais
