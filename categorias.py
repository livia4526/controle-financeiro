"""Separa cada lançamento em categoria, a partir das regras do arquivo regras.csv."""
import csv
import re
import unicodedata
from pathlib import Path

# Tipos de lançamento que NÃO são compras: aparecem à parte no relatório
PAGAMENTO = "Pagamento"
SALDO_ANTERIOR = "Saldo anterior"
CATEGORIA_PADRAO = "Comida"


def sem_acento(texto: str) -> str:
    normal = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in normal if not unicodedata.combining(c)).lower()


def carregar_regras(caminho: Path) -> list[tuple[str, str]]:
    regras = []
    with open(caminho, encoding="utf-8") as arquivo:
        linhas = (linha for linha in arquivo if not linha.startswith("#"))
        for linha in csv.DictReader(linhas):
            if linha["palavra"].strip():
                regras.append((sem_acento(linha["palavra"].strip()), linha["categoria"].strip()))
    return regras


def nome_da_loja(descricao: str) -> str:
    """Nome curto da loja (aparece no PDF na lista de lojas sem regra).
    'Rocha Atacado Sul - Parcela 2/3' -> 'Rocha Atacado Sul'"""
    nome = re.sub(r"\s*-?\s*(Parcela\s*)?\d+\s*(/|de)\s*\d+\s*$", "", descricao, flags=re.I)
    nome = re.sub(r"\s*-\s*NuPay\s*$", "", nome, flags=re.I)
    partes = [p.strip() for p in nome.split("*") if p.strip()]
    if not partes:
        return "Outros"
    # "Elo*maria Souza" / "MP*LOJA" / "Pix*banese*Fulano": o começo é só a bandeira ou o meio
    # de pagamento, o nome da loja vem depois do asterisco
    nome = partes[-1] if len(partes[0]) <= 3 and len(partes) > 1 else partes[0]
    palavras = [p for p in nome.split() if not re.fullmatch(r"[\d.\-/]+", p)]  # tira números
    nome = " ".join(palavras[:3])
    if nome.isupper() or nome.islower() or nome[:1].islower():
        nome = nome.title()
    return nome[:22].strip() or "Outros"  # nomes curtos, para o relatório ficar limpo


def classificar(lancamento: dict, regras: list[tuple[str, str]]) -> tuple[str, bool]:
    """Devolve (categoria, achou_regra)."""
    descricao = sem_acento(lancamento["descricao"])
    if lancamento["valor"] < 0 or "pagamento recebido" in descricao:
        return PAGAMENTO, True
    if any(t in descricao for t in ("pendente do mes anterior", "saldo anterior", "fatura anterior")):
        return SALDO_ANTERIOR, True
    for palavra, categoria in regras:
        if palavra in descricao:
            return categoria, True
    # O app do Banese diz o tipo da compra; "Mercado" vira Comida
    if "mercado" in sem_acento(lancamento.get("dica", "")):
        return "Comida", True
    # Sem regra: vai para Comida, que é o gasto mais comum (nome de pessoa sem Pix,
    # restaurante novo...). O PDF lista essas lojas no final para você conferir.
    return CATEGORIA_PADRAO, False


def parcela(descricao: str) -> tuple[int, int] | None:
    """'Gol ... - Parcela 1/8' -> (1, 8)   'iFood - NuPay - 2/2' -> (2, 2)
    'BIJOUARTS Parcela 3 de 3' -> (3, 3)"""
    achado = re.search(r"(?:(\d+)\s*/\s*(\d+)|parcela\s*(\d+)\s*de\s*(\d+))\s*$", descricao, flags=re.I)
    if not achado:
        return None
    numeros = [int(n) for n in achado.groups() if n]
    atual, total = numeros
    return (atual, total) if 0 < atual <= total else None
