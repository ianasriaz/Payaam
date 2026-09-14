"""Onboarding, Profile Vault, BYO-SMTP, and Right-to-be-Forgotten Tools for Payaam.

Enables 100% Zero-UI email lifecycle management:
1. Blank greeting response with capabilities and onboarding guide.
2. Profile creation and Memory Vault ingestion with cryptographic Deletion PIN generation.
3. Secure BYO-SMTP credential encryption at rest.
4. Cryptographic user-initiated data purge (Right-to-be-Forgotten).
"""

import logging
import re
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from strands import tool
from src.agent.copywriting import clean_user_name, extract_first_name
from src.services.crypto import encrypt_secret
from src.services.dynamodb import dynamodb_service

logger = logging.getLogger("payaam.agent.tools.onboarding")


class OnboardingInput(BaseModel):
    user_email: str = Field(description="Email address of the user who sent the email.")
    user_name: Optional[str] = Field(default=None, description="Name of the user if identified.")
    email_subject: str = Field(description="Subject line of the user's incoming email.")
    email_body: str = Field(description="Body text of the user's incoming email.")


class OnboardingResult(BaseModel):
    action_type: str = Field(description="GREETING, PROFILE_SAVED, SMTP_CONNECTED, DATA_DELETED, or PASSTHROUGH.")
    response_subject: str = Field(description="Subject line for the reply email.")
    response_body: str = Field(description="Formatted email body to send back to the user.")
    user_profile: Optional[Dict[str, Any]] = Field(default=None, description="Stored user profile data if applicable.")


@tool
def handle_onboarding_or_greeting_tool(input_data: OnboardingInput) -> OnboardingResult:
    """Evaluates whether an incoming email is a blank greeting, profile introduction,

    SMTP connection, or data deletion command, and executes the appropriate lifecycle action.
    """
    body = input_data.email_body.strip()
    subj = input_data.email_subject.strip()
    full_text = f"{subj}\n{body}".strip()
    norm_email = input_data.user_email.strip().lower()

    # -------------------------------------------------------------------------
    # 1. Check for Data Deletion Command ("DELETE MY DATA [PIN]")
    # -------------------------------------------------------------------------
    delete_with_pin = re.search(
        r"DELETE\s+(?:MY\s+)?(?:DATA|PROFILE|ACCOUNT)\s+(?:PIN:?\s*)?((?:PYM|WD)-[A-Za-z0-9]+)\b",
        full_text,
        re.IGNORECASE,
    )
    if not delete_with_pin:
        pin_cand = re.search(
            r"DELETE\s+(?:MY\s+)?(?:DATA|PROFILE|ACCOUNT)\s+(?:PIN:?\s*)?([A-Za-z0-9]{4,10})\b",
            full_text,
            re.IGNORECASE,
        )
        if pin_cand and pin_cand.group(1).upper() not in ["DATA", "PROFILE", "ACCOUNT", "DELETE"]:
            delete_with_pin = pin_cand

    delete_without_pin = re.search(
        r"\bDELETE\s+(?:MY\s+)?(?:DATA|PROFILE|ACCOUNT)\b",
        full_text,
        re.IGNORECASE,
    )

    if delete_with_pin or delete_without_pin:
        provided_pin = delete_with_pin.group(1).strip() if delete_with_pin else None
        if not provided_pin:
            # User asked to delete but didn't provide PIN -> send verification reminder
            user = dynamodb_service.get_user(norm_email)
            if user:
                pin = user.get("deletion_pin", "UNKNOWN")
                return OnboardingResult(
                    action_type="DELETION_CONFIRMATION_REQUIRED",
                    response_subject="⚠️ Action Required: Confirm Profile & Data Deletion",
                    response_body=(
                        f"Hello {user.get('name', 'there')},\n\n"
                        "You requested to permanently delete your Payaam profile, credentials, and mission history.\n\n"
                        "To protect against unauthorized requests, please confirm by replying:\n"
                        f"  DELETE MY DATA {pin}\n\n"
                        "Once received, all your data will be permanently purged immediately."
                    ),
                )
            return OnboardingResult(
                action_type="DATA_DELETED",
                response_subject="Payaam: No Profile Found",
                response_body="No profile exists under this email address.",
            )

        # Process actual purge with PIN
        purge_result = dynamodb_service.delete_user_and_all_data(norm_email, provided_pin)
        if purge_result.get("success"):
            return OnboardingResult(
                action_type="DATA_DELETED",
                response_subject="✅ Payaam Data Deleted: Right-to-be-Forgotten Complete",
                response_body=(
                    f"Hello,\n\n"
                    f"All your data under {norm_email} has been permanently purged from Payaam:\n"
                    f"• User Profile & Memory Vault: DELETED\n"
                    f"• Connected SMTP Credentials: PURGED\n"
                    f"• Ephemeral Mission Sessions ({purge_result.get('deleted_missions_count', 0)} items): DELETED\n\n"
                    f"We retain zero records of your identity or messages. Thank you for using Payaam!"
                ),
            )
        else:
            return OnboardingResult(
                action_type="DELETION_FAILED",
                response_subject="❌ Deletion Failed: Invalid PIN",
                response_body=f"Failed to delete profile: {purge_result.get('error')}. Please verify your PIN and try again.",
            )

    # -------------------------------------------------------------------------
    # 2. Check for BYO-SMTP Connection Command ("CONNECT_SMTP")
    # -------------------------------------------------------------------------
    if "CONNECT_SMTP" in full_text.upper():
        host_match = re.search(r"Host:\s*([^\r\n]+)", full_text, re.IGNORECASE)
        port_match = re.search(r"Port:\s*(\d+)", full_text, re.IGNORECASE)
        user_match = re.search(r"Username:\s*([^\r\n]+)", full_text, re.IGNORECASE)
        pass_match = re.search(r"Password:\s*([^\r\n]+)", full_text, re.IGNORECASE)

        if host_match and user_match and pass_match:
            raw_host = host_match.group(1).strip()
            raw_port = int(port_match.group(1).strip()) if port_match else 465
            raw_user = user_match.group(1).strip()
            raw_pass = pass_match.group(1).strip()

            # Encrypt password symmetrically at rest
            encrypted_pass = encrypt_secret(raw_pass)

            user = dynamodb_service.get_user(norm_email) or {
                "email": norm_email,
                "name": clean_user_name(input_data.user_name, norm_email),
            }
            user["smtp_config"] = {
                "host": raw_host,
                "port": raw_port,
                "username": raw_user,
                "encrypted_password": encrypted_pass,
            }
            saved = dynamodb_service.save_user(user)

            return OnboardingResult(
                action_type="SMTP_CONNECTED",
                response_subject="✅ Custom SMTP Connected Successfully",
                response_body=(
                    f"Hello {user.get('name')},\n\n"
                    f"Your custom sender email has been securely connected:\n"
                    f"• Sender Address: {raw_user}\n"
                    f"• SMTP Server: {raw_host}:{raw_port}\n"
                    f"• Password: Encrypted at rest (AES-128 Fernet)\n\n"
                    f"Future outreach missions will now be dispatched directly from your personal address!\n"
                    f"Your Data Deletion PIN is: {saved.get('deletion_pin')}"
                ),
                user_profile=saved,
            )

    # -------------------------------------------------------------------------
    # 3. Check for Existing User
    # -------------------------------------------------------------------------
    existing_user = dynamodb_service.get_user(norm_email)

    # -------------------------------------------------------------------------
    # 4. Check for Profile Introduction / Setup
    # -------------------------------------------------------------------------
    has_profile_keywords = any(kw in full_text.lower() for kw in [
        "portfolio", "rate", "services", "setup: my profile", "setup",
        "pricing", "developer", "designer", "freelance"
    ])
    has_target_leads = bool(re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", body.replace(norm_email, "")))

    if has_profile_keywords and not has_target_leads:
        portfolio_match = re.search(r"(?:https?://[^\s]+|[a-zA-Z0-9\-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?)", body)
        portfolio = portfolio_match.group(0).rstrip(".,;:)>]") if portfolio_match else ""

        user_data = dict(existing_user or {})
        user_data.update({
            "email": norm_email,
            "name": clean_user_name(input_data.user_name or user_data.get("name"), norm_email),
            "bio_notes": body,
            "portfolio": portfolio or user_data.get("portfolio", ""),
        })
        saved_user = dynamodb_service.save_user(user_data)
        pin = saved_user.get("deletion_pin")

        return OnboardingResult(
            action_type="PROFILE_SAVED",
            response_subject="✅ Payaam Profile Initialized: You're All Set!",
            response_body=(
                f"Welcome aboard, {saved_user.get('name')}! 🚀\n\n"
                "I have initialized your Memory Vault:\n"
                f"• Account Email: {norm_email}\n"
                f"• Portfolio Link: {portfolio or 'Not specified'}\n"
                f"• Permanent Data Deletion PIN: {pin}\n\n"
                "Whenever you find potential clients, job opportunities, or need vendor quotes, just email me with the target emails "
                "and your rough goal. Payaam will take care of the rest in the background!"
            ),
            user_profile=saved_user,
        )

    # -------------------------------------------------------------------------
    # 5. Check for Blank Greeting ("Hi", "Hello", "Hey", "What can you do?")
    # -------------------------------------------------------------------------
    greeting_patterns = [
        r"\b(?:hi|hello|hey|greetings|help|howdy|start)\b",
        r"what\s+can\s+you\s+do",
        r"who\s+are\s+you",
        r"how\s+(?:does\s+this|to)\s+work",
    ]
    matches_greeting = any(re.search(pat, full_text, re.IGNORECASE) for pat in greeting_patterns)

    if (matches_greeting and not has_target_leads) or not body:
        # Create minimal user record to generate their unique Deletion PIN
        if not existing_user:
            existing_user = dynamodb_service.save_user({
                "email": norm_email,
                "name": clean_user_name(input_data.user_name, norm_email),
            })

        deletion_pin = existing_user.get("deletion_pin", "PYM-XXXX")
        user_first = extract_first_name(existing_user.get("name", "there"))

        return OnboardingResult(
            action_type="GREETING",
            response_subject="👋 Welcome to Payaam - Your Background Autonomous Email Agent",
            response_body=(
                f"Hello {user_first}!\n\n"
                "I am Payaam (پیام), an autonomous AI agent that handles repetitive email outreach, "
                "job pitches, and client follow-ups silently in the background.\n\n"
                "💡 What I Can Do For You:\n"
                "1. Multi-Target Outreach: Pitch job applications, competition proposals, or client services with tailored pitches.\n"
                "2. Everyday Sourcing: Email suppliers, vendors, or venues to collect quotes & compare.\n"
                "3. Silent Follow-ups: Chase busy leads automatically without bothering you.\n"
                "4. 'Two-Knock' Privacy: I run silently and only email you when a real decision is needed!\n\n"
                "📋 What I Need From You to Get Started:\n"
                "Simply reply with your profile notes:\n"
                "• Your Name & Services (e.g., 'Anas, Full-Stack & AI Engineer')\n"
                "• Portfolio Link (e.g., 'https://anasriaz.com')\n"
                "• Pricing Baseline / Guardrails (e.g., '$200 - $500, min $150')\n"
                "• (Or just give me a task directly: a list of emails and what to pitch!)\n\n"
                "🔌 Connect Your Own Email (Optional):\n"
                "By default, I send via our platform relay. If you prefer me to send directly from your personal inbox, reply with:\n"
                "  CONNECT_SMTP\n"
                "  Host: mail.purelymail.com (or smtp.gmail.com)\n"
                "  Port: 465\n"
                "  Username: your_email@domain.com\n"
                "  Password: your_app_password\n\n"
                "🗑️ Your Data & Privacy (Right-to-be-Forgotten):\n"
                f"You have 100% control over your data. To permanently purge your profile, credentials, and missions, reply anytime:\n"
                f"  DELETE MY DATA {deletion_pin}"
            ),
            user_profile=existing_user,
        )

    # If it's a mission or task, pass through to outreach/triager tools
    return OnboardingResult(
        action_type="PASSTHROUGH",
        response_subject="",
        response_body="",
        user_profile=existing_user,
    )
