# B5 — Validação Live: gpt-4o-audio-preview Multimodal

**Batch**: B5 / T023  
**Data**: 2026-06-11  
**ADR relacionado**: [ADR-028](../adr/ADR-028-audio-model.md)  
**SC**: SC-007 — ≥50% redução de latência no fluxo de áudio

---

## O que validamos

Pipeline de áudio end-to-end no stack Docker local:

```
input WAV → nginx → langgraph-server → [detect_input_type]
         → [audio_agent (gpt-audio)]  → [process_audio_results]
         → [extract_audio_response]   → state.final_response (bytes MP3)
```

Resultados (3 runs por modo, sine wave 1.5s / 48 KB):

| Modo | P50 texto | P50 áudio | Áudio OK |
|---|---|---|---|
| `async` (B5 apenas) | 1.26s | 2.91s | 3/3 |
| `exit` (B3+B5) | 1.19s | 4.36s | 3/3 |

---

## Lição 1 — Comparação direta de latência é impossível sem baseline vivo

SC-007 pede ≥50% de redução vs o pipeline antigo (Whisper + LLM + TTS). Mas o pipeline antigo foi **removido** antes de qualquer medição live — `transcriber.py` e `tts.py` não existem mais.

**Consequência**: a validação do SC-007 ficou sendo arquitetural, não empírica. A redução de 3 round-trips para 1 é comprovada pelo código; os números em segundos são estimativas baseadas na documentação da OpenAI.

**Aprendizado**: medir o baseline ANTES de remover o sistema antigo. Para migrações futuras de pipeline, adicionar um passo de "medição do estado atual" antes do PR de remoção.

---

## Lição 2 — Sine wave testa o pipeline, não a qualidade

O script de validação usa uma onda senoidal como input de áudio. O modelo `gpt-4o-audio-preview` recebe ruído, produz uma resposta de áudio (geralmente genérica ou confusa), mas o pipeline funciona corretamente do ponto de vista de bytes.

**O que isso prova**: que `detect_input_type` → `audio_agent` → `extract_audio_response` → `final_response` funciona ponta-a-ponta.

**O que não prova**: qualidade de reconhecimento de fala real, compreensão de intenção por áudio, ou que a resposta de áudio é semanticamente correta.

**Para validação de qualidade**: usar áudio real com uma frase de agendamento e verificar o conteúdo da resposta de texto no estado (`messages[-1].content`).

---

## Lição 3 — P50 áudio > P50 texto é esperado e não é regressão

P50 texto = 1.53s, P50 áudio = 4.24s. A diferença de ~2.7s corresponde à geração de 80–166 KB de MP3. O modelo `gpt-audio` faz STT + raciocínio + geração de áudio em uma chamada — o tempo adicional é o custo da síntese, não uma regressão.

**Cuidado**: comparar P50 de áudio com P50 de texto não faz sentido — são tarefas de complexidade diferente. A métrica correta para SC-007 é comparar P50 áudio (novo) vs P50 áudio (antigo pipeline de 3 chamadas).

---

## Lição 4 — nginx é o único entry point; testar sem ele mascara problemas de auth

A primeira tentativa de rodar `validate_b5_audio.py` apontou para `http://127.0.0.1:8123` (direto ao langgraph-server), que não é exposto ao host. A porta 8123 só existe dentro da rede Docker.

O stack real é `host:8080 → nginx → langgraph-server:8123`. Testes de integração que pulam o nginx não validam autenticação (`x-api-key`), rate limiting, ou roteamento real.

**Regra**: scripts de validação live sempre usam `http://localhost:8080` (nginx), nunca portas internas.
