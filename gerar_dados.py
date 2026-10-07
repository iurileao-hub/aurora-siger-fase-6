"""Gera a base simulada dados_aurora_siger.csv usada pelo SCIC.

A base registra, para cada um dos 13 módulos da colônia e para cada um de 30
ciclos (sóis marcianos), a leitura do sensor de enlace de comunicação do módulo.

Não é preciso rodar este script para usar o sistema: o CSV já acompanha a
entrega. Ele existe para mostrar de onde os dados vieram e para permitir
regerar exatamente a mesma base (a semente aleatória é fixa).

Uso:
    python gerar_dados.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

SEMENTE = 2026
NUM_CICLOS = 30
ARQUIVO_SAIDA = Path(__file__).with_name("dados_aurora_siger.csv")

VELOCIDADE_LUZ_KM_S = 299_792.458
DISTANCIA_INICIAL_KM = 228.0e6       # distância Terra-Marte no ciclo 1
AFASTAMENTO_POR_CICLO_KM = 0.55e6    # os planetas se afastam a cada sol
PROCESSAMENTO_TERRA_MS = 1500.0      # atraso fixo das estações de retransmissão
TENSAO_NOMINAL_V = 28.0              # barramento de corrente contínua da colônia

# Os 13 módulos são os mesmos das fases anteriores do projeto.
# prioridade: 1 = vital, 2 = sustento, 3 = expansão
# latencia_base_ms: latência prevista no projeto do enlace até o hub de comunicação
# potencia_tx_w: potência elétrica do transceptor do módulo
# sem_fio: True se o enlace é por rádio (sofre com a poeira); False se é cabeado
# ramo_solar: True se o módulo está no ramo do barramento alimentado pelos painéis
MODULOS = [
    # id, nome, tipo, prioridade, latencia_base_ms, potencia_tx_w, carga_media, sem_fio, ramo_solar
    (1, "Centro de Controle", "controle", 1, 1.5, 22.0, 55, False, False),
    (2, "Suporte de Vida", "suporte de vida", 1, 2.0, 18.0, 45, False, False),
    (3, "Habitação", "habitação", 1, 2.5, 14.0, 40, False, False),
    (4, "Energia Solar", "energia", 2, 9.0, 12.0, 25, True, True),
    (5, "Energia Nuclear", "energia", 2, 7.0, 12.0, 25, True, False),
    (6, "Comunicações", "comunicação", 2, 0.0, 100.0, 60, True, False),
    (7, "Suporte Médico", "suporte médico", 1, 3.0, 16.0, 35, False, False),
    (8, "Produção de Alimentos", "agricultura", 2, 5.5, 10.0, 30, False, True),
    (9, "Logística e Armazenamento", "armazenamento", 3, 6.0, 10.0, 30, False, False),
    (10, "Extração de Recursos (ISRU)", "extração de recursos", 2, 11.0, 14.0, 35, True, False),
    (11, "Oficina e Manutenção", "manutenção", 3, 8.0, 10.0, 20, True, True),
    (12, "Laboratório Científico", "laboratório", 3, 4.5, 20.0, 50, False, True),
    (13, "Energia Eólica", "energia", 2, 12.0, 12.0, 20, True, False),
]

# Código numérico de cada tipo, usado para montar o código hexadecimal do sensor.
CODIGO_TIPO = {
    "controle": 1, "suporte de vida": 2, "habitação": 3, "energia": 4,
    "comunicação": 5, "suporte médico": 6, "agricultura": 7, "armazenamento": 8,
    "extração de recursos": 9, "manutenção": 10, "laboratório": 11,
}

# Eventos registrados à mão pela equipe de operações: (id do módulo, ciclo) -> evento
MANUTENCOES = {(11, 8), (12, 19), (13, 23)}
FALHAS_SENSOR = {(10, 14), (13, 15)}


def codigo_sensor(prioridade: int, tipo: str, id_modulo: int) -> str:
    """Monta o código de 16 bits: 4 bits de prioridade, 4 de tipo e 8 de id."""
    valor = (prioridade << 12) | (CODIGO_TIPO[tipo] << 8) | id_modulo
    return f"0x{valor:04X}"


def opacidade_atmosferica(ciclo: int, rng: np.random.Generator) -> float:
    """Opacidade (tau) da atmosfera: céu limpo perto de 0,5 e duas tempestades de poeira."""
    tau = 0.5 + rng.normal(0, 0.05)
    if 11 <= ciclo <= 16:                       # tempestade forte
        tau += 2.3 * (1 - abs(ciclo - 13.5) / 3.0)
    if 25 <= ciclo <= 28:                       # tempestade moderada
        tau += 1.4 * (1 - abs(ciclo - 26.5) / 2.0)
    return round(max(tau, 0.3), 2)


def gerar_base() -> pd.DataFrame:
    rng = np.random.default_rng(SEMENTE)
    linhas = []

    for ciclo in range(1, NUM_CICLOS + 1):
        tau = opacidade_atmosferica(ciclo, rng)
        em_tempestade = tau > 1.0

        for (id_mod, nome, tipo, prioridade, base_ms, potencia_w,
             carga_media, sem_fio, ramo_solar) in MODULOS:

            # Carga da rede: módulos vitais mandam mais telemetria durante tempestades.
            carga = carga_media + rng.normal(0, 6)
            if em_tempestade and prioridade == 1:
                carga += 25
            if nome == "Comunicações" and em_tempestade:
                carga += 20
            carga = float(np.clip(carga, 5, 98))

            # Tensão: o ramo solar perde tensão quando a poeira tapa os painéis.
            tensao = TENSAO_NOMINAL_V + rng.normal(0, 0.15)
            if ramo_solar:
                tensao -= 1.05 * max(tau - 0.5, 0)
            # O transceptor consome potência constante: tensão menor puxa corrente maior.
            corrente = potencia_w / tensao + rng.normal(0, 0.02)

            if nome == "Comunicações":
                # Enlace com a Terra: o atraso é dominado pelo tempo de viagem da luz.
                enlace = "Terra"
                distancia = DISTANCIA_INICIAL_KM + AFASTAMENTO_POR_CICLO_KM * (ciclo - 1)
                prevista = distancia / VELOCIDADE_LUZ_KM_S * 1000 + PROCESSAMENTO_TERRA_MS
                # A previsão vale para carga média e céu limpo; o desvio vem do que muda.
                observada = (prevista + 40 * (carga - carga_media) + 1200 * (tau - 0.5)
                             + rng.normal(0, 300))
            else:
                # Enlace local até o hub: atraso pequeno, sensível a carga e poeira.
                enlace = "local"
                prevista = base_ms
                fator_poeira = 1.0 if sem_fio else 0.3
                congestionamento = 0.6 * max(carga - 80, 0)   # a fila cresce rápido acima de 80%
                # A latência de projeto foi medida com carga média e céu limpo (tau = 0,5).
                observada = (prevista + 0.04 * (carga - carga_media)
                             + 2.2 * (tau - 0.5) * fator_poeira
                             + congestionamento + rng.normal(0, 0.1 + 0.05 * prevista))
                if rng.random() < 0.03:                         # rajada de retransmissões
                    observada += rng.uniform(8, 20)
                observada = max(observada, 0.3 * prevista)

            status, mensagem = "ativo", ""
            if (id_mod, ciclo) in MANUTENCOES:
                status, mensagem = "manutenção", "manutenção programada do transceptor"
                observada = np.nan
            elif (id_mod, ciclo) in FALHAS_SENSOR:
                status, mensagem = "alerta", "sensor de enlace sem resposta"
                observada = np.nan
            elif tensao < 26.5:
                status, mensagem = "alerta", f"subtensão no barramento ({tensao:.1f} V)"

            linhas.append({
                "ciclo": ciclo,
                "modulo": nome,
                "tipo": tipo,
                "prioridade": prioridade,
                "codigo_sensor": codigo_sensor(prioridade, tipo, id_mod),
                "enlace": enlace,
                "carga_rede_pct": round(carga, 1),
                "opacidade_tau": tau,
                "tensao_v": round(tensao, 2),
                "corrente_a": round(corrente, 3),
                "latencia_prevista_ms": round(prevista, 3),
                "latencia_observada_ms": round(observada, 3),
                "status": status,
                "mensagem": mensagem,
            })

    return pd.DataFrame(linhas)


if __name__ == "__main__":
    base = gerar_base()
    base.to_csv(ARQUIVO_SAIDA, index=False, encoding="utf-8")
    print(f"{len(base)} registros gravados em {ARQUIVO_SAIDA.name}")
