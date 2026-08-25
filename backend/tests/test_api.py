import pytest
from fastapi.testclient import TestClient
from src.api.app import app

client = TestClient(app)

def test_api_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "Validata API"}
