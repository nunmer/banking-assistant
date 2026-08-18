"""Tests for the web gateway's admin panel: auth gate, flags, logs, proxies."""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import web.app as gateway
from web.admin import docker_logs
from tests.test_web_gateway import _StubClient, _StubResponse

_CREDS = ("admin", "admin")


@pytest.fixture
async def client():
    gateway._hits.clear()
    _StubClient.calls = []
    _StubClient.responses = None
    async with AsyncClient(
        transport=ASGITransport(app=gateway.app), base_url="http://test"
    ) as ac:
        yield ac


class TestAdminAuth:
    @pytest.mark.asyncio
    async def test_admin_page_requires_auth(self, client):
        resp = await client.get("/admin")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_flags_api_requires_auth(self, client):
        resp = await client.get("/admin/api/flags")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_credentials_rejected(self, client):
        resp = await client.get("/admin/api/flags", auth=("admin", "wrong"))
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_admin_page_served_with_correct_credentials(self, client):
        resp = await client.get("/admin", auth=_CREDS)
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]


class TestFlags:
    @pytest.mark.asyncio
    async def test_get_flags(self, client):
        cfg = {"streaming_voice_enabled": True, "tts_voice_ru": "marina"}
        with patch(
            "web.admin.runtime_config.get_config", new=AsyncMock(return_value=cfg)
        ):
            resp = await client.get("/admin/api/flags", auth=_CREDS)
        assert resp.status_code == 200
        assert resp.json() == cfg

    @pytest.mark.asyncio
    async def test_set_flags_only_sends_provided_fields(self, client):
        with patch(
            "web.admin.runtime_config.update_config",
            new=AsyncMock(return_value={"streaming_voice_enabled": True}),
        ) as update:
            resp = await client.post(
                "/admin/api/flags", auth=_CREDS, json={"streaming_voice_enabled": True}
            )
        assert resp.status_code == 200
        update.assert_awaited_once_with({"streaming_voice_enabled": True})

    @pytest.mark.asyncio
    async def test_set_flags_surfaces_update_config_value_error_as_400(self, client):
        # runtime_config.update_config's own _EDITABLE_KEYS guard (defense in
        # depth for any future direct caller) raises ValueError on an unknown
        # key; the route must turn that into a 400, not a 500.
        with patch(
            "web.admin.runtime_config.update_config",
            new=AsyncMock(side_effect=ValueError("Unknown config key(s): bogus")),
        ):
            resp = await client.post(
                "/admin/api/flags", auth=_CREDS, json={"streaming_voice_enabled": True}
            )
        assert resp.status_code == 400


class TestLogs:
    @pytest.mark.asyncio
    async def test_list_containers(self, client):
        rows = [{"name": "banking-assistant-web-1", "image": "web:latest", "status": "running"}]
        with patch("web.admin.docker_logs.list_containers", return_value=rows):
            resp = await client.get("/admin/api/containers", auth=_CREDS)
        assert resp.status_code == 200
        assert resp.json() == rows

    @pytest.mark.asyncio
    async def test_list_containers_docker_unavailable(self, client):
        with patch(
            "web.admin.docker_logs.list_containers",
            side_effect=docker_logs.DockerUnavailable("no socket"),
        ):
            resp = await client.get("/admin/api/containers", auth=_CREDS)
        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_get_logs(self, client):
        with patch("web.admin.docker_logs.tail_logs", return_value="line1\nline2\n"):
            resp = await client.get(
                "/admin/api/logs/banking-assistant-web-1", auth=_CREDS
            )
        assert resp.status_code == 200
        assert "line1" in resp.text

    @pytest.mark.asyncio
    async def test_get_logs_container_not_found(self, client):
        with patch(
            "web.admin.docker_logs.tail_logs",
            side_effect=docker_logs.ContainerNotFound("nope"),
        ):
            resp = await client.get("/admin/api/logs/nope", auth=_CREDS)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_logs_docker_unavailable(self, client):
        with patch(
            "web.admin.docker_logs.tail_logs",
            side_effect=docker_logs.DockerUnavailable("no socket"),
        ):
            resp = await client.get("/admin/api/logs/x", auth=_CREDS)
        assert resp.status_code == 503


class TestOrchestratorProxy:
    @pytest.mark.asyncio
    async def test_list_sessions_proxies_with_own_admin_auth(self, client):
        _StubClient.response = _StubResponse(json_data=[{"session_id": "u1"}])
        with patch.object(gateway.httpx, "AsyncClient", _StubClient):
            resp = await client.get("/admin/api/conversations/sessions", auth=_CREDS)
        assert resp.status_code == 200
        assert resp.json() == [{"session_id": "u1"}]
        assert _StubClient.last_call["url"].endswith("/admin/conversations/sessions")
        assert _StubClient.last_call["auth"] == ("admin", "admin")

    @pytest.mark.asyncio
    async def test_get_conversation_proxies(self, client):
        _StubClient.response = _StubResponse(json_data=[{"role": "user", "text": "hi"}])
        with patch.object(gateway.httpx, "AsyncClient", _StubClient):
            resp = await client.get("/admin/api/conversations/u1", auth=_CREDS)
        assert resp.status_code == 200
        assert _StubClient.last_call["url"].endswith("/admin/conversations/u1")

    @pytest.mark.asyncio
    async def test_get_conversation_percent_encodes_windowed_session_id(self, client):
        """Regression guard: a windowed session id contains "#" (see

        orchestrator/services/session_window.py, e.g. "748371470#1") — an
        unescaped "#" in a URL is a fragment separator that httpx (and any
        URL-parsing client) silently drops along with everything after it,
        so the outbound proxy call must percent-encode it or this fetches
        the wrong (bare, pre-windowing) session and returns stale data with
        no visible error at all.
        """
        _StubClient.response = _StubResponse(json_data=[{"role": "user", "text": "hi"}])
        with patch.object(gateway.httpx, "AsyncClient", _StubClient):
            resp = await client.get("/admin/api/conversations/748371470%231", auth=_CREDS)
        assert resp.status_code == 200
        assert _StubClient.last_call["url"].endswith("/admin/conversations/748371470%231")
        assert "#" not in _StubClient.last_call["url"]

    @pytest.mark.asyncio
    async def test_orchestrator_error_status_propagates(self, client):
        _StubClient.response = _StubResponse(status_code=404, json_data={"detail": "not found"})
        with patch.object(gateway.httpx, "AsyncClient", _StubClient):
            resp = await client.get("/admin/api/scenarios/nonexistent", auth=_CREDS)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_scenario_proxies_post(self, client):
        _StubClient.response = _StubResponse(status_code=201, json_data={"intent": "new_one"})
        body = {
            "intent": "new_one", "display_name": "New", "confirm_template": "x?",
            "mib_endpoint": "/new",
        }
        with patch.object(gateway.httpx, "AsyncClient", _StubClient):
            resp = await client.post("/admin/api/scenarios", auth=_CREDS, json=body)
        assert resp.status_code == 201
        assert _StubClient.last_call["json"]["intent"] == "new_one"

    @pytest.mark.asyncio
    async def test_update_scenario_proxies_put(self, client):
        _StubClient.response = _StubResponse(json_data={"intent": "transfer", "active": False})
        with patch.object(gateway.httpx, "AsyncClient", _StubClient):
            resp = await client.put(
                "/admin/api/scenarios/transfer", auth=_CREDS, json={"active": False}
            )
        assert resp.status_code == 200
        assert _StubClient.last_call["url"].endswith("/admin/scenarios/transfer")

    @pytest.mark.asyncio
    async def test_list_sessions_forwards_search_query(self, client):
        _StubClient.response = _StubResponse(json_data=[{"session_id": "u1"}])
        with patch.object(gateway.httpx, "AsyncClient", _StubClient):
            resp = await client.get(
                "/admin/api/conversations/sessions?q=sanzhar", auth=_CREDS
            )
        assert resp.status_code == 200
        assert _StubClient.last_call["params"]["q"] == "sanzhar"

    @pytest.mark.asyncio
    async def test_list_sessions_omits_q_when_not_given(self, client):
        _StubClient.response = _StubResponse(json_data=[{"session_id": "u1"}])
        with patch.object(gateway.httpx, "AsyncClient", _StubClient):
            await client.get("/admin/api/conversations/sessions", auth=_CREDS)
        assert "q" not in _StubClient.last_call["params"]

    @pytest.mark.asyncio
    async def test_turn_events_proxies(self, client):
        events = [{"step": "stt", "detail": {"transcript": "hello"}, "created_at": None}]
        _StubClient.response = _StubResponse(json_data=events)
        with patch.object(gateway.httpx, "AsyncClient", _StubClient):
            resp = await client.get("/admin/api/turns/turn-1/events", auth=_CREDS)
        assert resp.status_code == 200
        assert resp.json() == events
        assert _StubClient.last_call["url"].endswith("/admin/turns/turn-1/events")
