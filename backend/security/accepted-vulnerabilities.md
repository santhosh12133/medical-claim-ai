# Accepted dependency vulnerabilities

**None.** CI runs `pip-audit` with no ignored advisories and `npm audit --audit-level=high`; any known
vulnerability fails the build.

## History

| Date | Package | Resolution |
| --- | --- | --- |
| 2026-11-22 | chromadb 1.5.9 — PYSEC-2026-311, -3813, -3814, -3815 (Chroma HTTP server: code injection via `trust_remote_code`, missing tenant authorisation, RBAC scope) | No patched release existed. **Removed from the default install**: embeddings are now stored in the application database and searched with an exact NumPy index (`RAG_VECTOR_BACKEND=sql`, migration 0010). Chroma remains available as an opt-in backend (`RAG_VECTOR_BACKEND=chroma`, `pip install chromadb`); if you enable it, never run the Chroma server or expose its data directory, and re-check these advisories. |
| 2026-11-22 | react-router 6.x (2 moderate) | Upgraded to react-router-dom 7. |
| 2026-11-22 | axios, vite, postcss, nanoid, follow-redirects, browserslist, source-map-js (7 high) | `npm audit fix` within semver ranges. |
