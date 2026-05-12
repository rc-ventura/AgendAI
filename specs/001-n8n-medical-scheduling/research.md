# Research: N8N Medical Scheduling Automation

**Phase 0 output para**: `specs/001-n8n-medical-scheduling/plan.md`
**Data**: 2026-05-12
**Stack**: Node.js 20 LTS + Express 4 + better-sqlite3 + N8N Docker

> Todas as decisões abaixo substituem a versão anterior (Python/FastAPI) após
> alinhamento com `docs/initial_plan.md` e o PDF do desafio técnico como fonte verdade.

---

## 1. Framework da API REST

**Decisão**: Node.js 20 LTS + Express 4 (ADR-01)

**Rationale**: Express sem boilerplate, integração trivial com N8N via HTTP Request
node, `better-sqlite3` síncrono no mesmo ecossistema JS, uma única linguagem para
API + testes (Jest/Supertest). O desafio avalia o uso correto de N8N, não a
sofisticação do backend — Express é a escolha de menor atrito.

**Alternativas consideradas**:
- FastAPI (Python): eliminado — forçaria dois runtimes no Docker Compose e a equipe
  de avaliação precisaria de Python instalado. N8N é nativo JS/TS.
- Fastify: mais performático, mas menos familiar para avaliadores; Express é padrão
  de mercado para APIs de demonstração.
- NestJS: desnecessariamente complexo para o escopo de um mock simples com 5 rotas.

---

## 2. Banco de Dados

**Decisão**: SQLite via `better-sqlite3` (síncrono) (ADR-02)

**Rationale**: O desafio indica SQLite como preferencial por simplicidade. `better-sqlite3`
é a implementação Node.js mais estável, sem driver externo, operações síncronas que
simplificam o código de rota (sem async/await no acesso a dados), e seed trivial. O
arquivo `clinica.db` persiste em volume Docker `./data:/app/data`.

**Decisões de schema**:
- `horarios.data_hora` como TEXT ISO 8601 (`"2026-05-13T09:00:00"`) — SQLite não tem
  tipo DATETIME nativo; string ISO é ordenável e comparável diretamente.
- `agendamentos.status` como TEXT (`"ativo"` | `"cancelado"`) — permite estados futuros
  sem migração de schema.
- `pagamentos.formas` como JSON serializado — evita tabela extra para dado estático.
- `pacientes.email` como UNIQUE — é a chave natural que o LLM usa para identificar
  pacientes na conversa (ADR-03).

**Alternativas consideradas**:
- PostgreSQL: eliminado — adiciona container extra desnecessário; SQLite é explicitamente
  preferido pelo desafio.
- Knex.js query builder: útil em projetos maiores; desnecessário aqui — queries diretas
  com `better-sqlite3` são mais simples e legíveis.

---

## 3. Arquitetura dos Fluxos N8N

**Decisão**: 4 fluxos separados exportados como JSONs individuais (ADR-N8N)

```
flow-a-entrada.json  →  Chat Trigger, detecta texto|áudio, roteia para B ou C
flow-b-ai-core.json  →  GPT-4o-mini + 5 functions + HTTP Request nodes para API
flow-c-audio.json    →  Whisper STT → Flow B → OpenAI TTS (voz alloy)
flow-d-email.json    →  Sub-workflow Gmail (reutilizado por B e C)
```

**Rationale**: Modularidade facilita importação incremental (A→B→C→D) e debugging
isolado. O avaliador consegue ativar flow-b independentemente para testar intents de
texto sem precisar de suporte a áudio. flow-d como sub-workflow é reutilizado tanto
no agendamento quanto no cancelamento sem duplicação de nodes.

Ver detalhes completos em `contracts/n8n-function-tools.md`.

**Alternativas consideradas**:
- Workflow único: mais simples de importar mas difícil de debugar; um erro no fluxo de
  áudio inutilizaria o fluxo de texto.
- N8N Chat Trigger nativo (UI embutida): adequado para demo mas não testável via
  Postman/curl; Webhook Trigger é preferível para evidências de teste.

---

## 4. LLM e Function Calling

**Decisão**: GPT-4o-mini via OpenAI Chat node do N8N (ADR-04)

**Rationale**: Function calling nativo elimina necessidade de parsear saída de texto
para identificar intenção — o modelo retorna estrutura JSON com nome da função e
parâmetros. Custo baixo por token para volume de demonstração. Uma única credencial
OpenAI reutilizada no Chat node (LLM), Whisper (STT) e TTS.

**5 functions declaradas** (ver `contracts/n8n-function-tools.md`):
1. `buscar_horarios_disponiveis` → `GET /horarios/disponiveis`
2. `criar_agendamento` → `POST /agendamentos`
3. `cancelar_agendamento` → `PATCH /agendamentos/:id/cancelar`
4. `buscar_pagamentos` → `GET /pagamentos`
5. `buscar_paciente` → `GET /pacientes/:email`

Saudação/encerramento não requer function — o LLM responde diretamente pelo system
prompt.

**Alternativas consideradas**:
- Classificação zero-shot + switch: frágil, exige parsing de texto livre; function
  calling é mais robusto e testável.
- Claude (Anthropic): eliminado para este projeto — a integração nativa do N8N com
  OpenAI é mais direta; GPT-4o-mini tem custo menor para avaliação.

---

## 5. Integração Gmail

**Decisão**: Gmail node nativo do N8N com OAuth2 (ADR-08)

**Rationale**: O N8N possui node Gmail com suporte a OAuth2 configurável pela UI,
retry nativo por node (3 tentativas, intervalo 5s), e template de e-mail construído
com Set nodes. Toda a lógica de envio fica em `flow-d-email.json`, sem código na
API — a API permanece responsável apenas por dados, satisfazendo Constitution
Principle V (Simplicity).

**Configuração de credenciais**:
1. Google Cloud Console → habilitar Gmail API.
2. Criar OAuth2 Client ID (Desktop app) → baixar `credentials.json`.
3. No N8N: Settings → Credentials → New → Gmail OAuth2 API → seguir fluxo de
   autorização. Token armazenado pelo N8N internamente.
4. Escopo necessário: `https://www.googleapis.com/auth/gmail.send`.
5. Passo a passo com prints em `docs/prints/gmail-setup/`.

**Alternativas consideradas**:
- Gmail via código na API (Nodemailer + OAuth2): adiciona dependência desnecessária
  à API; retry precisaria ser implementado manualmente.
- SendGrid: mais simples mas o desafio especifica Gmail API explicitamente.

---

## 6. Text-to-Speech (TTS)

**Decisão**: OpenAI TTS — modelo `tts-1`, voz `alloy` (ADR-07)

**Rationale**: Mesmo vendor e mesma credencial do LLM (GPT-4o-mini) e STT (Whisper) —
uma única chave `OPENAI_API_KEY` no N8N cobre os três serviços. A voz `alloy` foi
escolhida por ser neutra e articular bem português. O node HTTP Request do N8N
chama `POST /audio/speech` com retry nativo configurado para 3 tentativas com
intervalo de 3s. Se todas falharem, flow-c retorna a resposta texto do flow-b.

**Alternativas consideradas**:
- ElevenLabs: qualidade de voz superior mas exige API key adicional — contra
  Constitution Principle V (Simplicity).
- Google TTS: gratuito em tier básico mas SDK mais complexo e latência maior no
  demo. Pode ser configurado via variável de ambiente como alternativa.
- Voz `nova`: testada mas `alloy` mostrou melhor articulação em português nas
  avaliações iniciais.

---

## 7. Transcrição de Áudio (STT)

**Decisão**: OpenAI Whisper API — modelo `whisper-1` (ADR-06)

**Rationale**: Mesmo vendor dos outros serviços OpenAI; aceita `.ogg`, `.mp3`, `.wav`,
`.m4a`; detecção automática de idioma (funciona com português sem configuração
extra). Chamado via HTTP Request node no N8N (`POST /audio/transcriptions`). O
transcript é injetado como texto no flow-b para processamento de intenção.

**Alternativas consideradas**:
- Whisper local (Docker): elimina custo de API mas exige GPU ou grande overhead de
  CPU — incompatível com setup simples de demo.
- Google Speech-to-Text: credencial extra necessária; Whisper é superior em
  português.

---

## 8. Estratégia de Retry

**Decisão**: Retry nativo dos nodes N8N — não código na API (ADR-Retry)

**Configuração**:
- Gmail node (flow-d-email): retry 3 tentativas, intervalo 5s
- HTTP Request TTS (flow-c-audio): retry 3 tentativas, intervalo 3s

**Rationale**: Centralizar retry no N8N mantém a API responsável apenas por dados.
O N8N tem suporte nativo a retry por node (Settings → On error → Retry on fail),
sem código extra. O agendamento/cancelamento já está persistido no banco antes de
qualquer tentativa de envio — a falha no e-mail ou TTS não reverte a transação.

**Alternativas consideradas**:
- Biblioteca de retry na API (ex: `async-retry`): desnecessário para serviços que
  a API não chama diretamente — Gmail e TTS são chamados pelo N8N, não pela API.

---

## 9. Logging Estruturado

**Decisão**: `pino` (logger JSON para Node.js) com middleware Express customizado

**Rationale**: `pino` é o logger Node.js de menor overhead, com output JSON nativo
sem configuração. Satisfaz Constitution Principle IV: todo request da API emite log
com `correlation_id` (UUID gerado via `crypto.randomUUID()` ou lido do header
`X-Request-ID`), `timestamp`, `method`, `path`, `status_code` e `duration_ms`.
Interações com LLM (via N8N) incluem `tool_called` e `outcome` nos logs do N8N.

**Estrutura de log por request**:
```json
{
  "level": "info",
  "time": "2026-05-12T10:05:00.000Z",
  "correlation_id": "a1b2c3d4-...",
  "method": "POST",
  "path": "/agendamentos",
  "status_code": 201,
  "duration_ms": 12
}
```

**Alternativas consideradas**:
- `winston`: mais configurável mas overhead maior; pino é suficiente.
- `morgan`: HTTP logger apenas, sem suporte a campos customizados como
  `correlation_id` — insuficiente para Constitution Principle IV.
- `console.log`: sem estrutura JSON, impossível de parsear em produção.

---

## 10. Dados do Seed

**Decisão**: 3 médicos, 5 pacientes, 10 horários, 2 agendamentos pré-confirmados,
1 registro de pagamento

**Rationale**: Volume suficiente para exercitar todos os 6 intents do chat sem
sobrecarregar o avaliador. O seed é determinístico (mesmos dados em toda execução
limpa). Os 2 agendamentos pré-confirmados permitem testar cancelamento via chat
imediatamente, sem precisar criar um agendamento antes.

**Seed detalhado**:

| Tabela       | Qtd | Dados |
|--------------|-----|-------|
| medicos      | 3   | Dr. Carlos Lima (Clínico Geral), Dra. Ana Souza (Cardiologista), Dr. Pedro Costa (Dermatologista) |
| pacientes    | 5   | João Silva (joao@email.com), Maria Santos (maria@email.com), Pedro Oliveira (pedro@email.com), Ana Ferreira (ana@email.com), Lucas Pereira (lucas@email.com) |
| horarios     | 10  | Próximos 7 dias úteis, 09:00–17:00, `disponivel=1` |
| agendamentos | 2   | João (horario_id=1, ativo), Maria (horario_id=2, ativo) |
| pagamentos   | 1   | "Consulta Geral", R$ 150,00, ["PIX","Cartão de Débito","Cartão de Crédito","Dinheiro"] |

**Alternativas consideradas**:
- 30 horários: excessivo para demo — 10 são suficientes e o seed roda mais rápido.
- 1 médico: insuficiente para demonstrar que a API suporta múltiplos médicos
  conforme o desafio avalia ("modelagem simples e funcional").
