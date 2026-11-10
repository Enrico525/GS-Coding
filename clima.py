"""Fonte externa: previsão do tempo da Open-Meteo (https://open-meteo.com), via requests + JSON.

A resposta externa também é tratada como NÃO confiável: validamos estrutura e tipos.
"""
import math

import requests

import config


class ErroServicoExterno(Exception):
    """A API de clima falhou, demorou ou respondeu algo inesperado."""


def _numero(valor):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor):
        return None
    return float(valor)


def obter_previsao(latitude, longitude, dias=3):
    """Devolve [{data, chuva_mm, temp_max, prob_chuva}, ...] para os próximos `dias`."""
    parametros = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": "precipitation_sum,temperature_2m_max,precipitation_probability_max",
        "timezone": "America/Sao_Paulo",
        "forecast_days": dias,
    }
    try:
        resposta = requests.get(config.OPEN_METEO_URL, params=parametros, timeout=10)
        resposta.raise_for_status()
        dados = resposta.json()
    except requests.Timeout as e:
        raise ErroServicoExterno("tempo esgotado") from e
    except requests.RequestException as e:
        raise ErroServicoExterno("falha de rede/HTTP") from e
    except ValueError as e:  # JSON inválido
        raise ErroServicoExterno("resposta não é JSON") from e

    diario = dados.get("daily") if isinstance(dados, dict) else None
    if not isinstance(diario, dict):
        raise ErroServicoExterno("formato inesperado")

    datas = diario.get("time")
    chuvas = diario.get("precipitation_sum")
    temps = diario.get("temperature_2m_max")
    probs = diario.get("precipitation_probability_max") or [None] * len(datas or [])
    if not all(isinstance(x, list) for x in (datas, chuvas, temps, probs)):
        raise ErroServicoExterno("formato inesperado")
    if not (len(datas) == len(chuvas) == len(temps) == len(probs)):
        raise ErroServicoExterno("listas com tamanhos diferentes")

    previsao = []
    for data, chuva, temp, prob in zip(datas, chuvas, temps, probs):
        if not isinstance(data, str) or len(data) != 10:
            continue
        previsao.append({
            "data": data,
            "chuva_mm": _numero(chuva),
            "temp_max": _numero(temp),
            "prob_chuva": _numero(prob),
        })
    if not previsao:
        raise ErroServicoExterno("previsão vazia")
    return previsao
