-- PostgreSQL schema (migrated from SQLite). Idempotent: safe to run on every startup.

-- Médicos disponíveis
CREATE TABLE IF NOT EXISTS medicos (
  id            INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  nome          TEXT NOT NULL,
  especialidade TEXT NOT NULL
);

-- Pacientes cadastrados (email é chave natural usada pelo LLM)
CREATE TABLE IF NOT EXISTS pacientes (
  id       INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  nome     TEXT NOT NULL,
  email    TEXT NOT NULL UNIQUE,
  telefone TEXT
);

-- Slots de horário por médico
-- data_hora: ISO 8601 TEXT "2026-05-13T09:00:00" — mantido como TEXT para preservar o
-- contrato exato consumido pelo agente/UI e a ordenação lexicográfica natural.
CREATE TABLE IF NOT EXISTS horarios (
  id         INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  medico_id  INTEGER NOT NULL REFERENCES medicos(id),
  data_hora  TEXT NOT NULL,
  disponivel SMALLINT NOT NULL DEFAULT 1
);

-- Agendamentos realizados (nunca deletados após criação)
CREATE TABLE IF NOT EXISTS agendamentos (
  id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  paciente_id INTEGER NOT NULL REFERENCES pacientes(id),
  horario_id  INTEGER NOT NULL REFERENCES horarios(id),
  status      TEXT NOT NULL DEFAULT 'ativo',
  criado_em   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Valores e formas de pagamento
CREATE TABLE IF NOT EXISTS pagamentos (
  id        INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  descricao TEXT NOT NULL,
  valor     NUMERIC(10,2) NOT NULL,
  formas    TEXT NOT NULL
);
