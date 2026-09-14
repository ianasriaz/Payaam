"""Purelymail & Custom SMTP/IMAP Email Service for Payaam.

Handles outbound RFC 5322 MIME email dispatch over SMTP (SSL/TLS) and
inbound email retrieval, MIME parsing, and thread correlation over IMAP (SSL).
Supports per-user BYO-SMTP credentials and platform Purelymail defaults.
"""

import email
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid, parseaddr
import imaplib
import logging
import re
import smtplib
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from src.config import settings

logger = logging.getLogger("payaam.services.email")

SYSTEM_AND_BOUNCE_PATTERNS = [
    r"^noreply@",
    r"^no-reply@",
    r"^mailer-daemon@",
    r"^postmaster@",
    r"^bounce@",
    r"^bounces@",
    r"^notification.*@",
    r"@purelymail\.com$",
    r"@payaam\.ai$",
]

BOUNCE_SUBJECT_PATTERNS = [
    r"delivery\s+(?:status\s+notification|failure|issue)",
    r"undeliver(?:ed|able)\s+mail",
    r"mail\s+delivery\s+system",
    r"failure\s+notice",
    r"couldn't\s+reach",
    r"we\s+tried\s+reaching\s+you",
    r"mailbox\s+might\s+be\s+having\s+connection\s+issues",
]


def is_system_bounce_or_automated(msg: email.message.Message, from_addr: str, subject: str) -> bool:
    """Detects whether an email is a bounce, DSN, NDR, or automated system notification."""
    clean_from = from_addr.strip().lower()
    clean_subj = subject.strip().lower()

    # 1. Sender patterns
    if any(re.search(pat, clean_from) for pat in SYSTEM_AND_BOUNCE_PATTERNS):
        return True

    # 2. Subject patterns
    if any(re.search(pat, clean_subj) for pat in BOUNCE_SUBJECT_PATTERNS):
        return True

    # 3. System headers
    auto_submitted = (msg.get("Auto-Submitted") or "").strip().lower()
    if auto_submitted and auto_submitted != "no":
        return True

    content_type = (msg.get_content_type() or "").strip().lower()
    if content_type == "multipart/report":
        return True

    if msg.get("X-Failed-Recipients") or msg.get("X-Pm-Webmail-Alert"):
        return True

    return False


class EmailAttachment(BaseModel):
    """Normalized email attachment payload."""
    filename: str
    content_type: str
    data_bytes: bytes


class InboundEmail(BaseModel):
    """Normalized inbound email payload extracted from IMAP."""
    message_id: str
    subject: str
    from_address: str
    from_name: str
    to_address: str
    date: str
    body_text: str
    in_reply_to: Optional[str] = None
    references: Optional[str] = None
    thread_ref: Optional[str] = None  # e.g. PYM-8491 extracted from subject/body
    attachments: List[EmailAttachment] = Field(default_factory=list)


class EmailService:
    """Manages SMTP dispatch and IMAP polling with per-user custom credential support."""

    def __init__(self) -> None:
        self.default_smtp_host = settings.SMTP_HOST or settings.PURELYMAIL_SMTP_HOST
        self.default_smtp_port = settings.SMTP_PORT or settings.PURELYMAIL_SMTP_PORT
        self.default_smtp_user = settings.SMTP_USER or settings.PURELYMAIL_USER
        self.default_smtp_password = settings.SMTP_PASSWORD or settings.PURELYMAIL_PASSWORD

        self.default_imap_host = settings.PURELYMAIL_IMAP_HOST
        self.default_imap_port = settings.PURELYMAIL_IMAP_PORT
        self.default_user = settings.PURELYMAIL_USER
        self.default_password = settings.PURELYMAIL_PASSWORD

        self.default_from = settings.PURELYMAIL_DEFAULT_FROM or self.default_smtp_user
        self.default_reply_to = settings.REPLY_TO_ADDRESS or "agent@anasriaz.com"
        self._cached_imap: Optional[imaplib.IMAP4_SSL] = None
        self._cached_imap_key: Optional[str] = None

    # -------------------------------------------------------------------------
    # Outbound SMTP Dispatch
    # -------------------------------------------------------------------------
    def send_email(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = "Payaam",
        custom_smtp: Optional[Dict[str, Any]] = None,
        in_reply_to: Optional[str] = None,
        thread_ref: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Dispatches an email via SMTP using custom credentials or configured defaults.

        Args:
            to_email: Recipient email address.
            subject: Email subject line.
            body_text: Plain-text fallback body.
            body_html: Optional rich HTML body.
            from_email: Sender address.
            from_name: Display name.
            custom_smtp: Optional dictionary with host, port, username, password.
            in_reply_to: Optional Message-ID being replied to.
            thread_ref: Optional tracking reference (e.g. WD-1024).
            dry_run: If True, simulates send without network connection.
        """
        to_clean = to_email.strip().lower()
        # Guard: NEVER dispatch emails to bounce, system, or blacklisted addresses
        if any(re.search(pat, to_clean) for pat in SYSTEM_AND_BOUNCE_PATTERNS) or to_clean in [self.default_user, "agent@anasriaz.com"]:
            logger.warning(f"🚫 Blocked dispatch attempt to system/blacklisted address: {to_email}")
            return {
                "success": False,
                "error": f"Blocked sending to blacklisted address: {to_email}",
                "to": to_email,
            }

        sender_addr = from_email or (custom_smtp.get("username") if custom_smtp else None) or self.default_from
        sender_display = f'"{from_name}" <{sender_addr}>'

        # Ensure clean, focused subject line without forced robotic bracket prefixes
        final_subject = subject.strip()

        # Construct MIME message
        msg = MIMEMultipart("alternative")
        msg["From"] = sender_display
        msg["To"] = to_email
        msg["Reply-To"] = self.default_reply_to
        msg["Subject"] = final_subject
        msg["Date"] = formatdate(localtime=True)

        if thread_ref:
            msg["X-Payaam-Thread-Ref"] = thread_ref

        msg_id = make_msgid(domain="payaam.ai")
        msg["Message-ID"] = msg_id

        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to

        # Attach text and sleek HTML parts
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        if not body_html and body_text:
            try:
                from src.agent.copywriting import render_html_email
                body_html = render_html_email(body_text)
            except Exception as exc:
                logger.warning(f"Could not render HTML body: {exc}")

        if body_html:
            msg.attach(MIMEText(body_html, "html", "utf-8"))

        if dry_run or not (self.default_smtp_password or (custom_smtp and custom_smtp.get("password"))):
            logger.info(f"[DRY-RUN / MOCK] Dispatched email to {to_email} | Subj: {final_subject} | ID: {msg_id}")
            return {
                "success": True,
                "message_id": msg_id,
                "to": to_email,
                "subject": final_subject,
                "mocked": True,
            }

        # Resolve SMTP configuration
        host = (custom_smtp.get("host") if custom_smtp else None) or self.default_smtp_host
        port = (custom_smtp.get("port") if custom_smtp else None) or self.default_smtp_port
        user = (custom_smtp.get("username") if custom_smtp else None) or self.default_smtp_user
        password = (custom_smtp.get("password") if custom_smtp else None) or self.default_smtp_password

        try:
            logger.info(f"Connecting to SMTP {host}:{port} for dispatch to {to_email}")
            if port == 465:
                with smtplib.SMTP_SSL(host, port, timeout=15) as server:
                    if user and password:
                        server.login(user, password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(host, port, timeout=15) as server:
                    server.starttls()
                    if user and password:
                        server.login(user, password)
                    server.send_message(msg)

            logger.info(f"Email successfully sent to {to_email} with Message-ID: {msg_id}")
            return {"success": True, "message_id": msg_id, "to": to_email, "subject": final_subject}
        except smtplib.SMTPResponseException as exc:
            err_msg = exc.smtp_error.decode("utf-8", errors="replace") if isinstance(exc.smtp_error, bytes) else str(exc.smtp_error)
            logger.error(f"SMTP error {exc.smtp_code} dispatching to {to_email} via {host}:{port}: {err_msg}")
            return {
                "success": False,
                "error": f"SMTP {exc.smtp_code}: {err_msg}",
                "message_id": msg_id,
                "to": to_email,
                "subject": final_subject,
            }
        except Exception as exc:
            logger.error(f"SMTP network error dispatching to {to_email} via {host}:{port} ({exc})")
            return {
                "success": False,
                "error": str(exc),
                "message_id": msg_id,
                "to": to_email,
                "subject": final_subject,
            }

    # -------------------------------------------------------------------------
    # Inbound IMAP Polling & MIME Parsing
    # -------------------------------------------------------------------------
    def _get_imap_connection(self, host: str, port: int, user: str, password: str) -> imaplib.IMAP4_SSL:
        """Retrieves an active IMAP connection, reusing the cached TLS session if live."""
        key = f"{host}:{port}:{user}"
        if self._cached_imap is not None and self._cached_imap_key == key:
            try:
                # Fast noop check (takes ~20-40ms vs ~800ms for fresh TLS handshake + login)
                status, _ = self._cached_imap.noop()
                if status == "OK":
                    return self._cached_imap
            except Exception:
                self.close_cached_connections()

        # Connect & login
        mail = imaplib.IMAP4_SSL(host, port, timeout=10)
        mail.login(user, password)
        self._cached_imap = mail
        self._cached_imap_key = key
        return mail

    def close_cached_connections(self) -> None:
        """Cleanly terminates and purges any active IMAP TLS sessions."""
        if self._cached_imap is not None:
            try:
                self._cached_imap.logout()
            except Exception:
                pass
            self._cached_imap = None
            self._cached_imap_key = None

    def fetch_unread_emails(
        self,
        custom_imap: Optional[Dict[str, Any]] = None,
        mark_as_read: bool = True,
        dry_run: bool = False,
    ) -> List[InboundEmail]:
        """Polls IMAP inbox for unread messages and parses into InboundEmail models."""
        if dry_run or not (self.default_password or (custom_imap and custom_imap.get("password"))):
            logger.info("[DRY-RUN] IMAP check skipped (no active network credentials).")
            return []

        host = (custom_imap.get("host") if custom_imap else None) or self.default_imap_host
        port = (custom_imap.get("port") if custom_imap else None) or self.default_imap_port
        user = (custom_imap.get("username") if custom_imap else None) or self.default_user
        password = (custom_imap.get("password") if custom_imap else None) or self.default_password

        emails: List[InboundEmail] = []

        try:
            mail = self._get_imap_connection(host, port, user, password)
            mail.select("INBOX")

            status, messages = mail.search(None, "UNSEEN")
            if status != "OK":
                return []

            msg_ids = messages[0].split()
            if msg_ids:
                logger.info(f"Found {len(msg_ids)} unread email(s) in IMAP inbox.")

            for msg_id in msg_ids:
                res, data = mail.fetch(msg_id, "(RFC822)")
                if res != "OK" or not data or not data[0]:
                    continue

                if mark_as_read:
                    mail.store(msg_id, "+FLAGS", "\\Seen")

                raw_email = data[0][1]
                msg = email.message_from_bytes(raw_email)
                from_header = msg.get("From", "")
                _, from_address = parseaddr(from_header)
                subj = msg.get("Subject", "")

                # Detect and silently drop bounce loops, DSNs, and automated system alerts
                if is_system_bounce_or_automated(msg, from_address, subj):
                    logger.info(f"🛡️ Filtered out automated bounce/system message from {from_address} (Subj: {subj[:40]})")
                    continue

                parsed = self.parse_rfc822(raw_email)
                if parsed:
                    # Guard: Senders matching the agent itself must never be processed as incoming users
                    if parsed.from_address in [self.default_user, "agent@anasriaz.com", "payaam@anasriaz.com"]:
                        logger.info(f"Dropping self-sent loopback message from {parsed.from_address}")
                        continue
                    emails.append(parsed)

        except Exception as exc:
            logger.error(f"Error fetching unread emails from IMAP: {exc}")
            self.close_cached_connections()

        return emails

    # -------------------------------------------------------------------------
    # MIME Parser Helper
    # -------------------------------------------------------------------------
    def parse_rfc822(self, raw_bytes: bytes) -> Optional[InboundEmail]:
        """Parses raw RFC822 email bytes into a clean InboundEmail object."""
        try:
            msg = email.message_from_bytes(raw_bytes)

            # Decode Subject
            subject = ""
            raw_subj = msg.get("Subject", "")
            for part, encoding in decode_header(raw_subj):
                if isinstance(part, bytes):
                    subject += part.decode(encoding or "utf-8", errors="replace")
                else:
                    subject += str(part)

            # Sender address & name
            from_header = msg.get("From", "")
            from_name, from_address = parseaddr(from_header)
            to_header = msg.get("To", "")
            _, to_address = parseaddr(to_header)

            message_id = msg.get("Message-ID", "")
            in_reply_to = msg.get("In-Reply-To")
            references = msg.get("References")
            date_str = msg.get("Date", "")

            # Extract Body Text and Attachments
            body_text = ""
            attachments: List[EmailAttachment] = []
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition", ""))
                    filename = part.get_filename()
                    if "attachment" in content_disposition or filename:
                        payload = part.get_payload(decode=True)
                        if payload:
                            clean_fn = filename or f"attachment_{len(attachments) + 1}"
                            attachments.append(EmailAttachment(
                                filename=clean_fn,
                                content_type=content_type,
                                data_bytes=payload,
                            ))
                    elif content_type == "text/plain" and not body_text:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or "utf-8"
                            body_text += payload.decode(charset, errors="replace")
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    charset = msg.get_content_charset() or "utf-8"
                    body_text = payload.decode(charset, errors="replace")

            body_text = body_text.strip()

            # Extract Thread / Job Ref from custom header or Subject
            thread_ref = msg.get("X-Payaam-Thread-Ref") or None
            if not thread_ref:
                match = re.search(r"\[((?:PYM|WD)-[A-Za-z0-9\-]+)\]", subject) or re.search(r"\b((?:PYM|WD)-[A-Za-z0-9\-]+)\b", subject)
                if match:
                    thread_ref = match.group(1)

            return InboundEmail(
                message_id=message_id,
                subject=subject.strip(),
                from_address=from_address.strip().lower(),
                from_name=from_name.strip() or from_address,
                to_address=to_address.strip().lower(),
                date=date_str,
                body_text=body_text,
                in_reply_to=in_reply_to,
                references=references,
                thread_ref=thread_ref,
                attachments=attachments,
            )
        except Exception as exc:
            logger.error(f"Error parsing raw email bytes: {exc}")
            return None


email_service = EmailService()
