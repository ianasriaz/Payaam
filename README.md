# 🚀 Payaam — Autonomous Background Email Delegate

> **Autonomous Client Outreach, Lead Sourcing & Deal Delegation Agent for Solo Professionals**  
> Built for the **AWS Agents for Humans Hackathon** *(Professional Agents Track)*.  
> *"Payaam"* translates to *"The Message"* or *"The Dispatch"* — your tireless digital courier working silently across email networks.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://python.org)
[![AWS Bedrock](https://img.shields.io/badge/AWS-Amazon%20Bedrock-orange.svg)](https://aws.amazon.com/bedrock/)
[![AWS DynamoDB](https://img.shields.io/badge/AWS-Amazon%20DynamoDB-blue.svg)](https://aws.amazon.com/dynamodb/)
[![Strands Agents](https://img.shields.io/badge/SDK-Strands%20Agents-blueviolet.svg)](https://github.com/strands-agents)
[![Email: Purelymail](https://img.shields.io/badge/Protocol-Purelymail%20SMTP%2FIMAP-blue.svg)](https://purelymail.com)
[![Live on AWS](https://img.shields.io/badge/Hosted-AWS%20EC2%20(t3.micro)-success.svg)](http://54.226.141.96:8000/api/health)

---

## 🌟 Overview

**Payaam** is an autonomous, **100% Zero-UI** background email delegate built with the **Strands Agents SDK**, **Amazon Bedrock (Claude 3.5 Sonnet & Claude 3.5 Haiku)**, **Amazon DynamoDB**, and **Purelymail (SMTP/IMAP)**.

Instead of opening yet another web app, dashboard, CRM, or cold outreach tool, Payaam runs silently in the background of your existing native email client (Gmail, Apple Mail, Outlook). You simply email your agent raw instructions, and Payaam takes over:
- 🎯 **Individualized B2B Pitches**: Crafts bespoke, value-first outreach emails citing your actual portfolio, services, and past projects from your Memory Vault.
- 📄 **Multimodal Company Profile & Document Ingestion**: Attach your company profile PDF, brochure, services list, rate card, FAQs, or office location notes. Amazon Bedrock natively ingests and indexes them into your private Memory Vault.
- 🛡️ **Anti-Spam Collision Shield**: Checks a global DynamoDB registry before sending any pitch to prevent multi-user spam fatigue on the same recipient within 14 days.
- 🔕 **Two-Knock Policy**: Silently filters auto-responders, vacation notices, and opt-outs. Autonomously answers routine questions (services, packages, FAQs, office address, portfolio links) directly from your Company Knowledge Base without interrupting you.
- 🔥 **Action Cards**: Only surfaces to your inbox when a genuine human decision is required (e.g. budget counter-offer or scope adjustment).
- ✍️ **1-Line Refinements**: When an Action Card arrives, reply with a quick rough note from your phone (*"Make it $220 and ask for their menu PDF"*); Payaam immediately transforms it into a polished, professional client response.
- 🔐 **Privacy First & BYO-SMTP Controls**: Every email sent to the user includes a customized footer showing current email relay status (default agent email vs. connected personal SMTP encrypted via AES-128 Fernet) and instant Right-to-be-Forgotten command (`DELETE MY DATA PYM-XXXX`).

---

## 🧠 Core Features & Hackathon Directives

| Hackathon Directive | How Payaam Delivers |
| :--- | :--- |
| **"Routine & Repetitive Tasks in Background"** | Handles multi-day cold outreach, follow-ups, and quote chasing without human babysitting. |
| **"Instead of Another App to Open & Manage"** | **Pure Zero-UI**: Onboarding, profile creation, document ingestion, SMTP connection, mission launch, and account deletion happen 100% over native email. |
| **"Only Surfaces When There's a Real Decision"** | **Two-Knock Policy**: Filters noise silently; only alerts the user when terms must be approved or a meeting is locked in. |
| **Multimodal Document Understanding** | Ingests company profile PDFs, brochures, and rate cards using Amazon Bedrock native document processing. |
| **Multi-Tenant Collision Shield** | Global DynamoDB registry (`Payaam_ContactRegistry`) prevents multiple users from spamming the same business within 14 days. |
| **Security & Privacy (Right-to-be-Forgotten)** | User SMTP passwords encrypted with AES-128 Fernet at rest. Complete data purge with cryptographic deletion PINs (`DELETE MY DATA PYM-XXXX`). |

---

## 🏗️ Architecture & Cloud Infrastructure

```text
User (Any Email Client) ──> Purelymail IMAP ──> Strands Agent Core (Claude 3.5 Sonnet)
                                                           │
              ┌────────────────────────────────────────────┼────────────────────────────────────────────┐
              ▼                                            ▼                                            ▼
   [Onboarding & Document Tool]                 [Outreach & Dispatch Tool]                   [Two-Knock Inbox Triager]
   - Blank greeting guide                       - Pre-flight collision check                 - Silent filter: Auto-reply/OOO
   - PDF/Doc profile ingestion                  - 3-sentence B2B pitch copy                  - Silent resolver: Packages/FAQs
   - Memory Vault setup in DynamoDB             - Purelymail SMTP dispatch                   - Knock 1: Action Needed card
   - BYO-SMTP AES-128 encryption                - State recorded in DynamoDB                 - Knock 2: Result Achieved card
   - PIN-based data deletion                    - Collision ledger recorded                  - Refinement: 1-line to polished
```

### Live AWS Cloud Deployment
- **AWS Region**: `us-east-1`
- **Instance**: `t3.micro` (Amazon Linux 2023)
- **Public IP**: `54.226.141.96`
- **Agent Email Gateway**: `agent@anasriaz.com` (Purelymail 24/7 Daemon)
- **Health Check API**: [http://54.226.141.96:8000/api/health](http://54.226.141.96:8000/api/health)
- **Background Daemons**:
  - `payaam-worker.service`: 24/7 Purelymail IMAP listener and Strands Agent loop.
  - `payaam-sandbox.service`: FastAPI Health & Monitoring API on port 8000.

---

## 📁 Repository Structure

```text
├── .dcs/                               # Architecture, PRD, and Changelog specs
│   ├── ARCHITECTURE.md                 # Technical blueprint and sequence diagrams
│   ├── PRD.md                          # Product requirements & user personas
│   └── CHANGELOG.md                    # Engineering build history
├── src/
│   ├── agent/                          # Strands Agent Core & Tools
│   │   ├── core.py                     # Central PayaamAgent orchestrator & 4-tier routing
│   │   └── tools/
│   │       ├── onboarding.py           # Greeting, Vault setup, BYO-SMTP, Deletion
│   │       ├── outreach.py             # Collision check, pitch copywriter, dispatch
│   │       └── inbox_triager.py        # Two-Knock policy inbox classifier
│   ├── services/
│   │   ├── bedrock.py                  # Amazon Bedrock Converse API interface
│   │   ├── crypto.py                   # Fernet symmetric credential encryption
│   │   ├── dynamodb.py                 # Users, Missions, and Collision Registry
│   │   └── email_service.py            # Purelymail SMTP dispatch & IMAP parser
│   ├── handlers/
│   │   └── email_worker.py             # Purelymail background polling daemon
│   ├── sandbox/
│   │   └── app.py                      # Developer visual testing sandbox (FastAPI)
│   └── config.py                       # Pydantic centralized application settings
├── scripts/
│   ├── deploy_to_aws.py                # Automated EC2/DynamoDB AWS deployer
│   ├── simulate_email_flow.py          # 10-step full lifecycle automated simulation
│   ├── verify_aws.py                   # AWS STS, Bedrock & DynamoDB health check
│   └── run_sandbox.py                  # Local FastAPI visual sandbox launcher
├── tests/                              # Automated Pytest suite (17 tests)
│   ├── test_services.py                # Crypto, Email, DynamoDB, Collision tests
│   ├── test_tools.py                   # Onboarding, Outreach, Triager tool tests
│   └── test_sandbox.py                 # Visual sandbox API tests
├── .env.example                        # Environment variable template
├── SUBMISSION_GUIDE.md                 # Devpost copy-paste submission kit
└── requirements.txt                    # Project dependencies
```

---

## ⚡ Quickstart Setup

### 1. Prerequisites
- Python 3.10+
- Amazon Web Services (AWS) account with access to **Amazon Bedrock** (`anthropic.claude-3-5-sonnet-20241022-v2:0` & `anthropic.claude-3-5-haiku-20241022-v1:0`).
- Purelymail (or any standard SMTP/IMAP account).

### 2. Installation
```bash
git clone https://github.com/ianasriaz/Payaam.git
cd Payaam
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy `.env.example` to `.env` and fill in your credentials:
```bash
cp .env.example .env
```
Key configuration items:
```ini
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
BEDROCK_MODEL_SONNET=anthropic.claude-3-5-sonnet-20241022-v2:0
BEDROCK_MODEL_HAIKU=anthropic.claude-3-5-haiku-20241022-v1:0

DYNAMODB_TABLE_USERS=Payaam_Users
DYNAMODB_TABLE_MISSIONS=Payaam_Missions
DYNAMODB_TABLE_REGISTRY=Payaam_ContactRegistry

PURELYMAIL_SMTP_HOST=smtp.purelymail.com
PURELYMAIL_SMTP_PORT=465
PURELYMAIL_IMAP_HOST=imap.purelymail.com
PURELYMAIL_IMAP_PORT=993
PURELYMAIL_USER=payaam@yourdomain.com
PURELYMAIL_PASSWORD=your_password
APP_ENCRYPTION_KEY=your_32_byte_fernet_key
```

---

## 🧪 Verification & Simulation

### Run the 10-Scenario End-to-End Simulation
Demonstrates the entire autonomous lifecycle:
```bash
python -m scripts.simulate_email_flow
```
**Scenarios tested:**
1. **Cold Start Greeting**: Blank "Hi" email -> Welcome guide & Deletion PIN.
2. **Profile & Memory Vault**: User introduces themselves -> Stored in DynamoDB `Payaam_Users`.
3. **BYO-SMTP Connection**: Custom SMTP password encrypted with AES-128 Fernet at rest.
4. **Mission Dispatch**: 3 tailored pitches dispatched to local businesses.
5. **Multi-Tenant Collision Shield**: Second user attempts to pitch the same business -> Shield flags duplicate.
6. **Two-Knock Silent Ignore**: Auto-responder / out-of-office message filtered without bothering user.
7. **Two-Knock Silent Vault Resolution**: Prospect asks for portfolio -> Payaam answers autonomously citing vault.
8. **Two-Knock Action Needed**: Prospect counters on budget -> Surfaced to user with Action Card.
9. **User 1-Line Refinement**: User sends rough notes -> Polished response dispatched to client.
10. **Right-to-be-Forgotten**: Complete account and session wipe from DynamoDB (`DELETE MY DATA PYM-XXXX`).

### Run Automated Unit & Integration Tests
```bash
pytest
```
*Result: 22 passed in 22 tests.*

---

## 🚀 Cloud Deployment

To deploy or update Payaam on AWS:
```bash
python scripts/deploy_to_aws.py
```
This script packages the code, validates DynamoDB tables, uploads to S3, configures security groups, and launches an Amazon Linux 2023 EC2 host running systemd daemons.

---

## 📜 License
MIT License. Developed for the **AWS Agents for Humans Hackathon** (Professional Agents Track).
