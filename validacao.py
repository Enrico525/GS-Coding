"""Validação de TODA entrada vinda do usuário (lista branca de campos e formatos)."""
import math
import re

UFS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA",
    "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}
AREAS_DE_RISCO = {"ALAGAMENTO", "DESLIZAMENTO", "CALOR", "MISTO"}
CAMPOS_BAIRRO = {"nome", "cidade", "uf", "latitude", "longitude", "area_de_risco"}

# Letras (com acento), números, espaço, ponto, apóstrofo e hífen. Nada de < > ; " etc.
_TEXTO = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ0-9 .'\-]{2,80}$")


class ErroValidacao(Exception):
    """Carrega um dicionário campo -> mensagem, seguro para devolver ao cliente."""

    def __init__(self, erros):
        super().__init__("Dados inválidos")
        self.erros = erros


def _texto(valor, campo, erros):
    if not isinstance(valor, str):
        erros[campo] = "deve ser texto"
        return None
    valor = " ".join(valor.split())  # tira espaços repetidos
    if not _TEXTO.match(valor):
        erros[campo] = "use de 2 a 80 letras, números, espaço, ponto, apóstrofo ou hífen"
        return None
    return valor


def _coordenada(valor, campo, minimo, maximo, erros):
    # bool é subclasse de int em Python: precisa ser recusado explicitamente
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        erros[campo] = "deve ser número"
        return None
    if not math.isfinite(valor) or not (minimo <= valor <= maximo):
        erros[campo] = f"deve estar entre {minimo} e {maximo}"
        return None
    return round(float(valor), 5)


def validar_bairro(dados):
    """Valida o corpo de POST/PUT. Devolve um dicionário limpo ou levanta ErroValidacao."""
    if not isinstance(dados, dict):
        raise ErroValidacao({"corpo": "envie um objeto JSON"})

    erros = {}
    extras = set(dados) - CAMPOS_BAIRRO
    if extras:
        # coleta mínima: campo que não usamos não entra (nem dado pessoal "sem querer")
        erros["campos_nao_permitidos"] = sorted(extras)[:10]
    faltando = CAMPOS_BAIRRO - {"area_de_risco"} - set(dados)
    for campo in sorted(faltando):
        erros[campo] = "obrigatório"
    if erros:
        raise ErroValidacao(erros)

    limpo = {
        "nome": _texto(dados["nome"], "nome", erros),
        "cidade": _texto(dados["cidade"], "cidade", erros),
        "latitude": _coordenada(dados["latitude"], "latitude", -90, 90, erros),
        "longitude": _coordenada(dados["longitude"], "longitude", -180, 180, erros),
    }

    uf = dados["uf"]
    if not isinstance(uf, str) or uf.strip().upper() not in UFS:
        erros["uf"] = "sigla de estado inválida"
    else:
        limpo["uf"] = uf.strip().upper()

    area = dados.get("area_de_risco", "MISTO")
    if not isinstance(area, str) or area.strip().upper() not in AREAS_DE_RISCO:
        erros["area_de_risco"] = "use " + ", ".join(sorted(AREAS_DE_RISCO))
    else:
        limpo["area_de_risco"] = area.strip().upper()

    if erros:
        raise ErroValidacao(erros)
    return limpo


def validar_id(valor):
    """IDs devem ser inteiros positivos e de tamanho razoável."""
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        raise ErroValidacao({"id": "deve ser inteiro"})
    if not (1 <= numero <= 2_147_483_647):
        raise ErroValidacao({"id": "fora do intervalo permitido"})
    return numero
