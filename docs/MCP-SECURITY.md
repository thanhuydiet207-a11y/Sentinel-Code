# MCP security configuration

This plugin declares GitHub, Sentry, and PostgreSQL MCP servers. The declarations configure connectivity; **they do not, by themselves, enforce read-only access**. Permissions must be restricted by the credentials and the remote service.

## PostgreSQL: enforce read-only access in PostgreSQL

The server name `postgres-readonly` and environment variable `SECOPS_READONLY_DATABASE_URL` are labels, not security controls. Use a dedicated login role that is not a member of application-owner, migration, administrator, or writer roles.

Example for a dedicated audit role (run as a database administrator; replace identifiers and set the password through a secure secret manager):

```sql
CREATE ROLE secops_audit
  LOGIN
  NOSUPERUSER
  NOCREATEDB
  NOCREATEROLE
  NOINHERIT
  NOREPLICATION
  NOBYPASSRLS;

GRANT CONNECT ON DATABASE appdb TO secops_audit;
\c appdb

GRANT USAGE ON SCHEMA public TO secops_audit;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO secops_audit;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO secops_audit;

-- Apply to objects created later by the actual object-owning role.
ALTER DEFAULT PRIVILEGES FOR ROLE app_owner IN SCHEMA public
  GRANT SELECT ON TABLES TO secops_audit;
ALTER DEFAULT PRIVILEGES FOR ROLE app_owner IN SCHEMA public
  GRANT SELECT ON SEQUENCES TO secops_audit;
```

Repeat schema grants for every schema the auditor needs. Run the default-privilege statements for each role that creates objects. Do not grant this role membership in writer roles; `NOINHERIT` alone is not a substitute for removing dangerous role memberships or preventing `SET ROLE`.

### Verify effective privileges

Run as an administrator after creating the role. The query reports any table where the audit role effectively has a write-capable privilege, including privileges obtained through role membership:

```sql
SELECT
  n.nspname AS schema_name,
  c.relname AS table_name,
  p.privilege
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
CROSS JOIN (VALUES ('INSERT'), ('UPDATE'), ('DELETE'), ('TRUNCATE'), ('REFERENCES'), ('TRIGGER')) AS p(privilege)
WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND has_table_privilege('secops_audit', c.oid, p.privilege)
ORDER BY 1, 2, 3;
```

Expected result: **zero rows**. Also verify the role cannot create objects in application schemas and review database-level privileges, inherited memberships, SECURITY DEFINER functions, and row-level security policies. PostgreSQL permissions are the enforcement boundary; do not rely on the MCP server name.

## GitHub credentials

Use a fine-grained token restricted to the required repository. Grant only the read permissions needed for repository contents, metadata, and pull-request review. Do not use an organization-wide or classic broad-scope token unless a documented feature requires it. Store it in `GITHUB_PERSONAL_ACCESS_TOKEN` through the environment or secret manager.

## Sentry credentials

Use a dedicated Sentry token with read-only project/event access for the projects being audited. Do not reuse an administrator token. Store it using the supported Sentry MCP authentication mechanism; do not commit it to `.mcp.json`.

## General requirements

- Never commit real credentials, connection strings, or tokens.
- Keep secrets out of command-line arguments and logs where possible.
- Rotate any credential that has been committed or exposed.
- Re-check effective permissions whenever the service account, database schema, or MCP server configuration changes.
