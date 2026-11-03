# ADR-0004: Identity, tenancy and data ownership

- Status: Accepted; decisions 2–4 amended by ADR-0005
- Date: 2026-11-02

## Context

M1 introduces identity (Keycloak) and the data platform. We need to decide how tenants are modelled, how the gateway trusts tokens, and how services share one Postgres instance.

## Decision

1. **Single realm, tenant as a user attribute.** One realm (`northwind`) holds both tenants. `tenant` is a declared user-profile attribute (options `northwind-retail`, `northwind-b2b`; users can view but not edit it). A protocol mapper emits it as the `tenant` claim. Staff accounts have a home tenant (`northwind-retail`).
2. **Public client with PKCE.** `mayushi-web` is a public client, standard flow with S256 PKCE, and no direct access grants. An audience mapper adds `mayushi-api` to access tokens, and the gateway requires it.
3. **Gateway token validation.** RS256 only, JWKS fetched from Keycloak over the internal network and cached for five minutes. Issuer is the public URL. Required claims: `exp`, `iat`, `iss`, `aud`, `sub`. The tenant claim must match an active row in `app.tenants`; roles are filtered to the three application roles.
4. **Schema per service.** One `mayushi` database, one schema and login role per service (`app` → `gateway_svc`, `orders` → `orders_svc`), each with its own Alembic version table. Keycloak uses a separate `keycloak` database.
5. **Seed linkage.** The Keycloak realm export fixes user IDs. `orders.customers.external_ref` holds those IDs for the six seeded customers. A unit test keeps the realm export and the seed account list in sync.

## Consequences

- Moving a user between tenants is an admin operation in Keycloak; tokens issued before the change remain valid until expiry (15 minutes).
- Staff tenancy is coarse (one home tenant). Cross-tenant staff tooling will need an explicit mechanism.
- Sharing one Postgres instance keeps the footprint small; isolation relies on per-schema roles rather than separate servers.
