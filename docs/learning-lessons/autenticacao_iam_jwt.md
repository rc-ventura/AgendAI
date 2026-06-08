# Learning Lesson: API-First, IAM, Autenticação Robusta e JWT

**Data**: 2026-06-07
**Contexto**: Base conceitual para implementação da Spec 006 (autenticação + sessão)
**Aplicado em**: [Spec 006](../../specs/006-auth-session/spec.md)

---

## 1. API-First e OAS3 — Design antes de código

A abordagem **API-First** inverte o fluxo tradicional: em vez de escrever o código e depois
documentar, você **especifica o contrato da API antes de qualquer implementação**.

O artefato central é o arquivo **OpenAPI Specification 3.x (OAS3)** — um YAML ou JSON que
descreve endpoints, parâmetros, schemas, respostas, e os **esquemas de segurança**.

**Por que isso importa:**
- Frontend, backend e QA trabalham em paralelo a partir do mesmo contrato
- A especificação vira a única fonte de verdade
- Swagger UI, Postman e Redoc consomem o arquivo diretamente
- Gera stubs de código (server/client) automaticamente via OpenAPI Generator

**Estrutura básica de um arquivo OAS3:**

```yaml
openapi: 3.0.3
info:
  title: AgendAI API
  version: 1.0.0

components:
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT

security:
  - BearerAuth: []   # aplica globalmente; endpoints públicos sobrescrevem com security: []

paths:
  /agendamentos/{id}:
    get:
      summary: Busca agendamento por ID
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Agendamento encontrado
        '401':
          description: Não autenticado
        '403':
          description: Sem permissão
```

O design conceitual acontece aqui: **recursos** (`/agendamentos`), **verbos HTTP** como
semântica de operação, **status codes** como linguagem de erro, e **schemas** como contrato
de dados — tudo antes de abrir o editor de código.

---

## 2. Identity and Access Management (IAM)

IAM responde a duas perguntas fundamentais:

| Pergunta | Conceito | Mecanismo |
|---|---|---|
| **Quem é você?** | Autenticação (AuthN) | Login, JWT, OAuth2 |
| **O que você pode fazer?** | Autorização (AuthZ) | Roles, Scopes, Policies |

**Autenticação** valida identidade — prova que o cliente é quem diz ser.
**Autorização** valida permissão — define o que essa identidade pode acessar.

**Modelos de autorização:**

- **RBAC** (Role-Based Access Control) — permissões associadas a papéis (`admin`, `paciente`,
  `medico`). Simples e amplamente usado. Ideal para o AgendAI fase 2.
- **ABAC** (Attribute-Based Access Control) — decisões baseadas em atributos do usuário, do
  recurso e do contexto. Mais granular e flexível. Fase 3+.
- **Scopes OAuth2** — permissões delimitadas por escopo (`read:agendamentos`,
  `write:agendamentos`). Usados em APIs públicas e integrações B2B.

```yaml
# OAS3 — scopes por operação
paths:
  /admin/relatorios:
    get:
      security:
        - OAuth2: [read:relatorios]
```

---

## 3. Autenticação e Autorização robustas

**Autenticação robusta** vai além de verificar senha:

- **MFA** — segundo fator por TOTP, SMS ou hardware key
- **Rate limiting** em endpoints de login para mitigar brute force
- **Refresh token rotation** — invalidar o refresh token após cada uso
- **Device fingerprinting** — detectar logins de dispositivos não reconhecidos

**Autorização robusta:**

- **Principle of Least Privilege** — cada identidade recebe apenas as permissões mínimas
- **Verificação sempre no servidor** — nunca confiar apenas no que o cliente envia
- **Middleware centralizado** — não espalhar lógica de autorização pelo código
- **Audit logs** — registrar quem acessou o quê e quando

**Fluxo com refresh token:**

```
[Cliente] → POST /auth/login  → { access_token (15min), refresh_token (7d) }
[Cliente] → GET /api/dados    → Authorization: Bearer <access_token>
                                  ↓ expirou?
[Cliente] → POST /auth/refresh → { novo access_token, novo refresh_token }
                                  (refresh token antigo é invalidado)
```

---

## 4. Segurança de APIs com JWT

O **JSON Web Token (JWT)** é o formato padrão stateless para APIs REST. Estrutura com três
partes separadas por `.`:

```
HEADER.PAYLOAD.SIGNATURE
eyJhbGci...  .eyJ1c2VyX...  .SflKxwRJSM...
```

**Header** — algoritmo de assinatura:
```json
{ "alg": "RS256", "typ": "JWT" }
```

**Payload** — claims (afirmações sobre o usuário):
```json
{
  "sub": "usr_9f3a2b",
  "name": "Tom Ventura",
  "roles": ["paciente"],
  "scope": "read:agendamentos write:agendamentos",
  "iat": 1749369600,
  "exp": 1749370500
}
```

**Signature** — com RS256, gerada com chave privada e verificada com chave pública.
Qualquer serviço com a chave pública pode verificar o token **sem consultar banco de dados**.

**Boas práticas críticas:**

| Prática | Por quê |
|---|---|
| Usar **RS256** (assimétrico) em vez de HS256 | Verificação distribuída sem compartilhar segredo |
| **Expiration curto** no access token (5–15 min) | Minimiza janela de uso após comprometimento |
| **Nunca armazenar JWT no localStorage** | Vulnerável a XSS — preferir httpOnly cookie |
| Validar **todas as claims** no servidor | `exp`, `iss`, `aud` verificados explicitamente |
| **Blacklist de tokens** para logout imediato | JWT é stateless; invalidação requer estado extra |
| Não colocar dados sensíveis no payload | Payload é Base64, não criptografado — é legível |

**No OAS3:**
```yaml
components:
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT

paths:
  /publico/ping:
    get:
      security: []     # endpoint público, sem auth
```

---

## Como tudo se conecta

```
OAS3 (contrato)
    └── define SecuritySchemes
            └── BearerAuth (JWT) com RS256
                    └── gerado pelo IAM layer
                            ├── AuthN: valida credenciais → emite JWT
                            └── AuthZ: verifica claims/roles/scopes no middleware
```

O ciclo API-First completo:
1. **Especificar o contrato** (OAS3 com security schemes)
2. **Implementar o IAM** (auth server, emissão de JWT com RS256)
3. **Proteger endpoints** com middleware que valida token e claims
4. **Documentar** com Swagger UI gerado automaticamente do mesmo YAML

---

## Aplicação no AgendAI (Spec 006)

| Conceito | Aplicação concreta |
|---|---|
| API-First / OAS3 | Criar `api/openapi.yaml` com security schemes antes de implementar auth |
| IAM AuthN | Clerk ou Auth0 emite JWT com `user_id` no `sub` |
| IAM AuthZ | RBAC: roles `paciente` / `medico` no payload do JWT |
| RS256 | Clerk/Auth0 já usam RS256 por padrão — nginx valida via JWKS endpoint |
| httpOnly cookie | UI armazena JWT em cookie httpOnly, não localStorage |
| Refresh token | Clerk/Auth0 gerenciam rotation automaticamente |
| Audit log | `user_id` propagado como `X-User-ID` → logs estruturados (P5 da Spec 005) |
| thread_id = user_id | JWT `sub` vira `thread_id` do LangGraph → sessão isolada por paciente |

---

## Referências

- [Spec 006 — Autenticação + Sessão](../../specs/006-auth-session/spec.md)
- [OAS3 Specification](https://spec.openapis.org/oas/v3.0.3)
- [RFC 7519 — JWT](https://datatracker.ietf.org/doc/html/rfc7519)
- [OAuth 2.0 — RFC 6749](https://datatracker.ietf.org/doc/html/rfc6749)
