from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app


def test_known_govassist_frontend_origin_is_allowed_with_credentials():
    response = TestClient(app).get(
        "/health",
        headers={"Origin": "https://govassist-web-git-main-ronit-khannas-projects.vercel.app"},
    )
    assert response.headers["access-control-allow-origin"] == (
        "https://govassist-web-git-main-ronit-khannas-projects.vercel.app"
    )
    assert response.headers["access-control-allow-credentials"] == "true"


def test_arbitrary_vercel_origin_is_not_allowed():
    response = TestClient(app).get(
        "/health",
        headers={"Origin": "https://some-other-project.vercel.app"},
    )
    assert "access-control-allow-origin" not in response.headers
