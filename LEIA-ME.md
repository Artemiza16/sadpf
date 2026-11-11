# SADPF — como instalar e usar em outro computador

**Sistema de Apoio à Decisão para Pequenas Farmácias.** Este é um painel web que roda no seu
próprio computador. Ele lê o histórico de cotações e de movimentação do estoque de uma farmácia
e mostra indicadores e recomendações de compra. Depois de instalado, funciona sem internet.

Este repositório traz o código e a documentação, **sem dados**. Antes de abrir o painel,
coloque a sua planilha de cotações em `dados/`, como explica o `dados/LEIA-ME.txt`.

---

## 1. O que você precisa

| Item | Detalhe |
|---|---|
| Sistema operacional | Windows 10/11, macOS ou Linux |
| Python | versão 3.10 ou mais nova (testado com 3.12). Baixe em <https://www.python.org/downloads/>. No Windows, marque **Add python.exe to PATH** durante a instalação. |
| Internet | só na primeira execução, para baixar as bibliotecas |
| Navegador | Chrome, Edge ou Firefox |

As bibliotecas estão listadas em `requirements.txt` (Streamlit, pandas, NumPy, Plotly e
openpyxl) e são instaladas automaticamente.

## 2. Instalar e abrir

### Jeito mais fácil

- **Windows:** dê dois cliques em **`INICIAR_SADPF.bat`**.
- **macOS / Linux:** abra o Terminal nesta pasta e rode `bash iniciar_sadpf.sh`.

Na primeira vez, o script:

1. cria um ambiente Python só para o sistema (pasta `.venv`);
2. instala as bibliotecas;
3. roda a conferência automática (`verificar.py`);
4. abre o painel em <http://localhost:8501>.

Isso leva alguns minutos. Nas próximas vezes, o painel abre direto.

### Passo a passo manual

Abra um terminal nesta pasta e rode, em ordem:

```bash
python -m venv .venv
```

Depois, no **Windows**:

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe verificar.py
.venv\Scripts\python.exe -m streamlit run app.py
```

Ou, no **macOS / Linux**:

```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python verificar.py
.venv/bin/python -m streamlit run app.py
```

Com os seus dados, o bloco 4 do `verificar.py` aponta diferenças: ele compara os
cálculos com os valores da base usada no TCC, e isso é esperado. Os demais blocos devem passar. Ele confere em 16 blocos o ambiente, os cálculos, os filtros, a importação, o login,
a movimentação, o cadastro manual e as cores, sempre sobre cópias temporárias, sem alterar os dados.

## 3. Entrar

- **Empresa:** `Farmacia`
- **Senha:** `123`

Outras empresas podem ser cadastradas na aba **Criar acesso** da tela de entrada. Os acessos
ficam em `dados/usuarios.json`, que é criado na primeira execução e guarda só o *hash* das
senhas.

Para encerrar, feche a janela do terminal (Windows) ou pressione `Ctrl + C`.

## 4. O que tem nesta pasta

| Pasta ou arquivo | Conteúdo |
|---|---|
| `app.py` | ponto de entrada do painel |
| `core/` | cálculos: dados, métricas, movimentação, apoio à decisão, previsão, cadastro manual |
| `paginas/` | as 16 telas do painel |
| `dados/` | onde ficam os seus dados; traz só `modelo_cotacao.xlsx` (planilha vazia com as colunas) e `LEIA-ME.txt` |
| `movimentacao/` | onde fica o livro de movimentação (opcional) e os scripts do gerador |
| `assets/`, `static/`, `.streamlit/` | logo, fotos e tema visual |
| `DOCUMENTACAO.md` | documentação técnica completa: conceitos, fórmulas, testes e histórico |
| `README.md` | resumo técnico |
| `verificar.py` | conferência automática |
| `gerar_curva_abc.py`, `GERAR_CURVA_ABC.bat` | Curva ABC em Excel sem abrir o painel |
| `gerar_relatorio.py` | refaz as figuras e os números do relatório |

## 5. Atualizar os dados

Na tela **Base de Dados**:

- **Cotações:** envie uma planilha no mesmo formato. O botão *Baixar o modelo de importação*
  traz as colunas e as instruções.
- **Cadastro manual:** digite um pedido item a item, com as mesmas validações da importação.
- **Movimentação de estoque:** envie um livro novo, por exemplo com as vendas do caixa.

Toda gravação guarda uma cópia da versão anterior.

## 6. Refazer o relatório (opcional)

```bash
.venv\Scripts\python.exe -m pip install -r requirements-relatorio.txt
.venv\Scripts\python.exe gerar_relatorio.py
```

As figuras em PNG usam o pacote `kaleido`, que precisa do Google Chrome ou do Chromium instalado.
No macOS e no Linux, troque `.venv\Scripts\python.exe` por `.venv/bin/python`.

## 7. Cuidados com os dados

- Este repositório **não traz dados**. O que você colocar em `dados/` e `movimentacao/`
  fica só no seu computador: o `.gitignore` impede que seja enviado ao GitHub.
- As **vendas, perdas e o estoque inicial** do livro de movimentação são **simulados** a partir
  das compras reais (seção 9 da `DOCUMENTACAO.md`). Eles servem para demonstrar o método.
- Ao compartilhar a pasta, **não inclua a pasta `.venv`**: ela é recriada na primeira execução
  em cada computador.

## 8. Se algo der errado

| Sintoma | O que fazer |
|---|---|
| `'python' não é reconhecido` | reinstale o Python marcando *Add python.exe to PATH*, ou use `py` no lugar de `python` |
| `Port 8501 is already in use` | o painel já está aberto em outra janela; feche-a ou rode com `--server.port 8502` |
| `ModuleNotFoundError` | as bibliotecas não foram instaladas; repita o passo da seção 2 |
| Página em branco | aguarde alguns segundos e recarregue com F5 |

Mais casos na seção 12 da `DOCUMENTACAO.md`.
