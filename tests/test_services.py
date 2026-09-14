"""Unit tests for Payaam core email and security services."""

import pytest
from src.services.crypto import encrypt_secret, decrypt_secret, generate_new_key
from src.services.email_service import email_service
from src.services.dynamodb import (
    dynamodb_service,
    _floats_to_decimals,
    _decimals_to_floats,
)
from src.services.bedrock import extract_json_from_text


def test_fernet_encryption_and_decryption():
    key = generate_new_key()
    original_secret = "purelymail_smtp_password_99"
    cipher = encrypt_secret(original_secret, key=key)
    assert cipher != original_secret
    assert len(cipher) > 20

    decrypted = decrypt_secret(cipher, key=key)
    assert decrypted == original_secret


def test_email_service_dispatch_dry_run():
    res = email_service.send_email(
        to_email="test@business.com",
        subject="Testing Payaam Dispatch",
        body_text="Hello world plain text",
        dry_run=True,
        thread_ref="PYM-9021",
    )
    assert res["success"] is True
    assert res["subject"] == "Testing Payaam Dispatch"
    assert "test@business.com" in res["to"]


def test_email_mime_parsing():
    raw_email = b"""From: "Cafe Manager" <manager@cafedelight.com>
To: payaam@yourdomain.com
Subject: [PYM-104-Cafe] Re: Online Ordering Menu
Date: Mon, 14 Sep 2026 12:00:00 +0000
Message-ID: <msg-abc@cafedelight.com>
Content-Type: text/plain; charset="utf-8"

We received your pitch. What is your turnaround time?
"""
    parsed = email_service.parse_rfc822(raw_email)
    assert parsed is not None
    assert parsed.from_address == "manager@cafedelight.com"
    assert parsed.from_name == "Cafe Manager"
    assert parsed.thread_ref == "PYM-104-Cafe"
    assert "turnaround time" in parsed.body_text


def test_dynamodb_decimal_float_conversions():
    data = {"amount": 45.5, "rating": 4.9, "nested": [{"val": 1.25}]}
    converted = _floats_to_decimals(data)
    from decimal import Decimal
    assert isinstance(converted["amount"], Decimal)
    assert isinstance(converted["nested"][0]["val"], Decimal)

    restored = _decimals_to_floats(converted)
    assert restored["amount"] == 45.5
    assert restored["nested"][0]["val"] == 1.25


def test_bedrock_json_extraction():
    raw_markdown = """Here is the extracted quote:
```json
{
  "category": "freelance_web",
  "quote_amount": 250.0,
  "currency": "USD"
}
```
"""
    result = extract_json_from_text(raw_markdown)
    assert result["category"] == "freelance_web"
    assert result["quote_amount"] == 250.0

    raw_clean = '{"is_valid": true, "cost": 35}'
    assert extract_json_from_text(raw_clean)["cost"] == 35


def test_multi_tenant_collision_detection():
    import secrets
    target = f"lead_{secrets.token_hex(4)}@shoplocal.com"
    user_a = "alice@agency.com"

    # Initially no collision
    col1 = dynamodb_service.check_collision(target)
    assert col1["has_collision"] is False

    # Alice records outreach
    dynamodb_service.record_contact(target, user_a, category="web_design")

    # Immediate second check should detect collision
    col2 = dynamodb_service.check_collision(target, category="web_design")
    assert col2["has_collision"] is True
    assert col2["target_email"] == target


def test_bounce_detection_and_dispatch_blocking():
    import email
    from src.services.email_service import is_system_bounce_or_automated

    # DSN bounce email sample
    raw_bounce = b"""From: noreply@purelymail.com
To: agent@anasriaz.com
Subject: Delivery issue with anas@anasriaz.com - quick heads up
Auto-Submitted: auto-replied
Content-Type: multipart/report; report-type=delivery-status

We could not deliver the attached mail.
"""
    msg = email.message_from_bytes(raw_bounce)
    assert is_system_bounce_or_automated(msg, "noreply@purelymail.com", "Delivery issue with anas@anasriaz.com") is True

    # Blocked outbound send to system address
    res = email_service.send_email(
        to_email="noreply@purelymail.com",
        subject="Hello",
        body_text="Test",
        dry_run=False,
    )
    assert res["success"] is False
    assert "Blocked" in res["error"]


@pytest.mark.asyncio
async def test_process_inbound_drops_bounce():
    from src.agent.core import payaam_agent
    from src.services.email_service import InboundEmail

    inbound_bounce = InboundEmail(
        message_id="<bounce-123@purelymail.com>",
        subject="Undelivered Mail Returned to Sender",
        from_address="noreply@purelymail.com",
        from_name="Purelymail System",
        to_address="agent@anasriaz.com",
        date="Mon, 14 Sep 2026 20:00:00 +0000",
        body_text="Delivery failed: 550 User not found",
    )
    res = await payaam_agent.process_inbound_email(inbound_bounce)
    assert res["route"] == "DROPPED_BOUNCE"
    assert res["response_sent"] is False

