"""Launch script for Payaam Interactive Visual Sandbox.

Runs the FastAPI sandbox web application on http://localhost:8000.
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn


def main():
    print("\n" + "=" * 65)
    print(" 🚀 Launching Payaam Interactive Visual Sandbox")
    print(" AWS Agents for Humans Hackathon - Professional Agents Track")
    print("=" * 65)
    print("\n📱 Access Sandbox UI at: http://localhost:8000")
    print("Press Ctrl+C to stop the server.\n")

    uvicorn.run("src.sandbox.app:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
