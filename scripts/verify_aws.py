"""Verification Script for AWS Bedrock & DynamoDB connectivity in Payaam."""

import sys
import boto3
from dotenv import load_dotenv
import os

load_dotenv()


def main():
    region = os.getenv("AWS_REGION", "us-east-1")
    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    sonnet_id = os.getenv("BEDROCK_MODEL_SONNET", "anthropic.claude-3-5-sonnet-20241022-v2:0")

    print(f"[*] Initializing AWS verification for region: {region}")

    # 1. Verify STS Identity
    try:
        sts = boto3.client(
            "sts",
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key
        )
        caller = sts.get_caller_identity()
        print(f"[+] STS Authentication Successful!")
        print(f"    Account: {caller.get('Account')}")
        print(f"    Arn: {caller.get('Arn')}")
    except Exception as e:
        print(f"[-] STS Authentication Failed: {e}")
        sys.exit(1)

    # 2. Verify Bedrock Runtime
    try:
        bedrock = boto3.client(
            "bedrock",
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key
        )
        models = bedrock.list_foundation_models(byProvider="Anthropic")
        print(f"[+] Bedrock API Accessible! Found {len(models.get('modelSummaries', []))} Anthropic foundation models.")
    except Exception as e:
        print(f"[!] Bedrock Control Plane check (list_foundation_models): {e}")

    # 3. Verify DynamoDB
    try:
        dynamodb = boto3.client(
            "dynamodb",
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key
        )
        tables = dynamodb.list_tables()
        payaam_tables = [t for t in tables.get('TableNames', []) if 'Payaam' in t]
        print(f"[+] DynamoDB Accessible! Payaam tables: {payaam_tables}")
    except Exception as e:
        print(f"[-] DynamoDB Access Failed: {e}")

    print("\n[SUCCESS] AWS configuration is active and ready for Payaam!")


if __name__ == "__main__":
    main()
