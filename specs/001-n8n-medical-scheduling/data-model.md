# Data Model: N8N Medical Scheduling Automation

**Phase 1 output for**: `specs/001-n8n-medical-scheduling/plan.md`
**Date**: 2026-05-12

---

## Schema SQL

```sql
-- Médicos disponíveis
CREATE TABLE medicos (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  nome          TEXT NOT NULL,
  especialidade TEXT NOT NULL
);

-- Pacientes cadastrados (email é chave natural usada pelo LLM)
CREATE TABLE pacientes (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  nome     TEXT NOT NULL,
  email    TEXT NOT NULL UNIQUE,
  telefone TEXT
);

-- Slots de horário por médico
-- data_hora: ISO 8601 TEXT "2026-05-13T09:00:00" — ordenável, legível, sem tipo nativo no SQLite
CREATE TABLE horarios (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  medico_id INTEGER NOT NULL REFERENCES medicos(id),
  data_hora TEXT NOT NULL,
  disponivel INTEGER DEFAULT 1   -- 1 = disponível, 0 = ocupado
);

-- Agendamentos realizados (nunca deletados após criação)
CREATE TABLE agendamentos (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  paciente_id INTEGER NOT NULL REFERENCES pacientes(id),
  horario_id  INTEGER NOT NULL REFERENCES horarios(id),
  status      TEXT DEFAULT 'ativo',       -- 'ativo' | 'cancelado'
  criado_em   TEXT DEFAULT (datetime('now'))
);

-- Valores e formas de pagamento
CREATE TABLE pagamentos (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  descricao TEXT NOT NULL,
  valor     REAL NOT NULL,
  formas    TEXT NOT NULL   -- JSON array: ["PIX","Cartão de Débito","Cartão de Crédito"]
);
```

---

## Entidades

### medicos

Profissional de saúde associado aos horários disponíveis.

| Coluna       | Tipo    | Restrições          | Descrição              |
|--------------|---------|---------------------|------------------------|
| id           | INTEGER | PK AUTOINCREMENT    | Chave surrogate        |
| nome         | TEXT    | NOT NULL            | Nome completo          |
| especialidade| TEXT    | NOT NULL            | Especialidade médica   |

---

### pacientes

Pessoa fictícia que interage com o sistema para agendar consultas.

| Coluna   | Tipo    | Restrições       | Descrição                                           |
|----------|---------|------------------|-----------------------------------------------------|
| id       | INTEGER | PK AUTOINCREMENT | Chave surrogate                                     |
| nome     | TEXT    | NOT NULL         | Nome completo                                       |
| email    | TEXT    | NOT NULL, UNIQUE | E-mail de contato — **chave natural usada pelo LLM** |
| telefone | TEXT    |                  | Telefone de contato (opcional)                      |

**Regras de validação**:
- `email` DEVE ser endereço RFC 5321 válido (validado na camada de rota).
- `email` é único — o LLM identifica o paciente pelo e-mail declarado na conversa.

---

### horarios

Bloco de tempo disponível para agendamento, vinculado a um médico.

| Coluna     | Tipo    | Restrições                    | Descrição                                          |
|------------|---------|-------------------------------|----------------------------------------------------|
| id         | INTEGER | PK AUTOINCREMENT              | Chave surrogate                                    |
| medico_id  | INTEGER | NOT NULL, FK → medicos.id     | Médico responsável pelo horário                    |
| data_hora  | TEXT    | NOT NULL                      | Data e hora ISO 8601 (`"2026-05-13T09:00:00"`)     |
| disponivel | INTEGER | DEFAULT 1                     | 1 = disponível, 0 = ocupado                        |

**Decisões de modelagem**:
- `data_hora` como TEXT ISO 8601 — SQLite não tem tipo DATETIME nativo; string ISO é
  ordenável, comparável e legível sem conversão.
- `disponivel` como INTEGER (booleano SQLite) — simples e suficiente; status futuro
  como `remarcado` pode ser adicionado via coluna `status TEXT` em migração futura.

**Transições de estado**:
```
disponivel=1 ──agendamento──► disponivel=0
disponivel=0 ──cancelamento──► disponivel=1
```

---

### agendamentos

Vínculo entre um paciente e um horário. **Nunca deletado após criação.**

| Coluna      | Tipo    | Restrições                    | Descrição                          |
|-------------|---------|-------------------------------|------------------------------------|
| id          | INTEGER | PK AUTOINCREMENT              | Chave surrogate                    |
| paciente_id | INTEGER | NOT NULL, FK → pacientes.id   | Paciente que realizou o agendamento|
| horario_id  | INTEGER | NOT NULL, FK → horarios.id    | Horário agendado                   |
| status      | TEXT    | DEFAULT 'ativo'               | `'ativo'` ou `'cancelado'`         |
| criado_em   | TEXT    | DEFAULT datetime('now')       | Timestamp de criação               |

**Regras**:
- Cancelar um agendamento = `UPDATE agendamentos SET status='cancelado'` +
  `UPDATE horarios SET disponivel=1` — ambos em uma transação.
- `status` como TEXT permite estados futuros (`'remarcado'`) sem migração de schema.

**Transições de estado**:
```
ativo ──cancelar──► cancelado
```
Reativação após cancelamento está fora do escopo de v1.

---

### pagamentos

Configuração de tipos de consulta, valores e formas de pagamento aceitas.

| Coluna    | Tipo    | Restrições       | Descrição                                          |
|-----------|---------|------------------|----------------------------------------------------|
| id        | INTEGER | PK AUTOINCREMENT | Chave surrogate                                    |
| descricao | TEXT    | NOT NULL         | Tipo de consulta (ex: "Consulta Geral")            |
| valor     | REAL    | NOT NULL         | Valor em Reais (ex: 150.00)                        |
| formas    | TEXT    | NOT NULL         | JSON array (ex: `["PIX","Cartão de Débito"]`)      |

**Regras de validação**:
- `valor` DEVE ser ≥ 0.
- `formas` DEVE deserializar para array JSON não-vazio de strings.
- `formas` é armazenado como JSON serializado — evita tabela extra para dado simples
  e estático.

---

## Diagrama de Relacionamento (texto)

```
medicos ──────────────── horarios ──────────────── agendamentos
  id (PK)                  id (PK)                   id (PK)
  nome                     medico_id (FK)             paciente_id (FK → pacientes)
  especialidade            data_hora (ISO 8601)       horario_id  (FK → horarios)
                           disponivel (0|1)           status ('ativo'|'cancelado')
                                                      criado_em

pacientes (chave natural = email)
  id (PK)
  nome
  email (UNIQUE)
  telefone

pagamentos (tabela de configuração independente)
  id (PK)
  descricao
  valor
  formas (JSON array)
```

---

## Seed Data

| Tabela       | Qtd | Detalhes                                                      |
|--------------|-----|---------------------------------------------------------------|
| medicos      | 3   | Dr. Carlos Lima (Clínico Geral), Dra. Ana Souza (Cardiologista), Dr. Pedro Costa (Dermatologista) |
| pacientes    | 5   | João Silva, Maria Santos, Pedro Oliveira, Ana Ferreira, Lucas Pereira — todos com e-mail e telefone fictícios |
| horarios     | 10  | Distribuídos nos próximos 7 dias (09:00–17:00), todos com `disponivel=1` |
| agendamentos | 2   | Pré-confirmados (João + Maria) para teste de cancelamento via chat |
| pagamentos   | 1   | "Consulta Geral" — R$ 150,00 — ["PIX", "Cartão de Débito", "Cartão de Crédito", "Dinheiro"] |
