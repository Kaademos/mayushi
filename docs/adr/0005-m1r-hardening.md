# ADR-0005: Hardening of the identity and data platform (M1R)

- Status: Accepted (amends ADR-0004)
- Date: 2026-11-03

## Context

M0–M1 were built quickly. Reviewing them against the secure-by-design goals found shortcuts: committed default credentials (Keycloak `admin`/`admin`, a shared demo password in the realm export), `sslRequired=none`, a public browser client, a permissive CORS regex, an environment check that never matched the production value, stack traces in error responses, and runtime DB roles that owned their schemas.

## Decisions

1. **Credentials are generated locally, never committed.** `make bootstrap` writes 256-bit random values into `.env` (mode 600), never prints them, never overwrites strong values, and refuses short or default values unless `ROTATE=1`. Compose uses `${VAR:?}` so a missing secret stops the stack instead of falling back.
   - *Rejected:* Docker secrets files. Same protection locally with more moving parts; revisit when services read file-based secrets (M2c).
   - *Rejected:* defaults in compose "for convenience". This is exactly the failure mode being removed.
2. **Credentials that Keycloak needs at runtime are applied post-start** by `infra/keycloak/configure.sh` (web client secret, demo user passwords) over the admin API, passed on stdin. The realm export stays secret-free.
   - *Rejected:* templating secrets into the realm export at startup. That writes secrets to disk inside the container and makes the export non-reproducible.
3. **The web client becomes confidential** (client secret + S256 PKCE, exact redirect URI, no browser web origins), matching the BFF design in which tokens never reach browser JavaScript.
   - *Rejected:* keeping a public SPA client. It would put tokens in browser storage, contrary to the target architecture.
4. **Realm policy:** `sslRequired=external` (TLS required for non-private addresses; local development stays on HTTP), brute-force lockout, a length-only password policy (15–128 characters, per ASVS 5.0, which discourages composition rules), 5-minute access tokens, and single-use rotating refresh tokens.
   - *Rejected:* `sslRequired=all`. It needs TLS termination in front of Keycloak, which arrives with the edge network in M2c.
   - *Rejected:* password history. It makes reseeding fail (`make seed` resets the demo password), and ASVS 5.0 does not require it.
5. **JWT validation** pins issuer, audience and RS256/ES256, binds the header `alg` to the selected JWK, requires `typ=Bearer`, and uses a bounded JWKS cache (5-minute TTL; refetch on unknown `kid` at most every 30 s; keep cached keys during an IdP outage; fail closed when none are cached).
   - *Rejected:* PyJWT's `PyJWKClient`. It refetches on every unknown `kid`, so an attacker can make the gateway hammer the IdP; it also offers no outage fallback.
6. **Two DB roles per service.** `<svc>_migrator` owns the schema and runs only in one-shot `*-migrate` compose jobs (migrations and seeding). `<svc>_svc` gets explicit grants from migrations, deny by default. Long-running containers never hold owner credentials.
   - *Rejected:* running migrations in the service entrypoint with a privileged URL. Every runtime container would then carry DDL-capable credentials.
   - *Rejected:* `ALTER DEFAULT PRIVILEGES`. Implicit grants on future tables conflict with deny by default; explicit grants are reviewable in each migration.
7. **Dedicated Keycloak admin; the bootstrap admin is temporary.** Keycloak's `KC_BOOTSTRAP_ADMIN_*` values (their own generated pair) create a temporary admin on first start. `make seed` uses it once to create a permanent master-realm admin from `KEYCLOAK_ADMIN_*`, then deletes the temporary user. The bootstrap values left in the container environment no longer authenticate, and the dedicated admin's password is passed only to the one-off `exec`, never to container configuration.
   - *Rejected:* `kc.sh bootstrap-admin` as a separate one-shot. It starts a second Keycloak against the same database, which is meant for recovery, not routine setup.
   - *Rejected:* keeping the bootstrap admin as the permanent admin. Keycloak flags it as temporary, and its password sits in the container environment for the container's lifetime.

## Consequences

- Admin MFA (TOTP required action) is not yet enforced for the dedicated admin; it would break the scripted admin checks and is tracked as a follow-up.
- An existing `.env` with old placeholder values must be rotated (`make bootstrap ROTATE=1`), followed by `make reset` because role passwords are set when the volume is first initialised.
- Every future migration that adds a table must grant the runtime role explicitly; the live privilege-matrix test catches omissions and over-grants.
