# WorkDost - Guardrails & Responsible AI Policy

## 1. Core Principles of Autonomous Errand Coordination

WorkDost operates under strict safety, privacy, and anti-harassment protocols to ensure autonomous multi-merchant communication is ethical, non-intrusive, and secure for both end users and service providers.

---

## 2. Privacy & Data Masking Guardrails

### 2.1 Two-Stage Disclosure Policy
During the quotation and discovery phase, the user's sensitive PII must never be disclosed to service providers.

| Information Element | Quotation Phase (RFQ) | Post-Confirmation (Winning Merchant) | Losing Merchants |
| :--- | :--- | :--- | :--- |
| **User First Name** | Masked (e.g. "WorkDost Client") | Shared | Never Shared |
| **User Phone Number**| Masked via WorkDost Proxy | Shared (or coordinated via proxy) | Never Shared |
| **Exact Street & Unit**| Masked (Locality / Area only, e.g. "Downtown / F-7") | Full Address Disclosed | Never Shared |
| **Live Geolocation Pin**| Generalized (approximate 2km radius) | Exact Pin Shared | Never Shared |

### 2.2 Payment & Financial Separation
- WorkDost **never** asks for or stores credit card numbers, CVVs, or online banking passwords over WhatsApp.
- Quote agreements are strictly non-binding estimates until confirmed in person or through authorized payment links.

---

## 3. Anti-Spam & Communication Throttling

To prevent automated agent loops from overwhelming local businesses:

### 3.1 Hard Outreach Limits
1. **Maximum Outreach Targets:** A maximum of **5 merchants** can be contacted per individual job request.
2. **Follow-Up Frequency:** Maximum of **1 follow-up ping** per merchant, sent only after a minimum of 2 hours of inactivity.
3. **Duplicate Cooldown:** The same merchant phone number cannot be contacted for the same user within a **4-hour cooldown window**.
4. **Daily Outreach Quotas:** No single merchant may receive more than 3 distinct inquiries from WorkDost across all users within a 24-hour window.

### 3.2 Polite Closing Notices
When a user selects a winning quote, all other merchants who provided quotes or are pending response receive a courteous cancellation notice:
> *"Thank you for your time! The client has proceeded with another option for this task. We look forward to connecting on future jobs."*

---

## 4. Opt-Out & Unsubscribe Management (Compliance)

### 4.1 Trigger Keywords
If a merchant replies with any of the following standard or multilingual opt-out triggers, all active and future communications must immediately cease:
- **English:** `STOP`, `UNSUBSCRIBE`, `CANCEL`, `QUIT`, `OPT OUT`, `DON'T MESSAGE ME`, `LEAVE ME ALONE`, `NO` (when answering RFQ opt-in).
- **Urdu / Roman Urdu:** `MAT KARO`, `BAND KARO`, `MESSAGE NA KAREIN`, `INAKAR`.
- **Hindi / Roman Hindi:** `ROKO`, `MESSAGE MAT BHEJO`.

### 4.2 Automated Blacklist Flow
1. Instantly write the merchant's E.164 phone number to a DynamoDB blacklist with reason `MERCHANT_OPT_OUT`.
2. Cancel any pending outreach tasks targeting this number.
3. Remove the contact from active suggestions in future Mode A and Mode B queries.
4. Send an immediate confirmation: *"You have been unsubscribed from WorkDost job requests and will not receive further messages."*

---

## 5. Inference, Latency & Audio Bounds

### 5.1 Voice Note Processing Limits
- **Maximum Audio Duration:** 60 seconds. Voice notes longer than 60 seconds are rejected with a polite prompt: *"Please send a voice note under 1 minute or type your message."*
- **Speech-to-Text Model:** Amazon Transcribe / Bedrock Multimodal Audio Processing.

### 5.2 Tool Execution & Fallback Timeouts
- **Tool Invocation Timeout:** Maximum **15 seconds** per tool execution.
- **Circuit Breaker:** If an external discovery API (e.g. Google Places) or third-party service fails or exceeds 15 seconds, gracefully fall back to default user-saved contacts or prompt the user for a manual contact drop.
- **Model Fallback:** If `anthropic.claude-3-5-sonnet` encounters rate limiting or latency spikes (>8s), the pipeline seamlessly routes fallback extraction tasks to `anthropic.claude-3-5-haiku`.
