# Payaam (پیام) — Technical Architecture & System Blueprint

## 1. High-Level Architecture Overview

Payaam is an autonomous, event-driven agentic system built on **Amazon Bedrock**, the **Strands Agents SDK**, **Amazon DynamoDB**, and **Purelymail (SMTP/IMAP)**.

```text
  +-----------------------------------------------------------------------------------------------+
  |                                 USER (Native Email Client)                                    |
  +-----------------------------------------------+-----------------------------------------------+
                                                  | Inbound RFC 5322 Email
                                                  v
                              +---------------------------------------+
                              | Purelymail IMAP (SSL Port 993)        |
                              | / Email Worker Daemon                 |
                              +-------------------+-------------------+
                                                  |
                                                  v
  +-----------------------------------------------------------------------------------------------+
  | Payaam Agent Core (Strands Agents SDK & Amazon Bedrock)                                       |
  |                                                                                               |
  |   +---------------------------------------------------------------------------------------+   |
  |   | Reasoning & Copywriting: Amazon Bedrock (`anthropic.claude-3-5-sonnet-20241022-v2:0`) |   |
  |   | Fast Triage & Extraction: Amazon Bedrock (`anthropic.claude-3-5-haiku-20241022-v1:0`)  |   |
  |   +---------------------------------------------------------------------------------------+   |
  |                                                                                               |
  |   +---------------------------------------------------------------------------------------+   |
  |   | Strands Agent Tool Suite                                                              |   |
  |   |  1. handle_onboarding_or_greeting_tool: Greeting guides, Vaults, BYO-SMTP, Deletion   |   |
  |   |  2. dispatch_outreach_mission_tool: Pre-flight collision checks, B2B pitch dispatch     |   |
  |   |  3. triage_inbound_email_tool: Two-Knock reply evaluation & user 1-line refinement   |   |
  |   +---------------------------------------------------------------------------------------+   |
  +-----------------------------------------------+-----------------------------------------------+
                                                  |
                  +-------------------------------+-------------------------------+
                  |                                                               |
                  v                                                               v
  +-----------------------------------------------+               +-------------------------------+
  | Amazon DynamoDB State Engine                  |               | Outbound Email Engine         |
  | - Payaam_Users (Profiles, Vaults, PINs)       |               | (Purelymail SMTP / BYO-SMTP)  |
  | - Payaam_Missions (Ephemeral State & TTL)     |               | Dispatches to Candidates 1..N |
  | - Payaam_ContactRegistry (Collision Shield)   |               | with thread refs [PYM-XXXX]   |
  +-----------------------------------------------+               +-------------------------------+
```

---

## 2. The Two-Knock Policy State Machine

Payaam strictly isolates the user from intermediate email noise:

```text
                                INBOUND EMAIL DETECTED
                                          │
                                          ▼
                            [Bedrock Intent Classifier]
                                          │
        ┌───────────────────┬─────────────┴─────────────┬───────────────────┐
        ▼                   ▼                           ▼                   ▼
  [IGNORE_AUTO]         [OPT_OUT]              [RESOLVE_SILENTLY]    [ACTION_NEEDED / RESULT]
  (Out-of-office,      (Unsubscribe,           (Portfolio inquiry,    (Budget negotiation,
   vacation notice,     not interested)        turnaround times)      meeting request)
   bounces)                   │                         │                   │
        │                     │                         │                   │
        ▼                     ▼                         ▼                   ▼
   Drop Silently       Update Mission          Auto-Reply Citing      Two-Knock Surface:
   (No User Email)     State Silently          User Memory Vault      Action Card Sent
                       (No User Email)         (No User Email)        to User Inbox!
```

---

## 3. Four-Tier Inbound Routing Pipeline

When an email arrives at `payaam@yourdomain.com`:

1. **Tier 1 (Universal Admin Overrides):**
   Checks for `DELETE MY DATA` or `CONNECT_SMTP`. Immediately handled regardless of active threads.
2. **Tier 2 (Correlated Active Missions):**
   If the email contains a `[PYM-XXXXXX]` thread reference or comes from an active candidate lead, routes to `triage_inbound_email_tool` for Two-Knock evaluation.
3. **Tier 3 (Unthreaded User Commands):**
   If no mission is referenced, checks for greetings (`"Hi"`, `"Hello"`), help requests, or profile setup (`"Setup: My Profile"`, `"Rates: $250"`).
4. **Tier 4 (New Mission Requests):**
   If unthreaded and contains target business emails, parses leads, runs collision check against `Payaam_ContactRegistry`, generates personalized B2B pitches, and dispatches outreach.

---

## 4. Cloud Infrastructure & Hosting Topology

- **AWS Region:** `us-east-1`
- **Compute:** Amazon Linux 2023 `t3.micro` EC2 Instance
- **Security Group:** `payaam-agent-sg` (Port 8000 for Sandbox, Port 22 for SSH)
- **Persistence:** Amazon DynamoDB with `PAY_PER_REQUEST` billing:
  - `Payaam_Users` (Hash Key: `user_email`)
  - `Payaam_Missions` (Hash Key: `mission_id`, TTL enabled)
  - `Payaam_ContactRegistry` (Hash Key: `target_email`, Range Key: `category`)
- **Background Daemons (systemd):**
  - `payaam-worker.service`: 24/7 Purelymail IMAP watcher.
  - `payaam-sandbox.service`: FastAPI Sandbox and Monitoring API on port 8000.
