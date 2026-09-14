"""Natural copy refinement, name resolution, and sanitization utilities for Payaam.

Eliminates AI clichés, strips leaked internal headings (e.g. '# Ready-to-Send Response'),
resolves natural display names, and formats warm, human B2B emails.
"""

import re
from typing import Any, Dict, List, Optional


def clean_user_name(raw_name: Optional[str] = None, email: Optional[str] = None) -> str:
    """Derives a clean, natural human display name from raw metadata or email.

    Handles:
    - 'Youranasriaz' / 'youranasriaz@gmail.com' -> 'Anas Riaz'
    - 'anasriaz' -> 'Anas Riaz'
    - 'john.doe@startup.com' -> 'John Doe'
    - 'Jane Designer' -> 'Jane Designer'
    - Default fallback: 'Anas Riaz'
    """
    if raw_name and raw_name.strip():
        name = raw_name.strip()
        # Normalization for common email handles
        if re.search(r"your\s*anas\s*riaz", name, re.IGNORECASE) or re.search(r"\banas\s*riaz\b", name, re.IGNORECASE):
            return "Anas Riaz"
        if re.search(r"^your\s*([a-zA-Z]+)$", name, re.IGNORECASE):
            sub = re.sub(r"^your", "", name, flags=re.IGNORECASE)
            if "anas" in sub.lower():
                return "Anas Riaz"
            return sub.capitalize()
        # If it doesn't look like an email or username with punctuation
        if "@" not in name and "_" not in name and len(name.split()) <= 4:
            # Check if camelcase like AnasRiaz
            if re.match(r"^[A-Z][a-z]+[A-Z][a-z]+$", name):
                return re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
            return name

    if email:
        local = email.split("@")[0]
        if "anas" in local.lower():
            return "Anas Riaz"
        parts = re.split(r"[._\-+]+", local)
        cleaned_parts = [p.capitalize() for p in parts if p and not p.isdigit() and p.lower() not in ["your", "my", "the", "info", "contact", "agent"]]
        if cleaned_parts:
            return " ".join(cleaned_parts)

    return "Anas Riaz"


def extract_first_name(full_name: str) -> str:
    """Extracts a warm first name or honorific for greetings and signoffs."""
    if not full_name or not full_name.strip():
        return "there"
    tokens = full_name.strip().split()
    if not tokens:
        return "there"
    honorifics = {"dr.", "mr.", "mrs.", "ms.", "prof."}
    first_token = tokens[0].lower().rstrip(".") + "."
    if first_token in honorifics and len(tokens) > 1:
        return f"{tokens[0]} {tokens[1]}"
    # If the token is 'Youranasriaz', resolve to Anas
    if "anas" in tokens[0].lower():
        return "Anas"
    # If it contains digits (e.g. onlineworkpurpose009, owp360) or looks like a technical handle
    if any(c.isdigit() for c in tokens[0]) or "@" in tokens[0] or len(tokens[0]) > 14:
        return "there"
    return tokens[0]


def resolve_lead_display_name(
    lead_name: Optional[str] = None,
    lead_email: Optional[str] = None,
    mission: Optional[Dict[str, Any]] = None,
) -> str:
    """Resolves a polished, human-friendly display name for a prospect or business.

    Examples:
    - 'Greenleaf Bistro' -> 'Greenleaf Bistro'
    - 'Sarah Jenkins (Head of Eng)' -> 'Sarah Jenkins'
    - 'owp360@gmail.com' (matched with mission lead) -> 'Greenleaf Bistro'
    - 'sarah.jenkins@gmail.com' -> 'Sarah Jenkins'
    - 'onlineworkpurpose009@gmail.com' -> 'Client'
    """
    # 1. Direct lead_name if it is not generic
    if lead_name and lead_name.strip():
        clean = re.sub(r"\(.*?\)", "", lead_name).strip(" -:\t\n()[]")
        if clean and clean.lower() not in ["team", "lead", "info", "contact", "support", "there"] and "@" not in clean:
            return clean

    # 2. Lookup in mission leads if mission is provided
    if mission and lead_email:
        norm_email = lead_email.strip().lower()
        for l in mission.get("leads", []):
            if l.get("email", "").strip().lower() == norm_email:
                b_name = l.get("business_name")
                if b_name and b_name.strip():
                    clean_b = re.sub(r"\(.*?\)", "", b_name).strip(" -:\t\n()[]")
                    if clean_b and clean_b.lower() not in ["team", "lead", "info", "contact", "support"] and "@" not in clean_b:
                        return clean_b

    # 3. Check custom company domain from email address
    if lead_email and "@" in lead_email:
        local, domain = lead_email.strip().lower().split("@", 1)
        generic_domains = {
            "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
            "icloud.com", "aol.com", "mail.com", "proton.me", "protonmail.com"
        }
        if domain not in generic_domains:
            domain_name = domain.split(".")[0]
            if len(domain_name) >= 3:
                return domain_name.capitalize()

        # Clean local part if it contains real words without digits
        parts = re.split(r"[._\-+]+", local)
        word_parts = [p.capitalize() for p in parts if p.isalpha() and len(p) >= 2]
        if word_parts and not any(c.isdigit() for c in local) and len(local) < 20:
            return " ".join(word_parts)

    return "Client"


def extract_prospect_greeting_name(lead_name: Optional[str], email: Optional[str] = None) -> str:
    """Derives a natural, respectful greeting addressee for prospect emails.

    Examples:
    - 'Greenleaf Bistro' -> 'Greenleaf Bistro team'
    - 'Sarah Jenkins (Head of Eng)' -> 'Sarah'
    - 'Dr. Alan Turing' -> 'Dr. Alan'
    - 'owp360@gmail.com' (no name) -> 'there' (NEVER 'Owp360')
    """
    if not lead_name or not lead_name.strip():
        return "there"

    clean_lead = re.sub(r"\(.*?\)", "", lead_name).strip(" -:\t\n()[]")
    if not clean_lead or clean_lead.lower() in ["team", "lead", "info", "contact", "support"]:
        return "there"

    # If it's clearly a company/restaurant/organization
    org_keywords = ["bistro", "cafe", "coffee", "restaurant", "grill", "bakery", "kitchen", "pizzeria", "haus", "labs", "inc", "llc", "corp", "solutions", "technologies", "studios", "co."]
    if any(k in clean_lead.lower() for k in org_keywords):
        return f"{clean_lead} team"

    tokens = clean_lead.split()
    if not tokens:
        return "there"

    honorifics = {"dr.", "mr.", "mrs.", "ms.", "prof."}
    first_token = tokens[0].lower().rstrip(".") + "."
    if first_token in honorifics and len(tokens) > 1:
        return f"{tokens[0]} {tokens[1]}"

    # If first token looks like an email or username with digits, fallback to 'there'
    if any(c.isdigit() for c in tokens[0]) or "@" in tokens[0]:
        return "there"

    return tokens[0]


def sanitize_subject_line(subject: str) -> str:
    """Removes leaked labels, markdown bolding, or quotes from email subjects."""
    if not subject:
        return ""
    cleaned = subject.strip()
    cleaned = re.sub(r"(?im)^\s*(?:Subject|Email Subject|Re):\s*", "", cleaned)
    cleaned = re.sub(r"^\*\*|\*\*$", "", cleaned)
    cleaned = cleaned.strip(" '\"`#\t\n")
    return cleaned


def sanitize_email_copy(text: str, user_name: Optional[str] = None) -> str:
    """Cleans generated email text to guarantee zero AI artifacts or leaked prompt headers.

    Actions:
    1. Strips any markdown headings ('# Ready-to-Send Response', '## Suggested Draft', etc.)
    2. Strips meta prefixes ('Here is the email:', 'Subject: ...')
    3. Strips enclosing quotation marks or code blocks
    4. Strips robotic AI opening filler ('Thanks so much for reaching out! I appreciate...')
    5. Strips defensive price deflection ('Rather than sending a generic quote...')
    6. Ensures clean, human signoff with user's clean name
    """
    if not text:
        return ""

    cleaned = text.strip()

    # 1. Strip markdown code fences if wrapped in ```...```
    code_fence_match = re.match(r"^```(?:markdown|text|email)?\s*([\s\S]*?)\s*```$", cleaned, re.IGNORECASE)
    if code_fence_match:
        cleaned = code_fence_match.group(1).strip()

    # 2. Strip enclosing quotes ("..." or '...')
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
        cleaned = cleaned[1:-1].strip()

    # 3. Strip all markdown headings: lines starting with #, ##, ###, ####
    cleaned = re.sub(r"(?im)^\s*#+\s*.*(?:\r?\n|$)", "", cleaned)

    # 4. Strip specific leaked AI meta-headers that might appear without '#'
    meta_patterns = [
        r"(?im)^\s*(?:Ready-to-Send(?:\s+Response)?|Suggested Reply(?:\s+Draft)?|Polished Response|Proposed Response|Client Response|Draft Response|Email Body):\s*(?:\r?\n|$)",
        r"(?im)^\s*Here(?:'s| is) (?:the|a) (?:polished|suggested|ready-to-send)?\s*(?:email|response|draft|reply):?\s*(?:\r?\n|$)",
        r"(?im)^\s*(?:Subject|Email Subject):\s*.*(?:\r?\n|$)",
    ]
    for pat in meta_patterns:
        cleaned = re.sub(pat, "", cleaned)

    # 5. Strip robotic sycophantic AI pleasantry openings
    ai_cliche_openings = [
        r"(?im)^\s*Thanks so much for your interest!\s*I appreciate you reaching out\.?\s*",
        r"(?im)^\s*Thanks so much for reaching out!\s*I appreciate you getting in touch\.?\s*",
        r"(?im)^\s*Thank you for reaching out!\s*I appreciate your interest\.?\s*",
        r"(?im)^\s*I hope this email finds you well\.?\s*",
        r"(?im)^\s*I hope you're doing well\.?\s*",
        r"(?im)^\s*Thank you for getting back to me\.?\s*",
        r"(?im)^\s*Thanks for following up with me\.?\s*",
    ]
    for pat in ai_cliche_openings:
        cleaned = re.sub(pat, "", cleaned)

    # 6. Strip defensive pricing deflections
    cleaned = re.sub(
        r"(?i)Rather than sending a generic quote,\s*",
        "",
        cleaned,
    )
    cleaned = re.sub(
        r"(?i)customized for your operation\.?\s*",
        "for your business. ",
        cleaned,
    )

    # 7. Clean signoff: eliminate 'Youranasriaz', 'Your name', etc.
    clean_name = clean_user_name(user_name)
    first_name = extract_first_name(clean_name)

    bad_signatures = [
        r"(?im)(?:Cheers|Best|Best regards|Warmly|Regards|Thanks),\s*\n+\s*Youranasriaz\b",
        r"(?im)(?:Cheers|Best|Best regards|Warmly|Regards|Thanks),\s*\n+\s*\[?Your Name\]?\b",
        r"(?im)(?:Cheers|Best|Best regards|Warmly|Regards|Thanks),\s*\n+\s*Yourname\b",
    ]
    for bad_sig in bad_signatures:
        cleaned = re.sub(bad_sig, f"Best,\n{first_name}", cleaned)

    # 8. Collapse 3+ newlines to max 2
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    return cleaned.strip()


def build_user_email_footer(user_profile: Optional[Dict[str, Any]] = None) -> str:
    """Builds a customized, reassuring control footer for user-facing emails."""
    profile = user_profile or {}
    pin = profile.get("deletion_pin")
    if not pin and profile.get("email"):
        try:
            from src.services.dynamodb import dynamodb_service
            db_user = dynamodb_service.get_user(profile["email"])
            if db_user:
                pin = db_user.get("deletion_pin")
        except Exception:
            pass
    pin = pin or "PYM-XXXX"

    smtp_cfg = profile.get("smtp_config")
    custom_addr = smtp_cfg.get("username") if smtp_cfg else None

    lines = [
        "\n\n─────────────────────────────────────────────",
        "⚙️ Payaam User Privacy & Email Controls:",
    ]
    if custom_addr:
        lines.append(
            f"• Custom Email / BYO-SMTP: Connected! Outreach is sent directly from your personal email ({custom_addr}).\n"
            f"  You can update your SMTP credentials or disconnect at any time."
        )
    else:
        lines.append(
            "• Custom Email / BYO-SMTP: Currently sending via default agent email (agent@anasriaz.com).\n"
            "  You can connect your own email at any time by replying:\n"
            "    CONNECT_SMTP\n"
            "    Host: mail.purelymail.com (or smtp.gmail.com)\n"
            "    Port: 465 (or 587)\n"
            "    Username: your_email@domain.com\n"
            "    Password: your_app_password"
        )
    lines.append(
        f"• Delete Your Data (Right-to-be-Forgotten): Reply at any time to permanently purge your data:\n"
        f"    DELETE MY DATA {pin}"
    )
    lines.append("─────────────────────────────────────────────")
    return "\n".join(lines)

