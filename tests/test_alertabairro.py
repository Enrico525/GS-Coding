"""[BÔNUS] Testes automatizados (unittest, sem dependências extras).

Rodam SEM MySQL e SEM internet: o banco e a Open-Meteo são simulados (mock),
assim testamos as regras, a validação, os códigos HTTP e o socket isoladamente.

Execute na raiz do projeto:  python -m unittest -v
"""
import os
import socket
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["LOG_FILE"] = os.path.join(tempfile.mkdtemp(), "teste.log")
os.environ["COOLDOWN_VERIFICACAO"] = "30"

import app as modulo_app  # noqa: E402
import clima  # noqa: E402
import db  # noqa: E402
import regras  # noqa: E402
from socket_servidor import ServidorAlertas  # noqa: E402
from validacao import ErroValidacao, validar_bairro  # noqa: E402

BAIRRO_OK = {"nome": "Jardim Pantanal", "cidade": "São Paulo", "uf": "sp",
             "latitude": -23.496, "longitude": -46.429, "area_de_risco": "alagamento"}


class BancoFalso:
    """Substitui o db.py por um dicionário em memória."""

    def __init__(self):
        self.bairros, self.alertas, self.prox = {}, [], 1

    def listar_bairros(self):
        return list(self.bairros.values())

    def buscar_bairro(self, i):
        return self.bairros.get(i)

    def inserir_bairro(self, d):
        if any((b["nome"], b["cidade"], b["uf"]) == (d["nome"], d["cidade"], d["uf"])
               for b in self.bairros.values()):
            raise db.RegistroDuplicado()
        i, self.prox = self.prox, self.prox + 1
        self.bairros[i] = {"id": i, **d}
        return i

    def atualizar_bairro(self, i, d):
        self.bairros[i] = {"id": i, **d}

    def excluir_bairro(self, i):
        return self.bairros.pop(i, None) is not None

    def salvar_alerta(self, i, a):
        self.alertas.append((i, a))

    def listar_alertas(self, bairro_id=None, limite=50):
        return [a for i, a in self.alertas if bairro_id in (None, i)]


class TestValidacao(unittest.TestCase):
    def test_normaliza_dados_validos(self):
        limpo = validar_bairro(BAIRRO_OK)
        self.assertEqual(limpo["uf"], "SP")
        self.assertEqual(limpo["area_de_risco"], "ALAGAMENTO")

    def test_recusa_injecao_e_html(self):
        for nome in ["x' OR '1'='1'; --", "<script>alert(1)</script>", "a"]:
            with self.assertRaises(ErroValidacao):
                validar_bairro({**BAIRRO_OK, "nome": nome})

    def test_recusa_coordenadas_invalidas(self):
        for lat in [91, -91, True, "10", float("nan")]:
            with self.assertRaises(ErroValidacao):
                validar_bairro({**BAIRRO_OK, "latitude": lat})

    def test_recusa_campo_extra_coleta_minima(self):
        with self.assertRaises(ErroValidacao) as ctx:
            validar_bairro({**BAIRRO_OK, "cpf_morador": "000"})
        self.assertIn("campos_nao_permitidos", ctx.exception.erros)


class TestRegras(unittest.TestCase):
    def test_niveis(self):
        self.assertIsNone(regras.classificar("CHUVA_FORTE", 10))
        self.assertEqual(regras.classificar("CHUVA_FORTE", 30), "ATENCAO")
        self.assertEqual(regras.classificar("CHUVA_FORTE", 75), "ALERTA")
        self.assertEqual(regras.classificar("CALOR_EXTREMO", 39), "EMERGENCIA")
        self.assertIsNone(regras.classificar("CALOR_EXTREMO", None))

    def test_avaliar_previsao(self):
        prev = [{"data": "2026-11-10", "chuva_mm": 120.0, "temp_max": 25.0, "prob_chuva": 90},
                {"data": "2026-11-11", "chuva_mm": 0.0, "temp_max": 36.0, "prob_chuva": 5}]
        alertas = regras.avaliar_previsao(prev)
        self.assertEqual([(a["tipo"], a["nivel"]) for a in alertas],
                         [("CHUVA_FORTE", "EMERGENCIA"), ("CALOR_EXTREMO", "ALERTA")])
        self.assertTrue(all(len(a["mensagem"]) <= 255 for a in alertas))


class TestClima(unittest.TestCase):
    def _resposta(self, json_):
        r = mock.Mock()
        r.raise_for_status.return_value = None
        r.json.return_value = json_
        return r

    def test_converte_resposta(self):
        json_ = {"daily": {"time": ["2026-11-10"], "precipitation_sum": [42.5],
                           "temperature_2m_max": [31.0], "precipitation_probability_max": [80]}}
        with mock.patch("clima.requests.get", return_value=self._resposta(json_)):
            prev = clima.obter_previsao(-23.5, -46.4)
        self.assertEqual(prev[0]["chuva_mm"], 42.5)

    def test_resposta_estranha_vira_erro_controlado(self):
        with mock.patch("clima.requests.get", return_value=self._resposta({"daily": "lixo"})):
            with self.assertRaises(clima.ErroServicoExterno):
                clima.obter_previsao(0, 0)

    def test_timeout(self):
        with mock.patch("clima.requests.get", side_effect=clima.requests.Timeout):
            with self.assertRaises(clima.ErroServicoExterno):
                clima.obter_previsao(0, 0)


class TestAPI(unittest.TestCase):
    def setUp(self):
        self.banco = BancoFalso()
        self.patches = [mock.patch.object(db, nome, getattr(self.banco, nome)) for nome in
                        ("listar_bairros", "buscar_bairro", "inserir_bairro",
                         "atualizar_bairro", "excluir_bairro", "salvar_alerta", "listar_alertas")]
        for p in self.patches:
            p.start()
        self.cliente = modulo_app.criar_app().test_client()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_crud_completo_e_status(self):
        r = self.cliente.post("/api/bairros", json=BAIRRO_OK)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.headers["Location"], "/api/bairros/1")
        self.assertEqual(self.cliente.post("/api/bairros", json=BAIRRO_OK).status_code, 409)
        self.assertEqual(self.cliente.get("/api/bairros").status_code, 200)
        r = self.cliente.put("/api/bairros/1", json={**BAIRRO_OK, "nome": "Jardim Romano"})
        self.assertEqual((r.status_code, r.get_json()["nome"]), (200, "Jardim Romano"))
        self.assertEqual(self.cliente.put("/api/bairros/99", json=BAIRRO_OK).status_code, 404)
        self.assertEqual(self.cliente.delete("/api/bairros/1").status_code, 204)
        self.assertEqual(self.cliente.delete("/api/bairros/1").status_code, 404)

    def test_entradas_invalidas(self):
        self.assertEqual(self.cliente.post("/api/bairros", data="x").status_code, 415)
        r = self.cliente.post("/api/bairros", json={"nome": "<b>"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("detalhes", r.get_json())
        grande = {**BAIRRO_OK, "nome": "a" * 20000}
        self.assertEqual(self.cliente.post("/api/bairros", json=grande).status_code, 413)
        self.assertEqual(self.cliente.get("/api/alertas?bairro_id=abc").status_code, 400)

    def test_erro_de_banco_nao_vaza_detalhes(self):
        with mock.patch.object(db, "listar_bairros", side_effect=db.ErroBanco("mysql: errno=1045")):
            r = self.cliente.get("/api/bairros")
        self.assertEqual(r.status_code, 503)
        self.assertNotIn("1045", r.get_data(as_text=True))

    def test_cabecalhos_de_seguranca(self):
        r = self.cliente.get("/api/bairros")
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("default-src 'self'", r.headers["Content-Security-Policy"])

    def test_verificar_emite_alerta_e_limita_repeticao(self):
        self.cliente.post("/api/bairros", json=BAIRRO_OK)
        prev = [{"data": "2026-11-10", "chuva_mm": 60.0, "temp_max": 28.0, "prob_chuva": 95}]
        with mock.patch("clima.obter_previsao", return_value=prev):
            r = self.cliente.post("/api/bairros/1/verificar")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.get_json()["alertas"][0]["nivel"], "ALERTA")
            self.assertEqual(self.cliente.post("/api/bairros/1/verificar").status_code, 429)
        self.assertEqual(len(self.cliente.get("/api/alertas").get_json()), 1)

    def test_api_externa_fora_do_ar_retorna_502(self):
        self.cliente.post("/api/bairros", json=BAIRRO_OK)
        with mock.patch("clima.obter_previsao", side_effect=clima.ErroServicoExterno("x")):
            self.assertEqual(self.cliente.post("/api/bairros/1/verificar").status_code, 502)


class TestSocket(unittest.TestCase):
    def setUp(self):
        self.servidor = ServidorAlertas("127.0.0.1", 0)
        self.servidor.start()
        self.servidor.pronto.wait(3)

    def tearDown(self):
        self.servidor.parar()

    def _conectar(self, comando):
        s = socket.create_connection(("127.0.0.1", self.servidor.porta), timeout=3)
        s.sendall(comando)
        return s, s.recv(1024).decode()

    def test_inscricao_e_entrega(self):
        s, resp = self._conectar(b"INSCREVER 7\n")
        self.assertEqual(resp, "OK INSCRITO 7\n")
        time.sleep(0.1)
        self.assertEqual(self.servidor.publicar(7, {"nivel": "ALERTA", "mensagem": "teste"}), 1)
        self.assertEqual(self.servidor.publicar(8, {"nivel": "ALERTA", "mensagem": "outro"}), 0)
        self.assertIn('"nivel": "ALERTA"', s.recv(1024).decode())
        s.close()

    def test_comando_invalido_e_recusado(self):
        s, resp = self._conectar(b"DROP TABLE bairros\n")
        self.assertTrue(resp.startswith("ERRO"))
        s.close()


if __name__ == "__main__":
    unittest.main()
