# Learning Lesson: Arquitetura Redis + Postgres no LangGraph

**Data**: 2026-06-06  
**Contexto**: Investigação de performance em produção (Spec 004 → Spec 005)  
**Motivação**: Latência perceptível ("engasgo") no stream identificada em produção no Render.

---

## O problema original

Em produção, cada conversa adicionava overhead invisível ao usuário:

```
8 nós × 50–200ms por checkpoint no Neon free tier = 400ms–1.6s por conversa
```

A pergunta inicial: **Redis poderia ser um broker entre os nós para eliminar esse bloqueio?**

---

## Aprendizado 1 — O managed server não expõe o checkpointer

O `langgraph/langgraph-server` injeta Postgres automaticamente via `DATABASE_URI`.
Não há como trocar o checkpointer sem sair da imagem gerenciada — o que significa reescrever
o servidor com FastAPI (perdendo streaming SSE, thread management, SDK compatibility).

> **Conclusão**: qualquer otimização de checkpoint no managed server é limitada ao que a imagem
> expõe. Mudar o backend de persistência é uma decisão de migração de plataforma.

---

## Aprendizado 2 — Redis tem quatro papéis distintos no LangGraph

Quando Redis é mencionado com LangGraph em produção, pode significar coisas muito diferentes:

#### Padrão A — Redis substitui o Postgres (`langgraph-redis`)
```
Node → Redis (<1ms) → próximo Node   ← Redis É o checkpointer
```
- Lib: `langgraph-redis` (redis-developer, 223 stars)
- Ganho: ~1.2s por conversa vs Neon free
- Risco: Redis volátil — restart apaga histórico de conversas
- **Exige sair do managed server**

#### Padrão B — Redis como job queue entre runs (Aegra)
```
Browser → Redis queue → Worker executa o grafo → checkpoints ainda vão pro Postgres
```
- Resolve concorrência entre usuários, não latência por conversa
- Projeto Aegra: 961 stars, Apache 2.0

#### Padrão C — Redis como broker entre nós (proposta original do projeto)
```
Node 1 → Redis (<1ms) → Node 2 começa imediatamente
              ↓ background: Postgres persiste async
```
- Padrão arquitetural válido (write-behind cache)
- **Não existe implementação de referência para LangGraph**
- Também exige sair do managed server

#### Padrão D — Redis como cache de output de nós (oficial LangChain, PR #5834)
```
Node buscar_horarios executa → resultado salvo no Redis (TTL)
Próxima chamada igual → Redis retorna sem re-executar o nó
```
- Não elimina o checkpoint Postgres — evita re-execução de nós com mesmo input
- Disponível em LangGraph 1.0+ via `graph.compile(cache=RedisCache(...))`
- O Redis já presente no AgendAI (`REDIS_URI`) pode ser reutilizado

> **Conclusão**: ao falar em "usar Redis com LangGraph", sempre esclarecer qual padrão.
> São trade-offs completamente diferentes.

---

## Aprendizado 3 — A frequência de checkpoint é o gargalo real

O problema não é **onde** o LangGraph escreve (Postgres vs Redis), mas **com que frequência**.

#### Comportamento padrão: escreve após cada nó
Para 6 nós com tool calling (benchmark langchain-aws issue #806):

| Modo | Writes | Overhead medido |
|------|--------|-----------------|
| Por nó (padrão) | ~62 writes | ~8.7s |
| End-of-workflow | 2 writes | ~300ms |

#### Os três modos de durabilidade (vadim.blog)
- `'sync'` — bloqueante antes de cada nó (padrão atual — mais seguro, mais lento)
- `'async'` — não-bloqueante entre nós (risco pequeno de perda em crash)
- `'exit'` — apenas ao final do workflow (máxima performance, sem recovery mid-workflow)

#### Por que `'exit'` é seguro para AgendAI
- Falha no meio → usuário retenta a mensagem (sem perda permanente)
- O único nó com side effect real (`email_sender`) já tem retry com `tenacity`
- As 6 tools da API são idempotentes

#### Evidência acadêmica (Crab 2026, via vadim.blog)
> "Over 75% of agent turns produce no recovery-relevant state — blanket checkpointing is mostly waste."
> Checkpointing semântico reduz tráfego em até **87%**.

> **Conclusão**: antes de trocar infra, testar `checkpoint_mode='exit'` no managed server.
> Se funcionar: 2 linhas de código, maior ganho de latência disponível sem custo.

---

## Aprendizado 4 — O maior ganho não é o checkpoint, é o número de rounds de LLM

Mesmo eliminando o checkpoint, cada round de LLM soma 800ms–2s. Com 4 rounds por conversa:

| Fonte de latência | Ganho potencial | Esforço |
|-------------------|-----------------|---------|
| Prompt engineering (4→2 rounds) | 5–7s | Médio |
| Parallel tool calls | 1–3s | Mínimo (2 linhas) |
| checkpoint_mode='exit' | potencial ~8s | Investigar |
| Groq Whisper (fluxo de áudio) | ~1.7s | Baixo |
| Neon paid | ~1s | Nenhum (só $) |

> **Conclusão**: a ordem de implementação importa. Parallel tool calls e prompt engineering
> têm maior ROI que qualquer otimização de checkpoint.

---

## Aprendizado 5 — O Redis já presente é para SSE, não para dados

`REDIS_URI` no docker-compose serve o LangGraph Server para **streaming SSE** (buffer de
mensagens entre servidor e clientes). Não armazena estado do grafo.

Esse mesmo Redis pode ser reutilizado para o Padrão D (cache de output de nós) sem
infraestrutura adicional — requer investigar se o managed server expõe a configuração
de cache na compilação do grafo.

---

## O que este research trouxe de novo vs o que já estava documentado

### Já estava na Spec 005 / ADR-025
- Padrões A, B, C, D de Redis no LangGraph (ADR-025)
- Benchmark de frequência (62→2 writes, ADR-025)
- checkpoint_mode='exit' como QW-3 (Spec 005)
- Parallel tool calls como QW-1 (Spec 005)

### Contribuições novas que ainda faltam na Spec 005

**1. Padrão D como tarefa investigativa concreta (QW pendente)**
Verificar se `graph.compile(cache=RedisCache(...))` funciona no managed server
usando o Redis já existente (`REDIS_URI`). Zero custo de infra — só investigação.

**2. Migração para fora do managed server como P10 futuro**
Se `checkpoint_mode='exit'` não for suportado e o checkpoint continuar sendo gargalo
após QW-1/4, a saída do managed server (FastAPI + PostgresSaver customizado) deve ser
documentada como decisão futura com critérios de ativação claros.

**3. Hierarquia clara de fontes de latência**
A spec 005 lista os QWs mas não deixa explícito que LLM rounds > checkpoint overhead.
Um diagrama de impacto relativo ajuda na tomada de decisão de prioridade.

---

---

## B3 — Decisões de arquitetura: BFF, `exit` vs `async`, e `DeltaChannel` (2026-06-10)

### 1. Onde vive o `durability` — e por que isso exige um BFF

**Hipótese inicial**: `checkpoint_mode='exit'` seria configurado em `graph.py` (compile-time)
ou em `langgraph.json` — decisão do backend LangGraph.

**Sonda B0 revelou**: o parâmetro `durability` é lido do **payload HTTP por-run**:

```python
# langgraph_api/models/run.py:276-279 (código-fonte do servidor gerenciado)
durability = payload.get("durability")   # lê do corpo da requisição
if durability is None:
    checkpoint_during = payload.get("checkpoint_during")
    durability = "async" if checkpoint_during in (None, True) else "exit"
```

Não existe `env var` de default, nem campo em `langgraph.json`, nem parâmetro de
`graph.compile()`. Cada run decide sua durabilidade no momento da criação.

**Consequência**: quem cria o run controla a durabilidade. Em Python puro:

```python
run = await client.runs.create(
    thread_id=thread["thread_id"],
    assistant_id="agent",
    durability="exit",  # aqui, no código que chama o servidor
)
```

**Por que não pode ficar na UI (browser):**

1. **Segurança e consistência** — durabilidade afeta uso de recursos do banco. O cliente
   (browser) não deve controlar isso: um cliente malicioso poderia forçar `sync` em todos
   os runs e sobrecarregar o Postgres.
2. **Princípio arquitetural** — a UI dispara eventos; o servidor (ou o BFF intermediário)
   decide como persistir. A UI não deve conhecer detalhes do motor de execução.
3. **Sem Next.js** — o lugar correto seria um serviço Python/Node.js dedicado chamando
   `client.runs.create(durability=...)`. Com Next.js, o Route Handler **é** esse serviço.

**Por que nginx puro não resolve:**
nginx sem módulo Lua/NJS não consegue modificar o corpo JSON de requests POST. A única
opção não-BFF seria o próprio servidor LangGraph ler um env var de default — mas o código
mostra que ele não faz isso.

**Solução implementada — BFF Next.js Route Handler:**

```typescript
// agent-ui-pro/src/app/api/[..._path]/route.ts
// Node.js server-side — NÃO executado no browser
initApiPassthrough({
  apiUrl: process.env.LANGGRAPH_API_URL,         // env var server-side
  headers: () => ({ "X-Api-Key": process.env.LANGGRAPH_AUTH_TOKEN }),
  bodyParameters: (req, body) => {
    if (req.method === "POST" && req.url.includes("/runs")) {
      return { ...body, durability: "exit" };    // injetado aqui
    }
    return body;
  },
  baseRoute: "api",
  runtime: "nodejs",
});
```

O browser chama `http://localhost:8080/api/threads/:id/runs/stream`. nginx roteia `/api/...`
para o Next.js. O Route Handler adiciona `durability: "exit"` e encaminha para
`http://langgraph-server:8123`. O `LANGGRAPH_AUTH_TOKEN` nunca vai ao browser.

**Regra consolidada**: se o parâmetro é lido via `payload.get(...)` no servidor LangGraph,
ele só pode ser definido pelo código que cria o run — seja um serviço Python, um BFF Node.js,
ou outro intermediário. UI puro nunca é o lugar correto.

---

### 2. Por que `exit` e não `async` (o padrão)

Os três modos de durabilidade e o que cada um faz:

| Modo | Quando checkpointa | I/O por turno | Recovery em crash |
|---|---|---|---|
| `sync` | Antes de cada nó, **bloqueante** | ~6 writes síncronos | ✅ Total — recupera do nó exato |
| `async` *(padrão)* | Após cada nó, **não-bloqueante** | ~6 writes assíncronos | ⚠️ Quase total — pode perder último nó |
| `exit` | Apenas ao final do run | **1 write** | ❌ Zero mid-run — turn inteiro se perde |

**Por que não `async`:**
- `async` ainda produz ~6 writes por turno (igual ao `sync` em quantidade)
- A única diferença é que o write não bloqueia o próximo nó — o ganho de latência é
  pequeno (o Postgres processa os writes em paralelo, mas ainda consome I/O e conexões)
- Para o Neon free tier (50–200ms/write), `async` = 6 writes × overhead = mesma espera
  total, só distribuída diferente na timeline
- O `exit` é a única opção que reduz o **número** de writes: 6 → 1 (−83%)

**Trade-off escolhido (`exit`):**

| | `async` | `exit` |
|---|---|---|
| Writes/turno | ~6 | **1** |
| Latência checkpoint | Distribuída entre nós | Concentrada no final |
| Recovery em crash | Recupera do último nó | ❌ Perde o turno inteiro |
| Risco de side effect | Baixo | **Existe** (ver seção 3) |

Para o AgendAI — chat conversacional onde cada turno é independente — perder um turno
inteiro em crash é aceitável: o usuário simplesmente retenta a mensagem.

---

### 3. O problema de email duplicado com `exit` — e a solução

**Cenário de risco:**

```
Turno N-1: criar_agendamento → estado: {email_pending: True, email_payload: {...}}
           ↓ checkpoint escrito (exit do turno N-1)

Turno N:   LLM confirma → send_email executa → email enviado
           estado em memória: {email_pending: False, email_payload: None}
           ↓ CRASH DO PROCESSO antes do exit checkpoint
           ↓ checkpoint do turno N NUNCA é escrito

Retry do usuário (ou auto-retry):
           Thread carrega último checkpoint = turno N-1 = {email_pending: True}
           → send_email executa novamente → EMAIL DUPLICADO ✉️✉️
```

**Por que o `tenacity` no `email_sender.py` não ajuda aqui:**
O `tenacity` (3x retry, backoff exponencial) protege contra falhas de SMTP — o servidor
de e-mail fica fora do ar, timeout de rede, etc. Ele **não** protege contra o LangGraph
reexecutar o nó por causa de um run reiniciado.

**Com `async` o risco seria menor:**
Com `async`, após o nó `send_email` completar, um write assíncrono captura
`{email_pending: False}`. Se o processo cai depois desse write, o retry carrega o estado
correto e não envia o email novamente. A janela de vulnerabilidade é só o intervalo entre
o nó completar e o write assíncrono finalizar — muito menor que com `exit`.

**Soluções possíveis:**

**Opção A — Idempotência por `agendamento_id` (recomendada, não implementada):**
Antes de enviar, verificar se já existe um e-mail registrado para esse `agendamento_id`
em banco de dados. O custo de implementação é médio (nova tabela `emails_enviados`), mas
elimina o risco completamente.

```python
# pseudocódigo em email_sender.py
async def send_email(state):
    payload = state.get("email_payload")
    if not payload:
        return {"email_pending": False}
    
    agendamento_id = payload.get("agendamento_id")
    if agendamento_id and await email_already_sent(agendamento_id):
        return {"email_pending": False}  # idempotente: não envia de novo
    
    await _send_smtp(...)
    await mark_email_sent(agendamento_id)  # registra no DB
    return {"email_pending": False}
```

**Opção B — Aceitar o risco (decisão atual):**
- Crash entre `send_email` e run exit é um evento raro (requer crash de processo, não
  só falha de SMTP)
- A janela de vulnerabilidade é o tempo do último nó (`synthesize_tts`) + overhead do
  exit checkpoint (~200ms no Neon)
- Para um sistema médico MVP, email duplicado é incomum e o impacto é baixo (paciente
  recebe 2 confirmações — não é fatal)
- Se o risco for inaceitável em produção, trocar para `async` sem mudar código do agente

**Decisão atual**: aceitar o risco (Opção B) com registro desta lição como TODO para
Opção A quando o sistema entrar em produção real.

---

### 4. `DeltaChannel` — otimização de tamanho de checkpoint (deferida)

`DeltaChannel` e `durability: "exit"` são complementares mas independentes:

| Técnica | O que reduz | Mecanismo |
|---|---|---|
| `durability: "exit"` | **Frequência** de writes | 6 writes/turno → 1 write/turno |
| `DeltaChannel` | **Tamanho** de cada write | Armazena deltas, não estado completo |

**O problema que `DeltaChannel` resolve:**
O canal `messages` em `AgendAIState` usa `add_messages` (append-only). Sem `DeltaChannel`,
cada checkpoint armazena a lista **completa** de mensagens. Com 20 turnos de conversa,
o checkpoint do turno 20 armazena todas as 40+ mensagens anteriores — crescimento O(n²)
em armazenamento total ao longo da conversa.

Com `DeltaChannel`, o checkpoint armazena apenas os **deltas** (mensagens novas daquele
turno). O LangGraph reconstrói o estado completo fazendo replay dos deltas. Crescimento
linear em vez de quadrático.

**Implementação seria uma linha em `state.py`:**

```python
from langgraph.channels.delta import DeltaChannel

class AgendAIState(TypedDict):
    messages: Annotated[list[AnyMessage], DeltaChannel(add_messages)]  # era só add_messages
```

**Por que foi deferido:**
`DeltaChannel` está marcado como **beta** no LangGraph 1.2.0:

> *"Beta. The API and on-disk representation may change in future releases. Threads written
> with DeltaChannel today are expected to remain readable, but the surrounding contract
> is not yet stable."*

Riscos específicos para o managed LangGraph Server:
1. O servidor desserializa/reserializa o estado — se o formato `_DeltaSnapshot` mudar
   entre versões da imagem, threads antigas ficam ilegíveis
2. O contrato de `BaseCheckpointSaver.get_delta_channel_history` ainda não é estável
3. Não há garantia de compatibilidade forward com a imagem `langgraph/langgraph-server`

**Critério de ativação**: implementar quando `DeltaChannel` sair de beta (provavelmente
LangGraph 2.x) ou quando conversas longas (>20 turnos) forem o caso de uso dominante.
Para o AgendAI atual (consultas pontuais, 3–8 turnos por agendamento), o `exit` já resolve
o overhead crítico sem expor risco de instabilidade.

---

## Referências

- [ADR-025 — Estratégia de Checkpoint LangGraph](../adr/ADR-025-langgraph-checkpoint-strategy.md)
- [GitHub langchain-aws issue #806](https://github.com/langchain-ai/langchain-aws/issues/806)
- [vadim.blog — Durable Execution](https://vadim.blog/durable-execution-agents-that-survive-failure-and-resume-where-they-left-off)
- [langgraph-redis](https://github.com/redis-developer/langgraph-redis)
- [Aegra](https://github.com/ibbybuilds/aegra)
