# 🏆 Payaam (پیام) — AWS Hackathon Submission Kit

Use this document to copy-paste directly into your Devpost / Hackathon project submission!

---

## Project Overview

- **Project Title:** Payaam (پیام) — Autonomous Background Email Delegate for Freelancers & Solo Professionals
- **Target Track:** **Professional Agents Track** *(Secondary: Everyday Agents Track)*
- **Tagline:** An autonomous background email delegate built with the Strands Agents SDK and Amazon Bedrock that clears the runway for solo professionals by handling repetitive cold outreach, client nurturing, and deal follow-ups silently over native email.
- **Etymology:** *"Payaam"* (Urdu / Persian: **پیام**) translates to *"The Message"* or *"The Dispatch"* — an agent designed to be your tireless digital ambassador across email networks.

---

## 🎯 The Elevator Pitch (60 Seconds)

Skilled solo professionals—developers, designers, consultants, and contractors—spend 10+ hours every week acting as manual copy-paste middleware between ChatGPT, Gmail, and CRM spreadsheets. They hate writing cold emails, tracking unresponsive leads, and remembering multi-stage follow-ups, taking them away from what they actually do best: building and solving problems.

**Payaam** is a zero-UI, background autonomous agent built on the **Strands Agents SDK**, **Amazon Bedrock (Claude 3.5 Sonnet & Haiku)**, and **Purelymail (SMTP/IMAP)**. Users never open an app. They simply email raw notes to their agent, and Payaam takes over:
1. Crafts individualized, high-converting B2B pitches citing the professional's portfolio from their Memory Vault.
2. Dispatches from the user's dedicated email address or custom BYO-SMTP (with credentials encrypted symmetrically via AES-128 Fernet at rest).
3. Silently filters out auto-responders, bounces, and opt-outs.
4. Autonomously answers routine questions (portfolio samples, turnaround times) from the Memory Vault without bothering the user.
5. Operates under a strict **Two-Knock Policy**: surfaces to the user's inbox **ONLY** when an action is needed (e.g., budget counter-offers) or a result is achieved (e.g., meeting booked).

When a decision is needed, the user replies to the email from their phone with 1 rough line (*"Make it $220 and ask for their menu PDF"*), and Payaam instantly polishes and dispatches the professional agreement to the client.

---

## 🛠️ How We Built It

- **Agent Core & Orchestration:** Built with the **Strands Agents SDK (`strands-agents`)**, utilizing `@tool` decorators for Pydantic-validated actions, dynamic system prompting, and the Bedrock Converse API.
- **Reasoning & Copywriting:** **Amazon Bedrock (`anthropic.claude-3-5-sonnet-20241022-v2:0`)** for crafting persuasive 3-sentence B2B pitches and translating rough user notes into polished client responses.
- **Fast Extraction & Intent Triage:** **Amazon Bedrock (`anthropic.claude-3-5-haiku-20241022-v1:0`)** for lightning-fast sub-second categorization of inbound replies (bounces vs. opt-outs vs. deal signals).
- **Persistence & Multi-Tenancy:** **Amazon DynamoDB**:
  - `Payaam_Users`: User profiles, Memory Vaults, encrypted BYO-SMTP configs, and cryptographic Deletion PINs.
  - `Payaam_Missions`: Ephemeral multi-prospect outreach sessions with 72-hour TTL.
  - `Payaam_ContactRegistry`: Global multi-tenant anti-spam collision prevention ledger.
- **Protocol & Ingestion:** **Purelymail** via Python standard `smtplib` (SSL Port 465) and `imaplib` (SSL Port 993) background polling daemon.
- **Enterprise Security:** AES-128 Fernet symmetric encryption for user-connected SMTP credentials at rest.
- **Cloud-Native Deployment:** Dedicated **Amazon Linux 2023 EC2 (`t3.micro`)** host running in **us-east-1** with systemd daemons:
  - `payaam-worker.service`: 24/7 autonomous email listener.
  - `payaam-sandbox.service`: FastAPI Sandbox & Monitoring Dashboard on port 8000.

---

## 🛡️ Key Innovations & Guardrails

1. **The Anti-Spam Collision Shield:**
   Most cold outreach bots ruin domain deliverability by bombarding the same recipients. Payaam checks a global DynamoDB registry before sending any pitch. If a business was contacted in the last 14 days, the agent flags an advisory warning and offers strategic differentiation.

2. **The Two-Knock Policy (No Babysitting):**
   Unlike chatbots that demand constant attention, Payaam runs silently for 7–10 days. It only surfaces when human judgment is strictly required:
   - **Knock 1 (`ACTION_NEEDED`):** Budget negotiations or custom scope modifications.
   - **Knock 2 (`RESULT_ACHIEVED`):** Confirmed calendar booking or signed agreement.

3. **Zero-UI Email Native Experience & Right-to-be-Forgotten:**
   Onboarding, profile creation, BYO-SMTP setup, task execution, and data deletion all happen directly through email. Users can permanently purge all stored data and sessions on demand by replying: `DELETE MY DATA [PIN]`.

---

## 🧪 Verification & Proof of Execution

- **Live AWS Cloud Host:**
  - Sandbox UI: [http://44.223.28.134:8000](http://44.223.28.134:8000)
  - Health API: [http://44.223.28.134:8000/api/health](http://44.223.28.134:8000/api/health)
- **Pytest Suite:** 17/17 automated unit and integration tests passing (`pytest`).
- **End-to-End Simulation:** Automated 10-scenario simulation script (`python -m scripts.simulate_email_flow`) successfully exercising the entire lifecycle from cold-start greeting to cryptographic data wipe.
- **Live SMTP/IMAP Connectivity:** Verified live authentication with Purelymail SMTP (Port 465) and IMAP (Port 993).
