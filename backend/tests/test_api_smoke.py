"""End-to-end smoke test: boot the FastAPI app and hit the core REST endpoints.

This forces the MockLLMAdapter path so it works without any real LLM key. We
also disable sim autostart so the test doesn't race the lifecycle.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="module")
def client():
    os.environ["LLM_API_KEY"] = "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    os.environ["SIM_AUTOSTART"] = "false"

    # Drop any cached settings the import-time loader may have stashed.
    from app import settings as _settings_mod
    _settings_mod._settings = None

    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["n_agents"] >= 60


def test_scene_graph(client):
    r = client.get("/api/scene/graph")
    assert r.status_code == 200
    body = r.json()
    assert len(body["rooms"]) == 16
    assert len(body["nodes"]) == 16
    assert body["edges"], "scene must expose edges"


def test_agents_list(client):
    r = client.get("/api/agents")
    assert r.status_code == 200
    body = r.json()
    assert len(body) >= 60
    for entry in body:
        assert entry["id"]
        assert entry["name"]
        assert "location_uid" in entry


def test_agent_detail_memory_schedule_perception(client):
    list_r = client.get("/api/agents").json()
    agent_id = list_r[0]["id"]

    detail = client.get(f"/api/agents/{agent_id}")
    assert detail.status_code == 200
    assert detail.json()["id"] == agent_id

    mem = client.get(f"/api/agents/{agent_id}/memory")
    assert mem.status_code == 200
    assert "short_term" in mem.json()
    assert "long_term" in mem.json()
    assert "graph" in mem.json()

    sched = client.get(f"/api/agents/{agent_id}/schedule")
    assert sched.status_code == 200
    assert "slots" in sched.json()

    perc = client.get(f"/api/agents/{agent_id}/perception")
    assert perc.status_code == 200
    assert perc.json()["agent_id"] == agent_id


def test_relations(client):
    r = client.get("/api/relations")
    assert r.status_code == 200
    assert len(r.json()["edges"]) >= 120


def test_scenes_library_and_timeline(client):
    r = client.get("/api/scenes-library")
    assert r.status_code == 200
    assert "scenes" in r.json()
    r = client.get("/api/timeline-seed")
    assert r.status_code == 200
    assert "events" in r.json()


def test_world_and_sim_control(client):
    r = client.get("/api/world")
    assert r.status_code == 200
    assert "sim_time" in r.json()

    started = client.post("/api/sim/start")
    assert started.status_code == 200
    assert started.json()["status"] == "running"

    stepped = client.post("/api/sim/step")
    assert stepped.status_code == 200

    paused = client.post("/api/sim/pause")
    assert paused.status_code == 200


def test_config_endpoints(client):
    assert client.get("/api/config/personas").status_code == 200
    assert client.get("/api/config/actions").status_code == 200
    assert client.get("/api/config/fragments").status_code == 200

    reload = client.post("/api/config/reload")
    assert reload.status_code == 200
    body = reload.json()
    assert body["status"] == "reloaded"
    assert body["personas"] >= 60
