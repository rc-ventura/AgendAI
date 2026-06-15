# ADR-023 — Substituir Gmail SMTP por Resend HTTP API

**Status:** Aceito e implementado

**Data:** 2026-06-03

---

## Contexto

O `email_sender.py` usa `smtplib` com Gmail SMTP na porta 465. Em setembro de 2025, o Render
bloqueou permanentemente as portas SMTP 25, 465 e 587 em todos os serviços do free tier para
prevenir abuso e spam. O resultado em produção era:

```
[email_sender] Failed after retries: RetryError[<Future ... raised OSError>]
```

O tenacity tentava 3 vezes com backoff exponencial (~40s total), bloqueando o nó `send_email`
e atrasando o `synthesize_tts` que vem depois no fluxo de áudio — causando timeouts de 7+
minutos no SSE.

Referência oficial: [Render Changelog — Free web services will no longer allow outbound traffic
to SMTP ports](https://render.com/changelog/free-web-services-will-no-longer-allow-outbound-traffic-to-smtp-ports)

---

## Decisão

Substituir `smtplib` (SMTP) por **Resend** (HTTP API) como provedor de email transacional.

O Resend usa HTTPS (porta 443) para envio — não afetado pelo bloqueio do Render. A interface
pública do nó (`send_email`) e a estrutura de estado (`email_payload`) não mudam.

---

## Alternativas consideradas

| Opção | Protocolo | Free tier | Decisão |
|-------|-----------|-----------|---------|
| Gmail SMTP (anterior) | SMTP 465 | — | Bloqueado no Render free |
| SendGrid | HTTP API | 100 emails/dia | Viável, mas exige domínio verificado |
| Mailgun | HTTP API | 1.000 emails/mês (trial) | Viável, mas trial limitado |
| Postmark | HTTP API | 100 emails/mês | Muito restrito |
| **Resend** | **HTTP API** | **3.000 emails/mês** | **Escolhido** |

O Resend foi escolhido por:
- Free tier generoso (3.000/mês) sem cartão de crédito
- SDK Python oficial (`pip install resend`)
- Permite usar `onboarding@resend.dev` como remetente sem domínio próprio (para portfólio/dev)
- API minimalista — substituição direta do bloco SMTP sem alterar a interface do nó

---

## Implementação

### Mudanças no código

`agent/agent/nodes/email_sender.py`:
- Remove `smtplib`, `MIMEText`, `MIMEMultipart`
- Adiciona `import resend`
- Substitui `_send_smtp` por `_send_resend`
- Mantém `@retry` do tenacity, `_build_message`, e a assinatura de `send_email`

`agent/pyproject.toml`:
- Adiciona `resend>=2.0` em `dependencies`

### Variáveis de ambiente

| Variável | Antes | Depois |
|----------|-------|--------|
| `GMAIL_USER` | Remetente SMTP | Removido |
| `GMAIL_APP_PASSWORD` | Senha SMTP | Removido |
| `RESEND_API_KEY` | — | API key do Resend (obrigatório para enviar) |
| `EMAIL_FROM` | — | Remetente (default: `AgendAI <onboarding@resend.dev>`) |

Para portfólio/dev, `onboarding@resend.dev` funciona sem verificação de domínio.
Para produção real, verificar um domínio próprio no painel do Resend.

### Fluxo com Resend

```
send_email node
  → _build_message() → (subject, html_body)
  → _send_resend() com @retry(3x)
    → resend.Emails.send(from, to, subject, html)
    → HTTPS POST api.resend.com/emails (porta 443)
    → Render não bloqueia ✓
```

---

## Consequências

### Positivas
- Email funciona em produção no Render free tier
- Remove o timeout de 40s no fluxo de áudio (nó `send_email` não bloqueia mais)
- `onboarding@resend.dev` elimina necessidade de Gmail App Password para portfólio
- Logs de entrega disponíveis no dashboard do Resend

### Negativas / Trade-offs
- Nova dependência externa (`resend` PyPI)
- Requer conta no Resend e `RESEND_API_KEY` no Render dashboard
- Com domínio `onboarding@resend.dev`, o remetente não é o email da clínica (aceitável para portfólio)
- Para produção real: verificar domínio próprio no Resend ($0 — só requer DNS)

---

## Relação com outras decisões

- **ADR-021** (LangSmith para observabilidade): o `send_email` agora aparece com latência
  real no trace — sem o ruído dos retries SMTP que mascaravam o tempo real do nó.
- **Spec 005** (Agent Hardening): o Circuit Breaker (P1) em `llm_core.py` é independente
  desta mudança. O retry do tenacity permanece em `email_sender.py` para falhas transientes
  do Resend API.
