-- Médicos disponíveis
CREATE TABLE IF NOT EXISTS medicos (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  nome          TEXT NOT NULL,
  especialidade TEXT NOT NULL
);

-- Pacientes cadastrados (email é chave natural usada pelo LLM)
CREATE TABLE IF NOT EXISTS pacientes (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  nome     TEXT NOT NULL,
  email    TEXT NOT NULL UNIQUE,
  telefone TEXT
);

-- Slots de horário por médico
-- data_hora: ISO 8601 TEXT "2026-05-13T09:00:00" — ordenável, sem tipo nativo no SQLite
CREATE TABLE IF NOT EXISTS horarios (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  medico_id INTEGER NOT NULL REFERENCES medicos(id),
  data_hora TEXT NOT NULL,
  disponivel INTEGER DEFAULT 1
);

-- Agendamentos realizados (nunca deletados após criação)
CREATE TABLE IF NOT EXISTS agendamentos (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  paciente_id INTEGER NOT NULL REFERENCES pacientes(id),
  horario_id  INTEGER NOT NULL REFERENCES horarios(id),
  status      TEXT DEFAULT 'ativo',
  criado_em   TEXT DEFAULT (datetime('now'))
);

-- Valores e formas de pagamento
CREATE TABLE IF NOT EXISTS pagamentos (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  descricao TEXT NOT NULL,
  valor     REAL NOT NULL,
  formas    TEXT NOT NULL
);
