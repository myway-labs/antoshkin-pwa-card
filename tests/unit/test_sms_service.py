"""
Unit tests for sms_service.py

Tests SMS code generation, sending, and verification functions.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock
from app.services.sms_service import (
    generate_sms_code,
    send_sms,
    verify_sms_code,
    set_user_sms_code,
    resend_sms_code,
    TEST_CODE
)
from app.models import User


class TestGenerateSmsCode:
    """Tests for generate_sms_code() function."""

    def test_generate_sms_code_test_mode(self, monkeypatch):
        """A.2.1: Генерация кода в тестовом режиме."""
        monkeypatch.setattr('app.services.sms_service.settings.SMS_TEST_MODE', True)
        result = generate_sms_code()
        assert result == "0000"

    def test_generate_sms_code_prod_mode(self, monkeypatch):
        """A.2.2: Генерация кода в боевом режиме."""
        monkeypatch.setattr('app.services.sms_service.settings.SMS_TEST_MODE', False)
        result = generate_sms_code()
        # Should be 4 digits
        assert len(result) == 4
        assert result.isdigit()

    def test_generate_sms_code_format(self, monkeypatch):
        """A.2.3: Формат кода - строка из 4 цифр."""
        monkeypatch.setattr('app.services.sms_service.settings.SMS_TEST_MODE', False)
        result = generate_sms_code()
        assert isinstance(result, str)
        assert len(result) == 4


class TestSendSms:
    """Tests for send_sms() function."""

    @pytest.mark.asyncio
    async def test_send_sms_test_mode(self, monkeypatch, caplog):
        """Отправка SMS в тестовом режиме."""
        monkeypatch.setattr('app.services.sms_service.settings.SMS_TEST_MODE', True)
        success, message = await send_sms("+79991234567", "1234")
        assert success is True
        assert "test mode" in message.lower()

    @pytest.mark.asyncio
    async def test_send_sms_production_success(self, monkeypatch):
        """Отправка SMS в боевом режиме - успех."""
        monkeypatch.setattr('app.services.sms_service.settings.SMS_TEST_MODE', False)
        monkeypatch.setattr('app.services.sms_service.settings.SMS_API_KEY', 'test_key')

        # Mock httpx.AsyncClient
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "OK"}
        
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        
        with patch('app.services.sms_service.httpx.AsyncClient', return_value=mock_client):
            success, message = await send_sms("+79991234567", "1234")
            assert success is True
            assert message == "SMS sent"

    @pytest.mark.asyncio
    async def test_send_sms_production_error(self, monkeypatch):
        """Отправка SMS в боевом режиме - ошибка."""
        monkeypatch.setattr('app.services.sms_service.settings.SMS_TEST_MODE', False)
        monkeypatch.setattr('app.services.sms_service.settings.SMS_API_KEY', 'test_key')

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "ERROR", "status_message": "Invalid number"}
        
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        
        with patch('app.services.sms_service.httpx.AsyncClient', return_value=mock_client):
            success, message = await send_sms("+79991234567", "1234")
            assert success is False
            assert "error" in message.lower()

    @pytest.mark.asyncio
    async def test_send_sms_timeout(self, monkeypatch):
        """Отправка SMS - таймаут."""
        monkeypatch.setattr('app.services.sms_service.settings.SMS_TEST_MODE', False)
        monkeypatch.setattr('app.services.sms_service.settings.SMS_API_KEY', 'test_key')

        import httpx
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        
        with patch('app.services.sms_service.httpx.AsyncClient', return_value=mock_client):
            success, message = await send_sms("+79991234567", "1234")
            assert success is False
            assert "timeout" in message.lower()


class TestVerifySmsCode:
    """Tests for verify_sms_code() function."""

    @pytest.mark.asyncio
    async def test_verify_sms_code_valid(self, db, test_user_unverified):
        """A.2.4: Верификация верным кодом."""
        # Set SMS code
        expires_at = datetime.utcnow() + timedelta(minutes=5)
        test_user_unverified.sms_code = "1234"
        test_user_unverified.sms_code_expires_at = expires_at
        await db.commit()
        
        result = await verify_sms_code(db, test_user_unverified, "1234")
        success = result[0]
        assert success is True
        assert test_user_unverified.is_verified is True

    @pytest.mark.asyncio
    async def test_verify_sms_code_invalid(self, db, test_user_unverified):
        """A.2.5: Верификация неверным кодом."""
        expires_at = datetime.utcnow() + timedelta(minutes=5)
        test_user_unverified.sms_code = "1234"
        test_user_unverified.sms_code_expires_at = expires_at
        await db.commit()
        
        success, message = await verify_sms_code(db, test_user_unverified, "9999")
        assert success is False

    @pytest.mark.asyncio
    async def test_verify_sms_code_expired(self, db, test_user_unverified):
        """A.2.6: Верификация просроченным кодом."""
        expires_at = datetime.utcnow() - timedelta(minutes=5)  # Expired
        test_user_unverified.sms_code = "1234"
        test_user_unverified.sms_code_expires_at = expires_at
        await db.commit()
        
        success, message = await verify_sms_code(db, test_user_unverified, "1234")
        assert success is False

    @pytest.mark.asyncio
    async def test_verify_sms_code_already_verified(self, db, test_user):
        """Верификация уже верифицированного пользователя (повторный вход по SMS коду)."""
        test_user.is_verified = True
        test_user.sms_code = "1234"
        test_user.sms_code_expires_at = datetime.utcnow() + timedelta(minutes=5)
        await db.commit()
        
        # Previously verified user must still provide a valid active SMS code to verify session
        result = await verify_sms_code(db, test_user, "1234")
        assert result[0] is True
        assert "Verified" in result[1]

    @pytest.mark.asyncio
    async def test_verify_sms_code_no_code(self, db, test_user_unverified):
        """Верификация без установленного кода."""
        test_user_unverified.sms_code = None
        test_user_unverified.sms_code_expires_at = None
        await db.commit()
        
        success, message = await verify_sms_code(db, test_user_unverified, "1234")
        assert success is False


class TestSetUserSmsCode:
    """Tests for set_user_sms_code() function."""

    @pytest.mark.asyncio
    async def test_set_user_sms_code(self, db, test_user_unverified):
        """A.2.7: Установка SMS кода."""
        success, code, message = await set_user_sms_code(db, test_user_unverified)
        
        assert success is True
        assert code is not None
        assert len(code) == 4
        assert test_user_unverified.sms_code == code
        assert test_user_unverified.sms_code_expires_at is not None


class TestResendSmsCode:
    """Tests for resend_sms_code() function."""

    @pytest.mark.asyncio
    async def test_resend_sms_code(self, db, test_user_unverified):
        """A.2.8: Повторная отправка SMS."""
        # First send
        success1, code1, message1 = await resend_sms_code(db, test_user_unverified)
        assert success1 is True
        
        # Second send (should also succeed)
        success2, code2, message2 = await resend_sms_code(db, test_user_unverified)
        assert success2 is True

    @pytest.mark.asyncio
    async def test_resend_sms_code_verified(self, db, test_user):
        """Повторная отправка верифицированному пользователю."""
        # test_user is verified by fixture
        success, code, message = await resend_sms_code(db, test_user)
        assert success is False
        assert "already verified" in message.lower()
