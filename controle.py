"""Controle de gastos: lê as faturas da pasta faturas/, separa por categoria e gera um PDF.

Uso:
    python controle.py                      -> título do mês tirado da data da fatura
    python controle.py --mes "Outubro/2026" -> título escolhido por você
"""
import argparse
import re
from datetime import date
from pathlib import Path

from categorias import carregar_regras, classificar, nome_da_loja, parcela
from conferencia import conferir_banco
from leitores import ler_faturas
from relatorio import gerar_pdf

PASTA = Path(__file__).parent
ORDEM_DOS_BANCOS = ["Nubank", "Mercado Pago", "Banese"]
MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
         "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]


def mes_pelo_nome_do_arquivo(arquivos) -> str:
    """Nubank_2026-10-22.csv / fatura-cartao-mercado-pago-2026-10.pdf -> 'Outubro/2026'"""
    for arquivo in arquivos:
        achado = re.search(r"(\d{4})-(\d{2})", arquivo.name)
        if achado:
            return f"{MESES[int(achado.group(2)) - 1]}/{achado.group(1)}"
    hoje = date.today()
    return f"{MESES[hoje.month - 1]}/{hoje.year}"


def main():
    parametros = argparse.ArgumentParser(description="Separa os gastos das faturas por categoria.")
    parametros.add_argument("--pasta", default=str(PASTA / "faturas"), help="pasta com as faturas")
    parametros.add_argument("--mes", help='título do relatório, ex.: "Outubro/2026"')
    parametros.add_argument(
        "--sem-perguntas", action="store_true",
        help="não pergunta o valor das faturas (usa o que vem nos arquivos)",
    )
    args = parametros.parse_args()

    pasta = Path(args.pasta)
    pasta.mkdir(exist_ok=True)  # cria a pasta faturas/ na primeira vez
    arquivos = sorted(
        a for a in pasta.iterdir() if a.suffix.lower() in {".csv", ".pdf", ".jpg", ".jpeg", ".png"}
    )
    if not arquivos:
        print(f"Nenhuma fatura encontrada em {pasta}. Coloque os arquivos lá e rode de novo.")
        return

    regras = carregar_regras(PASTA / "regras.csv")
    lancamentos, totais = ler_faturas(arquivos)
    if not lancamentos:
        print("Nenhum lançamento lido. Confira os nomes dos arquivos (Nubank..., MercadoPago..., Banese...).")
        return

    for l in lancamentos:
        l["categoria"], l["tem_regra"] = classificar(l, regras)
        l["parcela"] = parcela(l["descricao"])
        l["loja"] = nome_da_loja(l["descricao"])

    bancos = [b for b in ORDEM_DOS_BANCOS if any(l["banco"] == b for l in lancamentos)]

    # O print do Banese é lido por OCR: mostra o que foi lido para você conferir
    lidos_por_print = [l for l in lancamentos if l["banco"] == "Banese" and "dica" in l]
    if lidos_por_print:
        print("\nO que foi lido do print do Banese:")
        for l in lidos_por_print:
            print(f"  {l['data']:%d/%m}  {l['descricao'][:34]:<34} {l['valor']:>9.2f}  -> {l['categoria']}")

    # Confere cada fatura com o valor real que você informa
    conferencias = {}
    if not args.sem_perguntas:
        for banco in bancos:
            conferencias[banco] = conferir_banco(lancamentos, banco, total_do_arquivo=totais.get(banco))
    titulo = args.mes or mes_pelo_nome_do_arquivo(arquivos)
    saida = PASTA / f"gastos_{titulo.replace('/', '_')}.pdf"
    gerar_pdf(saida, titulo, lancamentos, bancos, conferencias)
    print(f"Relatório gerado: {saida.name}")


if __name__ == "__main__":
    main()
