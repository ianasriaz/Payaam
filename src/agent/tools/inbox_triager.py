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
from src.agent.copywriting import (
    build_user_email_footer,
    clean_user_name,
    extract_first_name,
    extract_prospect_greeting_name,
    resolve_lead_display_name,
    sanitize_email_copy,
    sanitize_subject_line,
)
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


async def _classify_lead_reply(
    body: str,
    subject: str,
    user_vault: Dict[str, Any],
    prospect_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Uses Bedrock Claude 3.5 Haiku to classify intent and draft an authentic human reply using the Company Knowledge Base."""
    user_name = clean_user_name(user_vault.get("name"))
    user_first = extract_first_name(user_name)
    portfolio = user_vault.get("portfolio", "") or "Available upon request"
    company_kb = user_vault.get("company_profile") or user_vault.get("bio_notes", "")
    addressee = prospect_name or "there"

    prompt = f"""You are triaging an inbound reply from a prospective client to {user_name}.
Subject: {subject}
Body: {body}
Sender Name: {user_name} (Sign off as '{user_first}')
Portfolio: {portfolio}

Company Knowledge Base (Verified facts, packages, FAQs, and office details):
{company_kb if company_kb else "No detailed company profile on file."}

Categories:
1. "IGNORE_AUTO": Out of office, automated vacation notices, delivery failure/bounce.
2. "OPT_OUT": "Unsubscribe", "Not interested", "Remove me", "Wrong email", "No thanks".
3. "RESOLVE_SILENTLY": Inquiring about portfolio, past samples, services, packages, FAQs, contact info, or office address that are answered in the Company Knowledge Base.
4. "ACTION_NEEDED": Pricing negotiation (budget counters), custom requirements, asking for discounts outside standard packages, or scope changes.
5. "RESULT_ACHIEVED": Explicitly agreed to a meeting time, ready to hire/sign, or confirmed price/deal.
6. "BECOME_USER": The prospect is expressing interest in using, signing up for, or deploying the AI agent (Payaam) for their own business or outreach (e.g. 'Can I use this agent for my business?', 'How does this agent work? Can I sign up?', 'Who built this? I want to use it', 'Can you pitch my clients?').

Copywriting Guidelines for "suggested_reply":
- TONE: Natural, direct, conversational human peer. Sound like an experienced builder or freelancer writing a quick email from a laptop. 2 to 4 sentences maximum.
- IF RESOLVE_SILENTLY: Answer the client's specific inquiry directly and accurately using facts from the Company Knowledge Base (e.g. quote exact packages, FAQs, or office address). Follow with a warm, low-friction invitation for next steps.
- PRICING INQUIRIES (if not in KB): Be transparent, direct, and confident. State a realistic ballpark range (e.g. '$250 to $450 one-time setup depending on menu size—zero monthly software fees'), then offer a zero-pressure 5-minute screen share.
- ABSOLUTELY FORBIDDEN:
  * NO markdown headers (NEVER write '# Ready-to-Send Response', '## Draft', etc.).
  * NO quotes wrapping the text.
  * NO corporate AI pleasantries ('Thanks so much for reaching out! I appreciate your interest', 'I hope this email finds you well', 'Rather than sending a generic quote').
  * NO preambles or labels ('Here is the draft:').
- SIGNOFF: End cleanly with 'Best,\n{user_first}' or 'Cheers,\n{user_first}'.

Output valid JSON:
{{
  "category": "ONE_OF_THE_ABOVE",
  "summary": "1-sentence summary of reply",
  "client_question": "Key question or objection if any",
  "suggested_reply": "Clean, natural raw email body"
}}
"""

    try:
        raw_res = await bedrock_service.converse(
            prompt=prompt,
            system_prompt="You are an expert sales communication assistant. You produce natural, human, high-converting emails without AI tropes or leaked markdown headers.",
            temperature=0.2,
            max_tokens=512,
        )
        parsed = extract_json_from_text(raw_res)
        if "suggested_reply" in parsed:
            parsed["suggested_reply"] = sanitize_email_copy(parsed["suggested_reply"], user_name=user_name)
        return parsed
    except Exception as exc:
        logger.warning(f"Classification fallback triggered: {exc}")

    # Fallback heuristic
    body_lower = body.lower()
    if any(w in body_lower for w in ["out of the office", "auto-reply", "vacation", "undeliverable", "delivery failed"]):
        return {"category": "IGNORE_AUTO", "summary": "Auto-responder / bounce", "suggested_reply": ""}
    if any(w in body_lower for w in ["not interested", "unsubscribe", "remove me", "stop"]):
        return {"category": "OPT_OUT", "summary": "Prospect opted out", "suggested_reply": ""}
    if any(w in body_lower for w in ["use this agent", "sign up", "who are you", "who built this", "use payaam", "how does this agent", "pitch my clients"]):
        return {"category": "BECOME_USER", "summary": "Prospect wants to use the agent for their own business", "suggested_reply": ""}
    if any(w in body_lower for w in ["call", "meeting", "zoom", "thursday", "friday", "tomorrow", "sounds good"]):
        return {
            "category": "RESULT_ACHIEVED",
            "summary": "Meeting or interest confirmed",
            "suggested_reply": f"Hi {addressee},\n\nSounds great! Let's connect for a brief 10-minute chat.\n\nBest,\n{user_first}",
        }

    return {
        "category": "ACTION_NEEDED",
        "summary": "Client sent specific inquiry",
        "suggested_reply": f"Hi {addressee},\n\nOur setup typically runs between $250 and $450 one-time depending on your menu size—no monthly software fees.\n\nWould you be open to a quick 5-minute screen share tomorrow or Thursday to see how the WhatsApp order flow works?\n\nBest,\n{user_first}",
    }


@tool
async def triage_inbound_email_tool(input_data: InboundTriageInput) -> InboundTriageResult:
    """Classifies inbound emails and triggers either silent resolution or a Two-Knock User Alert."""
    from_addr = input_data.from_email.strip().lower()
    thread_ref = input_data.thread_ref

    # Correlate with active mission
    mission = dynamodb_service.find_mission_by_thread(thread_ref or "")
    user_email = mission.get("user_email") if mission else None
    user_profile = dynamodb_service.get_user(user_email or from_addr) or {}

    user_name = clean_user_name(user_profile.get("name"), user_email or from_addr)
    user_first_name = extract_first_name(user_name)

    # -------------------------------------------------------------------------
    # Case A: Is the User Replying to an Action Card?
    # -------------------------------------------------------------------------
    if user_email and from_addr == user_email:
        user_reply = input_data.body_text.strip()
        logger.info(f"User {from_addr} replied to Action Card: '{user_reply[:60]}'")

        target_client = mission.get("pending_client_email")
        raw_draft = mission.get("pending_draft", "")
        clean_context = sanitize_email_copy(raw_draft, user_name=user_name)

        # Resolve prospect name from mission record
        target_lead = next(
            (l for l in mission.get("leads", []) if l.get("email", "").lower() == (target_client or "").lower()),
            {},
        )
        prospect_greeting = extract_prospect_greeting_name(target_lead.get("business_name"), target_client)

        final_email_text = clean_context
        if user_reply.lower() not in ["approve", "yes", "send", "ok", "confirm"]:
            # User gave rough notes -> Polish with Bedrock Claude
            polish_prompt = f"""You are writing a natural, direct email response from {user_name} to a client.
Client: {prospect_greeting} ({target_client})
Original Draft Context:
{clean_context}

User's Rough Instructions: "{user_reply}"

Copywriting Rules:
1. Tone: Warm, direct, professional human tone. Sound like an authentic person writing directly from their inbox, NOT an AI bot.
2. Length: Short and punchy (2 to 4 sentences max).
3. Faithfully implement user adjustments (e.g. price counter, timeline, required files).
4. ABSOLUTELY FORBIDDEN:
   - NO markdown headings (NEVER write '# Ready-to-Send Response', '## Draft', etc.).
   - NO meta-labels ('Here is the response:', 'Draft:', 'Subject:').
   - NO quotes wrapping the text.
   - NO robotic pleasantries ('Thanks so much for reaching out', 'Rather than sending a generic quote').
5. Start directly with the greeting 'Hi {prospect_greeting},' and sign off with 'Best,\n{user_first_name}' or 'Cheers,\n{user_first_name}'.
6. Output ONLY the raw email body text.
"""
            try:
                raw_polished = await bedrock_service.converse(
                    prompt=polish_prompt,
                    system_prompt="You are an expert client communications copywriter. You produce concise, high-converting, 100% human-sounding emails.",
                    temperature=0.2,
                )
                final_email_text = sanitize_email_copy(raw_polished, user_name=user_name)
            except Exception as exc:
                logger.warning(f"Polish fallback: {exc}")
                final_email_text = sanitize_email_copy(f"{clean_context}\n\nUpdate: {user_reply}", user_name=user_name)
        else:
            final_email_text = clean_context

        # Dispatch polished reply to client
        if target_client:
            email_service.send_email(
                to_email=target_client,
                subject=f"Re: {sanitize_subject_line(input_data.subject)}",
                body_text=final_email_text,
                from_name=user_name,
                in_reply_to=input_data.in_reply_to,
                thread_ref=thread_ref,
            )

            # Update mission state
            mission["status"] = "CLIENT_REPLY_SENT"
            mission.pop("pending_client_email", None)
            mission.pop("pending_draft", None)
            dynamodb_service.save_mission(mission)

            # Resolve clean display name for target client
            target_display = resolve_lead_display_name(target_lead.get("business_name"), target_client, mission)

            return InboundTriageResult(
                intent_category="USER_REFINEMENT",
                should_surface_to_user=True,
                user_notification_subject=f"✅ Sent: Your reply to {target_display} has been dispatched",
                user_notification_body=(
                    f"Your instructions were polished and dispatched to {target_client}:\n\n"
                    f"----------------------------------------\n"
                    f"{final_email_text}\n"
                    f"----------------------------------------"
                    f"{build_user_email_footer(user_profile)}"
                ),
                client_reply_dispatched=True,
                client_reply_body=final_email_text,
            )

    # -------------------------------------------------------------------------
    # Case B: Inbound Email from a Prospect / Lead
    # -------------------------------------------------------------------------
    # Resolve prospect name from active mission
    matching_lead = {}
    if mission:
        matching_lead = next(
            (l for l in mission.get("leads", []) if l.get("email", "").lower() == from_addr),
            {},
        )
    prospect_greeting = extract_prospect_greeting_name(matching_lead.get("business_name"), from_addr)
    prospect_display = resolve_lead_display_name(matching_lead.get("business_name"), from_addr, mission)

    classification = await _classify_lead_reply(
        body=input_data.body_text,
        subject=input_data.subject,
        user_vault=user_profile,
        prospect_name=prospect_greeting,
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

    # 2b. Lead Wants to Use the Agent (Auto-Conversion to Independent User)
    if cat == "BECOME_USER":
        logger.info(f"Prospect {from_addr} wants to use Payaam! Converting to independent user silently.")
        if mission:
            mission["status"] = "PROSPECT_OPT_OUT"
            dynamodb_service.save_mission(mission)

        # Ensure user account exists in DynamoDB for from_addr
        lead_user = dynamodb_service.get_user(from_addr)
        if not lead_user:
            lead_user = dynamodb_service.save_user({
                "email": from_addr,
                "name": clean_user_name(None, from_addr),
            })

        user_pin = lead_user.get("deletion_pin", "PYM-XXXX")
        user_first = extract_first_name(lead_user.get("name", "there"))
        welcome_subject = "👋 Welcome to Payaam - Start Your Autonomous Outreach"
        welcome_body = (
            f"Hello {user_first}!\n\n"
            "We noticed you'd like to use Payaam for your own business! 🚀\n\n"
            "I am an autonomous background email delegate designed to handle repetitive cold outreach, "
            "client follow-ups, and lead sourcing silently from your inbox.\n\n"
            "💡 How to Get Started:\n"
            "Simply reply to this email with:\n"
            "1. Your Services & Portfolio (or attach your company profile PDF/brochure)\n"
            "2. (Or just reply with target email addresses and what you'd like me to pitch!)\n\n"
            f"Your Data Deletion PIN is: {user_pin}"
            f"{build_user_email_footer(lead_user)}"
        )
        email_service.send_email(
            to_email=from_addr,
            subject=welcome_subject,
            body_text=welcome_body,
            in_reply_to=input_data.in_reply_to,
        )
        return InboundTriageResult(
            intent_category="BECOME_USER",
            should_surface_to_user=False,
            client_reply_dispatched=True,
            client_reply_body=welcome_body,
        )

    # 3. Silent Vault Resolution (Answers routine inquiries directly from Company KB)
    if cat == "RESOLVE_SILENTLY":
        port_str = user_profile.get("portfolio")
        port_ref = f"Here are details and samples of our recent work: {port_str}.\n\n" if port_str else "I would be happy to share relevant project samples and case studies.\n\n"
        raw_vault_reply = classification.get("suggested_reply") or (
            f"Hi {prospect_greeting},\n\n"
            f"{port_ref}"
            f"Would you be open to a quick 5-minute screen share to see how this works for your business?\n\n"
            f"Best,\n{user_first_name}"
        )
        vault_reply = sanitize_email_copy(raw_vault_reply, user_name=user_name)
        email_service.send_email(
            to_email=from_addr,
            subject=f"Re: {sanitize_subject_line(input_data.subject)}",
            body_text=vault_reply,
            from_name=user_name,
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
        raw_draft = classification.get("suggested_reply", f"Hi {prospect_greeting},\n\nHappy to discuss the details.\n\nBest,\n{user_first_name}")
        suggested_draft = sanitize_email_copy(raw_draft, user_name=user_name)
        if mission:
            mission["pending_client_email"] = from_addr
            mission["pending_draft"] = suggested_draft
            mission["status"] = "ACTION_NEEDED_AWAITING_USER"
            dynamodb_service.save_mission(mission)

        action_subject = f"Action needed: {prospect_display} replied to your outreach"
        action_body = (
            f"Hey {user_first_name},\n\n"
            f"Prospect {from_addr} replied to your outreach:\n"
            f"\"{input_data.body_text}\"\n\n"
            f"Suggested Reply Draft:\n"
            f"----------------------------------------\n"
            f"{suggested_draft}\n"
            f"----------------------------------------\n\n"
            f"👉 How would you like to respond?\n"
            f"Reply 'Approve' to send as-is, or reply with your rough adjustments (e.g. 'Counter with $200 and ask for their menu')."
            f"{build_user_email_footer(user_profile)}"
        )
        return InboundTriageResult(
            intent_category="ACTION_NEEDED",
            should_surface_to_user=True,
            user_notification_subject=action_subject,
            user_notification_body=action_body,
        )

    # 5. Result Achieved (Two-Knock Knock #2)
    result_subject = f"🎉 Meeting ready: {prospect_display} wants to connect!"
    result_body = (
        f"Hey {user_first_name}!\n\n"
        f"Great news! Prospect {from_addr} sent a positive signal or agreed to connect:\n"
        f"\"{input_data.body_text}\"\n\n"
        f"Summary: {classification.get('summary')}\n"
        f"Booking Link sent: {user_profile.get('booking_link', 'cal.com')}\n\n"
        f"Mission marked as COMPLETED."
        f"{build_user_email_footer(user_profile)}"
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

