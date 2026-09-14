"""Tests for Payaam Email Agent Visual Sandbox API."""

import pytest
from fastapi.testclient import TestClient
from src.sandbox.app import app

client = TestClient(app)


def test_sandbox_ui_serves_html():
    response = client.get("/")
    assert response.status_code == 200
    assert "Payaam" in response.text
    assert "Autonomous Background Email Agent" in response.text


def test_sandbox_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "healthy"
    assert "Payaam" in data.get("service", "")



def test_sandbox_user_profile_endpoint():
    response = client.get("/api/user-profile?email=test@agency.com")
    assert response.status_code == 200
    data = response.json()
    assert "user" in data


def test_sandbox_reset_endpoint():
    response = client.post("/api/reset")
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "reset_successful"
