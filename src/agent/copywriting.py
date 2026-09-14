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
            # If it's a single concatenated word longer than 14 chars, it's a username/handle
            if len(name.split()) == 1 and len(name) > 14:
                return "there"
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
            # If parts resulted in a single very long word > 14 chars
            if len(cleaned_parts) == 1 and len(cleaned_parts[0]) > 14:
                return "there"
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
    # If it contains digits, @, or is a long technical handle > 14 chars
    if any(c.isdigit() for c in tokens[0]) or "@" in tokens[0] or len(tokens[0]) > 14 or tokens[0].lower() == "there":
        return "there"
    return tokens[0]


def extract_active_reply_text(body: str) -> str:
    """Extracts only the sender's active typed response, stripping quoted email history.

    Prevents quoted message footers (like previous deletion PINs or instructions)
    from being misconstrued as active user commands.
    """
    if not body:
        return ""

    # Common email client quote header patterns
    quote_patterns = [
        r"(?im)^\s*On\s+.*,\s+.*wrote:\s*$",
        r"(?im)^\s*On\s+.*\d{4}.*wrote:\s*$",
        r"(?im)^\s*On\s+.*<[^>]+>\s*wrote:\s*$",
        r"(?im)^\s*-{2,}\s*Original Message\s*-{2,}",
        r"(?im)^\s*_{10,}\s*$",
        r"(?im)^\s*From:\s*.*(?:\r?\n\s*Sent:|\r?\n\s*To:|\r?\n\s*Subject:)",
    ]

    text = body
    for pat in quote_patterns:
        m = re.search(pat, text)
        if m:
            text = text[:m.start()]

    # Strip quoted lines starting with '>'
    clean_lines = []
    for line in text.splitlines():
        if line.strip().startswith(">"):
            continue
        clean_lines.append(line)

    return "\n".join(clean_lines).strip()


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
    """Builds a concise, focused control footer for user-facing plain-text emails."""
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
        "\n\n────────────────────────────────────────────────────────────",
        "⚙️ Payaam User Privacy & Email Controls:",
    ]
    if custom_addr:
        lines.append(
            f"• Custom Email: Connected ({custom_addr}) — reply 'DISCONNECT_SMTP' to reset."
        )
    else:
        lines.append(
            "• Custom Email: Sending via default relay (agent@anasriaz.com). Reply with 'CONNECT_SMTP' to connect your own email."
        )
    lines.append(
        f"• Delete Profile & Data: Reply 'DELETE MY DATA {pin}' at any time to permanently purge all data."
    )
    lines.append("────────────────────────────────────────────────────────────")
    return "\n".join(lines)


def render_html_email(body_text: str, user_profile: Optional[Dict[str, Any]] = None) -> str:
    """Renders an executive, responsive HTML email with a sleek grey footer.

    Matches modern SaaS and Google account notification styling (Screenshot reference).
    Ensures the privacy and SMTP control box is distinct, elegant, and never mixes
    with the email body.
    """
    import html

    # Separate user control footer from main email body
    footer_plain = ""
    main_text = body_text

    divider_match = re.search(r"\n*─{10,}\s*\n([\s\S]*?)─{10,}\s*$", body_text)
    if divider_match:
        footer_plain = divider_match.group(1).strip()
        main_text = body_text[:divider_match.start()].strip()
    elif "⚙️ Payaam User Privacy & Email Controls" in body_text:
        idx = body_text.find("⚙️ Payaam User Privacy & Email Controls")
        footer_plain = body_text[idx:].strip()
        main_text = body_text[:idx].strip()

    # Format body into clean HTML blocks
    paragraphs = re.split(r"\n{2,}", main_text)
    formatted_paras = []
    for p in paragraphs:
        lines = p.strip().split("\n")
        # Check if list of bullet points or numbered items
        if all(line.strip().startswith(("•", "-", "*", "1.", "2.", "3.", "4.")) for line in lines if line.strip()):
            items_html = []
            for line in lines:
                if not line.strip():
                    continue
                clean_item = re.sub(r"^[\s•\-*]+|\s*^\d+\.\s*", "", line.strip())
                if ":" in clean_item:
                    k, v = clean_item.split(":", 1)
                    item_rendered = f"<strong>{html.escape(k)}:</strong> {html.escape(v)}"
                else:
                    item_rendered = html.escape(clean_item)
                item_rendered = re.sub(r"(https?://[^\s<]+)", r'<a href="\1" style="color: #1a73e8; text-decoration: none;">\1</a>', item_rendered)
                items_html.append(f'<li style="margin-bottom: 6px; line-height: 1.5;">{item_rendered}</li>')
            formatted_paras.append(f'<ul style="margin: 8px 0 16px 20px; padding: 0; color: #202124; font-size: 14px;">{"".join(items_html)}</ul>')
        else:
            escaped_p = html.escape("\n".join(lines))
            escaped_p = escaped_p.replace("\n", "<br>")
            escaped_p = re.sub(r"(https?://[^\s<]+)", r'<a href="\1" style="color: #1a73e8; text-decoration: underline;">\1</a>', escaped_p)
            formatted_paras.append(f'<p style="margin: 0 0 14px 0; line-height: 1.6; color: #202124; font-size: 14px;">{escaped_p}</p>')

    main_html = "\n".join(formatted_paras)

    footer_html = ""
    if footer_plain:
        profile = user_profile or {}
        pin = profile.get("deletion_pin")
        if not pin:
            pin_match = re.search(r"DELETE MY DATA\s+([A-Za-z0-9\-]+)", footer_plain)
            pin = pin_match.group(1) if pin_match else "PYM-XXXX"

        is_connected = "Connected (" in footer_plain
        custom_email_match = re.search(r"Connected \(([^)]+)\)", footer_plain)
        custom_addr = custom_email_match.group(1) if custom_email_match else None

        if is_connected and custom_addr:
            smtp_line = f'• <strong>Custom Email:</strong> Connected (<code>{html.escape(custom_addr)}</code>) &mdash; reply <code style="background-color: #e8eaed; padding: 2px 6px; border-radius: 4px; font-size: 11px;">DISCONNECT_SMTP</code> to reset.'
        else:
            smtp_line = '• <strong>Custom Email:</strong> Sending via default relay (<code>agent@anasriaz.com</code>). Reply with <code style="background-color: #e8eaed; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 600;">CONNECT_SMTP</code> to connect your own email.'

        deletion_line = f'• <strong>Delete Profile &amp; Data:</strong> Reply <code style="background-color: #e8eaed; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 600;">DELETE MY DATA {html.escape(pin)}</code> at any time to permanently purge all data.'

        footer_html = f"""
  <div style="margin-top: 36px; padding: 16px 20px; background-color: #f8f9fa; border: 1px solid #e8eaed; border-radius: 8px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 12px; line-height: 1.6; color: #5f6368;">
    <div style="font-weight: 600; color: #3c4043; margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
      <span>⚙️ Payaam Privacy &amp; Email Controls</span>
    </div>
    <div style="margin-bottom: 6px; color: #5f6368;">
      {smtp_line}
    </div>
    <div style="color: #5f6368;">
      {deletion_line}
    </div>
  </div>
"""

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 24px 16px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #ffffff; color: #202124;">
  <div style="max-width: 620px; margin: 0 auto;">
    {main_html}
    {footer_html}
  </div>
</body>
</html>"""


