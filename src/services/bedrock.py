"""Amazon Bedrock Client Service for Payaam.

Provides high-performance inference interfaces for Claude 3.5 Sonnet (reasoning)
and Claude 3.5 Haiku (fast extraction & normalization) using the Amazon Bedrock Converse API.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional
import boto3
from src.config import settings

logger = logging.getLogger("payaam.services.bedrock")


def extract_json_from_text(text: str) -> Dict[str, Any]:
    """Safely extracts JSON dictionary from raw model text output."""
    cleaned = text.strip()
    # Match markdown json block if present
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        # Match outermost curly braces
        brace_match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
        if brace_match:
            json_str = brace_match.group(1)
        else:
            json_str = cleaned

    try:
        return json.loads(json_str)
    except Exception as exc:
        logger.warning(f"Direct JSON parse failed on Bedrock output ({exc}): {text[:100]}...")
        # Fallback sanitize trailing commas or newlines
        sanitized = re.sub(r",\s*([\]}])", r"\1", json_str)
        return json.loads(sanitized)


class BedrockService:
    """Amazon Bedrock runtime interface."""

    def __init__(self) -> None:
        self.region = settings.AWS_REGION
        self.sonnet_model_id = settings.BEDROCK_MODEL_SONNET
        self.haiku_model_id = settings.BEDROCK_MODEL_HAIKU
        self._client: Optional[Any] = None

    @property
    def client(self) -> Any:
        """Lazy-loaded boto3 bedrock-runtime client."""
        if self._client is None:
            kwargs: Dict[str, Any] = {"region_name": self.region}
            if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
                kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
                kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
            self._client = boto3.client("bedrock-runtime", **kwargs)
        return self._client

    async def converse(
        self,
        prompt: str,
        system_prompt: str = "",
        model_id: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> str:
        """Invokes Amazon Bedrock Converse API synchronously/asynchronously."""
        target_model = model_id or self.haiku_model_id
        logger.info(f"Invoking Bedrock Converse API with model {target_model}")

        system_block = [{"text": system_prompt}] if system_prompt else []
        messages: List[Dict[str, Any]] = [
            {
                "role": "user",
                "content": [{"text": prompt}],
            }
        ]

        try:
            response = self.client.converse(
                modelId=target_model,
                messages=messages,
                system=system_block,
                inferenceConfig={
                    "temperature": temperature,
                    "maxTokens": max_tokens,
                },
            )
            output_content = response.get("output", {}).get("message", {}).get("content", [])
            if output_content and "text" in output_content[0]:
                return output_content[0]["text"]
            return ""
        except Exception as exc:
            logger.error(f"Bedrock Converse invocation error ({target_model}): {exc}")
            raise


bedrock_service = BedrockService()
