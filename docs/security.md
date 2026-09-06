# Security Guide

## Authentication

The API authenticates users with signed JWT access tokens. Passwords are stored as salted PBKDF2-HMAC-SHA256 hashes rather than plaintext passwords.

Production requirements:

- use a cryptographically random `SECRET_KEY`
- keep token lifetime short
- never commit credentials or tokens
- use HTTPS for every browser/API connection
- rotate signing secrets through the deployment secret manager

The current browser client stores the access token locally. For a hardened internet-facing deployment, migrate the refresh/session mechanism to an HttpOnly, Secure, SameSite cookie and keep short-lived access credentials out of persistent browser storage.

## Authorization

Role-based dependencies distinguish employee and admin operations.

Employees can access their own claims. Admin-only operations include claim administration, policy administration, verification history, and decision metrics.

Every claim lookup must enforce ownership for non-admin users.

## File Upload Security

Claim and policy uploads are protected by:

- allowlisted extensions
- file size limits
- magic/signature validation
- empty-file rejection
- cleanup when persistence fails
- storage outside the frontend source tree

Do not trust `Content-Type` or filename alone. Production deployments should additionally consider malware scanning and object-storage quarantine for untrusted documents.

## Secrets

Never place these values in Git:

- `OPENAI_API_KEY`
- production database credentials
- JWT signing secrets
- cloud-storage credentials
- deployment tokens

Use environment variables or the deployment platform's secret manager.

## CORS

Set `CORS_ORIGINS` to the exact production frontend origin. Do not use a wildcard origin when credentials are enabled.

## AI Safety

GPT output is treated as an assessment, not as an unrestricted source of truth. The service only provides retrieved policy evidence to GPT and validates its structured response.

Safety controls include:

- deterministic policy baseline
- confidence thresholds
- maximum approved amount protection
- conflict detection
- GPT availability checks
- approved-amount ceiling
- human-review escalation
- persistent decision audit records

A model must not be allowed to approve a claim above the deterministic policy result.

## Logging and Privacy

Logs should contain operational identifiers and errors without unnecessarily copying medical documents or sensitive personal information. Production log retention must follow the organization's privacy and compliance requirements.

Uploaded medical documents should have restricted access and a defined retention/deletion policy.

## Database Security

Use a dedicated application database user with only the permissions required by the application. Do not run the application using a superuser in production.

Enable managed PostgreSQL TLS where supported and restrict network access to trusted application services.

## Operational Controls

Before production traffic:

- verify HTTPS
- verify CORS
- verify authentication and role boundaries
- verify claim ownership enforcement
- verify upload limits/signatures
- verify secrets are not present in images or Git
- verify database backups
- verify audit records
- verify worker retry behavior
- verify human-review escalation
- verify monitoring and alerts
