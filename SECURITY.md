# Security

## Reporting a vulnerability

Please report authentication bypasses, access-control failures, credential exposure and similar issues privately. Use GitHub's **Report a vulnerability** entry on the [Security tab](https://github.com/WowCoder/OpenVMA/security) when private vulnerability reporting is enabled.

If that entry is unavailable, open an issue asking the maintainer to provide a private reporting channel. Include only the affected version and a broad category; do not include an exploit, personal data, credentials or private URLs in a public issue.

In a private report, include the affected commit/version, a minimal reproduction, expected impact and any suggested fix. Use synthetic accounts and media. Do not test against another person's account or a hosted deployment without permission.

## Scope and deployment

The project is under active development. Report problems against the latest `main`; a supported-version maintenance policy has not yet been established.

`docker-compose.yml` and `.env.example` are local development configurations with example credentials. Public deployments must use the production configuration and its security validation. See [deployment guidance](deploy/README.md).

Third-party AI services can receive prompts, source excerpts and media when explicitly enabled. Configure providers and data handling for your use case. Generated media must be persisted and verified before a task succeeds; this is not a guarantee about model accuracy or resistance to every prompt injection.

Never publish `.env` files, admin TOTP enrollment codes, logs containing tokens, database backups or user account mappings. If a credential is exposed, revoke or rotate it before considering Git history cleanup.
