# Feature Specification: LangGraph Medical Scheduling Orchestration

**Feature Branch**: `002-langgraph-orchestration`

**Created**: 2026-05-14

**Status**: Draft

---

## Clarifications

### Session 2026-05-14

- Q: Qual é a interface de chat para o paciente interagir com o agente? → A: Agent UI (open-source LangChain, Next.js) conectado ao servidor LangGraph Platform via `langgraph.json`
- Q: Qual linguagem para o serviço LangGraph? → A: Python (LangGraph Python v1.0+, LangSmith SDK, FastAPI)
- Q: Como o agente LangGraph integra com a API REST — MCP Server ou `@tool` + httpx direto? → A: `@tool` + httpx direto (v1); MCP Server documentado como evolução futura (v2)
- Q: Arquitetura dos nós de tool calling — loop nativo LangGraph ou switch manual? → A: Loop nativo via `StateGraph` + `ToolNode` + `tools_condition` (padrão v1.0+); NÃO usar `create_react_agent` pois os nós customizados de áudio/email/TTS exigem grafo próprio
- Q: Como o paciente envia áudio no Agent UI? → A: Agent UI customizado (fork de langchain-ai/agent-ui) com botão de upload de áudio adicionado; interface unificada para texto e áudio

---

## Overview

Substituir a camada de orquestração do N8N por um grafo de agentes construído com **LangGraph v1.0+**, mantendo exatamente os mesmos fluxos de atendimento médico já validados. Toda a lógica de negócio da API REST permanece intacta — apenas o orquestrador muda. A observabilidade de cada execução é garantida via **LangSmith**, com rastreamento de nós, decisões do LLM, chamadas de ferramentas e latências.

---

## User Scenarios & Testing

### User Story 1 — Paciente consulta horários por texto (Priority: P1)

O paciente envia uma mensagem de texto perguntando sobre horários disponíveis. O sistema interpreta a intenção, chama a API de disponibilidade e responde em linguagem natural com as opções.

**Why this priority**: É o fluxo mais básico e mais frequente. Sem ele, nenhum agendamento acontece.

**Independent Test**: Enviar `POST /chat` com `{"text": "Quais horários disponíveis?"}` e verificar que a resposta contém lista de horários e médicos sem erro.

**Acceptance Scenarios**:

1. **Given** o sistema está no ar, **When** o paciente envia texto com pergunta sobre horários, **Then** o sistema retorna lista de horários disponíveis com médico, especialidade, data e hora em linguagem natural
2. **Given** não há horários disponíveis, **When** o paciente pergunta, **Then** o sistema informa a ausência e sugere tentar novamente mais tarde
3. **Given** o paciente filtra por data, **When** pergunta "horários para segunda-feira", **Then** o sistema retorna apenas horários daquela data

---

### User Story 2 — Paciente agenda consulta por texto (Priority: P1)

O paciente confirma intenção de agendar. O sistema valida o paciente pelo e-mail, confirma o horário escolhido, grava o agendamento via API e envia e-mail de confirmação.

**Why this priority**: Agendamento é o objetivo central do produto.

**Independent Test**: Enviar sequência de mensagens culminando em `criar_agendamento` com e-mail e horário_id válidos e verificar que o banco registra o agendamento e um e-mail é disparado.

**Acceptance Scenarios**:

1. **Given** o paciente informou e-mail e horário, **When** o sistema confirma, **Then** o agendamento é gravado, o horário fica indisponível e um e-mail de confirmação chega ao paciente
2. **Given** o horário foi ocupado por outro paciente, **When** o sistema tenta agendar, **Then** informa que o horário não está mais disponível e oferece alternativas
3. **Given** o e-mail do paciente não existe no cadastro, **When** o sistema tenta buscar, **Then** informa que o paciente não foi encontrado e pede para verificar o e-mail

---

### User Story 3 — Paciente cancela consulta por texto (Priority: P2)

O paciente informa que quer cancelar uma consulta. O sistema cancela via API e envia e-mail de confirmação do cancelamento.

**Why this priority**: Cancelamentos liberam horários para outros pacientes.

**Independent Test**: Enviar mensagem com ID de agendamento ativo e verificar que o status muda para `cancelado` e e-mail é disparado.

**Acceptance Scenarios**:

1. **Given** o agendamento está ativo, **When** o paciente solicita cancelamento com o ID, **Then** o agendamento é cancelado e e-mail confirmando é enviado
2. **Given** o agendamento já está cancelado, **When** o paciente tenta cancelar novamente, **Then** o sistema informa que já foi cancelado
3. **Given** o paciente não sabe o ID, **When** ele pede para cancelar sem informar, **Then** o sistema solicita o ID do agendamento

---

### User Story 4 — Paciente envia áudio e recebe resposta em áudio (Priority: P2)

O paciente envia uma mensagem de voz. O sistema transcreve, processa com o mesmo fluxo de IA e retorna uma resposta em áudio.

**Why this priority**: Requisito de acessibilidade do desafio técnico — multimodalidade diferencia o produto.

**Independent Test**: Enviar `POST /chat` com arquivo de áudio e verificar que a resposta é um arquivo de áudio `.mp3` com conteúdo relevante.

**Acceptance Scenarios**:

1. **Given** o paciente envia arquivo de áudio, **When** o sistema recebe, **Then** transcreve o áudio, processa a intenção e retorna resposta em áudio .mp3
2. **Given** o áudio é inaudível ou corrompido, **When** a transcrição falha, **Then** o sistema retorna mensagem de erro orientando o paciente a tentar novamente
3. **Given** o áudio contém intenção de agendamento, **When** processado, **Then** o fluxo completo (validação, gravação, e-mail) executa normalmente

---

### User Story 5 — Desenvolvedor rastreia execuções no LangSmith (Priority: P2)

Toda execução do grafo é rastreada automaticamente no LangSmith. O desenvolvedor pode visualizar o caminho percorrido, as decisões do LLM, as chamadas de ferramentas e as latências de cada nó.

**Why this priority**: Observabilidade é requisito explícito e viabiliza depuração e otimização em produção.

**Independent Test**: Após qualquer interação via chat, acessar o projeto AgendAI no LangSmith e verificar que a execução aparece com todos os nós rastreados.

**Acceptance Scenarios**:

1. **Given** o sistema está configurado com credenciais LangSmith, **When** qualquer mensagem é processada, **Then** uma trace completa aparece no painel do LangSmith com todos os nós do grafo
2. **Given** uma chamada de ferramenta ocorre, **When** o nó executa, **Then** a trace registra o nome da ferramenta, parâmetros enviados e resposta recebida
3. **Given** o LLM toma uma decisão de roteamento, **When** decide qual nó seguir, **Then** a trace registra o raciocínio e a decisão com latência

---

### User Story 6 — Paciente consulta valores e formas de pagamento (Priority: P3)

O paciente pergunta quanto custa a consulta ou quais formas de pagamento são aceitas. O sistema retorna os dados cadastrados.

**Why this priority**: Funcionalidade de suporte à decisão do paciente, mas não bloqueia o agendamento.

**Independent Test**: Enviar mensagem "Quanto custa?" e verificar que a resposta contém valor e formas de pagamento.

**Acceptance Scenarios**:

1. **Given** o paciente pergunta sobre valores, **When** o sistema processa, **Then** retorna valor da consulta e formas de pagamento aceitas em linguagem natural

---

### Edge Cases

- O que acontece quando o LLM não identifica nenhuma intenção clara? → Resposta genérica de saudação/esclarecimento sem chamar ferramenta
- O que acontece quando a API REST está indisponível? → O sistema informa ao paciente que não foi possível completar a ação e sugere tentar novamente
- O que acontece quando o e-mail falha após 3 tentativas? → O agendamento/cancelamento é mantido no banco, mas o sistema registra o erro de e-mail como aviso ao paciente
- O que acontece com mensagens simultâneas de múltiplos pacientes? → Cada execução do grafo é independente e isolada

---

## Requirements

### Functional Requirements

- **FR-001**: O sistema DEVE expor um endpoint HTTP (`POST /chat`) que aceite texto ou arquivo de áudio como entrada e retorne texto ou áudio como saída
- **FR-002**: O sistema DEVE implementar um grafo de estados (LangGraph StateGraph) com nós correspondentes aos 4 fluxos anteriores do N8N: detecção de entrada, processamento de IA, pipeline de áudio e confirmação por e-mail
- **FR-003**: O LLM DEVE usar function calling com 5 ferramentas: `buscar_horarios_disponiveis`, `criar_agendamento`, `cancelar_agendamento`, `buscar_pagamentos`, `buscar_paciente`
- **FR-004**: O sistema DEVE integrar com a API REST existente (`http://api:3000`) para todas as operações de dados — nenhuma lógica de negócio deve ser duplicada no grafo
- **FR-005**: Quando a entrada for áudio, o sistema DEVE transcrever via OpenAI Whisper antes de passar ao LLM e sintetizar a resposta via OpenAI TTS antes de retornar
- **FR-006**: O sistema DEVE enviar e-mail de confirmação (via Gmail) após agendamentos e cancelamentos bem-sucedidos
- **FR-007**: Toda execução do grafo DEVE ser rastreada automaticamente no LangSmith com identificação do projeto `AgendAI`
- **FR-008**: O sistema DEVE responder no mesmo idioma em que o paciente escreveu (português ou inglês)
- **FR-009**: O sistema DEVE expor o grafo via servidor LangGraph Platform (`langgraph up`) com `langgraph.json`, e a interface do paciente é servida pelo **Agent UI** (Next.js open-source da LangChain), ambos orquestrados via `docker compose up --build -d`
- **FR-010**: O sistema DEVE manter compatibilidade com o banco SQLite existente — nenhuma migração de dados é necessária

### Key Entities

- **ConversationState**: Estado compartilhado entre os nós do grafo — contém mensagem de entrada (texto ou áudio), histórico de mensagens, resultado de ferramentas, resposta final e metadados de rastreamento
- **Tool**: Cada uma das 5 funções que o LLM pode invocar, mapeadas diretamente para endpoints da API REST
- **Trace**: Registro LangSmith de uma execução completa do grafo — contém nós percorridos, decisões, latências e erros
- **ChatRequest**: Payload de entrada do endpoint `/chat` — campo `text` (string) ou `audio` (arquivo binário)
- **ChatResponse**: Payload de saída — campo `text` (string) ou `audio` (arquivo `.mp3`)

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: Todos os 4 fluxos do desafio técnico funcionam com LangGraph sem regressão de comportamento em relação ao N8N
- **SC-002**: 100% das execuções do grafo geram uma trace visível no painel LangSmith do projeto AgendAI
- **SC-003**: O tempo de resposta para mensagens de texto não excede 10 segundos em condições normais de rede
- **SC-004**: O tempo de resposta para mensagens de áudio (incluindo transcrição e síntese) não excede 30 segundos
- **SC-005**: O sistema inicia com um único comando (`docker compose up --build -d`) sem etapas manuais adicionais
- **SC-006**: Os testes existentes da API REST continuam passando sem modificação (o grafo não toca a API)
- **SC-007**: Falhas em nós individuais (e-mail, TTS) não derrubam o fluxo principal — o sistema degrada graciosamente

---

## Assumptions

- A API REST (`api/`) permanece inalterada — o LangGraph consome seus endpoints como cliente HTTP
- O banco SQLite e os dados de seed existentes são aproveitados sem migração
- OpenAI é o provedor único de LLM (GPT-4o-mini), STT (Whisper) e TTS (tts-1) — uma única chave de API cobre os três
- A interface de chat com o paciente é exposta via endpoint HTTP próprio do serviço LangGraph (FastAPI ou Express), não mais pelo N8N Chat
- O serviço LangGraph roda como um container Docker adicional no `docker-compose.yml` existente
- As credenciais do Gmail (OAuth2) precisam ser reconfiguradas no novo serviço — o N8N não é mais responsável pelo envio
- O LangSmith requer `LANGCHAIN_API_KEY`, `LANGCHAIN_TRACING_V2=true` e `LANGCHAIN_PROJECT=AgendAI` nas variáveis de ambiente
- N8N permanece instalado no Docker Compose para não quebrar o ambiente existente, mas os fluxos ficam inativos
- Histórico de conversa é mantido em memória por sessão (sem persistência entre reinicializações do container)
- A versão do LangGraph utilizada é ≥ 1.0 (API estável com `StateGraph`, `ToolNode`, e suporte a streaming)
