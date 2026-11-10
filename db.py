"""Acesso ao MySQL SEM ORM: SQL escrito à mão e SEMPRE parametrizado (%s)."""
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal

import mysql.connector
from mysql.connector import errorcode

import config


class ErroBanco(Exception):
    """Falha genérica de banco (a mensagem real vai só para o log)."""


class RegistroDuplicado(Exception):
    """Violação de UNIQUE (ex.: mesmo bairro na mesma cidade/UF)."""


@contextmanager
def conexao():
    """[BÔNUS] Gerenciador de contexto: abre a conexão, faz commit no sucesso,
    rollback no erro e SEMPRE fecha (usado com `with conexao() as con:`)."""
    con = None
    try:
        con = mysql.connector.connect(
            host=config.DB_HOST, port=config.DB_PORT, user=config.DB_USER,
            password=config.DB_PASSWORD, database=config.DB_NAME,
            connection_timeout=5, charset="utf8mb4",
        )
        yield con
        con.commit()
    except mysql.connector.IntegrityError as e:
        if con:
            con.rollback()
        if e.errno == errorcode.ER_DUP_ENTRY:
            raise RegistroDuplicado() from e
        raise ErroBanco(f"integridade: errno={e.errno}") from e
    except mysql.connector.Error as e:
        if con:
            con.rollback()
        raise ErroBanco(f"mysql: errno={e.errno}") from e
    finally:
        if con is not None and con.is_connected():
            con.close()


def _serializar(linha):
    """Converte Decimal/datetime do MySQL para tipos que o JSON entende."""
    if linha is None:
        return None
    saida = {}
    for chave, valor in linha.items():
        if isinstance(valor, Decimal):
            valor = float(valor)
        elif isinstance(valor, (datetime, date)):
            valor = valor.isoformat()
        saida[chave] = valor
    return saida


def _consultar(sql, parametros=(), um=False):
    """Executa um SELECT e devolve uma linha (um=True) ou a lista de linhas."""
    with conexao() as con:
        cursor = con.cursor(dictionary=True)
        try:
            cursor.execute(sql, parametros)
            if um:
                return _serializar(cursor.fetchone())
            return [_serializar(linha) for linha in cursor.fetchall()]
        finally:
            cursor.close()


def _executar(sql, parametros=()):
    """Executa INSERT/UPDATE/DELETE; o commit/rollback fica a cargo de conexao()."""
    with conexao() as con:
        cursor = con.cursor()
        try:
            cursor.execute(sql, parametros)
            return cursor.lastrowid, cursor.rowcount
        finally:
            cursor.close()


# ---------------------------- BAIRROS (CRUD) ----------------------------
_COLUNAS = "id, nome, cidade, uf, latitude, longitude, area_de_risco, criado_em, atualizado_em"


def listar_bairros():
    return _consultar(f"SELECT {_COLUNAS} FROM bairros ORDER BY uf, cidade, nome")


def buscar_bairro(bairro_id):
    return _consultar(f"SELECT {_COLUNAS} FROM bairros WHERE id = %s", (bairro_id,), um=True)


def inserir_bairro(d):
    novo_id, _ = _executar(
        "INSERT INTO bairros (nome, cidade, uf, latitude, longitude, area_de_risco) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (d["nome"], d["cidade"], d["uf"], d["latitude"], d["longitude"], d["area_de_risco"]),
    )
    return novo_id


def atualizar_bairro(bairro_id, d):
    _executar(
        "UPDATE bairros SET nome=%s, cidade=%s, uf=%s, latitude=%s, longitude=%s, "
        "area_de_risco=%s WHERE id=%s",
        (d["nome"], d["cidade"], d["uf"], d["latitude"], d["longitude"],
         d["area_de_risco"], bairro_id),
    )


def excluir_bairro(bairro_id):
    _, linhas = _executar("DELETE FROM bairros WHERE id = %s", (bairro_id,))
    return linhas > 0


# ------------------------------- ALERTAS -------------------------------
def salvar_alerta(bairro_id, alerta):
    """Insere ou atualiza o alerta do dia (UNIQUE bairro + tipo + data)."""
    _executar(
        "INSERT INTO alertas (bairro_id, tipo, nivel, valor, data_previsao, mensagem) "
        "VALUES (%s, %s, %s, %s, %s, %s) "
        "ON DUPLICATE KEY UPDATE nivel=VALUES(nivel), valor=VALUES(valor), "
        "mensagem=VALUES(mensagem), criado_em=CURRENT_TIMESTAMP",
        (bairro_id, alerta["tipo"], alerta["nivel"], alerta["valor"],
         alerta["data"], alerta["mensagem"]),
    )


def listar_alertas(bairro_id=None, limite=50):
    sql = ("SELECT a.id, a.bairro_id, b.nome AS bairro, b.cidade, b.uf, a.tipo, a.nivel, "
           "a.valor, a.data_previsao, a.mensagem, a.criado_em "
           "FROM alertas a JOIN bairros b ON b.id = a.bairro_id ")
    parametros = []
    if bairro_id is not None:
        sql += "WHERE a.bairro_id = %s "
        parametros.append(bairro_id)
    sql += "ORDER BY a.criado_em DESC, a.id DESC LIMIT %s"
    parametros.append(int(limite))
    return _consultar(sql, tuple(parametros))
