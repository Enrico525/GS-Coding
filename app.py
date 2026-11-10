"""AlertaBairro - API REST (Flask) de alertas de chuva forte e calor extremo por bairro.

Rotas:
    GET    /api/bairros                 lista bairros monitorados            200
    GET    /api/bairros/<id>            detalhe                              200 | 404
    POST   /api/bairros                 cadastra                             201 | 400 | 409 | 415
    PUT    /api/bairros/<id>            atualiza (objeto completo)           200 | 400 | 404 | 409 | 415
    DELETE /api/bairros/<id>            remove (e seus alertas)              204 | 404
    POST   /api/bairros/<id>/verificar  consulta Open-Meteo e emite alertas  200 | 404 | 429 | 502
    GET    /api/alertas[?bairro_id=N]   histórico de alertas                 200 | 400
"""
import threading
import time

from flask import Flask, jsonify, render_template, request, url_for
from werkzeug.exceptions import HTTPException

import clima
import config
import db
import regras
from logger import configurar_log, registrar
from socket_servidor import ServidorAlertas
from validacao import ErroValidacao, validar_bairro, validar_id


def _erro(status, mensagem, **extra):
    """Resposta de erro padronizada e SEM detalhes internos (stack, SQL, caminhos)."""
    corpo = {"erro": mensagem}
    corpo.update(extra)
    return jsonify(corpo), status


def _json_do_corpo():
    if not request.is_json:
        return None, _erro(415, "Envie o corpo como application/json")
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        return None, _erro(400, "JSON inválido: envie um objeto")
    return dados, None


class Cooldown:
    """[BÔNUS] Limita verificações repetidas do mesmo bairro (protege a API externa de abuso)."""

    def __init__(self, segundos):
        self.segundos = segundos
        self._ultimo = {}
        self._trava = threading.Lock()

    def liberar(self, chave):
        """Devolve 0 se pode verificar agora, ou quantos segundos faltam."""
        agora = time.monotonic()
        with self._trava:
            restante = self.segundos - (agora - self._ultimo.get(chave, -1e9))
            if restante > 0:
                return int(restante) + 1
            self._ultimo[chave] = agora
            return 0


def criar_app(servidor_alertas=None):
    configurar_log(config.LOG_FILE)
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024   # 16 KB: corpo maior -> 413
    app.json.ensure_ascii = False
    app.json.sort_keys = False
    cooldown = Cooldown(config.COOLDOWN_VERIFICACAO)

    # ------------------------------------------- [BÔNUS] cabeçalhos de segurança
    @app.after_request
    def cabecalhos_seguranca(resposta):
        resposta.headers["X-Content-Type-Options"] = "nosniff"   # sem "adivinhar" tipo de arquivo
        resposta.headers["X-Frame-Options"] = "DENY"             # contra clickjacking
        resposta.headers["Referrer-Policy"] = "no-referrer"
        resposta.headers["Content-Security-Policy"] = (          # só scripts/estilos do próprio site
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; object-src 'none'; frame-ancestors 'none'"
        )
        return resposta

    # ------------------------------------------------- tratamento de erros
    @app.errorhandler(HTTPException)
    def erro_http(e):
        mensagens = {404: "Recurso não encontrado", 405: "Método não permitido",
                     413: "Corpo da requisição muito grande", 400: "Requisição inválida"}
        return _erro(e.code, mensagens.get(e.code, "Erro na requisição"))

    @app.errorhandler(ErroValidacao)
    def erro_validacao(e):
        registrar(f"{request.method} {request.path}", "INVALIDO", str(list(e.erros))[:120])
        return _erro(400, "Dados inválidos", detalhes=e.erros)

    @app.errorhandler(db.ErroBanco)
    def erro_banco(e):
        registrar(f"{request.method} {request.path}", "ERRO", f"banco: {e}")
        return _erro(503, "Serviço temporariamente indisponível")

    @app.errorhandler(Exception)
    def erro_inesperado(e):
        registrar(f"{request.method} {request.path}", "ERRO", type(e).__name__)
        return _erro(500, "Erro interno")

    # ----------------------------------------------------------------- web
    @app.get("/")
    def inicio():
        return render_template("index.html")

    # ------------------------------------------------------------- bairros
    @app.get("/api/bairros")
    def listar():
        bairros = db.listar_bairros()
        registrar("LISTAR_BAIRROS", "SUCESSO", f"total={len(bairros)}")
        return jsonify(bairros), 200

    @app.get("/api/bairros/<int:bairro_id>")
    def detalhar(bairro_id):
        bairro = db.buscar_bairro(validar_id(bairro_id))
        if not bairro:
            registrar("BUSCAR_BAIRRO", "NAO_ENCONTRADO", f"id={bairro_id}")
            return _erro(404, "Bairro não encontrado")
        return jsonify(bairro), 200

    @app.post("/api/bairros")
    def criar():
        dados, falha = _json_do_corpo()
        if falha:
            return falha
        limpo = validar_bairro(dados)
        try:
            novo_id = db.inserir_bairro(limpo)
        except db.RegistroDuplicado:
            registrar("CRIAR_BAIRRO", "CONFLITO", f"{limpo['nome']}/{limpo['cidade']}")
            return _erro(409, "Este bairro já está cadastrado nessa cidade/UF")
        registrar("CRIAR_BAIRRO", "SUCESSO", f"id={novo_id}")
        resposta = jsonify(db.buscar_bairro(novo_id))
        resposta.status_code = 201
        resposta.headers["Location"] = url_for("detalhar", bairro_id=novo_id)
        return resposta

    @app.put("/api/bairros/<int:bairro_id>")
    def atualizar(bairro_id):
        bairro_id = validar_id(bairro_id)
        dados, falha = _json_do_corpo()
        if falha:
            return falha
        limpo = validar_bairro(dados)
        if not db.buscar_bairro(bairro_id):
            registrar("ATUALIZAR_BAIRRO", "NAO_ENCONTRADO", f"id={bairro_id}")
            return _erro(404, "Bairro não encontrado")
        try:
            db.atualizar_bairro(bairro_id, limpo)
        except db.RegistroDuplicado:
            registrar("ATUALIZAR_BAIRRO", "CONFLITO", f"id={bairro_id}")
            return _erro(409, "Já existe outro bairro com esse nome nessa cidade/UF")
        registrar("ATUALIZAR_BAIRRO", "SUCESSO", f"id={bairro_id}")
        return jsonify(db.buscar_bairro(bairro_id)), 200

    @app.delete("/api/bairros/<int:bairro_id>")
    def excluir(bairro_id):
        bairro_id = validar_id(bairro_id)
        if not db.excluir_bairro(bairro_id):
            registrar("EXCLUIR_BAIRRO", "NAO_ENCONTRADO", f"id={bairro_id}")
            return _erro(404, "Bairro não encontrado")
        registrar("EXCLUIR_BAIRRO", "SUCESSO", f"id={bairro_id}")
        return "", 204

    # --------------------------------------------- verificação de clima/alertas
    @app.post("/api/bairros/<int:bairro_id>/verificar")
    def verificar(bairro_id):
        bairro_id = validar_id(bairro_id)
        bairro = db.buscar_bairro(bairro_id)
        if not bairro:
            return _erro(404, "Bairro não encontrado")

        espera = cooldown.liberar(bairro_id)
        if espera:
            registrar("VERIFICAR_CLIMA", "LIMITADO", f"id={bairro_id}")
            resposta, status = _erro(429, f"Aguarde {espera}s para verificar este bairro de novo")
            resposta.headers["Retry-After"] = str(espera)
            return resposta, status

        try:
            previsao = clima.obter_previsao(bairro["latitude"], bairro["longitude"])
        except clima.ErroServicoExterno as e:
            registrar("VERIFICAR_CLIMA", "ERRO", f"id={bairro_id} open-meteo: {e}")
            return _erro(502, "Serviço de previsão do tempo indisponível. Tente mais tarde.")

        alertas = regras.avaliar_previsao(previsao)
        entregues = 0
        for alerta in alertas:
            db.salvar_alerta(bairro_id, alerta)
            if servidor_alertas:
                entregues += servidor_alertas.publicar(
                    bairro_id, {**alerta, "bairro": f"{bairro['nome']} - {bairro['cidade']}/{bairro['uf']}"})
        registrar("VERIFICAR_CLIMA", "SUCESSO",
                  f"id={bairro_id} alertas={len(alertas)} entregues_socket={entregues}")
        return jsonify({"bairro": bairro, "previsao": previsao, "alertas": alertas,
                        "receptores_notificados": entregues}), 200

    @app.get("/api/alertas")
    def historico():
        filtro = request.args.get("bairro_id")
        bairro_id = validar_id(filtro) if filtro is not None else None
        alertas = db.listar_alertas(bairro_id)
        registrar("LISTAR_ALERTAS", "SUCESSO", f"total={len(alertas)}")
        return jsonify(alertas), 200

    return app


if __name__ == "__main__":
    config.validar_configuracao()
    servidor = ServidorAlertas(config.SOCKET_HOST, config.SOCKET_PORT)
    servidor.start()
    servidor.pronto.wait(5)
    aplicacao = criar_app(servidor)
    print(f"Web/API: http://{config.FLASK_HOST}:{config.FLASK_PORT}  |  "
          f"Socket de alertas: {config.SOCKET_HOST}:{servidor.porta}")
    # debug=False: o modo debug do Flask expõe um console que executa código.
    aplicacao.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=False)
