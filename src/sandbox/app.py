"""Payaam Email Agent Visual Sandbox & API.

Clean, high-performance, distraction-free environment for the AWS Hackathon.
Simulates inbound and outbound email interactions with the autonomous Strands Agent.
"""

import logging
from typing import Any, Dict, List, Optional
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.agent.core import payaam_agent
from src.services.dynamodb import dynamodb_service
from src.services.email_service import InboundEmail

logger = logging.getLogger("payaam.sandbox")

app = FastAPI(title="Payaam Email Agent Sandbox", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SimulateEmailRequest(BaseModel):
    from_address: str = "anas@anasriaz.com"
    from_name: str = "Anas Riaz"
    subject: str = "Outreach: Web Design for Local Cafes"
    body_text: str
    thread_ref: Optional[str] = None


@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    """Serves minimal monochromatic developer sandbox for testing email missions."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Payaam - Autonomous Background Email Agent</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0a0a0a; color: #ededed; margin: 0; padding: 2rem; }
        .container { max-width: 900px; margin: 0 auto; }
        h1 { font-size: 1.8rem; letter-spacing: -0.5px; color: #fff; margin-bottom: 0.2rem; }
        p.subtitle { color: #888; margin-top: 0; margin-bottom: 2rem; }
        .card { background: #141414; border: 1px solid #262626; border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem; }
        label { display: block; font-size: 0.85rem; color: #aaa; margin-bottom: 0.4rem; }
        input, textarea { width: 100%; box-sizing: border-box; background: #1f1f1f; border: 1px solid #333; border-radius: 6px; color: #fff; padding: 0.75rem; margin-bottom: 1rem; font-family: monospace; }
        button { background: #fff; color: #000; border: none; font-weight: 600; padding: 0.75rem 1.5rem; border-radius: 6px; cursor: pointer; }
        button:hover { background: #ccc; }
        #output { white-space: pre-wrap; font-family: monospace; background: #000; padding: 1rem; border-radius: 6px; border: 1px solid #222; margin-top: 1rem; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Payaam: Autonomous Email Agent</h1>
        <p class="subtitle">Powered by Strands Agents SDK & Amazon Bedrock (Purelymail SMTP/IMAP)</p>
        <div class="card">
            <h3>Simulate Inbound Email</h3>
            <label>From Address</label>
            <input id="from_address" value="anas@anasriaz.com" />
            <label>Subject</label>
            <input id="subject" value="Outreach: Mobile Menus for Cafes" />
            <label>Body</label>
            <textarea id="body_text" rows="5">Pitch mobile ordering menus with 1-click WhatsApp.
Leads:
- contact@roastandbean.com (Roast & Bean)
- info@greenleafbistro.com (Greenleaf Bistro)</textarea>
            <button onclick="sendSimulatedEmail()">Dispatch Inbound Email</button>
            <div id="output">Waiting for simulation event...</div>
        </div>
    </div>
    <script>
        async function sendSimulatedEmail() {
            const out = document.getElementById('output');
            out.innerText = 'Processing through Strands Agent...';
            try {
                const res = await fetch('/api/simulate-email', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        from_address: document.getElementById('from_address').value,
                        subject: document.getElementById('subject').value,
                        body_text: document.getElementById('body_text').value
                    })
                });
                const data = await res.json();
                out.innerText = JSON.stringify(data, null, 2);
            } catch (err) {
                out.innerText = 'Error: ' + err;
            }
        }
    </script>
</body>
</html>
"""


@app.post("/api/simulate-email")
async def simulate_inbound_email(req: SimulateEmailRequest):
    """Processes simulated inbound email using the Strands Agent."""
    inbound = InboundEmail(
        message_id="<simulated-msg-001@payaam.ai>",
        subject=req.subject,
        from_address=req.from_address,
        from_name=req.from_name,
        to_address="payaam@yourdomain.com",
        date="Mon, 14 Sep 2026 12:00:00 +0000",
        body_text=req.body_text,
        thread_ref=req.thread_ref,
    )
    result = await payaam_agent.process_inbound_email(inbound)
    return {
        "status": "success",
        "result": result,
    }


@app.get("/api/user-profile")
async def get_user_profile(email: str = "anas@anasriaz.com"):
    """Returns stored user profile and vault."""
    user = dynamodb_service.get_user(email)
    return {"user": user}


@app.get("/api/health")
async def health_check():
    """Health check endpoint for cloud load balancers and monitors."""
    return {
        "status": "healthy",
        "service": "Payaam Autonomous Email Agent",
        "track": "AWS Agents for Humans Hackathon - Professional Agents Track",
        "agent": "Strands Agent Core + Amazon Bedrock Claude 3.5 Sonnet",
    }


@app.post("/api/reset")
async def reset_sandbox():
    """Resets in-memory sandbox state."""
    dynamodb_service._mem_users.clear()
    dynamodb_service._mem_missions.clear()
    dynamodb_service._mem_registry.clear()
    return {"status": "reset_successful"}
