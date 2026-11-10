"""Servidor TCP que distribui os alertas aos "receptores" da comunidade.

Cenário: um computador na associação de moradores, escola ou UBS roda o
cliente_receptor.py inscrito no seu bairro e recebe os alertas em tempo real,
mesmo sem ninguém abrir o site.

Protocolo (texto, uma linha por mensagem, UTF-8):
    cliente -> servidor :  INSCREVER <bairro_id>\n      |  SAIR\n
    servidor -> cliente :  OK INSCRITO <bairro_id>\n    |  ERRO <motivo>\n
                           ALERTA {json}\n
"""
import json
import re
import socket
import threading

from logger import registrar

_COMANDO = re.compile(r"^INSCREVER ([1-9]\d{0,8})$")
TAM_MAX_LINHA = 64          # bytes: comandos são curtos; evita abuso de memória
TEMPO_INSCRICAO = 15        # segundos para o cliente mandar o comando
MAX_CLIENTES = 100


class ServidorAlertas(threading.Thread):
    def __init__(self, host, porta):
        super().__init__(daemon=True, name="servidor-alertas")
        self.host, self.porta = host, porta
        self._inscritos = {}            # socket -> bairro_id
        self._trava = threading.Lock()
        self._sock = None
        self.pronto = threading.Event()

    # ----------------------------------------------------------- ciclo de vida
    def run(self):
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.bind((self.host, self.porta))
            self._sock.listen()
            self.porta = self._sock.getsockname()[1]  # útil quando porta=0 (testes)
            registrar("SOCKET_INICIAR", "SUCESSO", f"{self.host}:{self.porta}")
        except OSError as e:
            registrar("SOCKET_INICIAR", "ERRO", f"errno={e.errno}")
            self.pronto.set()
            return
        self.pronto.set()
        while True:
            try:
                cliente, endereco = self._sock.accept()
            except OSError:
                break  # socket fechado em parar()
            with self._trava:
                lotado = len(self._inscritos) >= MAX_CLIENTES
            if lotado:
                self._enviar(cliente, "ERRO servidor lotado")
                cliente.close()
                continue
            threading.Thread(target=self._atender, args=(cliente, endereco), daemon=True).start()

    def parar(self):
        if self._sock:
            self._sock.close()
        with self._trava:
            for c in list(self._inscritos):
                c.close()
            self._inscritos.clear()

    # ---------------------------------------------------------------- clientes
    @staticmethod
    def _enviar(cliente, texto):
        try:
            cliente.sendall((texto + "\n").encode("utf-8"))
            return True
        except OSError:
            return False

    @staticmethod
    def _ler_linha(cliente):
        """Lê até \\n respeitando o limite de tamanho. None = conexão encerrada/abuso."""
        buffer = b""
        while b"\n" not in buffer:
            pedaco = cliente.recv(TAM_MAX_LINHA)
            if not pedaco:
                return None
            buffer += pedaco
            if len(buffer) > TAM_MAX_LINHA:
                return None
        return buffer.split(b"\n", 1)[0].decode("utf-8", errors="replace").strip()

    def _atender(self, cliente, endereco):
        ip = endereco[0]
        try:
            cliente.settimeout(TEMPO_INSCRICAO)
            linha = self._ler_linha(cliente)
            casou = _COMANDO.match(linha or "")
            if not casou:
                self._enviar(cliente, "ERRO comando invalido. Use: INSCREVER <id>")
                registrar("SOCKET_INSCRICAO", "NEGADO", f"ip={ip}")
                cliente.close()
                return
            bairro_id = int(casou.group(1))
            with self._trava:
                self._inscritos[cliente] = bairro_id
            self._enviar(cliente, f"OK INSCRITO {bairro_id}")
            registrar("SOCKET_INSCRICAO", "SUCESSO", f"ip={ip} bairro={bairro_id}")

            cliente.settimeout(None)  # agora só esperamos SAIR ou desconexão
            while True:
                linha = self._ler_linha(cliente)
                if linha is None or linha == "SAIR":
                    break
        except (OSError, socket.timeout):
            pass
        finally:
            with self._trava:
                self._inscritos.pop(cliente, None)
            try:
                cliente.close()
            except OSError:
                pass

    # -------------------------------------------------------------- publicação
    def publicar(self, bairro_id, alerta):
        """Envia o alerta a todos os inscritos no bairro. Devolve quantos receberam."""
        mensagem = "ALERTA " + json.dumps(alerta, ensure_ascii=False)
        with self._trava:
            destinos = [c for c, b in self._inscritos.items() if b == bairro_id]
        entregues = 0
        for cliente in destinos:
            if self._enviar(cliente, mensagem):
                entregues += 1
            else:
                with self._trava:
                    self._inscritos.pop(cliente, None)
        return entregues

    def total_inscritos(self):
        with self._trava:
            return len(self._inscritos)
