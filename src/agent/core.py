"""Payaam Strands Agent Core Orchestration Engine.

Initializes the Strands Agent instance powered by Amazon Bedrock Claude 3.5 Sonnet,
wires the email-native tool suite, and coordinates autonomous background execution,
Two-Knock surfacing, and Right-to-be-Forgotten data management.
"""

import logging
import re
from typing import Any, Dict, Optional
import boto3
from strands import Agent
from strands.models import BedrockModel
from src.config import settings
from src.services.dynamodb import dynamodb_service
from src.services.email_service import InboundEmail, email_service
from src.agent.copywriting import (
    build_user_email_footer,
    clean_user_name,
    extract_first_name,
    extract_active_reply_text,
    resolve_lead_display_name,
)
from src.agent.tools.onboarding import (
    handle_onboarding_or_greeting_tool,
    OnboardingInput,
)
from src.agent.tools.outreach import (
    dispatch_outreach_mission_tool,
    MissionDispatchInput,
)
from src.agent.tools.inbox_triager import (
    triage_inbound_email_tool,
    InboundTriageInput,
)

logger = logging.getLogger("payaam.agent")

AGENT_SYSTEM_PROMPT = """You are Payaam, an autonomous background email agent built for freelancers, creators, and professionals.
Your purpose is to handle routine and repetitive email tasks (client outreach, vendor sourcing, silent follow-ups)
in the background over SMTP/IMAP via Purelymail.

Operational Principles:
1. ZERO-APP EMAIL INTERFACE: All interactions occur naturally over email. You manage onboarding, credentials, missions, and data deletion natively.
2. TWO-KNOCK POLICY: Run silently in the background. Never surface to the user UNLESS:
   - (Knock 1) ACTION_NEEDED: A real decision, budget negotiation, or approval is required.
   - (Knock 2) RESULT_ACHIEVED: A meeting is booked, deal signed, or mission completed.
3. SILENT BACKGROUND HANDLING: Silently ignore auto-responders, bounces, and rejections. Autonomously answer routine questions from the user's Memory Vault.
4. PRIVACY & RIGHT-TO-BE-FORGOTTEN: Strictly enforce user privacy. Provide cryptographic PIN-based deletion so users can purge all data on demand.
5. ANTI-SPAM COLLISION SHIELD: Always check the global contact registry before reaching out to protect recipient deliverability.
"""


class PayaamAgent:
    """Core autonomous agent orchestrator for Purelymail email missions."""

    def __init__(self) -> None:
        self.logger = logger
        self._agent: Optional[Agent] = None
        self._initialize_agent()

    def _initialize_agent(self) -> None:
        """Configures Strands Agent with Bedrock provider and registered tools."""
        self.logger.info("Initializing Payaam Strands Agent core engine.")

        kwargs: Dict[str, Any] = {"region_name": settings.AWS_REGION}
        if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
            kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
            kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY

        session = boto3.Session(**kwargs)

        model = BedrockModel(
            boto_session=session,
            model_id=settings.BEDROCK_MODEL_SONNET,
            temperature=0.2,
        )

        tools = [
            handle_onboarding_or_greeting_tool,
            dispatch_outreach_mission_tool,
            triage_inbound_email_tool,
        ]

        self._agent = Agent(
            model=model,
            tools=tools,
            system_prompt=AGENT_SYSTEM_PROMPT,
        )

    async def plan_or_advise_user(
        self,
        sender: str,
        sender_name: Optional[str],
        subject: str,
        body: str,
        attachments: Any = None,
    ) -> Dict[str, str]:
        """Uses Amazon Bedrock (Claude 3.5 Sonnet) to intelligently comprehend the user's inquiry,
        provide custom pitch strategy/drafting, and guide them on how to dispatch.
        """
        user_profile = dynamodb_service.get_user(sender) or {}
        clean_name = clean_user_name(sender_name or user_profile.get("name"), sender)
        user_first = extract_first_name(clean_name)
        salutation = f"Hello {user_first}!" if user_first.lower() != "there" else "Hello there!"
        footer = build_user_email_footer(user_profile)

        system_prompt = (
            "You are Payaam, an autonomous AI email delegate for solo operators, agencies, and businesses. "
            "A user has emailed you instructions, questions, or an outreach goal, but hasn't provided specific recipient email addresses yet.\n"
            "Your job is to act as an executive, highly competent AI Chief of Staff:\n"
            "1. Acknowledge and understand their specific business, question, or outreach goal.\n"
            "2. If they described a service or wanting to pitch clients/partners:\n"
            "   - Provide a concise, punchy, tailored 3-sentence pitch draft specifically crafted for their business.\n"
            "   - Give them one crystal-clear next step: 'To dispatch this, simply reply with your list of recipient emails (e.g. contact@company.com, info@biz.com), and I will take over silently in your background!'\n"
            "3. If they asked a general question (e.g. capabilities, SMTP setup, or how Payaam works):\n"
            "   - Answer directly and warmly in 2-3 short, clear paragraphs.\n"
            "4. NEVER dump generic freelancer templates, and never mention unrelated personal links.\n"
            "5. Tone: Confident, respectful, human, and executive."
        )

        prompt = f"""User Email: {sender}
User Name: {clean_name}
Subject: {subject}
Message:
{body}

Write a helpful, direct response to this user. Do NOT include the privacy footer (it will be appended automatically)."""

        try:
            from src.services.bedrock import bedrock_service
            raw_response = await bedrock_service.converse(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.3,
            )
            from src.agent.copywriting import sanitize_email_copy, sanitize_subject_line
            body_cleaned = sanitize_email_copy(raw_response, user_name=clean_name)

            reply_subj = subject if subject.lower().startswith("re:") else f"Re: {subject}"
            if not reply_subj or reply_subj.strip().lower() in ["re:", "re: help", "re: query"]:
                reply_subj = "📋 Your Payaam Outreach Plan & Next Steps"

            return {
                "subject": sanitize_subject_line(reply_subj),
                "body": f"{body_cleaned}\n{footer}",
            }
        except Exception as exc:
            self.logger.warning(f"Bedrock planning fallback ({exc})")
            return {
                "subject": f"Re: {subject}",
                "body": (
                    f"{salutation}\n\n"
                    "I received your instructions! I'm ready to handle this outreach for you.\n\n"
                    "💡 To launch this mission:\n"
                    "Simply reply to this email with the recipient email addresses you would like me to contact "
                    "(e.g. 'contact@company.com, info@agency.com').\n\n"
                    "Once you provide the targets, I will generate bespoke pitches and manage the outreach silently in your background!"
                    f"{footer}"
                ),
            }

    async def process_inbound_email(self, email_data: InboundEmail) -> Dict[str, Any]:
        """Main entrypoint for processing any incoming email from IMAP.

        Routes intelligently between:
        1. Onboarding / Greeting / BYO-SMTP / Deletion.
        2. Inbound Lead Reply or User Refinement on Active Mission (Two-Knock Policy).
        3. New Mission Dispatch.
        """
        sender = email_data.from_address
        subject = email_data.subject
        body = email_data.body_text
        thread_ref = email_data.thread_ref

        self.logger.info(f"Processing inbound email from {sender} | Subj: {subject} | Ref: {thread_ref}")

        # Guard: Immediately drop any system, bounce, or self-addressed emails
        sender_clean = (sender or "").strip().lower()
        if any(re.search(pat, sender_clean) for pat in [
            r"^noreply@", r"^no-reply@", r"^mailer-daemon@", r"^postmaster@", r"^bounce@", r"^bounces@", r"@purelymail\.com$"
        ]) or sender_clean in ["agent@anasriaz.com", "payaam@anasriaz.com"]:
            self.logger.info(f"Dropping automated bounce/system email from {sender}")
            return {"route": "DROPPED_BOUNCE", "response_sent": False}

        # ---------------------------------------------------------------------
        # Step 1: Universal Admin Commands (Right-to-be-Forgotten or BYO-SMTP)
        # ---------------------------------------------------------------------
        active_body = extract_active_reply_text(body)
        active_upper = f"{subject}\n{active_body}".upper()
        if "DELETE" in active_upper or "CONNECT_SMTP" in active_upper:
            onboarding_res = await handle_onboarding_or_greeting_tool(
                OnboardingInput(
                    user_email=sender,
                    user_name=email_data.from_name,
                    email_subject=subject,
                    email_body=active_body,
                    attachments=email_data.attachments,
                )
            )
            if onboarding_res.action_type != "PASSTHROUGH":
                self.logger.info(f"Admin command handled: action={onboarding_res.action_type}")
                email_service.send_email(
                    to_email=sender,
                    subject=onboarding_res.response_subject,
                    body_text=onboarding_res.response_body,
                    in_reply_to=email_data.message_id,
                )
                return {
                    "route": "ONBOARDING",
                    "action": onboarding_res.action_type,
                    "response_sent": True,
                }

        # ---------------------------------------------------------------------
        # Step 2: Check If Correlated with an Active Mission (Two-Knock Policy)
        # ---------------------------------------------------------------------
        active_body = extract_active_reply_text(body)

        # 2a. Check if sender is an active prospect/lead in an ongoing mission
        correlated_mission = None
        is_lead_reply = False

        lead_mission = dynamodb_service.find_mission_by_thread(thread_ref or "", sender_email=sender)
        if lead_mission:
            # Verify if sender is one of the leads on this mission
            if any(l.get("email", "").strip().lower() == sender_clean for l in lead_mission.get("leads", [])):
                correlated_mission = lead_mission
                is_lead_reply = True

        # 2b. If not a lead, check if mission owner is replying to an Action Card
        if not correlated_mission and thread_ref:
            user_mission = dynamodb_service.find_mission_by_thread(thread_ref)
            if user_mission and user_mission.get("user_email", "").strip().lower() == sender_clean:
                from src.agent.tools.outreach import _extract_leads_from_text
                new_leads_in_reply = _extract_leads_from_text(active_body)
                if not new_leads_in_reply:
                    correlated_mission = user_mission

        if correlated_mission:
            self.logger.info(f"Correlated email with active mission {correlated_mission.get('mission_id')} (is_lead={is_lead_reply})")
            triage_res = await triage_inbound_email_tool(
                InboundTriageInput(
                    from_email=sender,
                    subject=subject,
                    body_text=active_body or body,
                    thread_ref=thread_ref or (correlated_mission.get("thread_refs", [""])[0] if correlated_mission.get("thread_refs") else None),
                    in_reply_to=email_data.message_id,
                )
            )

            # If Two-Knock dictates surfacing to user, dispatch notification
            if triage_res.should_surface_to_user and triage_res.user_notification_subject:
                user_target = correlated_mission.get("user_email", sender)
                email_service.send_email(
                    to_email=user_target,
                    subject=triage_res.user_notification_subject,
                    body_text=triage_res.user_notification_body or "",
                    thread_ref=thread_ref,
                )

            return {
                "route": "MISSION_TRIAGE",
                "intent": triage_res.intent_category,
                "surfaced_to_user": triage_res.should_surface_to_user,
                "client_replied": triage_res.client_reply_dispatched,
            }

        # ---------------------------------------------------------------------
        # Step 3: Check Onboarding / Greeting / Profile Setup (Unthreaded)
        # ---------------------------------------------------------------------
        onboarding_res = await handle_onboarding_or_greeting_tool(
            OnboardingInput(
                user_email=sender,
                user_name=email_data.from_name,
                email_subject=subject,
                email_body=body,
                attachments=email_data.attachments,
            )
        )

        if onboarding_res.action_type != "PASSTHROUGH":
            self.logger.info(f"Onboarding tool handled email: action={onboarding_res.action_type}")
            # Reply back to sender with guide/confirmation
            email_service.send_email(
                to_email=sender,
                subject=onboarding_res.response_subject,
                body_text=onboarding_res.response_body,
                in_reply_to=email_data.message_id,
            )
            return {
                "route": "ONBOARDING",
                "action": onboarding_res.action_type,
                "response_sent": True,
            }

        # ---------------------------------------------------------------------
        # Step 4: Check if Target Leads Are Provided for Active Mission
        # ---------------------------------------------------------------------
        from src.agent.tools.outreach import _extract_leads_from_text
        candidate_leads = _extract_leads_from_text(body)

        if candidate_leads:
            self.logger.info(f"Dispatching new mission for user {sender} ({len(candidate_leads)} leads)")

            # Ingest attached documents (e.g. Company Profile PDF/brochures) into user Memory Vault
            if email_data.attachments:
                from src.services.bedrock import bedrock_service
                extracted_doc_text = ""
                for att in email_data.attachments:
                    fn = getattr(att, "filename", "") or ""
                    ext = fn.split(".")[-1].lower() if "." in fn else ""
                    if ext in ["pdf", "txt", "md", "doc", "docx", "csv", "html"]:
                        raw_data = getattr(att, "data_bytes", b"")
                        if raw_data:
                            self.logger.info(f"Extracting company profile knowledge from mission attachment '{fn}'")
                            knowledge = await bedrock_service.extract_document_knowledge(
                                doc_bytes=raw_data,
                                doc_format=ext,
                                doc_name=fn,
                            )
                            if knowledge:
                                extracted_doc_text += f"\n\n--- Document Knowledge ({fn}) ---\n{knowledge}"
                if extracted_doc_text:
                    user_data = dict(dynamodb_service.get_user(sender) or {})
                    existing_profile = user_data.get("company_profile", "")
                    user_data.update({
                        "email": sender,
                        "name": clean_user_name(email_data.from_name or user_data.get("name"), sender),
                        "company_profile": (extracted_doc_text + "\n\n" + existing_profile).strip(),
                    })
                    dynamodb_service.save_user(user_data)
                    self.logger.info(f"Updated user {sender} company profile from mission attachment.")

            dispatch_res = await dispatch_outreach_mission_tool(
                MissionDispatchInput(
                    user_email=sender,
                    raw_instructions=body,
                    target_leads=candidate_leads,
                )
            )

            user_name = clean_user_name(email_data.from_name, sender)
            user_first = extract_first_name(user_name)
            salutation = f"Hey {user_first}," if user_first.lower() != "there" else "Hello there,"
            user_profile = dynamodb_service.get_user(sender) or {"name": user_name, "email": sender}
            footer = build_user_email_footer(user_profile)

            if dispatch_res.dispatched_count == 1 and dispatch_res.dispatched_leads:
                lead_disp = resolve_lead_display_name(None, dispatch_res.dispatched_leads[0])
                receipt_subject = f"🚀 Outreach launched to {lead_disp}"
            elif dispatch_res.dispatched_count > 0:
                receipt_subject = f"🚀 Outreach launched ({dispatch_res.dispatched_count} prospects)"
            else:
                receipt_subject = "🚀 Outreach mission processed"

            email_service.send_email(
                to_email=sender,
                subject=receipt_subject,
                body_text=(
                    f"{salutation}\n\n"
                    f"{dispatch_res.summary_message}\n\n"
                    f"Payaam is now managing this outreach silently in the background. "
                    f"I will handle auto-responders, follow-ups, and routine questions automatically, "
                    f"and will only surface to your inbox when a decision or confirmed meeting is ready!\n\n"
                    f"Mission ID: {dispatch_res.mission_id}"
                    f"{footer}"
                ),
                in_reply_to=email_data.message_id,
            )

            return {
                "route": "NEW_MISSION_DISPATCHED",
                "mission_id": dispatch_res.mission_id,
                "dispatched_count": dispatch_res.dispatched_count,
                "collisions": len(dispatch_res.collisions_detected),
            }

        # ---------------------------------------------------------------------
        # Step 5: Intelligent Assistant / Mission Planner (No Leads Provided)
        # ---------------------------------------------------------------------
        self.logger.info(f"Providing intelligent advisory response for user {sender}")
        advisory_res = await self.plan_or_advise_user(
            sender=sender,
            sender_name=email_data.from_name,
            subject=subject,
            body=body,
            attachments=email_data.attachments,
        )
        email_service.send_email(
            to_email=sender,
            subject=advisory_res["subject"],
            body_text=advisory_res["body"],
            in_reply_to=email_data.message_id,
        )
        return {
            "route": "ADVISORY_RESPONSE",
            "action": "PLANNING_OR_INQUIRY",
            "response_sent": True,
        }



payaam_agent = PayaamAgent()
