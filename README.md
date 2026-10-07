# Aurora Siger — Fase 6: SCIC

**Sistema de Comunicação Interplanetária da Colônia**

Atividade integradora da Fase 6 — Ciência da Computação (online), FIAP, 2026.

## Objetivo

O SCIC é um protótipo em Python, operado pelo terminal, que acompanha a comunicação da colônia
Aurora Siger em Marte. A partir das leituras dos sensores de enlace dos 13 módulos da colônia,
ao longo de 30 ciclos, ele:

- compara a latência medida com a prevista e calcula erro absoluto e erro relativo;
- treina uma regressão linear para prever a latência dos enlaces internos e avalia o resultado
  com MAE, MSE, RMSE e R²;
- organiza os alertas por urgência com um **heap** implementado à mão;
- busca módulos, sensores e alertas por prefixo com uma **trie**;
- decodifica os códigos dos sensores entre hexadecimal, decimal e binário e calcula potência e
  resistência dos transceptores pela lei de Ohm;
- termina com uma análise que aponta onde a comunicação falhou e o que acompanhar.

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `codigo_fonte.py` | **arquivo principal**: menu e todas as funcionalidades |
| `dados_aurora_siger.csv` | base simulada: 390 leituras (13 módulos × 30 ciclos) |
| `gerar_dados.py` | script que gerou a base (semente fixa; não é preciso rodá-lo) |
| `relatorio_tecnico.md` | relatório técnico completo |
| `link_video.txt` | link do vídeo de apresentação (YouTube, não listado) |
| `graficos_ou_imagens/avaliacao_modelo.png` | gráfico de avaliação do modelo |
| `graficos_ou_imagens/exemplo_execucao.txt` | saída completa de uma execução |
| `requirements.txt` | dependências |

## Dependências

Python 3.10 ou superior e quatro bibliotecas, todas estudadas na fase:

| Biblioteca | Uso no SCIC |
|---|---|
| NumPy | operações numéricas e análise de precisão do ponto flutuante |
| Pandas | leitura do CSV, organização e indicadores |
| scikit-learn | regressão linear e métricas (MAE, MSE, R²) |
| Matplotlib | gráfico de avaliação do modelo |

O restante usa só a biblioteca padrão do Python. Não usamos nenhuma biblioteca adicional.

```bash
pip install -r requirements.txt
```

## Como executar

```bash
python codigo_fonte.py          # menu interativo
python codigo_fonte.py --demo   # executa todas as funcionalidades em sequência, sem perguntas
```

O menu:

```
  1. Carregar dados                      → lê o CSV e mostra o resumo da base
  2. Cadastrar registro                  → nova leitura de sensor (vale para a sessão)
  3. Consultar registros                 → filtra por módulo, ciclo ou status
  4. Indicadores e erros numéricos       → erro absoluto, relativo e ponto flutuante
  5. Modelo de previsão e métricas       → regressão, MAE/MSE/RMSE/R² e gráfico
  6. Priorizar alertas (heap)            → fila de alertas por urgência
  7. Buscar por prefixo (trie)           → ex.: "co", "0x1", "subt"
  8. Dispositivos, bases numéricas e eletricidade
  9. Análise final
  0. Sair
```

## Exemplo de execução

Trecho da opção 6 (a saída completa está em `graficos_ou_imagens/exemplo_execucao.txt`):

```
32 alertas inseridos no heap (56 comparações).
Urgência = peso do módulo (vital 3, sustento 2, expansão 1) x gravidade (alta 2, crítica 3).

  # urg ciclo  módulo                      origem  descrição
  1   9    30  Suporte Médico              SCIC    latência 18.7 ms contra 3.0 ms previstos (erro de 84%)
  2   9    16  Suporte de Vida             SCIC    latência 18.2 ms contra 2.0 ms previstos (erro de 89%)
  3   9    15  Centro de Controle          SCIC    latência 7.6 ms contra 1.5 ms previstos (erro de 80%)

Comparações para inserir todos os alertas e retirá-los em ordem de urgência:
   alertas      heap   lista simples
        32       226             496
      1000     17712          499500
     10000    247485        49995000
```

## Equipe

| Nome | RM |
|---|---|
| Gabriel Carmona Bittencourt | RM569239 |
| Iúri Leão de Almeida | RM570215 |
| Márcio Francisco dos Santos Júnior | RM570758 |
| Maria Sophia Domingues dos Santos | RM571209 |
