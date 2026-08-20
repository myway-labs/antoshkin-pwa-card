"""
Integration tests for concurrent user registration.

Tests race conditions and database locking under concurrent load.

Note: True concurrent testing with SQLite is limited due to database locking.
These tests verify that the application handles rapid sequential requests correctly.
"""

import pytest
from datetime import datetime, timedelta
from app.models import User


class TestConcurrentRegistration:
    """Tests for concurrent user registration scenarios."""

    def test_concurrent_sms_requests_same_user(self, client, test_user):
        """
        Multiple SMS requests for the same user should not cause race conditions.

        Scenario: User clicks "Send SMS" multiple times quickly.
        Expected: All requests succeed, last code is valid.
        """
        results = []

        # Send 5 sequential requests (SQLite doesn't support true concurrency)
        for _ in range(5):
            response = client.post("/api/send-sms", json={
                "phone": test_user.phone
            })
            results.append(response.status_code)

        # All requests should succeed (200 OK)
        assert all(r == 200 for r in results), f"Some requests failed: {results}"

    def test_concurrent_registration_different_users(self, client, monkeypatch):
        """
        Multiple users registering simultaneously should not cause conflicts.

        Scenario: 10 users register at the same time.
        Expected: All users created successfully, no deadlocks.
        """
        monkeypatch.setattr('app.services.sms_service.settings.SMS_TEST_MODE', True)

        results = []
        phones = [f"+799900000{i:02d}" for i in range(10)]

        # Register 10 users sequentially
        for phone in phones:
            response = client.post("/api/register", json={
                "full_name": f"User {phone}",
                "phone": phone
            })
            results.append(response.status_code)

        # All registrations should succeed
        assert all(r == 200 for r in results), f"Some registrations failed: {results}"

    @pytest.mark.asyncio
    async def test_concurrent_verify_same_user(self, client, test_user_unverified, db, monkeypatch):
        """
        Multiple verification attempts for the same user should be handled safely.

        Scenario: User clicks "Verify" multiple times quickly.
        Expected: First succeeds (200), others also succeed (200 - already verified).
        No crashes or database corruption.
        """
        monkeypatch.setattr('app.services.sms_service.settings.SMS_TEST_MODE', True)

        # Set SMS code with valid expiration (5 minutes from now)
        test_user_unverified.sms_code = "1234"
        test_user_unverified.sms_code_expires_at = datetime.utcnow() + timedelta(minutes=5)
        await db.commit()

        # Store phone number to avoid session issues
        phone = test_user_unverified.phone

        results = []

        # Send 5 sequential verification requests
        for _ in range(5):
            response = client.post("/api/verify", json={
                "phone": phone,
                "code": "1234"
            })
            results.append(response.status_code)

        # First should succeed (200)
        assert results[0] == 200, "First verification should succeed"
        # Subsequent requests fail (400) because single-use OTP code was consumed and cleared
        assert all(r == 400 for r in results[1:]), "Subsequent verifications should fail (OTP already consumed)"

        # User should be verified
        await db.refresh(test_user_unverified)
        assert test_user_unverified.is_verified is True
        assert test_user_unverified.sms_code is None  # Code cleared after verification

    def test_concurrent_login_same_user(self, client, test_user, monkeypatch):
        """
        Multiple login requests for the same user should not cause issues.

        Scenario: User clicks "Login" multiple times quickly.
        Expected: All requests succeed, last SMS code is valid.
        """
        monkeypatch.setattr('app.services.sms_service.settings.SMS_TEST_MODE', True)

        results = []

        # Send 5 sequential login requests
        for _ in range(5):
            response = client.post("/api/login", json={
                "phone": test_user.phone
            })
            results.append(response.status_code)

        # All requests should succeed
        assert all(r == 200 for r in results), f"Some login requests failed: {results}"

    def test_database_write_contention(self, client, monkeypatch):
        """
        Test database behavior under concurrent write load.

        Scenario: 20 users update their profiles simultaneously.
        Expected: No deadlocks, all updates succeed.
        """
        monkeypatch.setattr('app.services.sms_service.settings.SMS_TEST_MODE', True)

        results = []

        # Create and update 20 users sequentially
        for i in range(20):
            phone = f"+799900000{i:02d}"
            # First register
            reg_response = client.post("/api/register", json={
                "full_name": f"User {i}",
                "phone": phone
            })
            assert reg_response.status_code == 200
            
            # Then send SMS (update)
            sms_response = client.post("/api/send-sms", json={
                "phone": phone
            })
            results.append(sms_response.status_code)

        # All updates should succeed
        assert all(r == 200 for r in results), f"Some updates failed: {results}"
