"""Testes: python -m unittest testes.py"""
import unittest
from datetime import date
from pathlib import Path

from categorias import PAGAMENTO, SALDO_ANTERIOR, carregar_regras, classificar, nome_da_loja, parcela
from conferencia import aplicar_ajuste, conferir_banco, ler_valor_digitado
from leitores import banco_do_arquivo, ler_banese_palavras, ler_mercado_pago_texto, sem_repetir, texto_para_valor, valor_do_ocr

REGRAS = carregar_regras(Path(__file__).parent / "regras.csv")


def lanc(descricao, valor=10.0):
    return {"data": date(2026, 10, 1), "descricao": descricao, "valor": valor, "banco": "Nubank"}


class TestValores(unittest.TestCase):
    def test_formatos(self):
        self.assertEqual(texto_para_valor("1.774,15"), 1774.15)
        self.assertEqual(texto_para_valor("- 20,00"), -20.0)
        self.assertEqual(texto_para_valor("R$ 25,21"), 25.21)


class TestCategorias(unittest.TestCase):
    def categoria(self, descricao, valor=10.0):
        return classificar(lanc(descricao, valor), REGRAS)[0]

    def test_uber_corrida_e_assinatura(self):
        self.assertEqual(self.categoria("Uber - NuPay"), "Uber")
        self.assertEqual(self.categoria("Dl*Uberrides"), "Uber")
        self.assertEqual(self.categoria("Uber *One Membership U"), "Assinaturas")

    def test_regras_conhecidas(self):
        self.assertEqual(self.categoria("Amazon Kindle Unltd"), "Assinaturas")
        self.assertEqual(self.categoria("Easy Minimercado"), "Comida")
        self.assertEqual(self.categoria("Gol Linhas A*Nrwphh011 - Parcela 1/8"), "Viagem")
        self.assertEqual(self.categoria("Petrox Comercial - Parcela 7/10"), "Petrox")
        self.assertEqual(self.categoria("Renegociação de pendências (22/Julho) - 2/2"), "Atraso")

    def test_pagamento_e_saldo(self):
        self.assertEqual(self.categoria("Pagamento recebido", -20.0), PAGAMENTO)
        self.assertEqual(self.categoria("Valor pendente do mês anterior", 847.28), SALDO_ANTERIOR)

    def test_sem_regra_vai_para_comida(self):
        categoria, tem_regra = classificar(lanc("Livraria Leitura - Parcela 1/2"), REGRAS)
        self.assertEqual(categoria, "Comida")
        self.assertFalse(tem_regra)
        self.assertEqual(self.categoria("Elo*maria Souza Lima Boa"), "Comida")  # nome de pessoa, sem Pix

    def test_regras_da_livia(self):
        self.assertEqual(self.categoria("CHAU CHAU"), "Comida")
        self.assertEqual(self.categoria("BIJOUARTS Parcela 3 de 3"), "Pessoais")
        self.assertEqual(self.categoria("MP*LIVIAEXEMPLO"), "Gastos normais")
        self.assertEqual(self.categoria("MP*MP"), "Gastos normais")
        self.assertEqual(self.categoria("Mercado Livre"), "Pessoais")
        self.assertEqual(self.categoria("Pix*banese*Fulano de Tal"), "Pix")

    def test_parcela(self):
        self.assertEqual(parcela("Gol Linhas - Parcela 1/8"), (1, 8))
        self.assertEqual(parcela("iFood - NuPay - 2/2"), (2, 2))
        self.assertIsNone(parcela("Uber - NuPay"))
        self.assertEqual(nome_da_loja("Rocha Atacado Sul - Parcela 2/3"), "Rocha Atacado Sul")


class TestConferencia(unittest.TestCase):
    def lancamentos(self):
        itens = [lanc("Uber - NuPay", 30.0), lanc("Easy Minimercado", 20.0), lanc("Pagamento recebido", -50.0)]
        for l in itens:
            l["categoria"], l["tem_regra"] = classificar(l, REGRAS)
            l["parcela"] = None
        return itens

    def test_ler_valor_digitado(self):
        self.assertEqual(ler_valor_digitado("724,85"), 724.85)
        self.assertEqual(ler_valor_digitado("724.85"), 724.85)
        self.assertEqual(ler_valor_digitado("R$ 1.774,15"), 1774.15)
        self.assertIsNone(ler_valor_digitado("  "))

    def test_abater_da_categoria_escolhida(self):
        itens = self.lancamentos()
        respostas = iter(["45,00", "1"])  # fatura real 45; abater da 1ª categoria (Uber)
        conf = conferir_banco(itens, "Nubank", perguntar=lambda _: next(respostas))
        self.assertEqual(conf["diferenca"], -5.0)
        uber = sum(l["valor"] for l in itens if l["categoria"] == "Uber")
        self.assertEqual(uber, 25.0)

    def test_somar_quando_a_fatura_e_maior(self):
        itens = self.lancamentos()
        respostas = iter(["60", "3"])  # 3 = "Outros"
        conf = conferir_banco(itens, "Nubank", perguntar=lambda _: next(respostas))
        self.assertEqual((conf["diferenca"], conf["categoria"]), (10.0, "Outros"))

    def test_nao_deixa_categoria_negativa(self):
        itens = self.lancamentos()
        respostas = iter(["25", "2", "1"])  # abater 25: Comida só tem 20, então pede outra
        conf = conferir_banco(itens, "Nubank", perguntar=lambda _: next(respostas))
        self.assertEqual(conf["categoria"], "Uber")

    def test_enter_usa_o_valor_do_arquivo(self):
        self.assertIsNone(conferir_banco(self.lancamentos(), "Nubank", perguntar=lambda _: ""))

    def test_enter_usa_o_total_impresso_na_fatura(self):
        itens = self.lancamentos()
        respostas = iter(["", "1"])  # Enter = 45,00 que veio do PDF; abate 5 do Uber
        conf = conferir_banco(itens, "Nubank", perguntar=lambda _: next(respostas), total_do_arquivo=45.0)
        self.assertEqual((conf["informado"], conf["diferenca"]), (45.0, -5.0))


# Texto inventado no mesmo formato do PDF do Mercado Pago
PDF_MERCADO_PAGO = [
    "Total a pagar Vence em Limite total\nR$ 120,50 14/01/2027 R$ 400,00\n"
    "Parcelamento de fatura\nAté 1 + 9x R$ 48,08",
    "Vencimento: 14/01/2027\nMovimentações na fatura\nData Movimentações Valor em R$\n"
    "18/12 Pagamento da fatura de dezembro/2026 R$ 80,00\n"
    "10/01 Multa por atraso R$ 2,50\n"
    "Cartão Visa [************0000]\nData Movimentações Valor em R$\n"
    "20/12 LOJA TESTE R$ 40,00\n"
    "05/01 SUBWAY CENTRO R$ 28,00\n"
    "25/11 BIJOUX Parcela 2 de 3 R$ 50,00\n"
    "Total R$ 118,00",
    "Pague em 10x\n01/02 R$ 99,99",
]


class TestMercadoPago(unittest.TestCase):
    def test_le_lancamentos_e_total(self):
        lancamentos, total = ler_mercado_pago_texto(PDF_MERCADO_PAGO)
        self.assertEqual(total, 120.50)
        self.assertEqual(len(lancamentos), 5)  # ignora o "Total" e a propaganda
        pagamento = lancamentos[0]
        self.assertEqual(pagamento["valor"], -80.0)
        self.assertEqual(pagamento["data"], date(2026, 12, 18))  # dezembro é do ano anterior
        self.assertEqual(lancamentos[3]["data"], date(2027, 1, 5))
        gastos = sum(l["valor"] for l in lancamentos if l["valor"] > 0)
        self.assertEqual(gastos, 120.50)

    def test_categorias_do_mercado_pago(self):
        cat = lambda d: classificar(lanc(d), REGRAS)[0]
        self.assertEqual(cat("Multa por atraso"), "Atraso")
        self.assertEqual(cat("IOF do rotativo"), "Atraso")
        self.assertEqual(cat("JIM.COM 12345678 FERNANDO"), "Comida")
        self.assertEqual(parcela("BIJOUX Parcela 2 de 3"), (2, 3))
        self.assertEqual(nome_da_loja("BIJOUX Parcela 2 de 3"), "Bijoux")

    def test_banco_pelo_nome_ou_tipo_do_arquivo(self):
        self.assertEqual(banco_do_arquivo(Path("fatura-cartao-mercado-pago-2026-10.pdf")), "Mercado Pago")
        self.assertEqual(banco_do_arquivo(Path("Nubank_2026-10-22.csv")), "Nubank")
        self.assertEqual(banco_do_arquivo(Path("image.jpg")), "Banese")


def palavra(texto, x, y):
    return {"texto": texto, "x": x, "y": y}


# Palavras com posição, como o OCR devolve a partir do print do app do Banese
PRINT_BANESE = [
    palavra("Setembro/2026", 17, 40), palavra("Fechada", 68, 40),
    palavra("R$", 36, 80), palavra("90,50", 45, 80),
    palavra("Vencimento", 33, 120), palavra("25/09/2026", 51, 120),
    palavra("17", 6, 200), palavra("SET", 10, 200), palavra("Elo*loja", 19, 200),
    palavra("Teste", 31, 200), palavra("R$", 83, 200), palavra("2448", 87, 200),  # vírgula sumiu
    palavra("Mercado", 22, 235), palavra("-", 35, 235), palavra("À", 37, 235), palavra("Vista", 40, 235),
    palavra("Pix*banese*Fulano", 19, 290), palavra("de", 40, 290), palavra("Tal", 45, 290),
    palavra("R$", 83, 290), palavra("66,02", 87, 290),  # sem data: mesmo dia de cima
    palavra("Outros", 22, 325), palavra("-", 32, 325), palavra("À", 34, 325), palavra("Vista", 37, 325),
    palavra("20", 5, 380), palavra("AGO", 9, 380), palavra("Pagamento", 19, 380), palavra("de", 36, 380),
    palavra("Fatura", 41, 380), palavra("-R$", 80, 380), palavra("100,00", 86, 380),
]


class TestBanese(unittest.TestCase):
    def test_le_o_print(self):
        lancamentos, total, vencimento = ler_banese_palavras(PRINT_BANESE)
        self.assertEqual(total, 90.50)
        self.assertEqual(vencimento, date(2026, 9, 25))
        self.assertEqual([l["valor"] for l in lancamentos], [24.48, 66.02, -100.0])
        self.assertEqual(lancamentos[1]["dia_mes"], (17, 9))
        self.assertIn("Mercado", lancamentos[0]["dica"])

    def test_categoria_pela_dica_do_app(self):
        item = lanc("Elo*loja Teste")
        item["dica"] = "Mercado - À Vista"
        self.assertEqual(classificar(item, REGRAS)[0], "Comida")
        self.assertEqual(nome_da_loja("Elo*maria Souza Lima Boav"), "Maria Souza Lima")
        self.assertEqual(classificar(lanc("Pix*banese*Fulano"), REGRAS)[0], "Pix")
        self.assertEqual(classificar(lanc("Fatura Anterior", 179.43), REGRAS)[0], SALDO_ANTERIOR)

    def test_valor_do_ocr(self):
        self.assertEqual(valor_do_ocr("24,48"), 24.48)
        self.assertEqual(valor_do_ocr("2448"), 24.48)
        self.assertIsNone(valor_do_ocr("R$"))

    def test_prints_que_se_repetem(self):
        a = [{"dia_mes": (1, 9), "valor": 10.0}, {"dia_mes": (2, 9), "valor": 20.0}]
        b = [{"dia_mes": (2, 9), "valor": 20.0}, {"dia_mes": (3, 9), "valor": 30.0}]
        self.assertEqual(sem_repetir(a, b), [{"dia_mes": (3, 9), "valor": 30.0}])


if __name__ == "__main__":
    unittest.main()
