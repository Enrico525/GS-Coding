"""Configuração lida do arquivo .env (credenciais nunca ficam no código)."""
import os

from dotenv import load_dotenv

load_dotenv()


def _int(nome, padrao):
    try:
        return int(os.getenv(nome, padrao))
    except ValueError:
        raise RuntimeError(f"Variável {nome} deve ser um número inteiro")


DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = _int("DB_PORT", 3306)
DB_USER = os.getenv("DB_USER", "")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "cidades_seguras")

FLASK_HOST = os.getenv("FLASK_HOST", "127.0.0.1")
FLASK_PORT = _int("FLASK_PORT", 5000)

SOCKET_HOST = os.getenv("SOCKET_HOST", "127.0.0.1")
SOCKET_PORT = _int("SOCKET_PORT", 5050)

LOG_FILE = os.getenv("LOG_FILE", "logs/cidades_seguras.log")
OPEN_METEO_URL = os.getenv("OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast")
COOLDOWN_VERIFICACAO = _int("COOLDOWN_VERIFICACAO", 30)


def validar_configuracao():
    """Falha cedo (e sem expor valores) se faltar credencial obrigatória."""
    faltando = [n for n in ("DB_USER", "DB_PASSWORD") if not os.getenv(n)]
    if faltando:
        raise RuntimeError(
            "Configuração incompleta: defina " + ", ".join(faltando) + " no arquivo .env"
        )
