# Changelog

## [1.3.0] - 2026-03-05

### Added
- User login, registration, logout with session cookies
- All pages protected — login required
- Admin panel at /admin — manage users and API keys
- Public API key support — use X-API-Key header for external access
- Probe editor at /probes — add and delete probes from the browser
- Run Benchmark page — trigger runs directly from the browser
- Export CSV at /api/export-csv — download all results
- PDF/HTML report export at /api/export-report
- Model comparison at /api/compare with bar chart
- Token counting (prompt_tokens, completion_tokens, total_tokens)
- Chart.js charts on stats, actuarial, and costs pages
- 105 probes across 4 vectors (NCA x30, SFC x25, IDL x25, CG x25)
- Pinned requirements.txt

## [1.0.0] - 2026-03-05

### Added
- Initial release — MTCP evaluation protocol
- Violation Engine, PRP Engine, constraint detector
- FastAPI dashboard, SQLite persistence
- Run manifest with SHA-256 integrity hashing
- DOI: https://doi.org/10.17605/OSF.IO/DXGK5
