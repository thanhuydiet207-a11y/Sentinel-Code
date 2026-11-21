# MCP security configuration

The repository's `.mcp.json` is a Claude Code configuration. MCP server declarations provide connectivity, not security boundaries. Every server's credentials and remote permissions must be scoped independently.

## PostgreSQL

The server name `postgres-readonly` and environment variable `SECOPS_READONLY_DATABASE_URL` are labels, not enforcement. Use a dedicated database role that is not a member of writer, owner, migration, administrator, or superuser roles. Grant only the required `CONNECT`, schema `USAGE`, and `SELECT` privileges. Review inherited memberships, `SET ROLE`, row-level security, SECURITY DEFINER functions, and default privileges.

Verify effective write privileges as an administrator. This query should return zero rows for the audit role:

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

## GitHub

Use a fine-grained token restricted to the required repository. Grant only read permissions needed for repository contents, metadata, and pull-request review. Avoid broad classic tokens and organization-wide credentials unless a documented feature requires them. Store the credential in `GITHUB_PERSONAL_ACCESS_TOKEN` through the environment or a secret manager.

## Sentry

The configured Sentry HTTP MCP endpoint may require an OAuth flow or another supported authentication setup. Do not assume the endpoint is authenticated merely because it is listed in `.mcp.json`. Use a dedicated token with read-only project/event access where supported.

## General controls

- Never commit real credentials, tokens, passwords, or database connection strings.
- Keep secrets out of process arguments, logs, and model-visible output where possible.
- Rotate credentials immediately if exposed.
- Re-check effective permissions after service-account, schema, or MCP configuration changes.
- Configure each MCP client separately on non-Claude hosts; this file is not a universal MCP configuration.
