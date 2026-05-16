# EDC microservices

This directory contains the service-level layout of the control plane.

The public `:8080` entry point is now `reverse-proxy`; the existing Python
control plane runs as `manager-api` for compatibility with the existing agent.
New services split the heavy operational paths:

- `manager-api` serves the existing UI and management API on port 8080.
- `reverse-proxy` is the public entry point and keeps the external center port stable.
- `agent-gateway` is the future narrow API for sensor agents on port 8081.
- `config-renderer` renders `DeviceMaskProfile` into desired state on port 8092.
- `log-receiver` accepts raw honeypot logs and normalized event batches on port 8091.
- `log-normalizer` periodically normalizes raw log rows that were accepted without inline parsing.

All service Dockerfiles are intentionally small and copy only the code required
for their responsibility.
