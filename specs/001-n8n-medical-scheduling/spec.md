# Feature Specification: N8N Medical Scheduling Automation

**Feature Branch**: `001-n8n-medical-scheduling`

**Created**: 2026-05-12

**Status**: Draft

**Input**: Desafio Técnico — Especialista em Automações com IA e N8N

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 – Consultar Horários Disponíveis (Priority: P1)

O paciente interage com a interface de chat e pergunta quais horários estão
disponíveis para consulta médica. O sistema consulta a API de agendamentos e
responde com a lista de horários disponíveis, incluindo o nome e especialidade
do médico, data e hora.

**Why this priority**: Ponto de entrada para toda interação de agendamento. Sem
informação de disponibilidade nenhum agendamento pode ocorrer; é também a consulta
autônoma mais frequente.

**Independent Test**: Enviar a mensagem "Quais os horários disponíveis para
amanhã?" via chat e verificar que a resposta lista horários reais buscados da API
— sem criar nenhum agendamento.

**Acceptance Scenarios**:

1. **Given** o paciente envia mensagem de texto perguntando horários disponíveis,
   **When** o sistema processa a requisição,
   **Then** responde com lista atualizada de data/hora e médico recuperada da API.

2. **Given** não há horários disponíveis para a data solicitada,
   **When** o sistema recebe a consulta,
   **Then** informa o paciente e sugere a próxima data disponível.

3. **Given** a API de agendamentos está temporariamente indisponível,
   **When** o sistema recebe a consulta,
   **Then** responde com mensagem de erro amigável e orienta o paciente a tentar novamente.

---

### User Story 2 – Realizar Agendamento (Priority: P1)

O paciente solicita um agendamento para um horário específico. O sistema registra
o agendamento via API (identificando o paciente pelo e-mail), persiste no banco de
dados e envia e-mail de confirmação para o endereço cadastrado do paciente.

**Why this priority**: Transação principal do sistema — razão de existência da solução.
A maioria das consultas de disponibilidade leva diretamente aqui.

**Independent Test**: Enviar solicitação de agendamento informando e-mail do paciente
e ID do horário desejado; verificar que (a) o horário não aparece mais como disponível,
(b) um registro de agendamento existe no banco e (c) e-mail de confirmação chega ao
endereço do paciente.

**Acceptance Scenarios**:

1. **Given** o paciente solicita um horário disponível identificando-se pelo e-mail,
   **When** o sistema processa o agendamento,
   **Then** o agendamento é registrado no banco, o horário marcado como indisponível
   e e-mail de confirmação enviado em até 60 segundos.

2. **Given** o paciente solicita um horário já ocupado,
   **When** o sistema tenta o agendamento,
   **Then** informa que o horário não está mais disponível e oferece alternativas.

3. **Given** o e-mail informado pelo paciente não está cadastrado,
   **When** o sistema valida os dados,
   **Then** responde com mensagem de erro clara sem criar registro algum.

4. **Given** a entrega do e-mail de confirmação falha na primeira tentativa,
   **When** o sistema detecta a falha,
   **Then** realiza até 3 tentativas adicionais; o agendamento permanece confirmado
   independentemente do resultado da entrega do e-mail.

---

### User Story 3 – Cancelar Agendamento (Priority: P2)

O paciente solicita o cancelamento de um agendamento existente. O sistema atualiza
o status do agendamento para cancelado via API, libera o horário e envia e-mail de
confirmação de cancelamento.

**Why this priority**: Essencial para o ciclo completo de agendamento; menos frequente
que o agendamento mas necessário para consistência operacional.

**Independent Test**: Dado um agendamento confirmado, enviar solicitação de cancelamento;
verificar que o horário volta a aparecer como disponível e e-mail de cancelamento é recebido.

**Acceptance Scenarios**:

1. **Given** o paciente solicita cancelamento de um agendamento existente,
   **When** o sistema processa a requisição,
   **Then** o status do agendamento é atualizado para "cancelado" no banco, o horário
   fica disponível novamente e e-mail de cancelamento é enviado.

2. **Given** o paciente informa um ID de agendamento inexistente ou já cancelado,
   **When** o sistema valida a requisição,
   **Then** responde com mensagem de erro clara sem alterar nenhum registro.

---

### User Story 4 – Consultar Valores e Formas de Pagamento (Priority: P2)

O paciente pergunta sobre valores de consulta e formas de pagamento aceitas. O
sistema retorna as informações configuradas diretamente do banco de dados, sem
precisar de chamada a serviço externo.

**Why this priority**: Pergunta frequente antes de confirmar agendamento; menor
complexidade de dados que os fluxos de agendamento.

**Independent Test**: Enviar mensagem "Quanto custa a consulta e quais formas de
pagamento vocês aceitam?" e verificar resposta completa com valor e formas aceitas.

**Acceptance Scenarios**:

1. **Given** o paciente pergunta sobre valores ou formas de pagamento,
   **When** o sistema processa a requisição,
   **Then** responde com os valores das consultas e lista de formas de pagamento aceitas
   em formato claro e legível.

---

### User Story 5 – Interação Multimodal: Áudio Entrada, Áudio Saída (Priority: P3)

O paciente envia mensagem de voz para a interface de chat. O sistema transcreve o
áudio, processa a intenção (ex: agendamento, consulta de horários) e responde com
mensagem de áudio sintetizado.

**Why this priority**: Capacidade diferenciadora que melhora acessibilidade, mas não é
pré-requisito para o funcionamento do agendamento principal.

**Independent Test**: Enviar arquivo de áudio perguntando horários disponíveis via
webhook de chat; verificar que (a) a intenção é corretamente identificada e (b) a
resposta contém arquivo de áudio reproduzível.

**Acceptance Scenarios**:

1. **Given** o paciente envia mensagem de áudio,
   **When** o sistema recebe via webhook de chat,
   **Then** o áudio é transcrito, a intenção processada identicamente a uma mensagem
   de texto, e a resposta retornada como arquivo de áudio sintetizado (.mp3).

2. **Given** o serviço de síntese de voz (TTS) está temporariamente indisponível,
   **When** o sistema tenta a síntese,
   **Then** realiza até 3 tentativas e, ao falhar em todas, retorna resposta em texto
   informando o paciente sobre o fallback.

---

### User Story 6 – Saudação e Encerramento (Priority: P3)

O paciente inicia ou encerra a conversa com saudação ou despedida. O sistema responde
de forma amigável sem consultar nenhuma API externa.

**Why this priority**: Melhora experiência do usuário e humaniza a interação. Não
requer integração — é tratada diretamente pelo LLM.

**Independent Test**: Enviar "Olá" e "Tchau" separadamente; verificar que o sistema
responde de forma contextualmente adequada sem chamar nenhum endpoint da API.

**Acceptance Scenarios**:

1. **Given** o paciente envia saudação ("Olá", "Bom dia", etc.),
   **When** o sistema processa a mensagem,
   **Then** responde com cumprimento amigável e apresenta as opções disponíveis.

2. **Given** o paciente sinaliza encerramento ("Obrigado", "Até logo", etc.),
   **When** o sistema processa a mensagem,
   **Then** responde com despedida cordial sem chamar nenhuma API externa.

---

### Edge Cases

- O que acontece quando o paciente envia mensagem ambígua que não corresponde a
  nenhuma intenção reconhecida?
- Como o sistema lida com dois pacientes tentando agendar o mesmo horário simultaneamente?
- O que acontece se o e-mail do paciente for inválido ou retornar bounce permanente?
- Como o sistema se comporta quando a transcrição de áudio produz resultado de baixa
  confiança?
- O que acontece se o banco de dados estiver indisponível durante um agendamento?
- O que acontece se o paciente tentar cancelar um agendamento já cancelado?

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema DEVE expor uma API REST com endpoints para: listar horários
  disponíveis, criar agendamento, cancelar agendamento (atualizar status — não deletar),
  buscar paciente por e-mail e retornar informações de valores e pagamento.
- **FR-002**: A API REST DEVE persistir todos os dados em banco SQLite e popular o banco
  com dados fictícios de pacientes, médicos, horários e pagamentos na primeira execução.
- **FR-003**: O banco DEVE ter pelo menos 3 médicos de especialidades diferentes, 5 pacientes
  com e-mail e telefone, 10 horários distribuídos nos próximos 7 dias e 1 registro de
  pagamento com valor e formas aceitas.
- **FR-004**: O agendamento DEVE identificar o paciente pelo e-mail (não por ID numérico).
- **FR-005**: O cancelamento DEVE atualizar o status do agendamento para "cancelado" e
  liberar o horário — NUNCA deletar o registro.
- **FR-006**: O fluxo N8N DEVE conectar-se à API REST para atender consultas de
  disponibilidade, agendamento, cancelamento e pagamento recebidas via chat.
- **FR-007**: O sistema DEVE detectar se a mensagem do paciente é texto ou áudio e
  rotear para o caminho de processamento adequado.
- **FR-008**: Para entrada de texto o sistema DEVE responder em texto.
- **FR-009**: Para entrada de áudio o sistema DEVE transcrever, processar a intenção e
  responder com arquivo de áudio sintetizado; em caso de falha no TTS após retentativas
  DEVE retornar resposta em texto.
- **FR-010**: O sistema DEVE enviar e-mail de confirmação via Gmail API em todo
  agendamento realizado com sucesso.
- **FR-011**: O sistema DEVE enviar e-mail de confirmação via Gmail API em todo
  cancelamento realizado com sucesso.
- **FR-012**: A entrega de e-mail DEVE ser tentada até 3 vezes antes de reportar falha;
  o agendamento NÃO DEVE ser revertido por falha de entrega de e-mail.
- **FR-013**: A síntese de áudio (TTS) DEVE ser tentada até 3 vezes antes do fallback
  para texto.
- **FR-014**: O fluxo N8N DEVE tratar saudação e encerramento respondendo diretamente,
  sem consultar a API REST.
- **FR-015**: O repositório DEVE incluir os fluxos N8N exportados como JSON (4 arquivos:
  flow-a-entrada, flow-b-ai-core, flow-c-audio, flow-d-email).
- **FR-016**: O repositório DEVE incluir coleção Postman ou Insomnia cobrindo todos os
  endpoints da API REST.
- **FR-017**: O repositório DEVE incluir README com instruções passo a passo de
  instalação, configuração e testes.
- **FR-018**: O repositório DEVE incluir CHECKLIST.md com cenários testados e evidências.
- **FR-019**: A API DEVE implementar cache de disponibilidade de horários com TTL de 60s,
  invalidado automaticamente em todo agendamento ou cancelamento.
- **FR-020**: O sistema DEVE incluir painel de visualização de agendamentos acessível
  via endpoint da API (diferencial implementado).

### Key Entities

- **Paciente** (`pacientes`): Pessoa fictícia com nome, e-mail único e telefone; o
  e-mail é o identificador natural utilizado pelo sistema para busca e agendamento.
- **Médico** (`medicos`): Profissional de saúde associado aos horários; tem nome e
  especialidade. Seed deve conter pelo menos 3 médicos de especialidades distintas.
- **Horário** (`horarios`): Bloco de tempo associado a um médico; armazena data e hora
  no formato ISO 8601 unificado (`data_hora`); tem flag de disponibilidade.
- **Agendamento** (`agendamentos`): Vínculo entre paciente e horário; status é
  `ativo` ou `cancelado`; nunca deletado após criação.
- **Pagamento** (`pagamentos`): Configuração de tipo de consulta, valor em R$ e
  formas de pagamento aceitas (array JSON).

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: O paciente recebe lista de horários disponíveis em até 5 segundos após
  enviar a consulta via chat.
- **SC-002**: Um agendamento é processado por completo (registro + e-mail enviado) em
  até 30 segundos da mensagem do paciente em condições normais.
- **SC-003**: Um cancelamento é processado por completo (status atualizado + e-mail
  enviado) em até 30 segundos da mensagem do paciente.
- **SC-004**: Uma mensagem de áudio é transcrita, processada e respondida com áudio
  em até 60 segundos do recebimento.
- **SC-005**: Todas as seis intenções de chat (horários, agendamento, cancelamento,
  pagamento, saudação, encerramento) são tratadas corretamente em 100% dos cenários
  documentados no CHECKLIST.md.
- **SC-006**: A API retorna respostas corretas para todos os endpoints da coleção
  Postman sem nenhuma configuração manual além das variáveis de ambiente.
- **SC-007**: Um avaliador consegue instalar e executar a solução completa seguindo
  apenas o README, sem orientação adicional.

---

## Assumptions

- A solução roda em instância N8N self-hosted via Docker; não é necessária conta N8N
  Cloud.
- Os dados de pacientes e médicos são inteiramente fictícios e pré-populados no seed;
  nenhum dado real é utilizado.
- As credenciais OAuth2 do Gmail são configuradas diretamente nas credenciais do N8N
  (não na API); o README documenta o passo a passo com prints.
- O provedor TTS padrão é OpenAI TTS (`tts-1`, voz `alloy`); o provedor é configurável
  via variável de ambiente.
- Os horários são pré-gerados no seed para os próximos 7 dias; geração dinâmica de
  slots está fora do escopo.
- Entrada de áudio chega como arquivo binário (.ogg, .mp3, .wav) via Chat Trigger do
  N8N; streaming de áudio em tempo real está fora do escopo.
- O sistema não implementa autenticação de pacientes — qualquer mensagem enviada ao
  webhook é tratada como interação válida; endurecimento de segurança está fora do
  escopo deste desafio.
- O cache de disponibilidade e o painel de visualização são diferenciais
  implementados — não opcionais.
