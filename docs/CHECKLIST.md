# CHECKLIST — Testes e Evidências AgendAI

> Cenários testados manualmente e via suite automatizada. Data dos testes: 2026-05-17 / 2026-05-18.

---

## Fluxos principais (chat)

| # | Cenário | Input | Esperado | Resultado | Status | Evidência |
|---|---|---|---|---|---|---|
| 1 | Saudação / tela inicial | Acesso à UI em `localhost:3002` | Chat exibe mensagem de boas-vindas e campo de entrada | Tela exibida corretamente com botões de mic e upload | ✅ | [chat-ui-tela-inicial.png](prints/chat-ui-tela-inicial.png) |
| 2 | Consultar horários disponíveis | `"Quais horários vocês têm?"` | Lista de horários com médico, data e hora | Agente consultou `GET /horarios/disponiveis` e retornou lista formatada | ✅ | [demo-consulta-horarios.mov](prints/demo-consulta-horarios.mov) |
| 3 | Agendar consulta via chat | `"Quero agendar para rafael.ventura1080@gmail.com no horário X"` | Confirmação de agendamento + e-mail enviado ao paciente | Agendamento criado, e-mail de confirmação recebido | ✅ | [email-confirmacao-agendamento.png](prints/email-confirmacao-agendamento.png) · [demo-agendamento-chat.mov](prints/demo-agendamento-chat.mov) |
| 4 | Cancelar agendamento via chat | `"Cancelar minha consulta ID X"` | Confirmação de cancelamento + e-mail enviado | Cancelamento confirmado, e-mail de cancelamento recebido | ✅ | [email-cancelamento-consulta.png](prints/email-cancelamento-consulta.png) · [demo-cancelamento-chat.mov](prints/demo-cancelamento-chat.mov) |
| 5 | Consultar formas de pagamento | `"Quais formas de pagamento vocês trabalha?"` | Valor da consulta (R$ 150) e formas aceitas (PIX, Débito, Crédito, Dinheiro) | Resposta correta com todos os dados da tabela `pagamentos` | ✅ | [chat-formas-pagamento.png](prints/chat-formas-pagamento.png) |
| 6 | Entrada por áudio | Upload de arquivo `.mp3` via botão de clipe | Agente transcreve com Whisper e responde em texto | Resposta gerada a partir da transcrição do áudio | ✅ | [demo-fluxo-audio.mov](prints/demo-fluxo-audio.mov) |

---

## Integrações externas

| # | Cenário | Esperado | Resultado | Status | Evidência |
|---|---|---|---|---|---|
| 7 | E-mail de confirmação de agendamento | Gmail recebe e-mail com médico, data/hora e assinatura AgendAI | E-mail recebido com assunto `AgendAI — Confirmação de consulta em 2026-05-27 16:00:00` | ✅ | [email-confirmacao-agendamento.png](prints/email-confirmacao-agendamento.png) |
| 8 | E-mail de cancelamento | Gmail recebe e-mail informando consulta cancelada | E-mail recebido com assunto `AgendAI — Consulta cancelada em 2026-05-19 11:00:00` | ✅ | [email-cancelamento-consulta.png](prints/email-cancelamento-consulta.png) |
| 9 | TTS — resposta em áudio | Input de áudio → agente responde com áudio | Agente devolveu arquivo de áudio ao chat | ✅ | [demo-fluxo-audio.mov](prints/demo-fluxo-audio.mov) |

---

## Erros semânticos da API

| # | Cenário | Input | Esperado | Resultado | Status | Evidência |
|---|---|---|---|---|---|---|
| 10 | Paciente não encontrado | `GET /pacientes/naoexiste@email.com` | `404 Paciente não encontrado` | Retornou `{"error": "Paciente não encontrado"}` com status 404 | ✅ | [postman-404-paciente-nao-encontrado.png](prints/postman-404-paciente-nao-encontrado.png) |
| 11 | Horário já ocupado | `POST /agendamentos` com `horario_id` já reservado | `409 Horário não está mais disponível` | Retornou `{"error": "Horário não está mais disponível"}` com status 409 | ✅ | [postman-409-horario-indisponivel.png](prints/postman-409-horario-indisponivel.png) |
| 12 | Agendamento não encontrado | `GET /agendamentos/999` | `404 Agendamento não encontrado` | Retornou `{"error": "Agendamento não encontrado"}` com status 404 | ✅ | [postman-404-agendamento-nao-encontrado.png](prints/postman-404-agendamento-nao-encontrado.png) |
| 13 | Agendamento já cancelado | `PATCH /agendamentos/:id/cancelar` em consulta já cancelada | `400 Agendamento já está cancelado` | Coberto por suite automatizada `agendamentos.test.js` | ✅ | [api-testes-39-passando.png](prints/api-testes-39-passando.png) |

---

## Painel de visualização

| # | Cenário | Esperado | Resultado | Status | Evidência |
|---|---|---|---|---|---|
| 14 | Painel HTML `GET /painel` | Tabela com todos agendamentos, status colorido (`ativo`/`cancelado`) | Painel com 10+ agendamentos, cores corretas, dados completos | ✅ | [painel-agendamentos.png](prints/painel-agendamentos.png) · [painel-agendamentos-browser.png](prints/painel-agendamentos-browser.png) |

---

## Arquitetura do agente (LangGraph Studio)

| # | Cenário | Resultado | Status | Evidência |
|---|---|---|---|---|
| 15 | Grafo LangGraph compilado e visualizado | Todos os nós visíveis: `detect_input_type`, `transcribe_audio`, `chat_with_llm`, `execute_tools`, `process_tool_results`, `send_email`, `synthesize_tts` | ✅ | [langgraph_studio.png](prints/langgraph_studio.png) |

---

## Suite de testes automatizados

### API REST — Jest (Node.js)

```bash
cd api && npm test
```

| Suite | Arquivo | Cobertura | Status |
|---|---|---|---|
| Agendamentos | `tests/agendamentos.test.js` | Criar, cancelar, listar, 409 conflito, 404 | ✅ |
| Validação | `tests/validation.test.js` | Campos obrigatórios, tipos inválidos | ✅ |
| Horários | `tests/horarios.test.js` | GET todos, filtro por data, cache TTL | ✅ |
| Cache | `tests/cache.test.js` | Invalidação ao criar/cancelar agendamento | ✅ |
| Pagamentos | `tests/pagamentos.test.js` | GET valor e formas | ✅ |
| Pacientes | `tests/pacientes.test.js` | Busca por e-mail, 404 | ✅ |
| Concorrência | `tests/concurrency.test.js` | Dois agendamentos simultâneos no mesmo horário | ✅ |

**Total: 39 testes, 7 suites — todos passando em 1.23s**

Evidência: [api-testes-39-passando.png](prints/api-testes-39-passando.png)

---

### Agente LangGraph — pytest (Python)

```bash
cd agent && uv run pytest
```

| Suite | Arquivo | Cobertura |
|---|---|---|
| API Client | `tests/test_api_client.py` | Singleton, chamadas HTTP, erros |
| Grafo | `tests/test_graph.py` | Compilação, edges, fluxo completo |
| Nós | `tests/test_nodes.py` | Cada node individualmente |
| Roteamento | `tests/test_routing.py` | Decisões de roteamento texto/áudio |
| Estado | `tests/test_state.py` | AgentState, mutações |
| Tool results | `tests/test_tool_result_processor.py` | Detecção de agendamento/cancelamento |

**Total: 70 testes — todos passando em 2.71s**

Evidência: [agente-testes-70-passando.png](prints/agente-testes-70-passando.png)

---

## Diferenciais verificados

| Diferencial | Implementação | Status |
|---|---|---|
| Function calling no LLM | GPT-4o-mini com 5 tools: `buscar_horarios`, `criar_agendamento`, `cancelar_agendamento`, `buscar_pagamentos`, `buscar_paciente` | ✅ |
| Retry e-mail | `tenacity` — 3 tentativas com backoff exponencial (`wait_exponential`) | ✅ |
| Retry TTS | `tenacity` — 3 tentativas em `tts.py` | ✅ |
| Cache de disponibilidade | `node-cache` TTL 60 s, invalidado em `POST /agendamentos` e `PATCH /cancelar` | ✅ |
| Painel de consultas | `GET /painel` → HTML com tabela colorida por status | ✅ |
| Testes unitários API | 39 testes Jest com banco SQLite em memória (`:memory:`), sem mocks | ✅ |
| Testes agente Python | 70 testes pytest cobrindo nodes, grafo, roteamento e estado | ✅ |

---

## Gravações de tela

| Arquivo | Conteúdo |
|---|---|
| [demo-consulta-horarios.mov](prints/demo-consulta-horarios.mov) | Consulta de horários disponíveis via chat |
| [demo-fluxo-audio.mov](prints/demo-fluxo-audio.mov) | Fluxo de áudio (upload + resposta) |
| [demo-agendamento-chat.mov](prints/demo-agendamento-chat.mov) | Agendamento via chat + confirmação |
| [demo-cancelamento-chat.mov](prints/demo-cancelamento-chat.mov) | Cancelamento via chat + confirmação |
