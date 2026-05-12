# API Contracts: AgendAI REST API

**Base URL (local)**: `http://localhost:3000`
**Content-Type**: `application/json`
**Auth**: Nenhuma (demo — todos os endpoints são abertos)

---

## Horários

### GET /horarios/disponiveis

Lista horários com `disponivel = 1`. Resposta cacheada (TTL 60s) — invalidada em
todo POST /agendamentos e PATCH /agendamentos/:id/cancelar.

**Query parameters**:

| Nome | Tipo   | Obrigatório | Descrição                               |
|------|--------|-------------|-----------------------------------------|
| data | string | Não         | Filtro por data no formato `YYYY-MM-DD` |

**Response 200**:
```json
[
  {
    "id": 3,
    "data_hora": "2026-05-13T09:00:00",
    "disponivel": 1,
    "medico": {
      "id": 1,
      "nome": "Dr. Carlos Lima",
      "especialidade": "Clínico Geral"
    }
  }
]
```

**Response 200 (sem resultados)**: `[]`

**Chave de cache**:
- Sem filtro: `"horarios"`
- Com filtro: `"horarios:2026-05-13"`

---

## Agendamentos

### POST /agendamentos

Cria um agendamento. Marca o horário como `disponivel=0`. Invalida cache de horários.
O paciente é identificado pelo **e-mail** (não por ID numérico).

**Request body**:
```json
{
  "paciente_email": "joao@email.com",
  "horario_id": 3
}
```

| Campo          | Tipo   | Obrigatório | Descrição                                    |
|----------------|--------|-------------|----------------------------------------------|
| paciente_email | string | Sim         | E-mail cadastrado do paciente                |
| horario_id     | number | Sim         | ID do horário com `disponivel=1`             |

**Response 201**:
```json
{
  "id": 12,
  "paciente": {
    "id": 2,
    "nome": "João Silva",
    "email": "joao@email.com"
  },
  "horario": {
    "id": 3,
    "data_hora": "2026-05-13T09:00:00"
  },
  "medico": {
    "nome": "Dr. Carlos Lima"
  },
  "status": "ativo",
  "criado_em": "2026-05-12T14:32:00"
}
```

**Response 404** (paciente não encontrado):
```json
{ "error": "Paciente não encontrado" }
```

**Response 409** (horário não disponível):
```json
{ "error": "Horário não está mais disponível" }
```

---

### PATCH /agendamentos/:id/cancelar

Cancela um agendamento existente. Define `status = 'cancelado'` e libera o horário
(`disponivel = 1`). **Não deleta o registro.** Invalida cache de horários.

**Path parameter**: `id` (integer)

**Body**: nenhum

**Response 200**:
```json
{
  "id": 12,
  "status": "cancelado"
}
```

**Response 404** (agendamento não encontrado):
```json
{ "error": "Agendamento não encontrado" }
```

**Response 400** (já cancelado):
```json
{ "error": "Agendamento já está cancelado" }
```

---

### GET /agendamentos/:id

Retorna detalhes de um agendamento específico.

**Path parameter**: `id` (integer)

**Response 200**:
```json
{
  "id": 12,
  "paciente": { "id": 2, "nome": "João Silva", "email": "joao@email.com" },
  "horario": { "id": 3, "data_hora": "2026-05-13T09:00:00" },
  "medico": { "nome": "Dr. Carlos Lima" },
  "status": "ativo",
  "criado_em": "2026-05-12T14:32:00"
}
```

**Response 404**:
```json
{ "error": "Agendamento não encontrado" }
```

---

## Pacientes

### GET /pacientes/:email

Busca paciente pelo e-mail. Utilizado pelo LLM para resolver o e-mail declarado
pelo paciente na conversa antes de criar um agendamento.

**Path parameter**: `email` (string URL-encoded)

**Response 200**:
```json
{
  "id": 2,
  "nome": "João Silva",
  "email": "joao@email.com",
  "telefone": "11999990001"
}
```

**Response 404**:
```json
{ "error": "Paciente não encontrado" }
```

---

## Pagamentos

### GET /pagamentos

Retorna tipos de consulta, valores e formas de pagamento. Dado estático — sem cache.

**Response 200**:
```json
[
  {
    "id": 1,
    "descricao": "Consulta Geral",
    "valor": 150.00,
    "formas": ["PIX", "Cartão de Débito", "Cartão de Crédito", "Dinheiro"]
  }
]
```

---

## Painel (Diferencial)

### GET /painel

Retorna página HTML com tabela de todos os agendamentos ordenados por data, com
filtro visual por status (`ativo` / `cancelado`).

**Response 200**: `Content-Type: text/html`

Página com tabela contendo: ID, paciente, médico, data/hora, status, criado_em.

---

## Erros Semânticos

| Situação                        | Status | Mensagem                              |
|---------------------------------|--------|---------------------------------------|
| Horário não encontrado          | 404    | `"Horário não encontrado"`            |
| Horário já ocupado              | 409    | `"Horário não está mais disponível"`  |
| Paciente não encontrado         | 404    | `"Paciente não encontrado"`           |
| Agendamento não encontrado      | 404    | `"Agendamento não encontrado"`        |
| Agendamento já cancelado        | 400    | `"Agendamento já está cancelado"`     |
| Erro inesperado do servidor     | 500    | `"Erro interno do servidor"`          |

Todos os erros seguem o formato:
```json
{ "error": "<mensagem legível>" }
```

---

## Cache de Disponibilidade

| Endpoint                         | Cache | Chave                    | TTL  | Invalidação               |
|----------------------------------|-------|--------------------------|------|---------------------------|
| GET /horarios/disponiveis        | Sim   | `"horarios"` ou `"horarios:YYYY-MM-DD"` | 60s | POST /agendamentos, PATCH /:id/cancelar |
| GET /agendamentos/:id            | Não   | —                        | —    | —                         |
| GET /pacientes/:email            | Não   | —                        | —    | —                         |
| GET /pagamentos                  | Não   | —                        | —    | —                         |
| GET /painel                      | Não   | —                        | —    | —                         |
