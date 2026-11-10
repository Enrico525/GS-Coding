"""Receptor de alertas (cliente TCP) para rodar na associação de moradores, escola, UBS...

Uso:  python cliente_receptor.py --bairro 1
"""
import argparse
import json
import socket
import sys

import config

CORES = {"ATENCAO": "\033[93m", "ALERTA": "\033[38;5;208m", "EMERGENCIA": "\033[91m"}
FIM = "\033[0m"


def exibir(linha):
    if linha.startswith("ALERTA "):
        try:
            alerta = json.loads(linha[7:])
        except json.JSONDecodeError:
            print("[aviso] mensagem de alerta mal formada ignorada")
            return
        cor = CORES.get(alerta.get("nivel"), "")
        print(f"\a{cor}*** {alerta.get('bairro', '')} | {alerta.get('mensagem', '')}{FIM}")
    else:
        print(f"[servidor] {linha}")


def main():
    parser = argparse.ArgumentParser(description="Receptor de alertas do projeto Cidades Seguras")
    parser.add_argument("--bairro", type=int, required=True, help="id do bairro a acompanhar")
    parser.add_argument("--host", default=config.SOCKET_HOST)
    parser.add_argument("--porta", type=int, default=config.SOCKET_PORT)
    args = parser.parse_args()

    if args.bairro < 1:
        sys.exit("O id do bairro deve ser positivo.")

    try:
        with socket.create_connection((args.host, args.porta), timeout=10) as sock:
            sock.sendall(f"INSCREVER {args.bairro}\n".encode("utf-8"))
            sock.settimeout(None)
            print(f"Conectado a {args.host}:{args.porta}. Aguardando alertas (Ctrl+C para sair)...")
            buffer = ""
            while True:
                dados = sock.recv(4096)
                if not dados:
                    print("Conexão encerrada pelo servidor.")
                    break
                buffer += dados.decode("utf-8", errors="replace")
                while "\n" in buffer:
                    linha, buffer = buffer.split("\n", 1)
                    exibir(linha.strip())
    except KeyboardInterrupt:
        print("\nEncerrado.")
    except OSError:
        sys.exit("Não foi possível conectar ao servidor de alertas. Ele está rodando?")


if __name__ == "__main__":
    main()
