# Feature Specification: Spec 006 — Autenticação + Sessão Persistente por Usuário

**Feature Branch**: `006-auth-session`

**Created**: 2026-06-07

**Updated**: 2026-06-07

**Status**: Draft

**Depende de**: [Spec 005](../005-agent-hardening/spec.md) — retry e logs estáveis em produção  
**Desbloqueia**: [Spec 007](../007-memory-hitl/spec.md) — memória e HITL precisam de `user_id`  
**Learning Lesson**: [autenticacao_iam_jwt.md](../../docs/learning-lessons/autenticacao_iam_jwt.md)

---

## Why This Feature Exists

O AgendAI expõe um único token de serviço compartilhado (`LANGGRAPH_AUTH_TOKEN`). Qualquer
usuário com o token acessa dados de todos os outros e compartilha o mesmo contexto de conversa.
Sem identidade de usuário não é possível isolar sessões, construir memória por paciente ou
implementar HITL com estado persistente.

Esta spec entrega o `user_id` autenticado como primitivo central usando a abordagem
**API-First**: o contrato OAS3 com security schemes é especificado antes de qualquer
implementação, garantindo que auth seja tratado como contrato e não como afterthought.

---

## Abordagem: API-First com OAS3

Antes de implementar, o contrato da API é especificado em `api/openapi.yaml`:

```yaml
openapi: 3.0.3
info:
  title: AgendAI API
  version: 2.0.0

components:
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT   # RS256, emitido pelo provider (Clerk/Auth0)

  schemas:
    Agendamento:
      type: object
      properties:
        id: { type: integer }
        paciente_id: { type: string }  # = user_id do JWT
        medico_id: { type: integer }
        data_hora: { type: string, format: date-time }
        status: { type: string, enum: [ativo, cancelado] }

# Segurança global — todos os endpoints exigem JWT exceto os explicitamente públicos
security:
  - BearerAuth: []

paths:
  /health:
    get:
      security: []          # endpoint público, sem auth
      summary: Health check

  /agendamentos:
    get:
      summary: Lista agendamentos do usuário autenticado
      # Retorna apenas agendamentos onde paciente_id = JWT sub
      responses:
        '200':
          description: Lista de agendamentos
        '401':
          description: JWT ausente ou expirado
        '403':
          description: Tentativa de acessar dados de outro usuário
```

O OAS3 é gerado/validado em CI — nenhuma rota pode existir sem estar declarada no contrato.

---

## IAM — Identity and Access Management

### AuthN (Autenticação) — Quem é você?

**Decisão de provider:**

| Provider | Free tier | JWT/RS256 | nginx JWKS | SDK React | Complexidade |
|----------|-----------|-----------|------------|-----------|--------------|
| **Clerk** | 10k MAU | ✅ | ✅ automático | ✅ pronto | Baixa |
| **Auth0** | 7.5k MAU | ✅ | ✅ automático | ✅ pronto | Baixa |
| **Supabase Auth** | Ilimitado OSS | ✅ | Manual | ✅ | Média |
| **JWT próprio** | — | Manual | Manual | Manual | Alta |

**Recomendação: Clerk** — SDK React com componentes de login prontos, JWKS endpoint público
para nginx validar sem código extra, free tier generoso para early production.

**Fluxo de autenticação:**
```
Paciente abre a UI
    ↓
Clerk exibe tela de login (email/password ou OAuth social)
    ↓
Clerk emite JWT com RS256
    ├── Header: { "alg": "RS256", "kid": "key-id" }
    ├── Payload: { "sub": "user_clerk_xyz", "name": "João", "roles": ["paciente"], "exp": ... }
    └── Signature: verificável via JWKS público do Clerk
    ↓
UI armazena JWT em httpOnly cookie (nunca localStorage — vulnerável a XSS)
    ↓
Toda request inclui o cookie → nginx extrai e valida o JWT
```

### AuthZ (Autorização) — O que você pode fazer?

**Modelo: RBAC** (Role-Based Access Control) com dois papéis iniciais:

| Role | Permissões |
|------|-----------|
| `paciente` | Ver/criar/cancelar **seus próprios** agendamentos |
| `medico` | Ver agendamentos da **sua agenda** (somente leitura) |
| `admin` | Acesso total — reservado para operações de suporte |

Roles são incluídos no payload do JWT pelo Clerk/Auth0 e verificados no middleware da API:

```javascript
// api/src/middleware/auth.js
const { jwtVerify, createRemoteJWKSet } = require('jose')

const JWKS = createRemoteJWKSet(new URL(process.env.CLERK_JWKS_URL))

async function requireAuth(req, res, next) {
  const token = req.cookies['__session'] || req.headers.authorization?.split(' ')[1]
  if (!token) return res.status(401).json({ error: 'Não autenticado' })

  try {
    const { payload } = await jwtVerify(token, JWKS, {
      issuer: process.env.CLERK_ISSUER,
      audience: process.env.CLERK_AUDIENCE,
    })
    req.userId = payload.sub        // user_id propagado para todos os handlers
    req.userRoles = payload.roles ?? []
    next()
  } catch {
    res.status(401).json({ error: 'Token inválido ou expirado' })
  }
}

function requireRole(role) {
  return (req, res, next) => {
    if (!req.userRoles.includes(role)) {
      return res.status(403).json({ error: 'Sem permissão' })
    }
    next()
  }
}
```

**Principle of Least Privilege**: cada endpoint valida que o `userId` da request bate com o
`paciente_id` do recurso — impede que um paciente acesse dados de outro mesmo com JWT válido.

---

## Segurança JWT — Boas Práticas Aplicadas

| Prática | Implementação no AgendAI |
|---|---|
| **RS256** (assimétrico) | Clerk/Auth0 usam RS256 por padrão |
| **Access token curto** (15 min) | Configurado no Clerk dashboard |
| **httpOnly cookie** | UI configura cookie `__session` via Clerk SDK |
| **Refresh token rotation** | Clerk gerencia automaticamente |
| **Validar `exp`, `iss`, `aud`** | `jwtVerify` do pacote `jose` verifica todas |
| **Nenhum dado sensível no payload** | Só `sub`, `roles` e `exp` — sem CPF, email, etc. |
| **Audit log** | `userId` → header `X-User-ID` → logs estruturados (P5 Spec 005) |

---

## nginx — Validação JWT no edge

nginx valida o JWT antes de qualquer request chegar à API ou ao agente:

```nginx
# nginx/nginx.conf.template

# Validação JWT via módulo lua-resty-jwt ou sub-request ao Clerk
location /api/ {
    # Clerk oferece um endpoint de verificação de token
    auth_request /_clerk_verify;
    auth_request_set $user_id $upstream_http_x_user_id;

    proxy_set_header X-User-ID $user_id;
    proxy_pass http://api:3000/;
}

location /_clerk_verify {
    internal;
    proxy_pass https://api.clerk.com/v1/tokens/verify;
    proxy_set_header Authorization $http_authorization;
}
```

**Alternativa mais simples** (sem sub-request): usar `nginx-jwt` (OpenResty) ou delegar
validação inteiramente à API com overhead mínimo (JWKS cached localmente).

---

## Sessão Persistente por Usuário (P2)

Com `user_id` disponível, o thread_id do LangGraph passa a ser determinístico por usuário:

```typescript
// agent-ui-pro: criar ou recuperar thread do usuário autenticado
const { userId } = useAuth()  // Clerk hook

// Thread ID = user_id → sempre o mesmo por paciente
const thread = await client.threads.create({
  thread_id: userId,          // idempotente — reutiliza se já existe
  metadata: { user_id: userId }
})
```

**Resultado:**
- Histórico de conversa persiste entre sessões do mesmo paciente
- Paciente A não vê threads do Paciente B — isolamento por `thread_id`
- Sobrevive a redeploys (Postgres já é backend do LangGraph Server)
- Sidebar da UI lista apenas threads do usuário autenticado

**Evolução:**
```
Spec 006 (agora): thread_id = user_id → isolamento via LangGraph Server + Postgres
Fase 3:           Vertex AI Agent Engine Sessions → managed, HIPAA compliant
```

---

## Propagação de user_id pelo sistema

```
Clerk emite JWT (sub = user_id)
    ↓
nginx valida JWT → extrai sub → header X-User-ID
    ↓
API recebe X-User-ID → middleware injeta em req.userId
    ├── Logs estruturados: { request_id, user_id, endpoint, status }
    └── Query guard: WHERE paciente_id = req.userId (impede vazamento de dados)
    ↓
Agente recebe X-User-ID via API
    └── thread_id = user_id → LangGraph checkpointer isola sessão por paciente
```

---

## Acceptance Criteria

### P3 (Autenticação)
1. Usuário sem login tenta acessar a UI → redirecionado para tela de login do Clerk
2. Token expirado → refresh automático transparente ou redirect para login
3. nginx rejeita request sem JWT válido com 401 antes de chegar à API
4. `user_id` disponível como `req.userId` em todos os handlers da API
5. Dois pacientes logados simultaneamente não veem os dados um do outro
6. Endpoint `GET /agendamentos` retorna apenas agendamentos do `user_id` autenticado
7. Tentativa de acessar `GET /agendamentos/{id}` de outro paciente → 403

### P2 (Sessão persistente)
1. Paciente fecha o browser e reabre → histórico de conversa restaurado no sidebar
2. Redeploy do langgraph-server → threads anteriores continuam acessíveis
3. Thread ID da UI = `user_id` do JWT (verificável via LangSmith)
4. 70 pytest + 39 Jest continuam passando

### Contrato OAS3
1. `api/openapi.yaml` existe e é válido (lint no CI via `spectral`)
2. Todos os endpoints têm security scheme declarado (ou `security: []` explícito)
3. Swagger UI disponível em `GET /api-docs` no ambiente de desenvolvimento

---

## Escopo de implementação

| Componente | Mudança |
|-----------|---------|
| `agent-ui-pro/` | Integrar Clerk SDK — `<ClerkProvider>`, `<SignIn>`, `useAuth()` |
| `nginx/nginx.conf.template` | Validação JWT + propagação `X-User-ID` |
| `api/src/middleware/auth.js` | Novo — `requireAuth` + `requireRole` via `jose` |
| `api/src/app.js` | Registrar middleware de auth em todas as rotas privadas |
| `api/src/repositories/*.js` | Query guards: `WHERE paciente_id = $userId` |
| `api/openapi.yaml` | Novo — contrato OAS3 com BearerAuth scheme |
| `agent-ui-pro/src/` | `thread_id = userId` no client do LangGraph |

---

## Out of Scope desta spec

- Memory Management (fatos do paciente) → [Spec 007](../007-memory-hitl/spec.md)
- Human-in-the-Loop → [Spec 007](../007-memory-hitl/spec.md)
- Roles médico e admin (apenas `paciente` nesta spec)
- MFA / 2FA
- Compliance LGPD formal
- Integração com sistemas legados de cadastro de pacientes

---

## Referências

- [Learning Lesson: autenticacao_iam_jwt.md](../../docs/learning-lessons/autenticacao_iam_jwt.md)
- [Spec 005](../005-agent-hardening/spec.md) — prerequisito
- [Spec 007](../007-memory-hitl/spec.md) — desbloqueia
- [ADR-017](../../docs/adr/ADR-017-api-security-tokens.md) — token de serviço atual
- [ADR-025](../../docs/adr/ADR-025-langgraph-checkpoint-strategy.md) — checkpoint por user_id
- [Clerk Documentation](https://clerk.com/docs)
- [jose — JWT library for Node.js](https://github.com/panva/jose)
- [OAS3 Specification](https://spec.openapis.org/oas/v3.0.3)
