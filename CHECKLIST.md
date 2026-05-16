# CHECKLIST de Testes — AgendAI

**Data**: 2026-05-12 | **Versão**: 1.0.0

---

## Cenários de Teste

| # | Cenário | Input | Esperado | Resultado | Status |
|---|---------|-------|----------|-----------|--------|
| 1 | Consultar horários disponíveis | `GET /horarios/disponiveis` | 200 — array JSON com médico, data_hora, disponivel=1 | _(preencher)_ | ⬜ |
| 2 | Agendar consulta | `POST /agendamentos` `{"paciente_email":"pedro@email.com","horario_id":3}` | 201 — objeto com status "ativo", e-mail enviado ao paciente | _(preencher)_ | ⬜ |
| 3 | Cancelar agendamento | `PATCH /agendamentos/1/cancelar` | 200 — `{"id":1,"status":"cancelado"}`, horário liberado, e-mail enviado | _(preencher)_ | ⬜ |
| 4 | Consultar pagamentos | `GET /pagamentos` | 200 — `[{"descricao":"Consulta Geral","valor":150,"formas":["PIX",...]}]` | _(preencher)_ | ⬜ |
| 5 | Entrada por áudio | `POST /webhook/chat` com arquivo .ogg | Resposta .mp3 com conteúdo em português; ou fallback texto se TTS falhar | _(preencher)_ | ⬜ |
| 6 | Horário já ocupado | `POST /agendamentos` com horario_id=1 (pré-ocupado) | 409 — `{"error":"Horário não está mais disponível"}` | _(preencher)_ | ⬜ |
| 7 | Paciente não encontrado | `POST /agendamentos` com `paciente_email:"fantasma@email.com"` | 404 — `{"error":"Paciente não encontrado"}` | _(preencher)_ | ⬜ |

---

## Testes Unitários

```bash
cd api && npm test
```

| Suite | Testes | Status |
|---|---|---|
| horarios.test.js | 4 | ⬜ |
| pacientes.test.js | 2 | ⬜ |
| agendamentos.test.js | 10 | ⬜ |
| pagamentos.test.js | 3 | ⬜ |
| cache.test.js | 3 | ⬜ |
| concurrency.test.js | 1 | ⬜ |
| validation.test.js | 11 | ⬜ |
| **Total** | **34** | ⬜ |

---

## Checklist de Entregáveis

| Item | Arquivo | Status |
|---|---|---|
| Código da API | `api/` | ✅ |
| Banco de dados com dados iniciais | `api/src/db/seed.js` | ✅ |
| Agente LangGraph | `agent/agent/graph.py` + `agent/agent/nodes/` | ✅ |
| Instruções de execução | `README.md` | ✅ |
| Coleção Postman | `postman/clinica.collection.json` | ✅ |
| Vídeo/GIF demonstrativo | `docs/demo.gif` | ⬜ |
| Checklist de testes e evidências | `CHECKLIST.md` | ✅ |

---

## Evidências

Adicionar prints em `docs/prints/` após execução:

- [ ] `docs/prints/01-horarios-disponiveis.png` — curl retornando horários
- [ ] `docs/prints/02-agendamento-criado.png` — POST /agendamentos 201
- [ ] `docs/prints/03-email-confirmacao.png` — e-mail recebido
- [ ] `docs/prints/04-cancelamento.png` — PATCH /cancelar 200
- [ ] `docs/prints/05-email-cancelamento.png` — e-mail de cancelamento
- [ ] `docs/prints/06-resposta-audio.png` — chat de áudio respondido
- [ ] `docs/prints/07-painel-html.png` — painel em http://localhost:3000/painel
- [ ] `docs/prints/08-langgraph-studio.png` — grafo executando no LangGraph Studio
- [ ] `docs/prints/09-testes-unitarios.png` — npm test todos passando

---

*Preencher coluna "Resultado" com a resposta real obtida e marcar Status como ✅ (passou) ou ❌ (falhou) após cada teste.*
