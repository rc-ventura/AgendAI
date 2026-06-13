# Learning Lesson: Áudio multimodal sem WebSocket + multi-provider via LiteLLM

**Data**: 2026-06-09
**Contexto**: Pesquisa para a Spec 005 QW-6 (avaliação de modelos), antes de definir direção.
**Motivação**: Correções do usuário — "multimodal/realtime talvez não precise WebSocket, só
ajustar a chamada; realtime/multimodal dispensa transcribe e talvez TTS; usar modelo não-OpenAI
talvez exija LiteLLM com API router." (estava certo nos três pontos.)
**Aplicado em**: [Spec 005 — research R8/R10](../../specs/005-agent-hardening/research.md)

---

## Lição 1 — Áudio multimodal via REST **não precisa de WebSocket**

Eu havia assumido que reduzir a latência de áudio exigiria o Realtime API (WebSocket). **Errado.**
Existem três caminhos distintos, e só o terceiro precisa de WebSocket:

| Caminho | Transporte | Elimina nós | Latência | Mudança de arquitetura |
|---------|-----------|-------------|----------|------------------------|
| **(a) Groq Whisper** (drop-in) | REST | nenhum (Whisper→LLM→TTS) | STT ~0.3s (10× + rápido) | nenhuma — troca provider no `transcriber.py` |
| **(b) `gpt-4o-audio-preview`** | **REST (sem WebSocket)** | **`transcriber.py` + `tts.py`** | 1 chamada, ok p/ async | **simplifica grafo — 2 nós → 0** |
| **(c) GPT-4o Realtime** | WebSocket/WebRTC | transcribe + TTS | menor (full-duplex) | **maior — troca o harness SSE** |

**Chave**: `gpt-4o-audio-preview` (e `gpt-4o-mini-audio-preview`, mais barato) está na **Chat
Completions REST API** — recebe áudio base64 e devolve áudio numa **única chamada normal**,
dispensando Whisper **e** TTS. WebSocket só é necessário para conversa full-duplex (Realtime).

O fluxo de voz do AgendAI é **assíncrono** (gravar → responder), não full-duplex — então o
caminho (b) encaixa sem WebSocket e ainda **deleta 2 nós do grafo**.

- Custo (b): ~$0.06/min input, ~$0.24/min output (`mini-audio` mais barato).
- Trade-off: (b) é mais lento que (c) Realtime, mas muito mais simples; adequado para async.

> Fontes: [GPT-4o Audio model](https://developers.openai.com/api/docs/models/gpt-4o-audio-preview) ·
> [Audio in Chat Completions (Simon Willison)](https://simonwillison.net/2024/Oct/18/openai-audio/) ·
> [Realtime API](https://openai.com/index/introducing-the-realtime-api/)

**Direção (spike no B5)**: comparar (a) vs (b) por latência + qualidade pt-BR antes de cravar.
(c) Realtime fica deferido por mudar a arquitetura de streaming.

## Lição 2 — Trocar de provider de texto → **LiteLLM**, não SDK por provider

Para sair da OpenAI no LLM de texto (Nemotron, Grok, Gemini — tabela QW-6), rotear por **LiteLLM**
em vez de trocar de SDK a cada provider.

- **LiteLLM**: gateway unificado p/ 100+ providers em formato OpenAI, com cost tracking, fallback,
  load-balancing, caching.
- **Integração LangChain é first-party**: `ChatLiteLLM` (drop-in do `ChatOpenAI`) e
  **`ChatLiteLLMRouter`** (load-balancing + fallback entre providers), via `langchain-litellm`.
- **Dois formatos**:
  - **SDK**: trocar `ChatOpenAI` por `ChatLiteLLM` no `llm_core.py` (mínimo).
  - **Proxy**: gateway FastAPI self-hosted com `/chat/completions`, `/audio/speech`,
    `/audio/transcriptions`, virtual keys, budgets, fallbacks (controle central + observabilidade).

**Por que importa**: troca de provider vira **config, não reescrita**; o fallback do router
**complementa o P1** (outage do provider → modelo de fallback). Tool-calling confiável continua
sendo o gate duro antes de qualquer troca.

> Fontes: [BerriAI/litellm](https://github.com/BerriAI/litellm/) ·
> [LangChain LiteLLM integration](https://docs.langchain.com/oss/python/integrations/chat/litellm)

## Conexões

- O caminho (b) multimodal também poderia passar por LiteLLM Proxy (`/audio/*`) se quiséssemos
  um único gateway para texto **e** áudio multi-provider.
- Decisões finais ficam para os spikes B5 (áudio) e um batch futuro (multi-provider texto) — não
  cravar antes de medir. Ver [[arquitetura_redis_postgress]] para o princípio de medir-antes-de-otimizar.

## Referências

- [GPT-4o Audio model](https://developers.openai.com/api/docs/models/gpt-4o-audio-preview)
- [Audio in Chat Completions API](https://simonwillison.net/2024/Oct/18/openai-audio/)
- [OpenAI Realtime API](https://openai.com/index/introducing-the-realtime-api/)
- [LiteLLM (BerriAI)](https://github.com/BerriAI/litellm/)
- [LangChain × LiteLLM](https://docs.langchain.com/oss/python/integrations/chat/litellm)
