Monitoring setup (Prometheus + Grafana + Loki + Promtail)

Quick start (from repository root):

```bash
docker compose up -d prometheus node_exporter cadvisor loki promtail grafana alertmanager
```

- Grafana: http://localhost:3000 (admin/admin)
- Grafana via gateway: http://logging.secra.top
- Prometheus: http://localhost:9090
- Loki: http://localhost:3100
- cAdvisor: http://localhost:8080
- Gateway metrics: http://localhost:8000/metrics

Notes:
- Promtail tails container logs under `/var/lib/docker/containers` (docker must use `json-file` logging driver).
- Services can be instrumented at `/metrics` to be scraped by Prometheus.
- The default Grafana dashboard is provisioned from `monitoring/grafana/dashboards/observability.json`.
