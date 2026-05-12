# N8N Function Tools & Arquitetura de Fluxos

**Phase 1 output for**: `specs/001-n8n-medical-scheduling/plan.md`
**Date**: 2026-05-12

---

## Visão Geral dos 4 Fluxos

```
flow-a-entrada   →  detecta tipo (texto | áudio), normaliza para texto
flow-b-ai-core   →  GPT-4o-mini + function calling + chamadas à API REST
flow-c-audio     →  Whisper (STT) → chama flow-b → TTS na resposta
flow-d-email     →  sub-workflow de envio de confirmação por Gmail (reutilizado)
```

---

## Flow A — Detecção de Entrada (`flow-a-entrada.json`)

```
[Chat Trigger]
    ↓
[IF: type === "audio" / binário]
    → SIM → [Executa Flow C]
    → NÃO → [Executa Flow B] com mensagem de texto diretamente
```

**Chat Trigger**: modo webhook público, aceita texto e binário (áudio).

---

## Flow B — Core de IA (`flow-b-ai-core.json`)

```
[Set: monta histórico de mensagens]
    ↓
[OpenAI Chat: gpt-4o-mini com 5 functions declaradas]
    ↓
[Switch: qual function foi chamada?]
    ├── buscar_horarios_disponiveis  → [HTTP GET /horarios/disponiveis]
    ├── criar_agendamento            → [HTTP POST /agendamentos] → [Flow D]
    ├── cancelar_agendamento         → [HTTP PATCH /agendamentos/:id/cancelar] → [Flow D]
    ├── buscar_pagamentos            → [HTTP GET /pagamentos]
    ├── buscar_paciente              → [HTTP GET /pacientes/:email]
    └── nenhuma function             → resposta direta (saudação/encerramento)
         ↓
[Set: formata resposta final]
    ↓
[Respond to Webhook]
```

---

## Flow C — Áudio (`flow-c-audio.json`)

```
[Recebe binário do Chat Trigger]
    ↓
[HTTP POST OpenAI /audio/transcriptions (Whisper whisper-1)]
    ↓
[Set: injeta transcrição como texto]
    ↓
[Executa Flow B com o texto transcrito]
    ↓
[HTTP POST OpenAI /audio/speech (TTS tts-1, voz: alloy)]
    ↓              └── Retry: 3 tentativas, intervalo 3s
[Respond: retorna arquivo .mp3]
    └── Se TTS falhar em todas tentativas: retorna resposta texto do Flow B
```

---

## Flow D — E-mail (sub-workflow) (`flow-d-email.json`)

```
[Execute Workflow Trigger]
    ↓
[Switch: tipo (agendamento | cancelamento)]
    ├── agendamento  → [Set: template confirmação]
    └── cancelamento → [Set: template cancelamento]
         ↓
[Gmail node: envia para paciente.email]
    └── Retry: 3 tentativas, intervalo 5s (configurado no node Gmail)
```

**Templates de e-mail**:
- Agendamento: `Confirmação de consulta — {data_hora} com {medico} | Valor: R$ {valor} | Pagamento: {formas}`
- Cancelamento: `Consulta cancelada — {data_hora} com {medico} foi cancelada com sucesso.`

---

## Functions Declaradas ao LLM (GPT-4o-mini)

### 1. buscar_horarios_disponiveis

```json
{
  "name": "buscar_horarios_disponiveis",
  "description": "Busca horários médicos disponíveis para agendamento. Use quando o paciente perguntar sobre horários ou datas disponíveis.",
  "parameters": {
    "type": "object",
    "properties": {
      "data": {
        "type": "string",
        "description": "Data no formato YYYY-MM-DD. Opcional — sem data retorna todos os disponíveis nos próximos dias."
      }
    }
  }
}
```

**HTTP Request node**: `GET {{ $env.API_BASE_URL }}/horarios/disponiveis?data={{ $json.data ?? '' }}`

---

### 2. criar_agendamento

```json
{
  "name": "criar_agendamento",
  "description": "Agenda uma consulta para o paciente em um horário disponível. Use após o paciente confirmar o horário desejado. Requer e-mail do paciente e ID do horário.",
  "parameters": {
    "type": "object",
    "properties": {
      "paciente_email": {
        "type": "string",
        "description": "E-mail cadastrado do paciente. Obter do contexto da conversa ou chamar buscar_paciente se necessário."
      },
      "horario_id": {
        "type": "number",
        "description": "ID do horário desejado (obtido de buscar_horarios_disponiveis)."
      }
    },
    "required": ["paciente_email", "horario_id"]
  }
}
```

**HTTP Request node**: `POST {{ $env.API_BASE_URL }}/agendamentos`
```json
{ "paciente_email": "{{ $json.paciente_email }}", "horario_id": {{ $json.horario_id }} }
```

---

### 3. cancelar_agendamento

```json
{
  "name": "cancelar_agendamento",
  "description": "Cancela um agendamento existente. Use quando o paciente solicitar cancelamento. Requer o ID do agendamento.",
  "parameters": {
    "type": "object",
    "properties": {
      "agendamento_id": {
        "type": "number",
        "description": "ID numérico do agendamento a cancelar."
      }
    },
    "required": ["agendamento_id"]
  }
}
```

**HTTP Request node**: `PATCH {{ $env.API_BASE_URL }}/agendamentos/{{ $json.agendamento_id }}/cancelar`

---

### 4. buscar_pagamentos

```json
{
  "name": "buscar_pagamentos",
  "description": "Retorna valores de consulta e formas de pagamento aceitas. Use quando o paciente perguntar sobre preços ou como pagar.",
  "parameters": {
    "type": "object",
    "properties": {}
  }
}
```

**HTTP Request node**: `GET {{ $env.API_BASE_URL }}/pagamentos`

---

### 5. buscar_paciente

```json
{
  "name": "buscar_paciente",
  "description": "Busca os dados de um paciente pelo e-mail. Use quando precisar confirmar se o e-mail informado pelo paciente está cadastrado antes de criar um agendamento.",
  "parameters": {
    "type": "object",
    "properties": {
      "email": {
        "type": "string",
        "description": "E-mail declarado pelo paciente na conversa."
      }
    },
    "required": ["email"]
  }
}
```

**HTTP Request node**: `GET {{ $env.API_BASE_URL }}/pacientes/{{ $json.email }}`

---

## System Prompt (OpenAI Chat Node — Flow B)

```
Você é AgendAI, assistente de agendamento médico da Clínica Saúde.

Regras:
1. SEMPRE use as functions fornecidas para responder perguntas sobre horários,
   agendamentos, cancelamentos e pagamentos. Nunca invente dados.
2. Para agendar: primeiro chame buscar_horarios_disponiveis para mostrar opções,
   confirme com o paciente, depois chame buscar_paciente para validar o e-mail,
   e só então chame criar_agendamento.
3. Para cancelar: peça o ID do agendamento se o paciente não informou.
4. Responda no mesmo idioma que o paciente usar (português ou inglês).
5. Seja cordial e objetivo. Saudações e despedidas não precisam de function call.
```

---

## Boas Práticas nos Nodes N8N

- Todos os nodes com **nomes descritivos em português** (ex: "Buscar Horários na API",
  não "HTTP Request1").
- Node `Error Trigger` em cada fluxo para capturar e logar falhas.
- URLs da API via variável de ambiente `API_BASE_URL` (nunca hardcoded).
- Credenciais OpenAI e Gmail referenciadas por nome de credencial do N8N (não por
  valor direto).
