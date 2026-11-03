"""Confere o total de cada fatura com o valor que você informa e ajusta a diferença.

Por que isso existe: o CSV do banco nem sempre bate com o valor final da fatura
(estornos, arredondamentos, ajustes do banco). Você diz quanto a fatura deu de verdade,
e o programa coloca a diferença na categoria que você escolher.
"""
import re

from categorias import PAGAMENTO, SALDO_ANTERIOR

DESCRICAO_AJUSTE = "Ajuste para bater com a fatura"


def ler_valor_digitado(texto: str) -> float | None:
    """'724,85' / '724.85' / 'R$ 1.774,15' / '1774,15' -> número. Vazio -> None."""
    limpo = texto.strip().replace("R$", "").replace(" ", "")
    if not limpo:
        return None
    if re.fullmatch(r"\d+\.\d{1,2}", limpo):  # ponto como vírgula decimal
        return float(limpo)
    return float(limpo.replace(".", "").replace(",", "."))


def gastos_por_categoria(lancamentos: list[dict], banco: str) -> dict[str, float]:
    soma: dict[str, float] = {}
    for l in lancamentos:
        if l["banco"] == banco and l["categoria"] not in (PAGAMENTO, SALDO_ANTERIOR):
            soma[l["categoria"]] = round(soma.get(l["categoria"], 0) + l["valor"], 2)
    return dict(sorted(soma.items(), key=lambda item: -item[1]))


def aplicar_ajuste(lancamentos: list[dict], banco: str, categoria: str, diferenca: float, data) -> dict:
    """Cria um lançamento de ajuste (positivo soma, negativo abate) na categoria escolhida."""
    ajuste = {
        "data": data, "descricao": DESCRICAO_AJUSTE, "valor": round(diferenca, 2),
        "banco": banco, "categoria": categoria, "tem_regra": True, "parcela": None,
        "loja": DESCRICAO_AJUSTE, "ajuste": True,
    }
    lancamentos.append(ajuste)
    return ajuste


def reais(valor: float) -> str:
    texto = f"{abs(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def conferir_banco(lancamentos: list[dict], banco: str, perguntar=input,
                   total_do_arquivo: float | None = None) -> dict | None:
    """Pergunta o valor real da fatura e, se for diferente, onde colocar a diferença.
    total_do_arquivo: o total impresso na fatura (PDF/print), sugerido ao apertar Enter.
    Devolve um resumo da conferência (para aparecer no PDF) ou None se não houve informação."""
    categorias = gastos_por_categoria(lancamentos, banco)
    calculado = round(sum(categorias.values()), 2)
    sugestao = calculado if total_do_arquivo is None else total_do_arquivo

    print(f"\n=== {banco} ===")
    print(f"Pelo arquivo, os gastos somam {reais(calculado)}.")
    if total_do_arquivo is not None:
        print(f"O total impresso na fatura é {reais(total_do_arquivo)}.")
    while True:
        try:
            informado = ler_valor_digitado(perguntar(
                f"Quanto deu a fatura do {banco}? (Enter para usar {reais(sugestao)}): "
            ))
            break
        except ValueError:
            print("Não entendi o valor. Digite assim: 724,85")
    if informado is None:
        if total_do_arquivo is None:
            return None
        informado = total_do_arquivo

    diferenca = round(informado - calculado, 2)
    if diferenca == 0:
        print("Bateu certinho!")
        return {"informado": informado, "calculado": calculado, "diferenca": 0, "categoria": None}

    acao = "abater" if diferenca < 0 else "somar"
    print(f"A fatura foi {reais(informado)}: diferença de {reais(diferenca)}.")
    nomes = list(categorias)
    for numero, nome in enumerate(nomes, start=1):
        print(f"  {numero}. {nome} ({reais(categorias[nome])})")
    print(f"  {len(nomes) + 1}. Outros (criar categoria \"Outros\")")

    while True:
        escolha = perguntar(f"Em qual categoria {acao} {reais(diferenca)}? Digite o número: ").strip()
        if escolha.isdigit() and 1 <= int(escolha) <= len(nomes) + 1:
            categoria = nomes[int(escolha) - 1] if int(escolha) <= len(nomes) else "Outros"
            # Não deixa uma categoria ficar negativa ao abater
            if diferenca < 0 and categorias.get(categoria, 0) + diferenca < 0:
                print(f"{categoria} só tem {reais(categorias.get(categoria, 0))}; escolha outra.")
                continue
            break
        print("Opção inválida.")

    data = max(l["data"] for l in lancamentos if l["banco"] == banco)
    aplicar_ajuste(lancamentos, banco, categoria, diferenca, data)
    print(f"Pronto: {reais(diferenca)} {'abatidos de' if diferenca < 0 else 'somados em'} {categoria}.")
    return {"informado": informado, "calculado": calculado, "diferenca": diferenca, "categoria": categoria}
