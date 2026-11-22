# Accepted dependency vulnerabilities

Each entry is ignored in the CI `pip-audit` step. Review this file whenever dependencies change; remove an
entry as soon as a fixed version exists.

| ID | Package (version) | Issue | Why it does not apply here | Revisit |
| --- | --- | --- | --- | --- |
| PYSEC-2026-311 | chromadb 1.5.9 | Pre-auth code injection via `trust_remote_code` in the Chroma **server** `/api/v2/.../collections` endpoint | The app embeds Chroma in-process (`chromadb.PersistentClient`); no Chroma HTTP server is started or exposed, and collections are created only by application code with the built-in embedding settings | When a fixed chromadb release is published |
| PYSEC-2026-3814 | chromadb 1.5.9 | Authenticated code injection via the Chroma **server** collection-update endpoint | Same: no Chroma server | Same |
| PYSEC-2026-3815 | chromadb 1.5.9 | `SimpleRBACAuthorizationProvider` ignores tenant/collection scope | Chroma server RBAC is not used; access control is enforced by the FastAPI layer | Same |
| PYSEC-2026-3813 | chromadb 1.5.9 | Missing tenant authorisation in the Chroma **server** | Single-tenant embedded use; no Chroma server | Same |

**Deployment rule:** never run `chroma run` / the Chroma server image alongside this app, and never expose the
`chroma` volume over the network. If a remote vector store is needed, put it behind the API with its own auth
and re-assess these entries first.

Audit date: 2026-11-22 (pip-audit against the latest releases resolved from `backend/requirements.txt`).
