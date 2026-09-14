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

Skilled solo professionals and agencies spend 10+ hours every week acting as manual copy-paste middleware between ChatGPT, Gmail, and CRM spreadsheets. They hate writing cold emails, tracking unresponsive leads, and answering repetitive questions about services, pricing, and office details—taking them away from what they actually do best: delivering client work.

**Payaam** is a 100% **Zero-UI**, background autonomous agent built on the **Strands Agents SDK**, **Amazon Bedrock (Claude 3.5 Sonnet & Haiku)**, and **Purelymail (SMTP/IMAP)**. Users never open an app or web dashboard. They simply send an email to their agent (`agent@anasriaz.com`), and Payaam takes over:
1. **Multimodal Document Understanding**: Ingests attached company profile PDFs, brochures, rate cards, and FAQs directly into a private DynamoDB Memory Vault using Amazon Bedrock native document processing.
2. **Individualized B2B Pitches**: Crafts bespoke, value-first outreach emails citing your verified services and portfolio.
3. **Dedicated Sender or BYO-SMTP**: Dispatches from default agent relay (`agent@anasriaz.com`) or the user's custom connected email (with credentials encrypted via AES-128 Fernet at rest).
4. **Anti-Spam Collision Shield**: Checks a global DynamoDB registry before sending any pitch to prevent multi-user spam fatigue on the same recipient within 14 days.
5. **Two-Knock Policy**: Silently filters out auto-responders, bounces, and opt-outs. Autonomously answers routine inquiries (packages, pricing, office address, FAQs) directly from your Company Knowledge Base without bothering you.
6. **Action Cards & 1-Line Refinements**: Surfaces to the user's inbox **ONLY** when a human decision is needed (e.g., budget counter-offers) or a meeting is booked. Users reply from their phone with 1 rough line (*"Make it $220 and ask for their menu PDF"*), and Payaam instantly polishes and dispatches the client response.
7. **Customized Privacy & Email Control Footer**: Every email sent to the user clearly displays their email relay status (how to connect personal SMTP anytime) and their unique Right-to-be-Forgotten PIN (`DELETE MY DATA PYM-XXXX`).

---

## 🛠️ How We Built It

- **Agent Core & Orchestration:** Built with the **Strands Agents SDK (`strands-agents`)**, utilizing `@tool` decorators for Pydantic-validated actions, dynamic system prompting, and the Bedrock Converse API.
- **Multimodal Document Ingestion & Reasoning:** **Amazon Bedrock (`anthropic.claude-3-5-sonnet-20241022-v2:0`)** with native `document` blocks for extracting structured company profiles, packages, FAQs, and office details from attached PDFs and documents.
- **Fast Intent Classification & Triage:** **Amazon Bedrock (`anthropic.claude-3-5-haiku-20241022-v1:0`)** for lightning-fast sub-second categorization of inbound replies (bounces vs. opt-outs vs. company knowledge resolution vs. deal signals).
- **Persistence & Multi-Tenancy:** **Amazon DynamoDB**:
  - `Payaam_Users`: User profiles, Memory Vaults, Company Profiles, encrypted BYO-SMTP configs, and cryptographic Deletion PINs.
  - `Payaam_Missions`: Ephemeral multi-prospect outreach sessions with 72-hour TTL.
  - `Payaam_ContactRegistry`: Global multi-tenant anti-spam collision prevention ledger.
- **Protocol & Ingestion:** **Purelymail** via Python standard `smtplib` (SSL Port 465) and `imaplib` (SSL Port 993) background polling daemon.
- **Enterprise Security:** AES-128 Fernet symmetric encryption for user-connected SMTP credentials at rest.
- **Cloud-Native Deployment:** Dedicated **Amazon Linux 2023 EC2 (`t3.micro`)** host running in **us-east-1** with systemd daemons:
  - `payaam-worker.service`: 24/7 autonomous email listener.
  - `payaam-sandbox.service`: FastAPI Health & Monitoring API on port 8000.

---

## 🛡️ Key Innovations & Guardrails

1. **Pure Zero-UI Philosophy:**
   No web dashboard to log into, no extensions to install. The entire user lifecycle—onboarding, PDF knowledge extraction, outreach dispatch, Action Card refinement, and cryptographic data deletion—happens natively through standard email.

2. **The Anti-Spam Collision Shield:**
   Most cold outreach bots ruin domain deliverability by bombarding the same recipients. Payaam checks a global DynamoDB registry before sending any pitch. If a business was contacted in the last 14 days, the agent flags an advisory warning and offers strategic differentiation.

3. **The Two-Knock Policy (No Babysitting):**
   Unlike chatbots that demand constant attention, Payaam runs silently in the background. It answers routine questions autonomously and only surfaces when human judgment is strictly required:
   - **Knock 1 (`ACTION_NEEDED`):** Budget negotiations or custom scope modifications.
   - **Knock 2 (`RESULT_ACHIEVED`):** Confirmed calendar booking or signed agreement.

4. **Right-to-be-Forgotten & Control Footers:**
   Every user-facing notification includes a reassuring control footer displaying their sender mode (default agent relay vs. connected custom SMTP) and their cryptographic deletion command (`DELETE MY DATA [PIN]`), which instantly purges all user data and mission logs from DynamoDB.

---

## 🧪 Verification & Proof of Execution

- **Live Agent Email (Pure Zero-UI Experience):**
  - Email: `agent@anasriaz.com` *(Judges can send a blank "Hi" email or attach a company profile PDF right from their inbox!)*
- **Live AWS Cloud Host:**
  - Public IP: `44.220.162.85`
  - Health API: [http://44.220.162.85:8000/api/health](http://44.220.162.85:8000/api/health)
- **Pytest Suite:** 22/22 automated unit and integration tests passing (`pytest`).
- **End-to-End Simulation:** Automated 10-scenario simulation script (`python -m scripts.simulate_email_flow`) successfully exercising the entire lifecycle from cold-start greeting to cryptographic data wipe.
- **Live SMTP/IMAP Connectivity:** Verified live authentication with Purelymail SMTP (Port 465) and IMAP (Port 993).
