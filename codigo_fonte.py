"""SCIC - Sistema de Comunicação Interplanetária da Colônia Aurora Siger.

Atividade integradora da Fase 6 (FIAP, Ciência da Computação, 2026).

Como executar:
    python codigo_fonte.py           -> menu interativo
    python codigo_fonte.py --demo    -> executa todas as funcionalidades em sequência

O programa lê dados_aurora_siger.csv (leituras dos sensores de enlace dos 13
módulos ao longo de 30 ciclos) e oferece:

    1. Carregar dados           6. Priorizar alertas (heap)
    2. Cadastrar registro       7. Buscar por prefixo (trie)
    3. Consultar registros      8. Dispositivos, bases numéricas e eletricidade
    4. Indicadores e erros      9. Análise final
    5. Modelo de previsão

Organização do arquivo (cada seção corresponde a um item do enunciado):
    Seção 1 - carga e preparação dos dados
    Seção 2 - indicadores, erro absoluto, erro relativo e ponto flutuante
    Seção 3 - modelo de previsão e métricas de desempenho
    Seção 4 - heap para priorização de alertas
    Seção 5 - trie para busca por prefixo
    Seção 6 - bases numéricas e eletricidade básica
    Seção 7 - análise final
    Seção 8 - telas do menu (toda a interação com o usuário fica aqui)
"""

import math
import sys
import unicodedata
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # salva o gráfico em arquivo, sem precisar de janela gráfica
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

PASTA = Path(__file__).resolve().parent
ARQUIVO_DADOS = PASTA / "dados_aurora_siger.csv"
PASTA_GRAFICOS = PASTA / "graficos_ou_imagens"

# Limiares para julgar o erro de previsão da latência (explicados no relatório).
# Enlaces locais são julgados pelo erro RELATIVO: 3 ms a mais pesam muito num
# enlace de 1,5 ms e quase nada num de 12 ms.
LIMIAR_LOCAL_ATENCAO = 0.25        # 25 %
LIMIAR_LOCAL_PREOCUPANTE = 0.50    # 50 %
# O enlace com a Terra é julgado pelo erro ABSOLUTO: o relativo fica abaixo de 1 %
# mesmo quando o atraso extra já é suficiente para perder uma janela de comando.
LIMIAR_TERRA_ATENCAO_MS = 1000.0
LIMIAR_TERRA_PREOCUPANTE_MS = 2500.0

# Tensão do barramento de 28 V abaixo da qual o módulo registra alerta.
TENSAO_ALERTA_V = 26.5
TENSAO_CRITICA_V = 26.0

# O modelo é treinado com os primeiros ciclos e testado com os últimos,
# como aconteceria na prática: prever o futuro a partir do passado.
ULTIMO_CICLO_TREINO = 22
VARIAVEIS_MODELO = ["carga_rede_pct", "opacidade_tau", "latencia_prevista_ms"]

# Resíduo acima do qual um registro de teste é tratado como rajada de retransmissão.
LIMIAR_RAJADA_MS = 8.0

HORAS_POR_SOL = 24.66  # duração de um dia marciano


# =============================================================================
# SEÇÃO 1 - CARGA E PREPARAÇÃO DOS DADOS
# =============================================================================

def carregar_dados(caminho: Path = ARQUIVO_DADOS) -> pd.DataFrame:
    """Lê o CSV com Pandas e acrescenta as colunas calculadas."""
    df = pd.read_csv(caminho, encoding="utf-8")
    df["mensagem"] = df["mensagem"].fillna("")
    return preparar(df)


def preparar(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula potência, resistência equivalente e os erros de previsão de cada registro.

    Registros sem leitura de latência (manutenção ou sensor sem resposta) ficam
    com erro NaN: não dá para comparar previsão com um valor que não foi medido.
    """
    df = df.copy()
    df["potencia_w"] = df["tensao_v"] * df["corrente_a"]              # P = V . I
    df["resistencia_ohm"] = df["tensao_v"] / df["corrente_a"]         # R = V / I
    df["erro_abs_ms"] = (df["latencia_observada_ms"] - df["latencia_prevista_ms"]).abs()
    df["erro_rel"] = df["erro_abs_ms"] / df["latencia_observada_ms"]  # referência: o valor medido
    df["acima_previsto"] = df["latencia_observada_ms"] > df["latencia_prevista_ms"]
    df["avaliacao_erro"] = [
        classificar_erro(enlace, abs_ms, rel)
        for enlace, abs_ms, rel in zip(df["enlace"], df["erro_abs_ms"], df["erro_rel"])
    ]
    return df


def classificar_erro(enlace: str, erro_abs_ms: float, erro_rel: float) -> str:
    """Diz se o erro de previsão é aceitável, merece atenção ou é preocupante."""
    if pd.isna(erro_abs_ms):
        return "sem leitura"
    if enlace == "Terra":
        if erro_abs_ms > LIMIAR_TERRA_PREOCUPANTE_MS:
            return "preocupante"
        return "atenção" if erro_abs_ms > LIMIAR_TERRA_ATENCAO_MS else "aceitável"
    if erro_rel > LIMIAR_LOCAL_PREOCUPANTE:
        return "preocupante"
    return "atenção" if erro_rel > LIMIAR_LOCAL_ATENCAO else "aceitável"


def cadastrar_registro(df: pd.DataFrame, modulo: str, ciclo: int, carga_pct: float,
                       tau: float, tensao_v: float, corrente_a: float,
                       latencia_ms: float) -> pd.DataFrame:
    """Acrescenta uma nova leitura de sensor e devolve a base atualizada.

    Os dados fixos do módulo (tipo, prioridade, código, enlace e latência
    prevista) vêm do cadastro que já existe na base.
    """
    ficha = df[df["modulo"] == modulo].iloc[-1]
    status, mensagem = "ativo", ""
    if tensao_v < TENSAO_ALERTA_V:
        status, mensagem = "alerta", f"subtensão no barramento ({tensao_v:.1f} V)"
    novo = {
        "ciclo": ciclo, "modulo": modulo, "tipo": ficha["tipo"],
        "prioridade": ficha["prioridade"], "codigo_sensor": ficha["codigo_sensor"],
        "enlace": ficha["enlace"], "carga_rede_pct": carga_pct, "opacidade_tau": tau,
        "tensao_v": tensao_v, "corrente_a": corrente_a,
        "latencia_prevista_ms": ficha["latencia_prevista_ms"],
        "latencia_observada_ms": latencia_ms, "status": status, "mensagem": mensagem,
    }
    colunas_originais = [c for c in df.columns if c in novo]
    base = pd.concat([df[colunas_originais], pd.DataFrame([novo])], ignore_index=True)
    return preparar(base)


# =============================================================================
# SEÇÃO 2 - INDICADORES, ERROS E PRECISÃO NUMÉRICA
# =============================================================================

def indicadores_por_modulo(df: pd.DataFrame) -> pd.DataFrame:
    """Resume cada módulo: latência, erros, disponibilidade, alertas e potência."""
    grupos = df.groupby("modulo", sort=False)
    tabela = pd.DataFrame({
        "enlace": grupos["enlace"].first(),
        "lat_media_ms": grupos["latencia_observada_ms"].mean(),
        "erro_abs_medio_ms": grupos["erro_abs_ms"].mean(),
        "erro_rel_medio_pct": grupos["erro_rel"].mean() * 100,
        "disponibilidade_pct": grupos["latencia_observada_ms"].apply(lambda s: s.notna().mean() * 100),
        "preocupantes": grupos["avaliacao_erro"].apply(lambda s: (s == "preocupante").sum()),
        "potencia_media_w": grupos["potencia_w"].mean(),
    })
    return tabela.round(2)


def resumo_erros_por_enlace(df: pd.DataFrame) -> pd.DataFrame:
    """Compara os dois tipos de enlace: mostra por que cada um usa um tipo de erro."""
    medidos = df.dropna(subset=["latencia_observada_ms"])
    return medidos.groupby("enlace").agg(
        registros=("erro_abs_ms", "size"),
        erro_abs_medio_ms=("erro_abs_ms", "mean"),
        erro_abs_max_ms=("erro_abs_ms", "max"),
        erro_rel_medio_pct=("erro_rel", lambda s: s.mean() * 100),
        erro_rel_max_pct=("erro_rel", lambda s: s.max() * 100),
    ).round(3)


def analise_ponto_flutuante(df: pd.DataFrame) -> dict:
    """Mede os limites de precisão numérica que afetam os dados do SCIC."""
    lat_terra = df.loc[df["enlace"] == "Terra", "latencia_observada_ms"].max()
    lat_local = df.loc[df["enlace"] == "local", "latencia_observada_ms"].min()
    return {
        "soma_0_1_0_2": 0.1 + 0.2,
        "igual_0_3": (0.1 + 0.2) == 0.3,
        "isclose_0_3": math.isclose(0.1 + 0.2, 0.3),
        "lat_terra_ms": lat_terra,
        "espaco_float64_terra": float(np.spacing(np.float64(lat_terra))),
        "espaco_float32_terra": float(np.spacing(np.float32(lat_terra))),
        "lat_local_ms": lat_local,
        "espaco_float32_local": float(np.spacing(np.float32(lat_local))),
        "erro_max_arredondamento_ms": 0.0005,  # o CSV guarda 3 casas decimais
        "menor_erro_abs_ms": df["erro_abs_ms"].min(),
    }


# =============================================================================
# SEÇÃO 3 - MODELO DE PREVISÃO E MÉTRICAS
# =============================================================================

def metricas(y_real, y_previsto) -> dict:
    """MAE, MSE, RMSE e R² de uma previsão."""
    mse = mean_squared_error(y_real, y_previsto)
    return {
        "MAE": mean_absolute_error(y_real, y_previsto),
        "MSE": mse,
        "RMSE": math.sqrt(mse),
        "R2": r2_score(y_real, y_previsto),
    }


def treinar_modelo(df: pd.DataFrame) -> dict:
    """Treina uma regressão linear para a latência dos enlaces locais.

    O enlace com a Terra fica de fora: seu atraso é quase todo tempo de viagem
    da luz, que a previsão nominal já calcula com erro abaixo de 1 %.

    Variáveis de entrada: carga da rede, opacidade da atmosfera e latência de
    projeto do enlace. Ciclo e código do sensor NÃO entram: são identificadores,
    e o modelo aprenderia a decorar o registro em vez de explicar a latência.
    """
    locais = df[(df["enlace"] == "local")].dropna(subset=["latencia_observada_ms"])
    treino = locais[locais["ciclo"] <= ULTIMO_CICLO_TREINO]
    teste = locais[locais["ciclo"] > ULTIMO_CICLO_TREINO].copy()

    modelo = LinearRegression()
    modelo.fit(treino[VARIAVEIS_MODELO], treino["latencia_observada_ms"])
    teste["previsao_modelo_ms"] = modelo.predict(teste[VARIAVEIS_MODELO])

    # Um número só esconde onde o modelo acerta e onde erra: separamos o teste
    # por condição do céu e isolamos as rajadas de retransmissão.
    real = teste["latencia_observada_ms"]
    por_condicao = {}
    for condicao, filtro in (("tempestade", teste["opacidade_tau"] > 1.0),
                             ("céu limpo", teste["opacidade_tau"] <= 1.0)):
        parte = teste[filtro]
        por_condicao[condicao] = {
            "registros": len(parte),
            "mae_nominal": mean_absolute_error(parte["latencia_observada_ms"],
                                               parte["latencia_prevista_ms"]),
            "mae_regressao": mean_absolute_error(parte["latencia_observada_ms"],
                                                 parte["previsao_modelo_ms"]),
        }
    rajada = (real - teste["previsao_modelo_ms"]).abs() > LIMIAR_RAJADA_MS
    sem_rajadas = teste[~rajada]

    return {
        "modelo": modelo,
        "n_treino": len(treino),
        "n_teste": len(teste),
        "teste": teste,
        "coeficientes": dict(zip(VARIAVEIS_MODELO, modelo.coef_)),
        "intercepto": modelo.intercept_,
        "nominal": metricas(teste["latencia_observada_ms"], teste["latencia_prevista_ms"]),
        "regressao": metricas(teste["latencia_observada_ms"], teste["previsao_modelo_ms"]),
        "por_condicao": por_condicao,
        "rajadas": int(rajada.sum()),
        "regressao_sem_rajadas": metricas(sem_rajadas["latencia_observada_ms"],
                                          sem_rajadas["previsao_modelo_ms"]),
    }


def salvar_grafico(df: pd.DataFrame, resultado: dict) -> Path:
    """Gera a figura de avaliação do modelo em graficos_ou_imagens/."""
    PASTA_GRAFICOS.mkdir(exist_ok=True)
    tinta, nominal, regressao, grade = "#3d3d3a", "#eb6834", "#2a78d6", "#e4e3dc"
    teste = resultado["teste"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5), facecolor="#fcfcfb")

    # Painel 1: previsto contra observado nos ciclos de teste.
    limite = teste["latencia_observada_ms"].max() * 1.05
    ax1.plot([0, limite], [0, limite], color="#a3a29a", linestyle="--", linewidth=1,
             label="previsão perfeita")
    ax1.scatter(teste["latencia_observada_ms"], teste["latencia_prevista_ms"],
                s=22, color=nominal, label="previsão nominal (projeto)")
    ax1.scatter(teste["latencia_observada_ms"], teste["previsao_modelo_ms"],
                s=22, color=regressao, label="regressão linear")
    ax1.set_xlabel("latência observada (ms)")
    ax1.set_ylabel("latência prevista (ms)")
    ax1.set_title("Previsto x observado nos ciclos de teste", loc="left", fontsize=11)
    ax1.legend(frameon=False, fontsize=9)

    # Painel 2: quanto a latência passou do valor de projeto, ciclo a ciclo.
    # Usamos o excesso de cada registro (observado - projeto) e a mediana entre os
    # módulos: assim um módulo em manutenção não muda a curva, e uma rajada isolada
    # num único módulo não esconde o efeito das tempestades.
    locais = df[df["enlace"] == "local"].dropna(subset=["latencia_observada_ms"]).copy()
    locais["previsao_modelo_ms"] = resultado["modelo"].predict(locais[VARIAVEIS_MODELO])
    locais["excesso_observado"] = locais["latencia_observada_ms"] - locais["latencia_prevista_ms"]
    locais["excesso_modelo"] = locais["previsao_modelo_ms"] - locais["latencia_prevista_ms"]
    por_ciclo = locais.groupby("ciclo")[["excesso_observado", "excesso_modelo", "opacidade_tau"]].median()
    topo = por_ciclo[["excesso_observado", "excesso_modelo"]].max().max()
    primeira = True
    for ciclo, tau in por_ciclo["opacidade_tau"].items():
        if tau > 1.0:
            ax2.axvspan(ciclo - 0.5, ciclo + 0.5, color=grade, linewidth=0,
                        label="tempestade de poeira" if primeira else None)
            primeira = False
    ax2.axvline(ULTIMO_CICLO_TREINO + 0.5, color="#a3a29a", linewidth=1, linestyle=":")
    ax2.text(ULTIMO_CICLO_TREINO + 0.7, topo * 0.95, "início\ndo teste", color="#6b6a63", fontsize=9,
             va="top")
    ax2.axhline(0, color=nominal, linewidth=2, label="previsão nominal")
    ax2.plot(por_ciclo.index, por_ciclo["excesso_observado"], color=tinta, linewidth=2,
             label="observado")
    ax2.plot(por_ciclo.index, por_ciclo["excesso_modelo"], color=regressao, linewidth=2,
             label="regressão linear")
    ax2.set_ylim(top=topo * 1.25)
    ax2.set_xlabel("ciclo (sol)")
    ax2.set_ylabel("latência acima do projeto (ms, mediana)")
    ax2.set_title("Excesso de latência nos enlaces locais", loc="left", fontsize=11)
    ax2.legend(frameon=False, fontsize=9, loc="upper left")

    for ax in (ax1, ax2):
        ax.set_facecolor("#fcfcfb")
        ax.grid(color=grade, linewidth=0.8)
        ax.set_axisbelow(True)
        for lado in ("top", "right"):
            ax.spines[lado].set_visible(False)

    fig.tight_layout()
    caminho = PASTA_GRAFICOS / "avaliacao_modelo.png"
    fig.savefig(caminho, dpi=150)
    plt.close(fig)
    return caminho


# =============================================================================
# SEÇÃO 4 - HEAP PARA PRIORIZAÇÃO DE ALERTAS
# =============================================================================

def chave_urgencia(alerta: dict) -> tuple:
    """Critério de prioridade: urgência primeiro; no empate, o alerta mais recente."""
    return (alerta["urgencia"], alerta["ciclo"])


class HeapAlertas:
    """Heap de máximo guardado numa lista comum.

    A árvore fica implícita nos índices: o pai do item i está em (i - 1) // 2 e
    os filhos em 2i + 1 e 2i + 2. A única regra mantida é que cada pai é pelo
    menos tão urgente quanto os filhos, então o mais urgente fica sempre no
    índice 0.
    """

    def __init__(self) -> None:
        self.itens: list[dict] = []
        self.comparacoes = 0  # usado para comparar com a lista simples

    def __len__(self) -> int:
        return len(self.itens)

    def _mais_urgente(self, i: int, j: int) -> bool:
        self.comparacoes += 1
        return chave_urgencia(self.itens[i]) > chave_urgencia(self.itens[j])

    def _trocar(self, i: int, j: int) -> None:
        self.itens[i], self.itens[j] = self.itens[j], self.itens[i]

    def inserir(self, alerta: dict) -> None:
        """Coloca o alerta no fim da lista e o faz subir (heapify-up)."""
        self.itens.append(alerta)
        self._subir(len(self.itens) - 1)

    def ver_mais_urgente(self) -> dict:
        """Consulta o topo sem remover."""
        if not self.itens:
            raise IndexError("não há alertas no heap")
        return self.itens[0]

    def remover_mais_urgente(self) -> dict:
        """Tira o topo, põe o último item no lugar e o faz descer (heapify-down)."""
        if not self.itens:
            raise IndexError("não há alertas no heap")
        self._trocar(0, len(self.itens) - 1)
        topo = self.itens.pop()
        if self.itens:
            self._descer(0)
        return topo

    def _subir(self, i: int) -> None:
        # heapify-up: enquanto o item for mais urgente que o pai, troca com ele.
        while i > 0:
            pai = (i - 1) // 2
            if not self._mais_urgente(i, pai):
                break
            self._trocar(i, pai)
            i = pai

    def _descer(self, i: int) -> None:
        # heapify-down: enquanto algum filho for mais urgente, troca com o maior deles.
        n = len(self.itens)
        while True:
            maior = i
            for filho in (2 * i + 1, 2 * i + 2):
                if filho < n and self._mais_urgente(filho, maior):
                    maior = filho
            if maior == i:
                break
            self._trocar(i, maior)
            i = maior


def gerar_alertas(df: pd.DataFrame) -> list[dict]:
    """Reúne os alertas de duas origens.

    - reportados pelo próprio módulo (coluna status = "alerta" no CSV):
      subtensão no barramento e sensor sem resposta;
    - detectados pelo SCIC: latência acima do previsto com erro preocupante.

    gravidade: 2 = alta, 3 = crítica.
    urgência = peso do módulo x gravidade, com peso 3 para módulos vitais
    (prioridade 1), 2 para sustento e 1 para expansão.
    """
    alertas = []
    for _, r in df.iterrows():
        if r["status"] == "alerta":
            if "subtensão" in r["mensagem"]:
                gravidade = 3 if r["tensao_v"] < TENSAO_CRITICA_V else 2
            else:
                gravidade = 2
            categoria = "subtensão" if "subtensão" in r["mensagem"] else "sensor sem resposta"
            alertas.append(_novo_alerta(r, "módulo", categoria, r["mensagem"], gravidade))

        if r["avaliacao_erro"] == "preocupante" and r["acima_previsto"]:
            if r["enlace"] == "Terra":
                extra_s = r["erro_abs_ms"] / 1000
                descricao = f"enlace com a Terra {extra_s:.1f} s mais lento que o previsto"
                gravidade = 3 if extra_s > 3 else 2
                categoria = "atraso Terra"
            else:
                descricao = (f"latência {r['latencia_observada_ms']:.1f} ms contra "
                             f"{r['latencia_prevista_ms']:.1f} ms previstos "
                             f"(erro de {r['erro_rel']:.0%})")
                gravidade = 3 if r["erro_rel"] > 0.75 else 2
                categoria = "latência alta"
            alertas.append(_novo_alerta(r, "SCIC", categoria, descricao, gravidade))
    return alertas


def _novo_alerta(registro, origem: str, categoria: str, descricao: str, gravidade: int) -> dict:
    peso_modulo = 4 - int(registro["prioridade"])
    return {
        "ciclo": int(registro["ciclo"]),
        "modulo": registro["modulo"],
        "codigo_sensor": registro["codigo_sensor"],
        "prioridade": int(registro["prioridade"]),
        "origem": origem,
        "categoria": categoria,
        "descricao": descricao,
        "gravidade": gravidade,
        "urgencia": peso_modulo * gravidade,
    }


def montar_heap(alertas: list[dict]) -> HeapAlertas:
    heap = HeapAlertas()
    for alerta in alertas:
        heap.inserir(alerta)
    return heap


def comparacoes_heap_medidas(n: int, semente: int = 7) -> int:
    """Insere e retira n alertas sintéticos num heap e conta as comparações feitas."""
    rng = np.random.default_rng(semente)
    heap = HeapAlertas()
    for ciclo in range(n):
        heap.inserir({"urgencia": int(rng.integers(1, 10)), "ciclo": ciclo})
    while heap:
        heap.remover_mais_urgente()
    return heap.comparacoes


def comparacoes_lista_simples(n: int) -> int:
    """Comparações para esvaziar uma lista sem ordem, achando o máximo a cada vez.

    Achar o maior entre k itens exige k - 1 comparações; somando de k = n até 1
    dá n(n - 1) / 2.
    """
    return n * (n - 1) // 2


# =============================================================================
# SEÇÃO 5 - TRIE PARA BUSCA POR PREFIXO
# =============================================================================

def normalizar(texto: str) -> str:
    """Minúsculas e sem acento: "Comunicações" e "comunicacoes" viram a mesma chave."""
    decomposto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


class NoTrie:
    def __init__(self) -> None:
        self.filhos: dict[str, "NoTrie"] = {}
        self.rotulo: str | None = None       # palavra original, se uma chave termina aqui
        self.referencias: list[str] = []     # o que essa chave aponta (módulos, alertas...)


class Trie:
    """Árvore de prefixos: cada nível consome um caractere da chave.

    Para achar tudo que começa com um prefixo de m letras, a busca desce m
    nós e depois só percorre o galho abaixo dele; o resto da base nem é visitado.
    """

    def __init__(self) -> None:
        self.raiz = NoTrie()
        self.total_chaves = 0

    def inserir(self, chave: str, referencia: str) -> None:
        no = self.raiz
        for letra in normalizar(chave):
            no = no.filhos.setdefault(letra, NoTrie())
        if no.rotulo is None:
            no.rotulo = chave
            self.total_chaves += 1
        if referencia not in no.referencias:
            no.referencias.append(referencia)

    def buscar_prefixo(self, prefixo: str) -> list[tuple[str, list[str]]]:
        """Devolve (chave, referências) de todas as chaves que começam com o prefixo."""
        no = self.raiz
        for letra in normalizar(prefixo):
            if letra not in no.filhos:
                return []
            no = no.filhos[letra]
        encontrados = []
        pilha = [no]
        while pilha:  # percorre só o galho abaixo do prefixo
            atual = pilha.pop()
            if atual.rotulo is not None:
                encontrados.append((atual.rotulo, atual.referencias))
            pilha.extend(atual.filhos.values())
        return sorted(encontrados, key=lambda par: normalizar(par[0]))


def construir_indice(df: pd.DataFrame, alertas: list[dict]) -> Trie:
    """Indexa nomes de módulos, códigos de sensores e palavras das mensagens de alerta."""
    trie = Trie()
    fichas = df.drop_duplicates("modulo")
    for _, f in fichas.iterrows():
        descricao = f"módulo {f['modulo']} | sensor {f['codigo_sensor']} | prioridade {f['prioridade']}"
        trie.inserir(f["modulo"], descricao)
        trie.inserir(f["codigo_sensor"], f"sensor do módulo {f['modulo']}")
        # Cada palavra do nome também vira chave: "cien" acha o Laboratório Científico.
        palavras = f["modulo"].replace("(", " ").replace(")", " ").split()
        for palavra in palavras[1:]:
            if len(palavra) > 3:  # ignora "de", "e"...
                trie.inserir(palavra, descricao)
    for a in alertas:
        trie.inserir(a["categoria"], f"ciclo {a['ciclo']:>2} | {a['modulo']} | {a['descricao']}")
    return trie


# =============================================================================
# SEÇÃO 6 - BASES NUMÉRICAS E ELETRICIDADE BÁSICA
# =============================================================================

def decimal_para_binario(numero: int, bits: int = 16) -> str:
    """Conversão por divisões sucessivas por 2: os restos, lidos de baixo para cima."""
    restos = []
    while numero > 0:
        restos.append(str(numero % 2))
        numero //= 2
    return "".join(reversed(restos)).zfill(bits)


def hexadecimal_para_decimal(codigo: str) -> int:
    """Soma posicional: cada dígito vale digito x 16^posição."""
    digitos = "0123456789ABCDEF"
    texto = codigo.upper().removeprefix("0X")
    if not texto:
        raise ValueError("código vazio")
    valor = 0
    for posicao, digito in enumerate(reversed(texto)):
        valor += digitos.index(digito) * 16 ** posicao
    return valor


def decodificar_codigo(codigo: str) -> dict:
    """Separa os campos do código de 16 bits do sensor.

    bits 15-12: prioridade | bits 11-8: tipo do módulo | bits 7-0: id do módulo
    """
    valor = hexadecimal_para_decimal(codigo)
    if valor > 0xFFFF:
        raise ValueError("o código do sensor tem 16 bits (no máximo 4 dígitos hexadecimais)")
    binario = decimal_para_binario(valor)
    return {
        "hexadecimal": codigo,
        "decimal": valor,
        "binario": " ".join(binario[i:i + 4] for i in range(0, 16, 4)),
        "prioridade": (valor >> 12) & 0xF,
        "tipo": (valor >> 8) & 0xF,
        "id_modulo": valor & 0xFF,
    }


def eletrica_por_modulo(df: pd.DataFrame) -> pd.DataFrame:
    """Tensão, corrente, potência e resistência média de cada transceptor."""
    tabela = df.groupby("modulo", sort=False)[
        ["tensao_v", "corrente_a", "potencia_w", "resistencia_ohm"]].mean()
    tabela["energia_wh_por_sol"] = tabela["potencia_w"] * HORAS_POR_SOL
    return tabela.round(2)


# =============================================================================
# SEÇÃO 7 - ANÁLISE FINAL
# =============================================================================

def chance_repeticao_por_acaso(eventos: int, modulos: int) -> float:
    """Chance de algum módulo receber dois ou mais eventos sorteados ao acaso.

    É o "paradoxo do aniversário": a chance de NENHUM repetir é
    modulos x (modulos - 1) x ... dividido por modulos^eventos.
    """
    return 1 - math.perm(modulos, eventos) / modulos ** eventos


def analise_final(df: pd.DataFrame, resultado: dict, alertas: list[dict]) -> dict:
    """Junta os principais números para apoiar a decisão da equipe de operações."""
    locais = df[df["enlace"] == "local"].dropna(subset=["latencia_observada_ms"])
    tempestade = locais["opacidade_tau"] > 1.0

    # Erros preocupantes com céu limpo não têm a poeira como explicação:
    # são os candidatos a acompanhamento do transceptor (manutenção preditiva).
    sem_explicacao = locais[(~tempestade) & (locais["avaliacao_erro"] == "preocupante")
                            & locais["acima_previsto"]]

    heap = montar_heap(alertas)
    mais_urgentes = [heap.remover_mais_urgente() for _ in range(min(3, len(heap)))]

    return {
        "lat_media_ceu_limpo": locais.loc[~tempestade, "latencia_observada_ms"].mean(),
        "lat_media_tempestade": locais.loc[tempestade, "latencia_observada_ms"].mean(),
        "mae_nominal": resultado["nominal"]["MAE"],
        "mae_regressao": resultado["regressao"]["MAE"],
        "total_alertas": len(alertas),
        "mais_urgentes": mais_urgentes,
        "inspecionar": sem_explicacao[["ciclo", "modulo", "latencia_observada_ms",
                                       "latencia_prevista_ms"]],
        "chance_repeticao": chance_repeticao_por_acaso(len(sem_explicacao),
                                                       locais["modulo"].nunique()),
        "subtensao_ciclos": sorted(df.loc[df["mensagem"].str.contains("subtensão"), "ciclo"].unique()),
    }


# =============================================================================
# SEÇÃO 8 - TELAS DO MENU
# =============================================================================

def titulo(texto: str) -> None:
    print("\n" + "=" * 72)
    print(texto)
    print("=" * 72)


def tela_carregar() -> pd.DataFrame:
    titulo("1. CARREGAR DADOS")
    df = carregar_dados()
    print(f"Arquivo: {ARQUIVO_DADOS.name}")
    print(f"{len(df)} registros | {df['modulo'].nunique()} módulos | "
          f"ciclos {df['ciclo'].min()} a {df['ciclo'].max()}")
    print(f"Leituras sem latência (manutenção ou sensor mudo): "
          f"{df['latencia_observada_ms'].isna().sum()}")
    print("\nStatus dos registros:")
    print(df["status"].value_counts().to_string())
    return df


def tela_cadastrar(df: pd.DataFrame) -> pd.DataFrame:
    titulo("2. CADASTRAR REGISTRO")
    modulos = list(df["modulo"].unique())
    for i, nome in enumerate(modulos, start=1):
        print(f"  {i:>2}. {nome}")
    try:
        numero = int(input("Número do módulo: "))
        if not 1 <= numero <= len(modulos):
            raise IndexError
        modulo = modulos[numero - 1]
        ciclo = int(input("Ciclo (sol): "))
        carga = float(input("Carga da rede (%): "))
        tau = float(input("Opacidade da atmosfera (tau): "))
        tensao = float(input("Tensão no transceptor (V): "))
        corrente = float(input("Corrente no transceptor (A): "))
        latencia = float(input("Latência medida (ms): "))
    except (ValueError, IndexError, EOFError):
        print("\nEntrada inválida. Nada foi cadastrado.")
        return df
    df = cadastrar_registro(df, modulo, ciclo, carga, tau, tensao, corrente, latencia)
    novo = df.iloc[-1]
    print(f"\nRegistro cadastrado nesta sessão (o CSV original não é alterado).")
    print(f"Potência: {novo['potencia_w']:.1f} W | erro relativo: {novo['erro_rel']:.1%} "
          f"| avaliação: {novo['avaliacao_erro']} | status: {novo['status']}")
    return df


def tela_consultar(df: pd.DataFrame, filtro: str | None = None, valor: str | None = None) -> None:
    titulo("3. CONSULTAR REGISTROS")
    if filtro is None:
        print("Filtrar por: 1) módulo  2) ciclo  3) status")
        filtro = {"1": "modulo", "2": "ciclo", "3": "status"}.get(input("Opção: ").strip(), "")
        if not filtro:
            print("Opção inválida.")
            return
        valor = input("Valor procurado: ").strip()
    if filtro == "ciclo":
        if not valor.isdigit():
            print("Informe o número do ciclo.")
            return
        resultado = df[df["ciclo"] == int(valor)]
    else:
        resultado = df[df[filtro].map(normalizar).str.contains(normalizar(valor), regex=False)]
    colunas = ["ciclo", "modulo", "status", "latencia_prevista_ms", "latencia_observada_ms",
               "erro_rel", "avaliacao_erro", "mensagem"]
    if resultado.empty:
        print("Nenhum registro encontrado.")
        return
    print(f"{len(resultado)} registro(s):\n")
    print(resultado[colunas].to_string(index=False, max_rows=20,
                                       formatters={"erro_rel": "{:.1%}".format}))


def tela_indicadores(df: pd.DataFrame) -> None:
    titulo("4. INDICADORES E ERROS NUMÉRICOS")
    print("Indicadores por módulo (latência em ms; Comunicações é o enlace com a Terra):\n")
    print(indicadores_por_modulo(df).to_string())

    print("\nErro absoluto x erro relativo por tipo de enlace:\n")
    print(resumo_erros_por_enlace(df).to_string())
    print("\nNo enlace com a Terra o erro absoluto chega a segundos, mas o relativo fica")
    print("abaixo de 1 %: o atraso é dominado pela distância. Nos enlaces locais o erro")
    print("absoluto é de poucos milissegundos e mesmo assim pode passar de 50 %.")
    print(f"Por isso o SCIC julga a Terra pelo erro absoluto (preocupante acima de "
          f"{LIMIAR_TERRA_PREOCUPANTE_MS / 1000:.1f} s)")
    print(f"e os enlaces locais pelo relativo (preocupante acima de "
          f"{LIMIAR_LOCAL_PREOCUPANTE:.0%}).")
    contagem = df["avaliacao_erro"].value_counts()
    print("\nAvaliação dos registros: " +
          ", ".join(f"{nome}: {qtd}" for nome, qtd in contagem.items()))

    pf = analise_ponto_flutuante(df)
    print("\nPrecisão numérica:")
    print(f"  0.1 + 0.2 = {pf['soma_0_1_0_2']!r}  (igual a 0.3? {pf['igual_0_3']}; "
          f"math.isclose? {pf['isclose_0_3']})")
    print(f"  Maior latência da Terra: {pf['lat_terra_ms']:.3f} ms. Distância até o próximo")
    print(f"  número representável: {pf['espaco_float64_terra']:.1e} ms em float64 e "
          f"{pf['espaco_float32_terra']:.4f} ms em float32.")
    print(f"  Menor latência local: {pf['lat_local_ms']:.3f} ms. Em float32 o passo é "
          f"{pf['espaco_float32_local']:.1e} ms.")
    print(f"  O CSV guarda 3 casas: o arredondamento erra no máximo "
          f"{pf['erro_max_arredondamento_ms']} ms,")
    print("  muito abaixo dos erros de previsão medidos. Nos dados do SCIC, o erro que pesa")
    print("  nas decisões vem do modelo e do sensor; o da representação é desprezível.")


def tela_modelo(df: pd.DataFrame) -> dict:
    titulo("5. MODELO DE PREVISÃO E MÉTRICAS")
    r = treinar_modelo(df)
    print("Regressão linear para a latência dos enlaces locais.")
    print(f"Treino: ciclos 1 a {ULTIMO_CICLO_TREINO} ({r['n_treino']} registros). "
          f"Teste: ciclos {ULTIMO_CICLO_TREINO + 1} a 30 ({r['n_teste']} registros).")
    print("\nlatência = " + f"{r['intercepto']:.3f}" + "".join(
        f" {c:+.3f} x {nome}" for nome, c in r["coeficientes"].items()))

    print("\nDesempenho nos ciclos de teste:")
    print(f"  {'':22}{'MAE':>8}{'MSE':>9}{'RMSE':>8}{'R²':>8}")
    for nome, chave in (("previsão nominal", "nominal"), ("regressão linear", "regressao")):
        m = r[chave]
        print(f"  {nome:22}{m['MAE']:8.3f}{m['MSE']:9.3f}{m['RMSE']:8.3f}{m['R2']:8.3f}")

    print("\nMAE por condição do céu:")
    for condicao, c in r["por_condicao"].items():
        print(f"  {condicao:11} ({c['registros']:>2} registros): nominal {c['mae_nominal']:.2f} ms"
              f" | regressão {c['mae_regressao']:.2f} ms")

    m, limpo = r["regressao"], r["regressao_sem_rajadas"]
    print("\nComo ler:")
    print(f"  - Na média geral a regressão erra {m['MAE']:.2f} ms (MAE), contra "
          f"{r['nominal']['MAE']:.2f} ms da previsão de projeto.")
    print("    O ganho está nas tempestades: com céu limpo a latência de projeto já basta.")
    print(f"  - O RMSE ({m['RMSE']:.2f} ms) é {m['RMSE'] / m['MAE']:.1f} vezes o MAE: "
          "poucos registros concentram erros grandes.")
    print(f"    São {r['rajadas']} rajadas de retransmissão (erro acima de {LIMIAR_RAJADA_MS:.0f} ms), "
          "que nenhuma variável do modelo anuncia.")
    print(f"  - Sem essas {r['rajadas']} rajadas, o R² sobe de {m['R2']:.2f} para {limpo['R2']:.2f} "
          f"e o RMSE cai para {limpo['RMSE']:.2f} ms.")
    print("    O R² mede a fração da variação explicada; um registro isolado ainda pode errar muito.")

    caminho = salvar_grafico(df, r)
    print(f"\nGráfico salvo em {caminho.relative_to(PASTA)}")
    return r


def tela_heap(df: pd.DataFrame, quantos: int = 10) -> None:
    titulo("6. PRIORIZAÇÃO DE ALERTAS (HEAP)")
    alertas = gerar_alertas(df)
    heap = montar_heap(alertas)
    insercoes = heap.comparacoes
    print(f"{len(alertas)} alertas inseridos no heap ({insercoes} comparações).")
    print("Urgência = peso do módulo (vital 3, sustento 2, expansão 1) x gravidade "
          "(alta 2, crítica 3).")
    print("Empate: o alerta mais recente vem primeiro.\n")
    topo = heap.ver_mais_urgente()
    print(f"Topo do heap (consulta sem remover): ciclo {topo['ciclo']}, {topo['modulo']}\n")
    print(f"{'#':>3} {'urg':>3} {'ciclo':>5}  {'módulo':<28}{'origem':<8}descrição")
    for posicao in range(1, min(quantos, len(heap)) + 1):
        a = heap.remover_mais_urgente()
        print(f"{posicao:>3} {a['urgencia']:>3} {a['ciclo']:>5}  {a['modulo']:<28}"
              f"{a['origem']:<8}{a['descricao']}")
    while heap:
        heap.remover_mais_urgente()

    print("\nComparações para inserir todos os alertas e retirá-los em ordem de urgência:")
    print(f"  {'alertas':>8}{'heap':>10}{'lista simples':>16}")
    for n, feitas in ((len(alertas), heap.comparacoes),
                      (1000, comparacoes_heap_medidas(1000)),
                      (10000, comparacoes_heap_medidas(10000))):
        print(f"  {n:>8}{feitas:>10}{comparacoes_lista_simples(n):>16}")
    print("No heap, inserir ou retirar percorre no máximo a altura da árvore, que cresce")
    print("com log2(n). Na lista sem ordem, achar o mais urgente exige olhar todos os itens,")
    print("então a diferença aumenta junto com o número de alertas.")


def tela_trie(df: pd.DataFrame, prefixos: list[str] | None = None) -> None:
    titulo("7. BUSCA POR PREFIXO (TRIE)")
    trie = construir_indice(df, gerar_alertas(df))
    print(f"Índice com {trie.total_chaves} chaves: nomes de módulos, palavras dos nomes,")
    print("códigos de sensores e categorias de alerta. Acentos e maiúsculas são ignorados.")
    interativo = prefixos is None
    while True:
        if interativo:
            prefixo = input("\nPrefixo (Enter para voltar): ").strip()
            if not prefixo:
                return
        else:
            if not prefixos:
                return
            prefixo = prefixos.pop(0)
            print(f"\nPrefixo: {prefixo}")
        encontrados = trie.buscar_prefixo(prefixo)
        if not encontrados:
            print("  nada encontrado")
        for chave, referencias in encontrados:
            print(f"  {chave}")
            for ref in referencias[:4]:
                print(f"      -> {ref}")
            if len(referencias) > 4:
                print(f"      ... e mais {len(referencias) - 4}")


def tela_dispositivos(df: pd.DataFrame, codigo: str | None = None) -> None:
    titulo("8. DISPOSITIVOS, BASES NUMÉRICAS E ELETRICIDADE")
    print("Entrada: um sensor de enlace em cada módulo mede latência, tensão e corrente do")
    print("transceptor; neste protótipo o arquivo CSV faz o papel desses sensores.")
    print("Saída: terminal (este menu), gráfico PNG e relatório.")
    print("Interfaces: cabo no núcleo da base, rádio nos módulos afastados e antena de")
    print("longa distância para a Terra (apenas conceituais neste protótipo).")

    if codigo is None:
        codigo = input("\nCódigo do sensor (ex.: 0x2506) ou Enter para o da Comunicações: ").strip()
    codigo = codigo or "0x2506"
    try:
        d = decodificar_codigo(codigo)
        conferido = int(codigo, 16)  # a função pronta do Python, para comparar
    except ValueError:
        print("Código inválido: use até 4 dígitos hexadecimais, como 0x2506.")
        return
    print(f"\nCódigo {d['hexadecimal']} = {d['decimal']} em decimal = {d['binario']} em binário")
    print(f"  conferência com as funções do Python: int = {conferido}, bin = {bin(conferido)}")
    print(f"  bits 15-12 -> prioridade {d['prioridade']} | bits 11-8 -> tipo {d['tipo']} | "
          f"bits 7-0 -> módulo {d['id_modulo']}")
    dono = df.loc[df["codigo_sensor"].str.upper() == codigo.upper(), "modulo"]
    if not dono.empty:
        print(f"  sensor do módulo {dono.iloc[0]}")

    print("\nEletricidade dos transceptores (médias dos 30 ciclos):")
    print("P = V x I (potência) | R = V / I (resistência equivalente, lei de Ohm)\n")
    print(eletrica_por_modulo(df).to_string())

    solar = df[(df["modulo"] == "Energia Solar") & df["ciclo"].isin([5, 13])]
    a, b = solar.iloc[0], solar.iloc[1]
    print(f"\nEnergia Solar, ciclo 5 x ciclo 13 (tempestade): tensão {a['tensao_v']:.2f} V -> "
          f"{b['tensao_v']:.2f} V,")
    print(f"corrente {a['corrente_a']:.3f} A -> {b['corrente_a']:.3f} A, potência "
          f"{a['potencia_w']:.1f} W -> {b['potencia_w']:.1f} W.")
    print("A potência fica praticamente igual: quando a tensão cai, o transceptor puxa")
    print("mais corrente para continuar transmitindo.")
    total = eletrica_por_modulo(df)["energia_wh_por_sol"].sum()
    print(f"Consumo total dos transceptores: {total / 1000:.2f} kWh por sol.")


def tela_analise_final(df: pd.DataFrame, resultado: dict | None = None) -> None:
    titulo("9. ANÁLISE FINAL")
    resultado = resultado or treinar_modelo(df)
    a = analise_final(df, resultado, gerar_alertas(df))
    print(f"Latência média dos enlaces locais: {a['lat_media_ceu_limpo']:.2f} ms com céu limpo e "
          f"{a['lat_media_tempestade']:.2f} ms em tempestade.")
    print(f"Subtensão no ramo solar apenas nos ciclos {', '.join(map(str, a['subtensao_ciclos']))}, "
          "no pico da poeira.")
    tempestade = resultado["por_condicao"]["tempestade"]
    print(f"A regressão reduziu o erro médio de {a['mae_nominal']:.2f} ms para "
          f"{a['mae_regressao']:.2f} ms nos ciclos de teste; nas tempestades, de "
          f"{tempestade['mae_nominal']:.2f} para {tempestade['mae_regressao']:.2f} ms.")
    print(f"\n{a['total_alertas']} alertas no período. Os três primeiros da fila:")
    for alerta in a["mais_urgentes"]:
        print(f"  ciclo {alerta['ciclo']:>2} | {alerta['modulo']} | {alerta['descricao']}")
    print("\nErros preocupantes com céu limpo (a poeira não explica):")
    if a["inspecionar"].empty:
        print("  nenhum")
    else:
        print(a["inspecionar"].to_string(index=False))
        repetidos = a["inspecionar"]["modulo"].value_counts()
        repetidos = repetidos[repetidos > 1]
        if not repetidos.empty:
            print(f"Módulos que aparecem mais de uma vez: {', '.join(repetidos.index)}.")
        print(f"Com {len(a['inspecionar'])} picos distribuídos ao acaso entre 12 módulos, a chance de "
              f"algum módulo repetir é de {a['chance_repeticao']:.0%}.")
        print("Uma repetição, sozinha, ainda não separa defeito de coincidência.")
    print("\nRecomendações:")
    print("  1. Na previsão de tempestade, reservar banda para os módulos vitais: são eles")
    print("     que congestionam quando a telemetria aumenta.")
    print("  2. Durante tempestades, agendar a comunicação local pela previsão do modelo de")
    print("     regressão; com céu limpo, a latência de projeto continua suficiente.")
    print("  3. Acompanhar os transceptores listados acima; o módulo que continuar acumulando")
    print("     picos nos próximos ciclos, além do esperado pelo acaso, deve ser inspecionado.")
    print("  4. Toda decisão sugerida aqui passa pela equipe de operações antes de ser executada.")


def menu() -> None:
    df = tela_carregar()
    resultado = None
    opcoes = {
        "1": "Carregar dados", "2": "Cadastrar registro", "3": "Consultar registros",
        "4": "Indicadores e erros numéricos", "5": "Modelo de previsão e métricas",
        "6": "Priorizar alertas (heap)", "7": "Buscar por prefixo (trie)",
        "8": "Dispositivos, bases numéricas e eletricidade", "9": "Análise final",
        "0": "Sair",
    }
    while True:
        print("\nSCIC - Sistema de Comunicação Interplanetária da Colônia")
        for chave, nome in opcoes.items():
            print(f"  {chave}. {nome}")
        try:
            escolha = input("Escolha uma opção: ").strip()
        except EOFError:
            escolha = "0"
        if escolha == "0":
            print("Encerrando o SCIC.")
            break
        try:
            df, resultado = executar_opcao(escolha, df, resultado)
        except EOFError:  # entrada encerrada (Ctrl-D) no meio de uma opção
            print("\nEntrada encerrada. Encerrando o SCIC.")
            break


def executar_opcao(escolha: str, df: pd.DataFrame, resultado: dict | None):
    """Chama a tela da opção escolhida e devolve a base e o último modelo treinado."""
    if escolha == "1":
        df = tela_carregar()
    elif escolha == "2":
        df = tela_cadastrar(df)
    elif escolha == "3":
        tela_consultar(df)
    elif escolha == "4":
        tela_indicadores(df)
    elif escolha == "5":
        resultado = tela_modelo(df)
    elif escolha == "6":
        tela_heap(df)
    elif escolha == "7":
        tela_trie(df)
    elif escolha == "8":
        tela_dispositivos(df)
    elif escolha == "9":
        tela_analise_final(df, resultado)
    else:
        print("Opção inválida.")
    return df, resultado


def demonstracao() -> None:
    """Executa todas as funcionalidades com entradas de exemplo, sem perguntar nada."""
    df = tela_carregar()
    tela_consultar(df, "modulo", "Comunicações")
    tela_indicadores(df)
    resultado = tela_modelo(df)
    tela_heap(df)
    tela_trie(df, ["co", "0x1", "subt", "cien"])
    tela_dispositivos(df, "0x2506")
    tela_analise_final(df, resultado)


if __name__ == "__main__":
    # Evita erro de codificação em terminais que não suportam algum caractere.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    if "--demo" in sys.argv:
        demonstracao()
    else:
        menu()
