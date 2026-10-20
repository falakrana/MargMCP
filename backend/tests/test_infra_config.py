"""Phase 4 — static validation of infra/ configuration (no containers required).

These checks do NOT prove Prometheus/Tempo/Grafana start correctly; that needs
Docker (see docs/observability.md manual verification). They catch drift between
the configs, the compose file, and the metrics the backend really exposes.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from agentops_backend.metrics import Metrics

INFRA = Path(__file__).resolve().parents[2] / "infra"


def load_yaml(*parts):
    return yaml.safe_load(INFRA.joinpath(*parts).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def compose():
    return load_yaml("docker-compose.yml")


def test_compose_defines_observability_services(compose):
    # Core backend + observability stack. Local postgres is optional (commented out when using cloud/Neon Postgres).
    assert {"backend", "prometheus", "tempo", "grafana"} <= set(compose["services"])


def test_compose_images_are_pinned(compose):
    for name, svc in compose["services"].items():
        image = svc.get("image")
        if image:
            assert ":" in image and not image.endswith(":latest"), f"{name} image not pinned"


def test_compose_contains_no_literal_secrets(compose):
    text = (INFRA / "docker-compose.yml").read_text(encoding="utf-8")
    for line in text.splitlines():
        if re.search(r"(PASSWORD|TOKEN|SECRET_KEY)\s*:", line):
            assert "${" in line, f"secret must come from env: {line.strip()}"


def test_documented_ports_are_published(compose):
    ports = lambda s: " ".join(compose["services"][s]["ports"])
    assert "9090:9090" in ports("prometheus")
    for p in ("3200:3200", "4317:4317", "4318:4318"):
        assert p in ports("tempo")
    assert "3000:3000" in ports("grafana")


def test_backend_does_not_depend_on_trace_backend(compose):
    deps = compose["services"]["backend"].get("depends_on", {})
    assert "tempo" not in deps and "prometheus" not in deps


def test_backend_exports_to_tempo_otlp_http(compose):
    env = compose["services"]["backend"]["environment"]
    assert "tempo:4318/v1/traces" in env["AGENTOPS_OTLP_ENDPOINT"]


def test_prometheus_scrapes_backend_with_token_file():
    cfg = load_yaml("prometheus", "prometheus.yml")
    job = next(j for j in cfg["scrape_configs"] if j["job_name"] == "agentops-backend")
    assert job["metrics_path"] == "/metrics"
    assert any(t in ("backend:8000", "host.docker.internal:8000") for t in job["static_configs"][0]["targets"])
    auth = job["authorization"]
    assert auth["type"] == "Bearer" and "credentials_file" in auth
    assert "credentials" not in auth  # never an inline secret


def test_prometheus_command_wires_token_file_and_retention(compose):
    cmd = " ".join(compose["services"]["prometheus"]["command"])
    assert "/tmp/agentops_metrics_token" in cmd
    assert "retention.time=30d" in cmd


def test_tempo_has_otlp_receivers_and_retention():
    cfg = load_yaml("tempo", "tempo.yml")
    protocols = cfg["distributor"]["receivers"]["otlp"]["protocols"]
    assert "4317" in protocols["grpc"]["endpoint"] and "4318" in protocols["http"]["endpoint"]
    assert cfg["compactor"]["compaction"]["block_retention"] == "720h"


def test_grafana_datasources_and_dashboard_provider():
    ds = load_yaml("grafana", "provisioning", "datasources", "datasources.yml")["datasources"]
    assert {d["type"] for d in ds} == {"prometheus", "tempo"}
    prov = load_yaml("grafana", "provisioning", "dashboards", "dashboards.yml")["providers"][0]
    assert prov["options"]["path"] == "/var/lib/grafana/dashboards"


def _dashboard():
    return json.loads((INFRA / "grafana" / "dashboards" / "agentops-overview.json")
                      .read_text(encoding="utf-8"))


def test_dashboard_uses_provisioned_datasource_uids():
    ds = load_yaml("grafana", "provisioning", "datasources", "datasources.yml")["datasources"]
    uids = {d["uid"] for d in ds}
    dash = _dashboard()
    assert dash["uid"] and dash["panels"]
    for panel in dash["panels"]:
        assert panel["datasource"]["uid"] in uids


def test_dashboard_queries_reference_only_real_metrics():
    known: set[str] = set()
    for fam in Metrics().registry.collect():
        known |= {fam.name, f"{fam.name}_total", f"{fam.name}_bucket",
                  f"{fam.name}_count", f"{fam.name}_sum"}
    referenced: set[str] = set()
    for panel in _dashboard()["panels"]:
        for target in panel["targets"]:
            referenced |= set(re.findall(r"agentops_[a-z_]+", target["expr"]))
    assert referenced, "dashboard should query AgentOps metrics"
    assert referenced <= known, f"unknown metrics: {referenced - known}"


def test_dashboard_never_groups_by_unbounded_labels():
    for panel in _dashboard()["panels"]:
        for target in panel["targets"]:
            for label in ("run_id", "trace_id", "event_id", "user_id", "prompt"):
                assert label not in target["expr"]
