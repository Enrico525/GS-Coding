# Cidades Seguras

Protótipo CitizenTech da Global Solution de **Coding for Security (FIAP)**: alertas de **chuva forte** e **calor extremo** por bairro, gerados a partir da previsão do tempo e enviados a receptores da comunidade (associação de moradores, escola, UBS) por **sockets TCP**.

- **Cidadão:** moradores de bairros em área de risco de alagamento, deslizamento ou calor extremo.
- **ODS:** 11 (Cidades e comunidades sustentáveis), 13 (Ação contra a mudança do clima), 3 (Saúde e bem-estar).
- **Fonte externa:** [Open-Meteo](https://open-meteo.com) (gratuita, sem chave, licença CC BY 4.0).

---

## Arquitetura

```
 Navegador (HTML/CSS/JS) ──HTTP/JSON──> API Flask (app.py) ──SQL parametrizado──> MySQL
                                           │   │
                    requests + JSON <──────┘   └──> Servidor TCP (socket_servidor.py)
                    (clima.py → Open-Meteo)              │  ALERTA {json}
                                                         ▼
                                           cliente_receptor.py (na comunidade)
 Todas as ações → logs/cidades_seguras.log (data/hora | ação | resultado)
```

| Arquivo | Responsabilidade |
|---|---|
| `app.py` | API REST, tratamento de erros, cabeçalhos de segurança, inicialização |
| `db.py` | CRUD no MySQL **sem ORM**, sempre com `%s` (consultas parametrizadas) |
| `validacao.py` | Validação de toda entrada (lista branca de campos, regex, faixas) |
| `clima.py` | Consumo da Open-Meteo com `requests`, timeout e validação da resposta |
| `regras.py` | Transforma a previsão em alertas (ATENÇÃO / ALERTA / EMERGÊNCIA) |
| `socket_servidor.py` | Servidor TCP que distribui alertas aos inscritos de cada bairro |
| `cliente_receptor.py` | Cliente TCP que recebe e exibe os alertas |
| `logger.py` | Log rotativo em arquivo |
| `config.py` | Lê as configurações do `.env` |
| `sql/` | Criação do banco, dados fictícios e usuário de privilégio mínimo |
| `templates/`, `static/` | Interface web |
| `tests/` | Testes automatizados com mock (rodam sem MySQL e sem internet) |

### Modelo de dados

- **bairros** (`id`, `nome`, `cidade`, `uf`, `latitude`, `longitude`, `area_de_risco`, `criado_em`, `atualizado_em`) — `UNIQUE(nome, cidade, uf)`.
- **alertas** (`id`, `bairro_id` → bairros `ON DELETE CASCADE`, `tipo`, `nivel`, `valor`, `data_previsao`, `mensagem`, `criado_em`) — `UNIQUE(bairro_id, tipo, data_previsao)`: verificar de novo atualiza o alerta do dia em vez de duplicar.

Nenhuma tabela guarda dados pessoais: o sistema monitora **lugares**, não pessoas.

---

## Como executar do zero

### 1. Pré-requisitos
- Python 3.10 ou superior
- MySQL 8 (ou MariaDB 10.5+) rodando localmente

### 2. Baixar o projeto e criar o ambiente virtual

```bash
git clone https://github.com/Enrico525/GS-Coding.git cidades-seguras
cd cidades-seguras
python -m venv venv
```

Ative o ambiente:
- **Windows (PowerShell):** `venv\Scripts\Activate.ps1`
- **Linux/macOS:** `source venv/bin/activate`

```bash
pip install -r requirements.txt
```

### 3. Criar o banco de dados

```bash
mysql -u root -p < sql/01_schema.sql
```

Abra `sql/02_usuario_app.sql`, troque `TROQUE_ESTA_SENHA` por uma senha forte e execute:

```bash
mysql -u root -p < sql/02_usuario_app.sql
```

> No Windows, se o comando `mysql` não for reconhecido, abra os arquivos no MySQL Workbench e execute-os (raio ⚡), na mesma ordem.

### 4. Configurar o `.env`

Copie o modelo e coloque a senha definida no passo anterior:

- **Windows:** `copy .env.example .env`
- **Linux/macOS:** `cp .env.example .env`

Edite `DB_PASSWORD` no `.env`. Esse arquivo nunca deve ir para o Git (já está no `.gitignore`).

### 5. Rodar

```bash
python app.py
```

Saída esperada:

```
Web/API: http://127.0.0.1:5000  |  Socket de alertas: 127.0.0.1:5050
```

Abra **http://127.0.0.1:5000** no navegador.

### 6. (Opcional) Receptor de alertas da comunidade

Em **outro terminal** (com o venv ativado):

```bash
python cliente_receptor.py --bairro 1
```

Na página, clique em **Verificar clima** no bairro 1: se a previsão indicar risco, o alerta aparece na hora nesse terminal.

### 7. Roteiro de testes manuais

| # | Ação | Resultado esperado |
|---|---|---|
| 1 | Abrir a página | Lista com os 4 bairros de exemplo |
| 2 | Cadastrar um bairro válido | Mensagem "Bairro cadastrado" (API devolve 201) |
| 3 | Cadastrar o mesmo bairro de novo | Erro de duplicidade (409) |
| 4 | Cadastrar com nome `x' OR 1=1--` ou `<script>` | Erro "Dados inválidos" (400); nada é gravado |
| 5 | Cadastrar com latitude 200 ou UF "ZZ" | Erro "Dados inválidos" (400) |
| 6 | Editar um bairro | Mensagem "Bairro atualizado" (200) |
| 7 | Excluir um bairro | Some da lista (204) |
| 8 | Clicar em "Verificar clima" | Alertas na lista (se houver risco) e no terminal do receptor |
| 9 | Desligar a internet e verificar clima | "Serviço de previsão do tempo indisponível" (502) |
| 10 | Parar o MySQL e recarregar a página | "Serviço temporariamente indisponível" (503), sem detalhes técnicos |
| 11 | Abrir `logs/cidades_seguras.log` | Uma linha por ação, com data/hora, ação e resultado |
| 12 | Clicar em "Verificar clima" duas vezes seguidas | Na segunda: "Aguarde Ns..." (429) |

### 8. Rodar os testes automatizados

```bash
python -m unittest -v
```

São 17 testes que usam um banco em memória e uma Open-Meteo simulada (mock), portanto funcionam sem MySQL e sem internet.

---

## Endpoints

| Método | Rota | Descrição | Status |
|---|---|---|---|
| GET | `/api/bairros` | Lista bairros monitorados | 200 |
| GET | `/api/bairros/<id>` | Detalha um bairro | 200, 404 |
| POST | `/api/bairros` | Cadastra bairro | 201 (+ `Location`), 400, 409, 415 |
| PUT | `/api/bairros/<id>` | Atualiza bairro (objeto completo) | 200, 400, 404, 409, 415 |
| DELETE | `/api/bairros/<id>` | Remove bairro e seus alertas | 204, 404 |
| POST | `/api/bairros/<id>/verificar` | Consulta a Open-Meteo e emite alertas | 200, 404, 429, 502 |
| GET | `/api/alertas?bairro_id=<id>` | Histórico de alertas (filtro opcional) | 200, 400 |

Erros comuns a todas as rotas: 413 (corpo maior que 16 KB), 503 (banco indisponível), 500 (erro interno, sem detalhes).

### Exemplos com curl

```bash
# Cadastrar
curl -X POST http://127.0.0.1:5000/api/bairros -H "Content-Type: application/json" \
  -d '{"nome":"Vila Nova","cidade":"Blumenau","uf":"SC","latitude":-26.9,"longitude":-49.07,"area_de_risco":"ALAGAMENTO"}'

# Atualizar
curl -X PUT http://127.0.0.1:5000/api/bairros/5 -H "Content-Type: application/json" \
  -d '{"nome":"Vila Nova","cidade":"Blumenau","uf":"SC","latitude":-26.91,"longitude":-49.07,"area_de_risco":"MISTO"}'

# Verificar clima e emitir alertas
curl -X POST http://127.0.0.1:5000/api/bairros/1/verificar

# Excluir
curl -X DELETE http://127.0.0.1:5000/api/bairros/5
```

> No PowerShell, use `curl.exe` em vez de `curl` e troque as aspas simples do `-d` por aspas duplas escapadas, ou teste pelo Postman/Insomnia.

### Protocolo do socket (TCP, texto UTF-8, uma linha por mensagem)

| Direção | Mensagem |
|---|---|
| cliente → servidor | `INSCREVER <bairro_id>` ou `SAIR` |
| servidor → cliente | `OK INSCRITO <bairro_id>`, `ERRO <motivo>` ou `ALERTA {json}` |

---

## Regras de alerta

| Tipo | ATENÇÃO | ALERTA | EMERGÊNCIA |
|---|---|---|---|
| Chuva acumulada no dia | ≥ 30 mm | ≥ 50 mm | ≥ 100 mm |
| Temperatura máxima | ≥ 32 °C | ≥ 35 °C | ≥ 38 °C |

Os limiares ficam em `regras.py` e são parâmetros do protótipo; numa implantação real seriam calibrados com a Defesa Civil de cada município.

---

## Segurança e privacidade (resumo)

- **Credenciais no `.env`**, lidas por `python-dotenv`; `.env.example` sem segredos; usuário MySQL com **privilégio mínimo** (só SELECT/INSERT/UPDATE/DELETE).
- **Consultas parametrizadas** em todo o `db.py` (nenhuma concatenação de valores no SQL).
- **Validação de toda entrada:** lista branca de campos, regex para textos, faixas para coordenadas, UF e tipo de risco em listas fechadas, IDs inteiros positivos; corpo limitado a 16 KB; comandos do socket validados por regex e limitados a 64 bytes.
- **Erros sem detalhes internos:** respostas genéricas (ex.: "Serviço temporariamente indisponível"); o detalhe técnico vai só para o log.
- **Log seguro:** sem senhas nem dados pessoais; quebras de linha removidas (evita injeção de log).
- **Front-end sem XSS:** dados exibidos com `textContent`; cabeçalhos `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`.
- **Abuso da API externa:** intervalo mínimo entre verificações do mesmo bairro (HTTP 429 + `Retry-After`); timeout de 10 s; resposta da Open-Meteo validada antes do uso.
- **LGPD:** nenhum dado pessoal é coletado; campos extras enviados são recusados; dados de demonstração são fictícios/abertos.
- **Flask com `debug=False`**: o console de depuração permite executar código remotamente.

---

## Limitações conhecidas

- A verificação é disparada manualmente (botão ou `POST .../verificar`); não há agendamento automático.
- Sem autenticação: qualquer pessoa com acesso à rede local pode cadastrar e excluir bairros. Por isso o servidor escuta só em `127.0.0.1` por padrão.
- O socket não usa TLS; adequado para rede local de demonstração.
- O limite de verificações fica em memória e é zerado ao reiniciar.

## Recursos extras (bônus)

| Recurso | Onde | Por que foi usado |
|---|---|---|
| Cabeçalhos de segurança (CSP, X-Frame-Options, nosniff) | `app.py` | Segunda camada contra XSS e clickjacking, caso algum dado escape da validação |
| Limite de requisições (429 + `Retry-After`) | `app.py` (`Cooldown`) | Impede que alguém use o sistema para sobrecarregar a API de clima |
| Testes automatizados com `unittest.mock` | `tests/` | Comprovam validação, status HTTP, regras e socket sem depender de banco ou internet |
| `RotatingFileHandler` | `logger.py` | O log não cresce sem limite (1 MB x 5 arquivos), evitando encher o disco |
| `@contextmanager` | `db.py` | Garante commit/rollback e fechamento da conexão em um único lugar |

## Créditos

- Previsão do tempo: [Open-Meteo.com](https://open-meteo.com), licença CC BY 4.0.
- Bibliotecas: Flask, requests, python-dotenv, mysql-connector-python.
