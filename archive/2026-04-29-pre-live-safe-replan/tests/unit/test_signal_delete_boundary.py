from fastapi.testclient import TestClient

from src.interfaces.api import app


class _RepoStub:
    def __init__(self) -> None:
        self.delete_called = False
        self.clear_called = False

    async def delete_signals(self, request=None):
        self.delete_called = True
        return 3

    async def clear_all_signals(self):
        self.clear_called = True
        return 7


def test_delete_signals_rejects_live(monkeypatch):
    repo = _RepoStub()
    monkeypatch.setattr("src.interfaces.api._get_repository", lambda: repo)
    client = TestClient(app)

    response = client.request(
        "DELETE",
        "/api/signals",
        json={"ids": [1], "source": "live"},
    )

    assert response.status_code == 409
    payload = response.json()
    message = payload.get("detail") or payload.get("message") or str(payload)
    assert "Live signals do not support physical delete" in message
    assert repo.delete_called is False


def test_delete_signals_allows_backtest(monkeypatch):
    repo = _RepoStub()
    monkeypatch.setattr("src.interfaces.api._get_repository", lambda: repo)
    client = TestClient(app)

    response = client.request(
        "DELETE",
        "/api/signals",
        json={"ids": [1], "source": "backtest"},
    )

    assert response.status_code == 200
    assert response.json()["deleted_count"] == 3
    assert repo.delete_called is True


def test_clear_all_signals_requires_backtest_source(monkeypatch):
    repo = _RepoStub()
    monkeypatch.setattr("src.interfaces.api._get_repository", lambda: repo)
    client = TestClient(app)

    response = client.request("DELETE", "/api/signals/clear_all?source=backtest")

    assert response.status_code == 200
    assert response.json()["deleted_count"] == 7
    assert repo.clear_called is True


def test_clear_all_signals_query_validation_rejects_live(monkeypatch):
    repo = _RepoStub()
    monkeypatch.setattr("src.interfaces.api._get_repository", lambda: repo)
    client = TestClient(app)

    response = client.request("DELETE", "/api/signals/clear_all?source=live")

    assert response.status_code == 422
    assert repo.clear_called is False
