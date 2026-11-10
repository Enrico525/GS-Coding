-- =============================================================
-- Usuário da aplicação com PRIVILÉGIO MÍNIMO (sem DROP/ALTER/GRANT).
-- 1) Troque 'TROQUE_ESTA_SENHA' por uma senha forte ANTES de executar.
-- 2) Coloque a mesma senha em DB_PASSWORD no arquivo .env (nunca no código).
-- Execute como administrador:  mysql -u root -p < sql/02_usuario_app.sql
-- =============================================================

CREATE USER IF NOT EXISTS 'alerta_app'@'localhost' IDENTIFIED BY 'TROQUE_ESTA_SENHA';
GRANT SELECT, INSERT, UPDATE, DELETE ON alertabairro.* TO 'alerta_app'@'localhost';
FLUSH PRIVILEGES;
