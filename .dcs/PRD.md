# Product Requirements Document (PRD) — Payaam (پیام)

## 1. Executive Summary
**Payaam** (Urdu / Persian: **پیام** — *"The Message"* or *"The Dispatch"*) is an autonomous background email delegate built for the **AWS Agents for Humans Hackathon** *(Professional Agents Track)*. Operating natively over **Email (Purelymail SMTP/IMAP)**, Payaam handles routine, high-friction email tasks—including personalized freelance client outreach, multi-vendor sourcing, and client negotiation—silently in the background. Enforcing a strict **Two-Knock Policy**, Payaam never bothers the user with auto-responders or routine questions, surfacing to their inbox **only when a real decision is needed or a result is achieved.**

---

## 2. Problem Statement
Freelancers, solo agency operators, creators, and busy professionals lose 10+ hours each week to tedious email chores:
- **Copy-Paste AI Exhaustion:** Users currently act as human copy-paste middleware between ChatGPT, Gmail, and CRM spreadsheets.
- **Outreach & Follow-up Friction:** Pitching potential clients requires customizing copy, tracking replies, remembering multi-touch follow-ups, and handling rejections.
- **SaaS Clutter:** Existing tools require downloading separate apps, configuring complex drip campaign UIs, or paying steep subscription fees.
- **Deliverability & Spam Damage:** Uncoordinated cold email tools bombard the same businesses, destroying sender domain reputation.

---

## 3. Product Vision & Value Proposition
1. **Zero New Apps (Email-Native):** Onboarding, Memory Vault creation, BYO-SMTP connection, mission execution, and account deletion happen 100% via standard email.
2. **Strict Two-Knock Policy:** 
   - **Knock 1 (`ACTION_NEEDED`):** Budget negotiation, scope changes, or terms requiring human approval.
   - **Knock 2 (`RESULT_ACHIEVED`):** Meeting booked, contract accepted, or project milestone confirmed.
   - Everything in between (vacation auto-replies, bounces, portfolio FAQs) is handled silently in the background.
3. **Rough-In, Polished-Out Delegation:** Users reply from their phone with 1-line rough notes (e.g. *"Make it $220 and ask for menu PDF"*), and Payaam polishes and dispatches a professional B2B client email.
4. **Multi-Tenant Collision Prevention Shield:** Global DynamoDB registry (`Payaam_ContactRegistry`) prevents multiple freelancers from spamming the same business within 14 days.
5. **Privacy & Right-to-be-Forgotten:** User SMTP passwords are encrypted symmetrically (AES-128 Fernet) at rest. Users can permanently purge all data on demand via `DELETE MY DATA [PIN]`.

---

## 4. Key User Personas & Use Cases

### Personas
- **The Freelancer / Solo Consultant:** Needs a dedicated autonomous sales delegate to pitch potential clients and nurture deals without spending all day writing cold emails.
- **The Creator / Agency Owner:** Needs to source merchandise, custom packaging, or event venues across multiple suppliers.
- **The Busy Professional:** Wants to delegate annoying administrative email threads (disputes, cancellations, appointment chasing).

### Primary Use Cases
1. **Freelance Client Acquisition:** "Pitch modern mobile menus to these 4 local cafes without websites. Goal: Book a 15-min demo call."
2. **Everyday Procurement & Sourcing:** "Email 3 packaging suppliers for per-unit quotes on 500 custom mailer boxes (10x8x4 in)."
3. **Thread Delegation:** Forwarding an email thread to Payaam to handle follow-up, inquiries, or resolution.

---

## 5. Technical Architecture & Stack
- **Framework:** Strands Agents SDK (`strands-agents`)
- **Reasoning Engine:** Amazon Bedrock (`anthropic.claude-3-5-sonnet-20241022-v2:0`)
- **Fast Intent Triage:** Amazon Bedrock (`anthropic.claude-3-5-haiku-20241022-v1:0`)
- **Persistence Store:** Amazon DynamoDB (`Payaam_Users`, `Payaam_Missions`, `Payaam_ContactRegistry`)
- **Email Protocol:** Purelymail (SMTP on Port 465 SSL, IMAP on Port 993 SSL)
- **Security:** AES-128 Fernet symmetric encryption for user-connected credentials at rest.
- **Cloud Host:** Amazon Linux 2023 EC2 (`t3.micro`) in `us-east-1` with systemd daemons.
