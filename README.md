# 💳 Controle de gastos

Lê as faturas de cartão do mês (CSV do Nubank, PDF do Mercado Pago e print do Banese), separa cada compra em uma categoria e gera um **PDF** organizado: total gasto, gastos por categoria em cada cartão, parcelas que ainda vão vir e a lista completa para conferir.

## Como usar

1. Coloque as faturas do mês na pasta `faturas/`, do jeito que vêm do banco:
   - **Nubank:** o CSV exportado pelo app (`Nubank_2026-10-22.csv`).
   - **Mercado Pago:** o PDF da fatura (`fatura-cartao-mercado-pago-2026-10.pdf`).
   - **Banese:** o print da tela da fatura no app (`.jpg` ou `.png`). Se a fatura não couber numa tela, tire vários prints rolando a tela e coloque todos na pasta; as compras repetidas entre um print e outro são descartadas.

   Não precisa renomear: o programa reconhece o banco pelo nome ou, se não der, pelo tipo do arquivo (CSV = Nubank, PDF = Mercado Pago, imagem = Banese).
2. Rode:
   ```
   python controle.py
   ```
   O programa mostra o que leu do print do Banese, para você conferir se o OCR leu certo.
3. Para cada banco, o programa pergunta **quanto deu a fatura de verdade**. No Mercado Pago e no Banese ele já sugere o total impresso na fatura (é só apertar Enter). Se o valor for diferente da soma das compras, ele mostra as categorias e pergunta de qual **abater** (ou em qual **somar**) a diferença.
4. O PDF aparece na pasta do programa: `gastos_Outubro_2026.pdf`.

Para gerar o PDF sem perguntas: `python controle.py --sem-perguntas`.

Para testar sem dados reais: `python controle.py --pasta exemplo` (um CSV inventado do Nubank). Os leitores do PDF e do print são testados com dados inventados em `testes.py`.

## Categorias

As regras ficam no arquivo **`regras.csv`**: se a descrição da compra tiver a palavra, ela vai para a categoria. A primeira regra que combinar ganha, então as mais específicas ficam em cima (por isso `uber *one` vem antes de `uber`).

Compras que não combinam com nenhuma regra viram uma **categoria com o nome da loja**, e o PDF lista essas categorias no final para você decidir se cria uma regra. Pagamentos e saldo do mês anterior não contam como gasto: aparecem à parte, em "Movimentação da fatura".

## Instalação (Windows)

1. Instale o **Tesseract** (o programa que lê o texto do print do Banese):
   - Baixe o instalador em <https://github.com/UB-Mannheim/tesseract/wiki>.
   - Na instalação, em *Additional language data*, marque **Portuguese**.
   - Deixe na pasta padrão (`C:\Program Files\Tesseract-OCR`): o programa acha sozinho.
2. No terminal, dentro da pasta do projeto:
   ```
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   python -m unittest testes.py
   ```

O Tesseract só é usado para o print do Banese; o Nubank e o Mercado Pago funcionam sem ele.

## Privacidade

As faturas reais e os PDFs gerados ficam fora do Git (`.gitignore`). No repositório vão apenas o código e dados de **exemplo inventados**.
