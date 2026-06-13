# Learning Lesson — Context Management: SummarizationMiddleware (B8)

**Batch:** B8 · **Data:** 2026-06-12

---

## L1 — Cada middleware state-level (`before_model`/`after_model`) adiciona nós ao subgrafo compilado

**O que**: o `create_agent` implementa hooks `before_model`/`after_model` como **nós separados**
no subgrafo compilado — não são chamadas inline. Cada nó adicional consome steps do recursion
counter do LangGraph na transição de estado.

**Por que importa**: `_MAX_GRAPH_STEPS` deve ser calibrado considerando o número de middlewares
state-level, não só o número de LLM calls. Fórmula aproximada:
`steps_por_flow ≈ n_llm_calls × (1 + 2 × n_middlewares_state_level) + n_tool_calls + n_outer_nodes`

**Regra**: ao adicionar middleware com `before_model`/`after_model`, re-medir o step count
com um test de flow real e ajustar `_MAX_GRAPH_STEPS` se necessário.

---

## L1b — `SummarizationMiddleware` adiciona steps ao grafo LangGraph (medição B8)

**O que**: o `create_agent` implementa hooks `before_model`/`after_model` como nós adicionais
no subgrafo compilado. Cada middleware com esses hooks adiciona passos ao counter de recursão.

**Impacto medido**: adicionar 1 `SummarizationMiddleware` elevou o consumo de steps por flow
de ~24 para ~30 (delta de ~6 steps para um flow com 3 LLM calls). `_MAX_GRAPH_STEPS` ajustado
de 25 → 60.

---

## L2 — `SummarizationMiddleware` vem DEPOIS dos PII middlewares

**Por quê**: o middleware gera um resumo das mensagens armazenadas no estado. Se PII já foi
redigido nas mensagens antes do resumo, o texto do resumo também será sem PII. Ordem inversa
(summarization antes de PII) faria o resumo conter dados sensíveis que depois seriam
parcialmente redigidos — mas o texto do resumo em si (salvo em estado) ficaria com PII.

---

## L3 — `abefore_model` com `_ensure_message_ids` muta mensagens mesmo retornando `None`

**O que**: `SummarizationMiddleware.abefore_model` chama `_ensure_message_ids` (que atribui
UUIDs a mensagens sem ID) ANTES de verificar o threshold. Quando o threshold não é atingido,
retorna `None` — mas a mutação in-place já ocorreu.

**Implicação para testes**: ao inspecionar `result is None` em `before_model`, as mensagens
no estado JÁ têm IDs mesmo quando nenhuma sumarização aconteceu. Isso é seguro para o
`add_messages` reducer do LangGraph (mensagens com ID são atualizadas, não duplicadas).

---

## L4 — `trigger=("messages", N)` vs `trigger=("fraction", X)` vs `trigger=("tokens", N)`

| Estratégia | Quando usar |
|------------|-------------|
| `("messages", 30)` | Domínio com conversas previsíveis em tamanho; simples de calibrar e testar |
| `("tokens", 8000)` | Quando custo por token é a preocupação central; mais preciso, mais caro de computar |
| `("fraction", 0.7)` | Quando o modelo tem `profile.max_input_tokens` configurado; auto-adapta a qualquer modelo |

Para agendamento médico (conversas de 4-8 turnos), `("messages", 30)` é conservador o
suficiente e zero custo de token counting em contextos normais.

---

## L5 — Resumo é gerado a partir das mensagens, não de `context_summary`

O `SummarizationMiddleware` não lê nem escreve o campo `context_summary` do estado — ele
opera diretamente sobre `messages`. O campo `context_summary: str | None` foi adicionado ao
`AgendAIState` para uso futuro (observabilidade, B9), mas não é preenchido automaticamente
pelo middleware. Se quiser o texto do resumo no estado, seria necessário um custom subclass
ou um hook pós-sumarização.
