# ADR-030 — Context Management: SummarizationMiddleware

**Status:** Accepted  
**Data:** 2026-06-12  
**Spec relacionada:** [Spec 005 — Agent Hardening (B8/US4)](../../specs/005-agent-hardening/spec.md)  
**Depende de:** [ADR-026](./ADR-026-create-agent-middleware-vs-manual.md) (create_agent + middleware)

---

## Contexto

FR-018 e FR-019 exigem que o sistema mantenha o contexto dentro do limite do modelo e
compacte (resuma) histórico antigo em vez de truncar abruptamente. O `create_agent` (ADR-026)
expõe `SummarizationMiddleware` built-in como o caminho oficial para isso.

---

## Decisão

**Usar `SummarizationMiddleware` built-in com trigger OR (messages | tokens) e `keep=("messages", 10)`.**

```python
# agent/agent/middleware.py
summarization_middleware = SummarizationMiddleware(
    "openai:gpt-4o-mini",
    trigger=[("messages", 30), ("tokens", 6000)],   # OR: dispara se qualquer um atingir
    keep=("messages", 10),
)
```

### Parâmetros escolhidos

| Parâmetro | Valor | Rationale |
|-----------|-------|-----------|
| `model` | `"openai:gpt-4o-mini"` | Mesmo modelo do agente — sem novo provider/custo de configuração |
| `trigger` | `[("messages", 30), ("tokens", 6000)]` | OR logic: cobre tanto conversas longas (30 msgs) quanto mensagens pesadas em tokens (transcrições de áudio / tool results volumosos). Um único threshold de mensagens não captura o segundo caso. |
| `keep` | `("messages", 10)` | Preserva os 5 turnos mais recentes verbatim; demais condensados no resumo |

### Notas de versão (langchain 1.3.1)

- `PIIMiddleware` com `apply_to_output=True` redige output em SSE stream somente em `langchain>=1.3.2`.
  Na versão atual, a redigação funciona no estado (state-level) mas não em text deltas de stream.
  **Ação**: atualizar para 1.3.2+ quando disponível; streaming redaction será automático.

- `TriggerClause` dict (AND logic: `trigger={"tokens": 4000, "messages": 10}`) documentado a partir
  de 1.3.2+. A sintaxe de lista (OR) já funciona em 1.3.1 e foi adotada.

### Limitação multimodal — se aplica ao fluxo de áudio

`input_detector.py` cria uma `HumanMessage` com `content=[{"type": "input_audio", "data": base64...}]`
e a injeta em `messages`. Isso significa que **bytes de áudio entram no histórico de mensagens**
e o aviso dos docs é relevante:

- Se a sumarização disparar, `get_buffer_string()` converte o `input_audio` em representação
  de string dict — sem sentido para o modelo de resumo. O resumo gerado para mensagens de áudio
  seria de baixa qualidade.
- A AIMessage de resposta do `gpt-audio` contém os bytes de áudio em `additional_kwargs["audio"]["data"]`
  e texto no `.content` — o texto seria resumido corretamente, mas os bytes sobreviveriam no `keep`.

**Por que não foi corrigido neste batch**: a solução natural (transcrever áudio → texto antes de
entrar em `messages`) conflita com o ganho do B5 (ADR-028) — `gpt-audio` faz transcrição +
resposta + síntese numa única chamada. Adicionar Whisper novamente desfaria essa otimização.

**Impacto prático**: conversas de agendamento tipicamente têm 4-8 turnos — abaixo dos thresholds
configurados (30 msgs / 6000 tokens). A sumarização provavelmente nunca dispara em áudio.

**Ação futura**: se monitoramento mostrar conversas de áudio longas, considerar armazenar a
transcrição de texto (do response do `gpt-audio`) na `HumanMessage` original retroativamente,
para que o sumarizador tenha texto ao invés de bytes.

### Posição no LLM_MIDDLEWARE

```python
LLM_MIDDLEWARE = [
    injection_guard_middleware,   # B7
    pii_email, pii_cpf, pii_phone, # B7 — PII redacted BEFORE summarization
    summarization_middleware,     # B8 — comes after PII (summary generated from redacted msgs)
    llm_circuit_breaker_middleware,
    _llm_retry_middleware,
    _tool_retry_middleware,
    api_circuit_breaker_middleware,
]
```

Summarization vem APÓS PII: o resumo é gerado a partir de mensagens já redigidas, garantindo
que PII não entre no texto do resumo (que é preservado no estado e pode aparecer em logs).

---

## Impacto: `_MAX_GRAPH_STEPS`

`SummarizationMiddleware` utiliza hooks `before_model`/`after_model` (state-level), que o
`create_agent` implementa como nós adicionais no subgrafo compilado. Cada invocação do LLM
consome mais passos do counter de recursão do LangGraph.

**Medição** (B8, 2026-06-12):
- Before B8 (8 middleware items): flow com 3 LLM calls usa ~24 steps → limit=25 suficiente
- After B8 (9 middleware items): mesmo flow usa ~30 steps → limit=25 **insuficiente**

**Ajuste**: `_MAX_GRAPH_STEPS` elevado de 25 → 60 em `agent/agent/graph.py`. Isso permite
5-6 rounds de LLM+tool numa conversa legítima, bem acima do uso normal (3-4 rounds) e ainda
suficientemente baixo para detectar loops infinitos antes de 1000 passos.

---

## Alternativas consideradas

### A) Truncar mensagens sem resumo

Remove mensagens antigas abruptamente. Viola FR-019 (preservar fatos críticos). Não adotado.

### B) Token-based trigger (`("tokens", N)`)

Trigger mais preciso mas requer token counting em cada turno. O `("messages", 30)` é simples,
determinístico, e adequado para o domínio (conversas de agendamento são estruturalmente
previsíveis em tamanho). Pode ser revisado com dados reais de produção.

### C) Modelo diferente para resumo (ex.: `gpt-4o-mini` separado com temperatura=0)

O middleware já usa `gpt-4o-mini` por default via string init. Um modelo separado não
traz benefício mensurável para resumos de conversas curtas de agendamento.

---

## Consequências

### Positivas

- SC-011: contexto nunca estoura o limite do modelo em conversas normais
- SC-008: custo por conversa fica estável — quando resumo dispara, o total de tokens enviados
  ao LLM na próxima chamada não cresce além de `keep` + tamanho do resumo
- Zero infra nova — `SummarizationMiddleware` é built-in, mesmo modelo, mesmo provider
- `context_summary: str | None` adicionado ao `AgendAIState` (observabilidade / debug)
- 91 pytest verdes (83 anteriores + 8 novos de B8)

### Negativas / riscos

- Trigger de 30 mensagens é conservador para sessões de agendamento (típicas: 4-8). Custo do
  resumo provavelmente zero em produção na fase inicial. Ajustar se monitoramento mostrar
  conversas longas frequentes.
- `_MAX_GRAPH_STEPS=60`: mais permissivo que o anterior (25). Loops infinitos seriam detectados
  apenas após ~60 steps em vez de 25. Aceitável — o limite de 1000 agents do framework ainda
  protege contra loops verdadeiramente infinitos.

### Condições que revisam esta decisão

1. Conversas médias em produção atingem 20+ mensagens frequentemente → reduzir `trigger`
2. Token counting mostra que 30 mensagens ≈ X tokens muito acima do threshold desejado →
   migrar para `trigger=("fraction", 0.6)` com profile do modelo

---

## Relação com outras decisões

- **ADR-026**: `SummarizationMiddleware` é o terceiro concern adicionado ao middleware stack
  (após resilience B6 e guardrails B7).
- **ADR-029**: Ordem no stack — summarization depois de PII para que o resumo seja gerado
  de mensagens já redigidas.
- **ADR-031** (B9): `context_summary` no estado pode ser incluído em structured logs para
  observabilidade do contexto ativo.
