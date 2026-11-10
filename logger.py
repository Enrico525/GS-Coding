"""Log em arquivo: data/hora, ação e resultado de cada operação."""
import logging
import os
from logging.handlers import RotatingFileHandler

_logger = logging.getLogger("cidades_seguras")


def configurar_log(caminho):
    """Cria a pasta (se preciso) e liga o log rotativo [BÔNUS] (1 MB x 5 arquivos)."""
    if _logger.handlers:
        return _logger
    pasta = os.path.dirname(caminho)
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    handler = RotatingFileHandler(caminho, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s",
                                           datefmt="%Y-%m-%d %H:%M:%S"))
    _logger.addHandler(handler)
    _logger.setLevel(logging.INFO)
    return _logger


def _limpar(texto):
    """Evita injeção de log: remove quebras de linha e limita o tamanho."""
    return str(texto).replace("\r", " ").replace("\n", " ")[:300]


def registrar(acao, resultado, detalhe=""):
    """Ex.: 2026-11-09 22:30:01 | INFO | acao=CRIAR_BAIRRO | resultado=SUCESSO | id=3

    Nunca registre senhas, tokens ou dados pessoais aqui.
    """
    nivel = logging.INFO if resultado in ("SUCESSO", "ENVIADO") else logging.WARNING
    if resultado == "ERRO":
        nivel = logging.ERROR
    _logger.log(nivel, "acao=%s | resultado=%s | %s", _limpar(acao), _limpar(resultado), _limpar(detalhe))
