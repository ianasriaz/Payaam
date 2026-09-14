"""Two-Knock Inbox Triager Tool for Payaam.

Enforces the Two-Knock Policy:
- Filters out auto-replies, bounces, and opt-outs silently.
- Autonomously answers routine questions (portfolio, links) from the User Vault.
- Surfaces ONLY when an Action is Needed (budget negotiation/scope) or a Result is Achieved (meeting confirmed).
- Translates 1-line user rough replies into polished client-ready emails.
"""

import logging
import re
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from strands import tool
from src.services.bedrock import bedrock_service, extract_json_from_text
from src.services.dynamodb import dynamodb_service
from src.services.email_service import email_service

logger = logging.getLogger("payaam.agent.tools.inbox_triager")


class InboundTriageInput(BaseModel):
    from_email: str = Field(description="Email of the sender.")
    subject: str = Field(description="Email subject line.")
    body_text: str = Field(description="Body of the incoming email.")
    thread_ref: Optional[str] = Field(default=None, description="Thread tracking ref if present (e.g. WD-1024-Cafe).")
    in_reply_to: Optional[str] = Field(default=None, description="Message-ID being replied to.")


class InboundTriageResult(BaseModel):
    intent_category: str = Field(description="IGNORE_AUTO, OPT_OUT, RESOLVE_SILENTLY, ACTION_NEEDED, RESULT_ACHIEVED, or USER_REFINEMENT.")
    should_surface_to_user: bool = Field(description="True if an email should be sent to the user.")
    user_notification_subject: Optional[str] = Field(default=None)
    user_notification_body: Optional[str] = Field(default=None)
    client_reply_dispatched: bool = Field(default=False)
    client_reply_body: Optional[str] = Field(default=None)


async def _classify_lead_reply(body: str, subject: str, user_vault: Dict[str, Any]) -> Dict[str, Any]:
    """Uses Bedrock Claude 3.5 Haiku to classify intent and extract deal signals."""
    prompt = f"""You are triaging an inbound reply from a prospective client or service provider.
Subject: {subject}
Body: {body}
User Vault: {user_vault}

Categories:
1. "IGNORE_AUTO": Out of office, automated vacation notices, delivery failure/bounce.
2. "OPT_OUT": "Unsubscribe", "Not interested", "Remove me", "Wrong email", "No thanks".
3. "RESOLVE_SILENTLY": Inquiring about portfolio, past samples, or booking link that are already available in User Vault.
4. "ACTION_NEEDED": Pricing negotiation (budget counter), custom requirements, asking for discount, or scope changes.
5. "RESULT_ACHIEVED": Explicitly agreed to a meeting time, ready to hire/sign, or confirmed price/deal.

Output valid JSON:
{{
  "category": "ONE_OF_THE_ABOVE",
  "summary": "1-sentence summary of reply",
  "client_question": "Key question or objection if any",
  "suggested_reply": "Proposed polite response"
}}
"""
    try:
        raw_res = await bedrock_service.converse(
            prompt=prompt,
            system_prompt="You are a strict B2B sales email intent classifier.",
            temperature=0.1,
            max_tokens=512,
        )
        return extract_json_from_text(raw_res)
    except Exception as exc:
        logger.warning(f"Classification fallback triggered: {exc}")

    # Fallback heuristic
    body_lower = body.lower()
    if any(w in body_lower for w in ["out of the office", "auto-reply", "vacation", "undeliverable", "delivery failed"]):
        return {"category": "IGNORE_AUTO", "summary": "Auto-responder / bounce", "suggested_reply": ""}
    if any(w in body_lower for w in ["not interested", "unsubscribe", "remove me", "stop"]):
        return {"category": "OPT_OUT", "summary": "Prospect opted out", "suggested_reply": ""}
    if any(w in body_lower for w in ["call", "meeting", "zoom", "thursday", "friday", "tomorrow", "sounds good"]):
        return {"category": "RESULT_ACHIEVED", "summary": "Meeting or interest confirmed", "suggested_reply": "Let's schedule a call!"}

    return {"category": "ACTION_NEEDED", "summary": "Client sent specific inquiry", "suggested_reply": "Thank you for the inquiry."}


@tool
async def triage_inbound_email_tool(input_data: InboundTriageInput) -> InboundTriageResult:
    """Classifies inbound emails and triggers either silent resolution or a Two-Knock User Alert."""
    from_addr = input_data.from_email.strip().lower()
    thread_ref = input_data.thread_ref

    # Correlate with active mission
    mission = dynamodb_service.find_mission_by_thread(thread_ref or "")
    user_email = mission.get("user_email") if mission else None
    user_profile = dynamodb_service.get_user(user_email or from_addr) or {}

    # -------------------------------------------------------------------------
    # Case A: Is the User Replying to an Action Card?
    # -------------------------------------------------------------------------
    if user_email and from_addr == user_email:
        # User is giving rough instructions or saying "Approve"
        user_reply = input_data.body_text.strip()
        logger.info(f"User {from_addr} replied to Action Card: '{user_reply[:60]}'")

        target_client = mission.get("pending_client_email")
        draft = mission.get("pending_draft", "")

        final_email_text = draft
        if user_reply.lower() not in ["approve", "yes", "send", "ok", "confirm"]:
            # User gave rough notes -> Polish with Bedrock Claude
            polish_prompt = f"""Transform these rough user notes into a polished, professional client response.
Client: {target_client}
Original Draft Context: {draft}
User's Rough Instructions: "{user_reply}"

Rules:
1. Keep it friendly, concise, and professional.
2. Incorporate all adjustments (e.g. price change, file requests).
3. Do not include subject or pleasantry placeholders; provide ready-to-send body text.
"""
            try:
                final_email_text = await bedrock_service.converse(
                    prompt=polish_prompt,
                    system_prompt="You are an expert client communications assistant.",
                    temperature=0.2,
                )
            except Exception as exc:
                logger.warning(f"Polish fallback: {exc}")
                final_email_text = f"{draft}\n\nUpdate: {user_reply}"

        # Dispatch polished reply to client
        if target_client:
            email_service.send_email(
                to_email=target_client,
                subject=f"Re: {input_data.subject}",
                body_text=final_email_text,
                from_name=user_profile.get("name", "Payaam"),
                in_reply_to=input_data.in_reply_to,
                thread_ref=thread_ref,
            )

            # Update mission state
            mission["status"] = "CLIENT_REPLY_SENT"
            mission.pop("pending_client_email", None)
            mission.pop("pending_draft", None)
            dynamodb_service.save_mission(mission)

            return InboundTriageResult(
                intent_category="USER_REFINEMENT",
                should_surface_to_user=True,
                user_notification_subject="✅ Client Response Dispatched",
                user_notification_body=f"Your instructions were polished and dispatched to {target_client}:\n\n\"{final_email_text}\"",
                client_reply_dispatched=True,
                client_reply_body=final_email_text,
            )

    # -------------------------------------------------------------------------
    # Case B: Inbound Email from a Prospect / Lead
    # -------------------------------------------------------------------------
    classification = await _classify_lead_reply(
        body=input_data.body_text,
        subject=input_data.subject,
        user_vault=user_profile,
    )
    cat = classification.get("category", "ACTION_NEEDED")

    # 1. Silent Ignore for Auto-responders / Bounces
    if cat == "IGNORE_AUTO":
        logger.info(f"Silently ignored auto-responder from {from_addr}")
        return InboundTriageResult(
            intent_category="IGNORE_AUTO",
            should_surface_to_user=False,
        )

    # 2. Silent Opt-Out
    if cat == "OPT_OUT":
        logger.info(f"Prospect {from_addr} opted out. Updating mission state silently.")
        if mission:
            mission["status"] = "PROSPECT_OPT_OUT"
            dynamodb_service.save_mission(mission)
        return InboundTriageResult(
            intent_category="OPT_OUT",
            should_surface_to_user=False,
        )

    # 3. Silent Vault Resolution (e.g. asking for portfolio links already in vault)
    if cat == "RESOLVE_SILENTLY" and user_profile.get("portfolio"):
        vault_reply = (
            f"Hi {from_addr.split('@')[0].title()},\n\n"
            f"Thanks for following up! You can check out samples of our recent work here: {user_profile.get('portfolio')}.\n\n"
            f"Let me know if you'd like to explore a quick demo for your business!\n\n"
            f"Best,\n{user_profile.get('name', 'Payaam')}"
        )
        email_service.send_email(
            to_email=from_addr,
            subject=f"Re: {input_data.subject}",
            body_text=vault_reply,
            from_name=user_profile.get("name", "Payaam"),
            in_reply_to=input_data.in_reply_to,
            thread_ref=thread_ref,
        )
        return InboundTriageResult(
            intent_category="RESOLVE_SILENTLY",
            should_surface_to_user=False,
            client_reply_dispatched=True,
            client_reply_body=vault_reply,
        )

    # 4. Action Needed (Two-Knock Knock #1)
    if cat == "ACTION_NEEDED":
        suggested_draft = classification.get("suggested_reply", "Thank you for getting back to us.")
        if mission:
            mission["pending_client_email"] = from_addr
            mission["pending_draft"] = suggested_draft
            mission["status"] = "ACTION_NEEDED_AWAITING_USER"
            dynamodb_service.save_mission(mission)

        action_subject = f"🔥 Payaam Action Needed: {from_addr} Replied"
        action_body = (
            f"Hey {user_profile.get('name', 'there')},\n\n"
            f"Prospect {from_addr} replied to your outreach:\n"
            f"\"{input_data.body_text}\"\n\n"
            f"Suggested Reply Draft:\n"
            f"\"{suggested_draft}\"\n\n"
            f"👉 How would you like to respond?\n"
            f"Reply 'Approve' to send as-is, or reply with your rough adjustments (e.g. 'Counter with $200 and ask for their menu')."
        )
        return InboundTriageResult(
            intent_category="ACTION_NEEDED",
            should_surface_to_user=True,
            user_notification_subject=action_subject,
            user_notification_body=action_body,
        )

    # 5. Result Achieved (Two-Knock Knock #2)
    result_subject = f"🎉 Payaam Deal Signal / Meeting Ready: {from_addr}"
    result_body = (
        f"Hey {user_profile.get('name', 'there')}!\n\n"
        f"Great news! Prospect {from_addr} sent a positive signal or agreed to connect:\n"
        f"\"{input_data.body_text}\"\n\n"
        f"Summary: {classification.get('summary')}\n"
        f"Booking Link sent: {user_profile.get('booking_link', 'cal.com')}\n\n"
        f"Mission marked as COMPLETED."
    )
    if mission:
        mission["status"] = "RESULT_ACHIEVED"
        dynamodb_service.save_mission(mission)

    return InboundTriageResult(
        intent_category="RESULT_ACHIEVED",
        should_surface_to_user=True,
        user_notification_subject=result_subject,
        user_notification_body=result_body,
    )
