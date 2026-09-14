"""Autonomous Outreach & Multi-Vendor Dispatch Tool for Payaam.

Coordinates:
1. Extraction of target leads and mission parameters.
2. Pre-flight multi-tenant collision checking (anti-spam guardrail).
3. Contextual copywriting via Bedrock Claude 3.5 Sonnet utilizing the user's Memory Vault.
4. Reliable email dispatch via Purelymail or user's connected BYO-SMTP.
5. Ephemeral mission persistence and global registry updates in DynamoDB.
"""

import logging
import re
import secrets
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from strands import tool
from src.services.bedrock import bedrock_service
from src.services.crypto import decrypt_secret
from src.services.dynamodb import dynamodb_service
from src.services.email_service import email_service

logger = logging.getLogger("payaam.agent.tools.outreach")


class LeadTarget(BaseModel):
    email: str = Field(description="Target business email address.")
    business_name: Optional[str] = Field(default=None, description="Extracted business or recipient name.")


class MissionDispatchInput(BaseModel):
    user_email: str = Field(description="Email of the user requesting the mission.")
    raw_instructions: str = Field(description="User's plain instruction or goal.")
    target_leads: Optional[List[LeadTarget]] = Field(default=None, description="Explicit list of leads if pre-parsed.")
    category: str = Field(default="freelance_web_design", description="Category for collision tracking.")


class MissionDispatchResult(BaseModel):
    mission_id: str
    dispatched_count: int
    collisions_detected: List[Dict[str, Any]]
    dispatched_leads: List[str]
    summary_message: str


def _clean_lead_name(raw: Optional[str], email: str) -> str:
    """Sanitizes raw lead name by stripping bullet lists, numbering, and trailing punctuation."""
    if not raw:
        return email.split("@")[0].title()
    cleaned = re.sub(r"^\s*(?:\d+[\.\)]|\*|-|\+)\s*", "", raw)
    cleaned = cleaned.strip(" -:\t\n()[]")
    if cleaned.count("(") > cleaned.count(")"):
        cleaned += ")"
    return cleaned or email.split("@")[0].title()


def _extract_greeting_name(raw_name: str) -> str:
    """Extracts a personalized greeting name (e.g. 'Sarah' or 'Dr. Chen') from a lead's full description."""
    cleaned = re.sub(r"\(.*?\)", "", raw_name).strip(" -:\t\n()[]")
    tokens = cleaned.split()
    if not tokens:
        return "there"
    honorifics = {"dr.", "mr.", "mrs.", "ms.", "prof."}
    first_token = tokens[0].lower().rstrip(".") + "."
    if first_token in honorifics and len(tokens) > 1:
        return f"{tokens[0]} {tokens[1]}"
    return tokens[0]


def _extract_leads_from_text(text: str) -> List[LeadTarget]:
    """Extracts email addresses and individual recipient names or titles from text.

    Supports:
    - Name <email> (e.g. Alex Chen <alex@ai-labs.org>)
    - Name (email - Title) (e.g. Sarah Jenkins (sarah@fintech.io - Head of Eng))
    - email (Name / Title) (e.g. sarah@fintech.io (Sarah Jenkins))
    - Name: email / Name - email (e.g. David Ross: david@cloudscale.com)
    - Standalone email (e.g. orders@startup.com)
    """
    leads: List[LeadTarget] = []
    seen = set()

    def _add_lead(email_str: str, raw_name_str: Optional[str] = None):
        clean_email = email_str.strip().lower()
        if clean_email not in seen and not any(w in clean_email for w in ["payaam", "workdost", "yourdomain", "purelymail"]):
            seen.add(clean_email)
            clean_name = _clean_lead_name(raw_name_str, clean_email)
            leads.append(LeadTarget(email=clean_email, business_name=clean_name))

    # Pattern 1: Name <email>
    for match in re.finditer(r"([A-Za-z0-9\s&'.-]+?)\s*<([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)>", text):
        _add_lead(match.group(2), match.group(1))

    # Pattern 2: Name (email - Title) or Name (email)
    for match in re.finditer(r"([A-Za-z0-9\s&'.-]+?)\s*\(\s*([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)(?:\s*[-–]\s*([^)]+))?\)", text):
        name_part = match.group(1).strip()
        extra_title = match.group(3)
        full_info = f"{name_part} ({extra_title})" if extra_title else name_part
        _add_lead(match.group(2), full_info)

    # Pattern 3: Name: email (Title) or Name - email (Title)
    for match in re.finditer(r"([A-Za-z0-9\s&'.-]+?)\s*[:\-–]\s*([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)(?:\s*\(([^)]+)\))?", text):
        name_part = match.group(1).strip()
        extra = match.group(3)
        full_info = f"{name_part} ({extra.strip()})" if extra else name_part
        _add_lead(match.group(2), full_info)

    # Pattern 4: email (Name / Title)
    for match in re.finditer(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)\s*\(([^)]+)\)", text):
        _add_lead(match.group(1), match.group(2))

    # Pattern 5: Standalone email
    for match in re.finditer(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", text):
        _add_lead(match.group(1), None)

    return leads


async def _generate_pitch_copy(
    target_name: str,
    target_email: str,
    user_name: str,
    user_portfolio: str,
    instructions: str,
) -> Dict[str, str]:
    """Uses Bedrock Claude 3.5 Sonnet to draft an individualized, high-converting outreach email.

    Dynamically adapts for:
    - Job applications / recruiting pitches to hiring managers.
    - Competition, grant, or hackathon project submissions to judges.
    - B2B client acquisition or freelance services.
    """
    greeting_name = _extract_greeting_name(target_name)

    prompt = f"""You are drafting a concise, highly personalized outreach email for {user_name}.
Target Recipient: {target_name} ({target_email})
Sender Name: {user_name}
Sender Portfolio / Work: {user_portfolio or 'Available upon request'}
Mission Intent & Instructions: {instructions}

Personalization & Intent Rules:
1. GREETING:
   - Address the individual by their name (e.g., 'Hi {greeting_name},' or 'Dear {greeting_name},').
   - If the target is strictly an organization with no person specified, use 'Hi {target_name} team,'.
   - Never use robotic placeholders like '[Name]', 'Dear Sir/Madam', or 'To Whom It May Concern'.
2. ADAPT TO THE GOAL:
   - JOB / HIRING APPLICATION:
     * Hook: Reference their company/team and why the role/work stands out.
     * Proof: Highlight {user_name}'s specific technical strengths and impact requested in the instructions, citing the portfolio ({user_portfolio or 'portfolio'}).
     * Call to Action: Low-friction invitation (e.g., 'Would you be open to a brief 10-minute chat this week if my background aligns?').
   - COMPETITION / HACKATHON / GRANT PITCH:
     * Hook: Introduce the project and the specific problem it solves for the competition/hackathon.
     * Proof: Highlight the architecture, unique innovation, and link to the demo/repository ({user_portfolio or 'live demo'}).
     * Call to Action: Respectfully invite their evaluation and offer to answer any technical questions.
   - B2B CLIENT / FREELANCE OUTREACH:
     * Hook: Specific, empathetic observation about their current setup or customer experience.
     * Proof: High-impact turnaround, citing portfolio ({user_portfolio or 'case studies'}).
     * Call to Action: Zero-pressure soft question (e.g., 'Mind if I share a quick 30-second walkthrough?').
3. LENGTH & STYLE:
   - 3 to 4 punchy, respectful sentences.
   - Crisp, engaging, human tone with zero generic fluff.
   - Tailor an eye-catching subject line mentioning the recipient, company, role, or project.

Return JSON in this format:
{{
  "subject": "Subject Line",
  "body": "Email Body"
}}
"""
    try:
        raw_response = await bedrock_service.converse(
            prompt=prompt,
            system_prompt="You are an expert personalized outreach copywriter for professionals, builders, and solo creators.",
            temperature=0.2,
        )
        from src.services.bedrock import extract_json_from_text
        parsed = extract_json_from_text(raw_response)
        if "subject" in parsed and "body" in parsed:
            return parsed
    except Exception as exc:
        logger.warning(f"Bedrock pitch generation fallback ({exc})")

    # High-quality dynamic fallback template
    instr_lower = instructions.lower()
    port = user_portfolio or "https://anasriaz.com"
    clean_org = target_name.split("(")[0].strip()

    if any(w in instr_lower for w in ["job", "role", "hire", "hiring", "position", "engineer", "developer", "resume", "apply"]):
        subj = f"Application / Engineering Inquiry - {user_name}"
        body = (
            f"Hi {greeting_name},\n\n"
            f"I came across your work at {clean_org} and wanted to reach out regarding the role and opportunities with your engineering team. "
            f"I specialize in building scalable software systems, Python engineering, and autonomous AI agents (portfolio & projects at {port}). "
            f"Would you be open to a quick 10-minute conversation this week if my background looks like a fit?\n\n"
            f"Best regards,\n{user_name}"
        )
    elif any(w in instr_lower for w in ["competition", "hackathon", "grant", "contest", "award", "judge"]):
        subj = f"Project Submission - {user_name}"
        body = (
            f"Hi {greeting_name},\n\n"
            f"I am writing to share our project submission and technical proposal for the competition. "
            f"We have engineered an autonomous, privacy-first platform (live demo and documentation at {port}). "
            f"We would love your feedback and are available to answer any questions during the review process.\n\n"
            f"Warmly,\n{user_name}"
        )
    else:
        subj = f"Quick question regarding {clean_org}'s setup"
        body = (
            f"Hi {greeting_name},\n\n"
            f"I noticed an opportunity to elevate and streamline your current online workflow at {clean_org}. "
            f"We build clean, high-impact digital solutions that launch in under 4 days (case studies at {port}). "
            f"Mind if I share a quick 30-second walkthrough of how this works?\n\n"
            f"Best,\n{user_name}"
        )

    return {"subject": subj, "body": body}


@tool
async def dispatch_outreach_mission_tool(input_data: MissionDispatchInput) -> MissionDispatchResult:
    """Dispatches personalized outreach emails to candidate leads with collision protection and state persistence."""
    user_email = input_data.user_email.strip().lower()
    user_profile = dynamodb_service.get_user(user_email) or {
        "name": user_email.split("@")[0].title(),
        "portfolio": "https://anasriaz.com",
    }
    user_name = user_profile.get("name", "Freelance Consultant")
    user_portfolio = user_profile.get("portfolio", "")

    # Decrypt BYO-SMTP credentials if configured
    custom_smtp = None
    if user_profile.get("smtp_config"):
        cfg = user_profile["smtp_config"]
        try:
            plain_pass = decrypt_secret(cfg.get("encrypted_password", ""))
            custom_smtp = {
                "host": cfg.get("host"),
                "port": cfg.get("port", 465),
                "username": cfg.get("username"),
                "password": plain_pass,
            }
        except Exception as exc:
            logger.error(f"Failed to decrypt user custom SMTP credentials: {exc}")

    # Extract leads
    leads = input_data.target_leads or _extract_leads_from_text(input_data.raw_instructions)
    if not leads:
        return MissionDispatchResult(
            mission_id="",
            dispatched_count=0,
            collisions_detected=[],
            dispatched_leads=[],
            summary_message="No valid target email addresses could be identified from your instructions.",
        )

    mission_id = f"PYM-{secrets.token_hex(3).upper()}"
    collisions: List[Dict[str, Any]] = []
    dispatched: List[str] = []
    thread_refs: List[str] = []

    for lead in leads:
        # Pre-flight collision check
        collision = dynamodb_service.check_collision(lead.email, category=input_data.category)
        if collision.get("has_collision"):
            logger.warning(f"Collision detected for lead {lead.email}: Contacted {collision.get('days_ago')} days ago.")
            collisions.append({
                "lead_email": lead.email,
                "days_ago": collision.get("days_ago"),
                "category": collision.get("last_category"),
            })

        # Draft tailored pitch
        pitch = await _generate_pitch_copy(
            target_name=lead.business_name or "Team",
            target_email=lead.email,
            user_name=user_name,
            user_portfolio=user_portfolio,
            instructions=input_data.raw_instructions,
        )

        clean_slug = re.sub(r"[^A-Za-z0-9]", "", lead.business_name or "Lead")[:10]
        thread_ref = f"{mission_id}-{clean_slug}"
        thread_refs.append(thread_ref)

        # Dispatch email
        send_res = email_service.send_email(
            to_email=lead.email,
            subject=pitch["subject"],
            body_text=pitch["body"],
            from_name=user_name,
            from_email=custom_smtp.get("username") if custom_smtp else None,
            custom_smtp=custom_smtp,
            thread_ref=thread_ref,
        )

        if send_res.get("success"):
            dispatched.append(lead.email)
            # Record contact in global collision registry
            dynamodb_service.record_contact(
                target_email=lead.email,
                contacted_by=user_email,
                category=input_data.category,
            )

    # Save mission state
    mission_record = {
        "mission_id": mission_id,
        "user_email": user_email,
        "instructions": input_data.raw_instructions,
        "category": input_data.category,
        "leads": [lead.model_dump() for lead in leads],
        "dispatched_leads": dispatched,
        "thread_refs": thread_refs,
        "status": "OUTREACH_DISPATCHED",
        "collisions": collisions,
    }
    dynamodb_service.save_mission(mission_record)

    # Build summary message
    summary = f"🚀 Mission {mission_id} dispatched to {len(dispatched)} recipient(s)."
    if collisions:
        summary += f" ⚠️ Note: {len(collisions)} contact(s) had previous outreach logged within 14 days."

    return MissionDispatchResult(
        mission_id=mission_id,
        dispatched_count=len(dispatched),
        collisions_detected=collisions,
        dispatched_leads=dispatched,
        summary_message=summary,
    )
