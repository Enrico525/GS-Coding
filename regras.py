"""Regras que transformam a previsão em alertas para a população.

Limiares inspirados nas faixas de aviso de chuva acumulada e onda de calor usadas
por órgãos meteorológicos (ex.: INMET). São parâmetros do protótipo e podem ser
calibrados por bairro com a Defesa Civil.
"""

# (limite mínimo, nível) — do mais grave para o mais leve
LIMIARES = {
    "CHUVA_FORTE": [(100.0, "EMERGENCIA"), (50.0, "ALERTA"), (30.0, "ATENCAO")],   # mm/dia
    "CALOR_EXTREMO": [(38.0, "EMERGENCIA"), (35.0, "ALERTA"), (32.0, "ATENCAO")],  # °C máx.
}

ORIENTACOES = {
    "CHUVA_FORTE": "Evite áreas alagáveis e encostas; não atravesse ruas inundadas. Emergência: Defesa Civil 199.",
    "CALOR_EXTREMO": "Beba água, evite sol entre 10h e 16h e cuide de idosos e crianças. Emergência: SAMU 192.",
}

_CAMPO = {"CHUVA_FORTE": "chuva_mm", "CALOR_EXTREMO": "temp_max"}
_UNIDADE = {"CHUVA_FORTE": "mm", "CALOR_EXTREMO": "°C"}


def classificar(tipo, valor):
    """Devolve o nível para o valor previsto, ou None se não houver risco."""
    if valor is None:
        return None
    for limite, nivel in LIMIARES[tipo]:
        if valor >= limite:
            return nivel
    return None


def avaliar_previsao(previsao):
    """Recebe a lista de dias da previsão e devolve a lista de alertas a emitir."""
    alertas = []
    for dia in previsao:
        for tipo, campo in _CAMPO.items():
            valor = dia.get(campo)
            nivel = classificar(tipo, valor)
            if nivel:
                texto = (f"{nivel} - {tipo.replace('_', ' ').title()} previsto(a) para "
                         f"{dia['data']}: {valor:.1f} {_UNIDADE[tipo]}. {ORIENTACOES[tipo]}")
                alertas.append({
                    "tipo": tipo, "nivel": nivel, "valor": round(valor, 1),
                    "data": dia["data"], "mensagem": texto[:255],
                })
    return alertas
