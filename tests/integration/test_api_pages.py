"""
Integration tests for API page endpoints.

Tests /, /verify, /splash, /health endpoints.
"""

import pytest


class TestApiPages:
    """Tests for page endpoints."""

    def test_root_page(self, client):
        """B.7.1: Доступ к главной странице."""
        response = client.get("/")
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"
        assert "Регистрация".encode('utf-8') in response.content
        assert "Антошкин дворик".encode('utf-8') in response.content

    def test_verify_page(self, client):
        """B.7.2: Доступ к странице верификации."""
        response = client.get("/verify")
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"
        assert "Подтверждение кода".encode('utf-8') in response.content

    def test_splash_page(self, client):
        """B.7.3: Доступ к splash screen."""
        response = client.get("/splash")
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"
        assert "Антошкин дворик".encode('utf-8') in response.content

    def test_health_check(self, client):
        """B.7.4: Проверка health endpoint."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_favicon_endpoint(self, client):
        """B.7.5: Проверка доступности favicon.ico."""
        response = client.get("/favicon.ico")
        
        assert response.status_code == 200
        assert "image/" in response.headers["content-type"] or "application/" in response.headers["content-type"]
        assert len(response.content) > 0

    def test_apple_touch_icon_endpoint(self, client):
        """B.7.6: Проверка доступности apple-touch-icon.png."""
        response = client.get("/apple-touch-icon.png")
        
        assert response.status_code == 200
        assert "image/png" in response.headers["content-type"]
        assert len(response.content) > 0

    def test_apple_touch_icon_precomposed_endpoint(self, client):
        """B.7.7: Проверка доступности apple-touch-icon-precomposed.png."""
        response = client.get("/apple-touch-icon-precomposed.png")
        
        assert response.status_code == 200
        assert "image/png" in response.headers["content-type"]
        assert len(response.content) > 0

    def test_robots_txt_endpoint(self, client):
        """B.7.8: Проверка доступности robots.txt."""
        response = client.get("/robots.txt")
        
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        assert "User-agent:" in response.text
