"""Payaam Strands Agent Core Orchestration Engine.

Initializes the Strands Agent instance powered by Amazon Bedrock Claude 3.5 Sonnet,
wires the email-native tool suite, and coordinates autonomous background execution,
Two-Knock surfacing, and Right-to-be-Forgotten data management.
"""

import logging
from typing import Any, Dict, Optional
import boto3
from strands import Agent
from strands.models import BedrockModel
from src.config import settings
from src.services.dynamodb import dynamodb_service
from src.services.email_service import InboundEmail, email_service
from src.agent.copywriting import clean_user_name, extract_first_name
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

AGENT_SYSTEM_PROMPT = """You are Payaam (پیام), an autonomous background email agent built for freelancers, creators, and professionals.
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

        # ---------------------------------------------------------------------
        # Step 1: Universal Admin Commands (Right-to-be-Forgotten or BYO-SMTP)
        # ---------------------------------------------------------------------
        body_upper = body.upper()
        if "DELETE MY DATA" in body_upper or "CONNECT_SMTP" in body_upper:
            onboarding_res = handle_onboarding_or_greeting_tool(
                OnboardingInput(
                    user_email=sender,
                    user_name=email_data.from_name,
                    email_subject=subject,
                    email_body=body,
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
        correlated_mission = dynamodb_service.find_mission_by_thread(thread_ref or "", sender_email=sender)
        if correlated_mission:
            self.logger.info(f"Correlated email with active mission {correlated_mission.get('mission_id')}")
            triage_res = await triage_inbound_email_tool(
                InboundTriageInput(
                    from_email=sender,
                    subject=subject,
                    body_text=body,
                    thread_ref=thread_ref,
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
        onboarding_res = handle_onboarding_or_greeting_tool(
            OnboardingInput(
                user_email=sender,
                user_name=email_data.from_name,
                email_subject=subject,
                email_body=body,
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
        # Step 4: Treat as a New Mission Request
        # ---------------------------------------------------------------------
        self.logger.info(f"Dispatching new mission for user {sender}")
        dispatch_res = await dispatch_outreach_mission_tool(
            MissionDispatchInput(
                user_email=sender,
                raw_instructions=body,
            )
        )

        # Send launch receipt back to the user
        user_name = clean_user_name(email_data.from_name, sender)
        user_first = extract_first_name(user_name)
        email_service.send_email(
            to_email=sender,
            subject=f"🚀 Payaam Mission Launched: {dispatch_res.mission_id}",
            body_text=(
                f"Hey {user_first},\n\n"
                f"{dispatch_res.summary_message}\n\n"
                f"Payaam is now managing this outreach silently in the background. "
                f"I will handle auto-responders, follow-ups, and routine questions automatically, "
                f"and will only surface to your inbox when a decision or confirmed meeting is ready!\n\n"
                f"Mission ID: {dispatch_res.mission_id}"
            ),
            in_reply_to=email_data.message_id,
        )

        return {
            "route": "NEW_MISSION_DISPATCHED",
            "mission_id": dispatch_res.mission_id,
            "dispatched_count": dispatch_res.dispatched_count,
            "collisions": len(dispatch_res.collisions_detected),
        }


payaam_agent = PayaamAgent()
