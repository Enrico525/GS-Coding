-- AlertaBairro - Esquema do banco de dados (MySQL 8+)
-- Execute como administrador:  mysql -u root -p < sql/01_schema.sql

SET NAMES utf8mb4;

CREATE DATABASE IF NOT EXISTS alertabairro
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE alertabairro;

-- Bairros/áreas monitoradas. Não há NENHUM dado pessoal:
-- a solução monitora LUGARES, não pessoas (minimização - LGPD art. 6º, III).
CREATE TABLE IF NOT EXISTS bairros (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    nome           VARCHAR(80)  NOT NULL,
    cidade         VARCHAR(80)  NOT NULL,
    uf             CHAR(2)      NOT NULL,
    latitude       DECIMAL(8,5) NOT NULL,
    longitude      DECIMAL(8,5) NOT NULL,
    area_de_risco  ENUM('ALAGAMENTO','DESLIZAMENTO','CALOR','MISTO') NOT NULL DEFAULT 'MISTO',
    criado_em      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em  DATETIME NULL ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT uq_bairro    UNIQUE (nome, cidade, uf),
    CONSTRAINT ck_latitude  CHECK (latitude  BETWEEN -90  AND 90),
    CONSTRAINT ck_longitude CHECK (longitude BETWEEN -180 AND 180)
) ENGINE=InnoDB;

-- Alertas gerados a partir da previsão do tempo (Open-Meteo).
-- Uma linha por bairro + tipo + dia previsto (reverificar atualiza a linha).
CREATE TABLE IF NOT EXISTS alertas (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    bairro_id      INT NOT NULL,
    tipo           ENUM('CHUVA_FORTE','CALOR_EXTREMO') NOT NULL,
    nivel          ENUM('ATENCAO','ALERTA','EMERGENCIA') NOT NULL,
    valor          DECIMAL(6,1) NOT NULL,
    data_previsao  DATE NOT NULL,
    mensagem       VARCHAR(255) NOT NULL,
    criado_em      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_alerta_bairro FOREIGN KEY (bairro_id)
        REFERENCES bairros(id) ON DELETE CASCADE,
    CONSTRAINT uq_alerta_dia UNIQUE (bairro_id, tipo, data_previsao),
    INDEX idx_alerta_criado (criado_em)
) ENGINE=InnoDB;

-- Dados FICTÍCIOS/ABERTOS para demonstração (coordenadas aproximadas e públicas).
INSERT IGNORE INTO bairros (nome, cidade, uf, latitude, longitude, area_de_risco) VALUES
    ('Jardim Pantanal', 'São Paulo', 'SP', -23.49600, -46.42900, 'ALAGAMENTO'),
    ('Alto da Serra',   'Petrópolis','RJ', -22.52600, -43.17000, 'DESLIZAMENTO'),
    ('Centro',          'Cuiabá',    'MT', -15.59600, -56.09600, 'CALOR'),
    ('Sarandi',         'Porto Alegre','RS', -29.98800, -51.12700, 'ALAGAMENTO');
