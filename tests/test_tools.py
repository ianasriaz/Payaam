"""Unit tests for the Payaam Email Agent Tools."""

import pytest
from src.agent.tools.onboarding import (
    handle_onboarding_or_greeting_tool,
    OnboardingInput,
)
from src.agent.tools.outreach import (
    dispatch_outreach_mission_tool,
    MissionDispatchInput,
    _extract_leads_from_text,
)
from src.agent.tools.inbox_triager import (
    triage_inbound_email_tool,
    InboundTriageInput,
    _classify_lead_reply,
)
from src.services.dynamodb import dynamodb_service


@pytest.mark.asyncio
async def test_onboarding_greeting_detection():
    res = await handle_onboarding_or_greeting_tool(
        OnboardingInput(
            user_email="newuser@example.com",
            user_name="New User",
            email_subject="Hi",
            email_body="What can you do for me?",
        )
    )
    assert res.action_type == "GREETING"
    assert "Welcome to Payaam" in res.response_subject
    assert "DELETE MY DATA" in res.response_body
    assert "CONNECT_SMTP" in res.response_body


@pytest.mark.asyncio
async def test_onboarding_profile_setup():
    res = await handle_onboarding_or_greeting_tool(
        OnboardingInput(
            user_email="designer@example.com",
            user_name="Jane Designer",
            email_subject="Setup: My Profile",
            email_body="I'm a UI/UX designer. Portfolio: https://jane.design. Rates $400 - $800.",
        )
    )
    assert res.action_type == "PROFILE_SAVED"
    assert res.user_profile is not None
    assert res.user_profile["portfolio"] == "https://jane.design"
    assert any(p in res.user_profile["deletion_pin"] for p in ["PYM-", "WD-"])
    assert "Payaam User Privacy & Email Controls" in res.response_body


@pytest.mark.asyncio
async def test_onboarding_data_deletion_with_pin():
    email = "delete_me@example.com"
    user = dynamodb_service.save_user({"email": email, "name": "Temporary User"})
    pin = user["deletion_pin"]

    res = await handle_onboarding_or_greeting_tool(
        OnboardingInput(
            user_email=email,
            email_subject="Delete my data",
            email_body=f"DELETE MY DATA {pin}",
        )
    )
    assert res.action_type == "DATA_DELETED"
    assert dynamodb_service.get_user(email) is None



def test_extract_leads_from_text():
    text = """Please outreach these prospects:
- contact@roastandbean.com (Roast & Bean)
- Greenleaf Bistro <info@greenleafbistro.com>
- orders@pizzahaus.com
"""
    leads = _extract_leads_from_text(text)
    assert len(leads) == 3
    emails = [l.email for l in leads]
    assert "contact@roastandbean.com" in emails
    assert "info@greenleafbistro.com" in emails
    assert "orders@pizzahaus.com" in emails


@pytest.mark.asyncio
async def test_lead_reply_classification_heuristics():
    vault = {"portfolio": "https://anasriaz.com", "name": "Anas"}

    # 1. Out of office
    res_ooo = await _classify_lead_reply(
        body="I am out of the office on vacation until next Tuesday.",
        subject="Re: Inquiry",
        user_vault=vault,
    )
    assert res_ooo["category"] == "IGNORE_AUTO"

    # 2. Opt out
    res_opt = await _classify_lead_reply(
        body="Please unsubscribe and remove me from your list. Not interested.",
        subject="Re: Inquiry",
        user_vault=vault,
    )
    assert res_opt["category"] == "OPT_OUT"


def test_extract_leads_job_and_competition_formats():
    text = """Apply for the Senior Backend Engineer role:
1. Sarah Jenkins (sarah@fintech.io - Head of Engineering)
2. Alex Chen <alex@ai-labs.org>
3. David Ross - david@cloudscale.com
4. Dr. Alan Turing: alan@cambridge.edu (Hackathon Judge)
5. plain@company.com
"""
    leads = _extract_leads_from_text(text)
    assert len(leads) == 5
    lead_map = {l.email: l.business_name for l in leads}

    assert "sarah@fintech.io" in lead_map
    assert "Sarah Jenkins" in lead_map["sarah@fintech.io"]

    assert "alex@ai-labs.org" in lead_map
    assert lead_map["alex@ai-labs.org"] == "Alex Chen"

    assert "david@cloudscale.com" in lead_map
    assert lead_map["david@cloudscale.com"] == "David Ross"

    assert "alan@cambridge.edu" in lead_map
    assert "Dr. Alan Turing" in lead_map["alan@cambridge.edu"]


@pytest.mark.asyncio
async def test_personalized_pitch_copy_fallback():
    from src.agent.tools.outreach import _generate_pitch_copy

    # 1. Job application copy
    job_pitch = await _generate_pitch_copy(
        target_name="Sarah Jenkins (Head of Engineering)",
        target_email="sarah@fintech.io",
        user_name="Anas Riaz",
        user_portfolio="https://anasriaz.com",
        instructions="Apply for the Senior Python Engineer role. Mention AWS Bedrock and Strands experience.",
    )
    assert "Sarah" in job_pitch["body"]
    assert any(w in job_pitch["body"].lower() for w in ["python", "engineer", "role", "fintech"])

    # 2. Competition / Hackathon copy
    comp_pitch = await _generate_pitch_copy(
        target_name="Dr. Alan Turing (Judge)",
        target_email="alan@cambridge.edu",
        user_name="Anas Riaz",
        user_portfolio="https://anasriaz.com",
        instructions="Submit our Payaam project entry for the AWS Hackathon competition.",
    )
    assert "Dr. Alan" in comp_pitch["body"] or "Alan" in comp_pitch["body"]
    assert any(w in comp_pitch["body"].lower() for w in ["hackathon", "competition", "submitting", "submission", "project", "payaam"])


def test_sanitize_email_copy_strips_markdown_headers_and_ai_cliches():
    from src.agent.copywriting import sanitize_email_copy

    raw_ai_output = """# Ready-to-Send Response

Thanks so much for your interest! I appreciate you reaching out.

Our pricing is flexible and tailored to your restaurant's specific volume and feature needs. Rather than sending a generic quote, I'd like to show you exactly how this works for Greenleaf Bistro.

Would you have 5 minutes this week for a quick call? I can walk you through a live demo and share pricing tiers customized for your operation.

Let me know what works best for your schedule.

Cheers,
Youranasriaz"""

    sanitized = sanitize_email_copy(raw_ai_output, user_name="Youranasriaz")

    assert "# Ready-to-Send Response" not in sanitized
    assert "#" not in sanitized
    assert "Thanks so much for your interest" not in sanitized
    assert "I appreciate you reaching out" not in sanitized
    assert "Rather than sending a generic quote" not in sanitized
    assert "Youranasriaz" not in sanitized
    assert "Best,\nAnas" in sanitized or "Anas" in sanitized


def test_clean_user_name_and_greeting_resolution():
    from src.agent.copywriting import clean_user_name, extract_first_name, extract_prospect_greeting_name

    assert clean_user_name("Youranasriaz", "youranasriaz@gmail.com") == "Anas Riaz"
    assert clean_user_name(None, "youranasriaz@gmail.com") == "Anas Riaz"
    assert clean_user_name(None, "anas@anasriaz.com") == "Anas Riaz"
    assert clean_user_name("Jane Designer", "jane@design.io") == "Jane Designer"

    assert extract_first_name("Anas Riaz") == "Anas"
    assert extract_first_name("Dr. Alan Turing") == "Dr. Alan"

    assert extract_prospect_greeting_name("Greenleaf Bistro") == "Greenleaf Bistro team"
    assert extract_prospect_greeting_name("Roast & Bean") == "there" or "Roast" in extract_prospect_greeting_name("Roast & Bean")
    assert extract_prospect_greeting_name("Sarah Jenkins (Head of Eng)") == "Sarah"
    assert extract_prospect_greeting_name(None, "owp360@gmail.com") == "there"


@pytest.mark.asyncio
async def test_company_profile_attachment_ingestion_and_user_footer():
    from src.services.email_service import EmailAttachment
    from src.agent.copywriting import build_user_email_footer

    doc_text = b"Company: Apex Digital\nServices: Web & AI\nPackages: $500 Starter, $1500 Pro\nOffice: 450 Lexington Ave, NY\nFAQ: Support is 24/7."
    att = EmailAttachment(
        filename="company_profile.txt",
        content_type="text/plain",
        data_bytes=doc_text,
    )

    res = await handle_onboarding_or_greeting_tool(
        OnboardingInput(
            user_email="apex_founder@company.com",
            user_name="Apex Founder",
            email_subject="Our Company Profile Attachment",
            email_body="Attached is our company overview and services.",
            attachments=[att],
        )
    )

    assert res.action_type == "PROFILE_SAVED"
    assert res.user_profile is not None
    assert "Company Knowledge Base" in res.response_subject or "Profile" in res.response_subject
    assert "DELETE MY DATA" in res.response_body
    assert "Payaam User Privacy & Email Controls" in res.response_body
    assert res.user_profile.get("company_profile") is not None

    # Test footer with and without custom SMTP
    footer_no_smtp = build_user_email_footer({"deletion_pin": "PYM-1234"})
    assert "agent@anasriaz.com" in footer_no_smtp
    assert "DELETE MY DATA PYM-1234" in footer_no_smtp

    footer_with_smtp = build_user_email_footer({
        "deletion_pin": "PYM-5678",
        "smtp_config": {"username": "ceo@apex.com"}
    })
    assert "ceo@apex.com" in footer_with_smtp
    assert "DELETE MY DATA PYM-5678" in footer_with_smtp


