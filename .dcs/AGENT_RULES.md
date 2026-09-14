# WorkDost - AI Agent Development & Governance Rules

## 1. Hackathon Context & Mission
**WorkDost** ("Your Daily Task Companion") is an autonomous background errand and trade coordination agent built for the **AWS Agents for Humans Hackathon (Everyday Agents Track)**.

WorkDost eliminates human friction in booking, negotiating, comparing quotes, and coordinating errands with local trade merchants (plumbing, electricians, tailors, bakeries, mechanics, pharmacies) via seamless WhatsApp messaging.

---

## 2. Mandatory 4-Step Engineering Protocol (Vibe-Coding Governance)

For every single implementation prompt, tool addition, or architectural refactor, all collaborating engineers and autonomous coding assistants must follow this strict 4-step sequence:

### Step 1: WHY (Architectural Rationale)
- Explicitly state the motivation behind the change.
- Highlight which Hackathon evaluation criteria the change directly reinforces:
  - **Everyday Impact & Autonomy** (real-world daily human utility).
  - **Strands Agents SDK & Amazon Bedrock Utilization** (agentic tool loops, model switching).
  - **Enterprise Architecture & State Handling** (DynamoDB idempotency, TTL, async decoupling).
  - **Safety & Responsible AI** (location masking, anti-spam, consent enforcement).

### Step 2: WHAT'S CHANGING (File Plan)
- Provide an exact file modification/creation breakdown.
- Include explicit diff outlines, new classes, functions, and signature changes before writing code.

### Step 3: EXPECTED RESULT (Verification Plan)
- Detail expected inputs, outputs, schemas, and edge case coverage.
- Outline automated unit tests (`pytest`) and manual verification steps.

### Step 4: PERMISSIONS REQUEST
- Present the planned actions clearly and pause for explicit developer confirmation whenever introducing destructive schema shifts or external infrastructure costs.

---

## 3. Max-Score Technical Directives

To achieve maximum scores across all AWS Hackathon rubric dimensions, all codebase contributions must strictly adhere to the following rules:

### 1. Strict Strands Agents SDK & Pydantic 2.x Typing
- All agent tools must be built using the `strands-agents` tool decorators.
- Tool input arguments and return structures must be rigorously typed using `pydantic.BaseModel` (v2.x).
- Avoid untyped `dict` payloads or string-parsed pseudo-schemas.

### 2. Zero Hardcoding & Global Multi-Country Compliance
- **No hardcoded currencies:** Currencies must be dynamically extracted, normalized, or inferred from local country codes (e.g., USD `$`, PKR `₨`, GBP `£`, EUR `€`, INR `₹`).
- **No hardcoded timezones or date formats:** All temporal computations must respect the user's localized timezone offset and ISO 8601 timestamps with UTC storage.
- **No hardcoded distance/measurement units:** Dynamically accommodate metric (km, m) and imperial (miles, ft) based on geo-locale.
- **Phone Numbers:** All phone numbers must be strictly validated and formatted to E.164 standard (`+<country_code><number>`) via `phonenumbers`.

### 3. Decoupled Synchronous Ingestion vs. Asynchronous Dispatch
- Webhook endpoints (Twilio/WhatsApp Cloud API) must respond immediately with HTTP 200/202 to avoid provider timeout retries.
- Background tasks (multi-merchant outreach, LLM quote parsing, reminder timers) must be executed asynchronously via decoupled handlers or worker tasks.

### 4. Idempotency & DynamoDB TTL Expiration
- Every inbound message must be deduplicated using `message_id` or session idempotency keys.
- All session records in DynamoDB (`WorkDost_JobSessions`) must have an active UNIX epoch `ttl` attribute (default: 48-72 hours) to avoid stale state retention and control storage cost.

### 5. Automated Ledger Tracking
- Every merged feature, fix, or tool addition must be logged in `.dcs/CHANGELOG.md` with session numbering, timestamp, and architectural summary.
