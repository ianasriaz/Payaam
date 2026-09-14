"""Payaam Automated AWS Cloud Deployment Script.

Uses the user's connected AWS IAM credentials in `.env` via boto3 to:
1. Verify / provision DynamoDB serverless tables (Payaam_*) in us-east-1.
2. Package the application into a lightweight zip bundle.
3. Upload the bundle to S3 and generate a secure presigned transfer URL.
4. Ensure the EC2 Security Group (payaam-agent-sg) is configured.
5. Launch a dedicated t3.micro EC2 instance running Amazon Linux 2023.
6. Install and configure systemd services for:
   - `payaam-worker.service`: 24/7 Purelymail IMAP daemon & Strands Agent.
   - `payaam-sandbox.service`: FastAPI Sandbox & Health Dashboard on Port 8000.
7. Print public IP, endpoints, and live monitoring commands.
"""

import io
import os
import sys
import time
import zipfile
import boto3
from dotenv import load_dotenv

# Ensure UTF-8 output on Windows PowerShell
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

load_dotenv()

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET = os.getenv("AWS_SECRET_ACCESS_KEY")

if not AWS_KEY or not AWS_SECRET:
    print("❌ Error: AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY not found in .env.")
    sys.exit(1)

session = boto3.Session(
    aws_access_key_id=AWS_KEY,
    aws_secret_access_key=AWS_SECRET,
    region_name=AWS_REGION,
)


def create_code_bundle() -> bytes:
    """Compresses project files into a memory zip archive."""
    print("📦 [1/6] Packaging Payaam codebase into archive...")
    buf = io.BytesIO()
    ignored_patterns = [".git", "__pycache__", ".pytest_cache", "venv", ".venv", ".system_generated", "dist"]

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk("."):
            if any(p in root for p in ignored_patterns):
                continue
            for f in files:
                if f.endswith((".pyc", ".log", ".tmp")):
                    continue
                fp = os.path.join(root, f)
                arcname = os.path.relpath(fp, ".")
                zf.write(fp, arcname)

    data = buf.getvalue()
    print(f"   Bundle created: {len(data) / 1024:.1f} KB")
    return data


def ensure_dynamodb_tables() -> None:
    """Ensures Payaam DynamoDB tables exist."""
    print("🗄️  [2/6] Verifying DynamoDB tables...")
    ddb = session.client("dynamodb")
    existing = ddb.list_tables()["TableNames"]

    tables = [
        {
            "TableName": "Payaam_Users",
            "KeySchema": [{"AttributeName": "email", "KeyType": "HASH"}],
            "AttributeDefinitions": [{"AttributeName": "email", "AttributeType": "S"}],
            "BillingMode": "PAY_PER_REQUEST",
        },
        {
            "TableName": "Payaam_Missions",
            "KeySchema": [{"AttributeName": "mission_id", "KeyType": "HASH"}],
            "AttributeDefinitions": [{"AttributeName": "mission_id", "AttributeType": "S"}],
            "BillingMode": "PAY_PER_REQUEST",
        },
        {
            "TableName": "Payaam_ContactRegistry",
            "KeySchema": [
                {"AttributeName": "target_email", "KeyType": "HASH"},
                {"AttributeName": "category", "KeyType": "RANGE"},
            ],
            "AttributeDefinitions": [
                {"AttributeName": "target_email", "AttributeType": "S"},
                {"AttributeName": "category", "AttributeType": "S"},
            ],
            "BillingMode": "PAY_PER_REQUEST",
        },
    ]

    for t in tables:
        name = t["TableName"]
        if name not in existing:
            print(f"   Creating table {name}...")
            ddb.create_table(**t)
        else:
            print(f"   Table {name} is active.")


def upload_bundle_to_s3(bundle_bytes: bytes) -> str:
    """Uploads bundle to S3 and returns a presigned URL valid for 2 hours."""
    print("☁️  [3/6] Uploading code bundle to S3...")
    from botocore.client import Config
    s3 = session.client("s3", region_name=AWS_REGION, config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))
    buckets = [b["Name"] for b in s3.list_buckets().get("Buckets", [])]

    # Find or create a deployment bucket
    bucket_name = None
    for b in buckets:
        if "payaam" in b or "samclisourcebucket" in b or "workdost" in b:
            bucket_name = b
            break

    if not bucket_name:
        sts = session.client("sts")
        account = sts.get_caller_identity()["Account"]
        bucket_name = f"payaam-deploy-{account}"
        print(f"   Creating dedicated S3 bucket: {bucket_name}...")
        s3.create_bucket(Bucket=bucket_name)

    key = "payaam/bundle.zip"
    s3.put_object(Bucket=bucket_name, Key=key, Body=bundle_bytes)
    print(f"   Uploaded to s3://{bucket_name}/{key}")

    presigned_url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket_name, "Key": key},
        ExpiresIn=7200,
    )
    return presigned_url


def ensure_security_group() -> str:
    """Finds or creates the payaam-agent-sg security group."""
    print("🛡️  [4/6] Verifying Security Group...")
    ec2 = session.client("ec2")
    vpcs = ec2.describe_vpcs(Filters=[{"Name": "is-default", "Values": ["true"]}])["Vpcs"]
    if not vpcs:
        vpcs = ec2.describe_vpcs()["Vpcs"]
    vpc_id = vpcs[0]["VpcId"]

    sg_name = "payaam-agent-sg"
    sgs = ec2.describe_security_groups(Filters=[{"Name": "group-name", "Values": [sg_name]}])["SecurityGroups"]

    if sgs:
        sg_id = sgs[0]["GroupId"]
        print(f"   Using existing Security Group: {sg_id}")
        return sg_id

    res = ec2.create_security_group(
        GroupName=sg_name,
        Description="Payaam Autonomous Agent Security Group",
        VpcId=vpc_id,
    )
    sg_id = res["GroupId"]
    ec2.authorize_security_group_ingress(
        GroupId=sg_id,
        IpPermissions=[
            {
                "IpProtocol": "tcp",
                "FromPort": 8000,
                "ToPort": 8000,
                "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "Payaam Web Sandbox UI"}],
            },
            {
                "IpProtocol": "tcp",
                "FromPort": 22,
                "ToPort": 22,
                "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "SSH Admin Access"}],
            },
        ],
    )
    print(f"   Created Security Group: {sg_id}")
    return sg_id


def build_user_data_script(presigned_url: str) -> str:
    """Generates the cloud-init script for EC2 provisioning."""
    with open(".env", "r", encoding="utf-8") as f:
        env_content = f.read().strip()

    script = f"""#!/bin/bash
set -e
exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1

echo "=== [Payaam] Starting Cloud Provisioning ==="
dnf update -y
dnf install -y python3.11 python3.11-pip git unzip

mkdir -p /opt/payaam
cd /opt/payaam

# Download application bundle
echo "=== [Payaam] Downloading bundle ==="
curl -fsSL -o bundle.zip "{presigned_url}"
unzip -o bundle.zip
rm -f bundle.zip

# Create and populate .env
echo "=== [Payaam] Configuring environment ==="
cat <<'EOF' > /opt/payaam/.env
{env_content}
EOF

# Setup Python Virtual Environment
echo "=== [Payaam] Installing Python dependencies ==="
python3.11 -m venv /opt/payaam/venv
source /opt/payaam/venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Create systemd service for the Autonomous Email Worker
echo "=== [Payaam] Registering payaam-worker.service ==="
cat <<'EOF' > /etc/systemd/system/payaam-worker.service
[Unit]
Description=Payaam Autonomous Email Worker Daemon
After=network.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/opt/payaam
ExecStart=/opt/payaam/venv/bin/python -m src.handlers.email_worker
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

# Create systemd service for the FastAPI Sandbox & Health Dashboard
echo "=== [Payaam] Registering payaam-sandbox.service ==="
cat <<'EOF' > /etc/systemd/system/payaam-sandbox.service
[Unit]
Description=Payaam FastAPI Sandbox & Health Dashboard
After=network.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/opt/payaam
ExecStart=/opt/payaam/venv/bin/uvicorn src.sandbox.app:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

# Fix permissions
chown -R ec2-user:ec2-user /opt/payaam

# Start and enable services
systemctl daemon-reload
systemctl enable --now payaam-worker.service
systemctl enable --now payaam-sandbox.service

echo "=== [Payaam] Cloud Provisioning Complete! ==="
"""
    return script


def launch_ec2_instance(sg_id: str, user_data: str) -> None:
    """Launches the EC2 host."""
    print("🚀 [5/6] Launching Amazon EC2 Instance (t3.micro)...")
    ec2 = session.client("ec2")
    ssm = session.client("ssm")

    # Fetch latest Amazon Linux 2023 AMI
    param = ssm.get_parameter(Name="/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64")
    ami_id = param["Parameter"]["Value"]

    # Terminate any existing host instances to ensure fresh deployment
    existing = ec2.describe_instances(
        Filters=[
            {"Name": "tag:Name", "Values": ["Payaam-Agent-Host", "WorkDost-Agent-Host"]},
            {"Name": "instance-state-name", "Values": ["running", "pending", "stopped"]},
        ]
    )["Reservations"]

    for res in existing:
        for inst in res["Instances"]:
            old_id = inst["InstanceId"]
            print(f"   Terminating previous instance: {old_id}...")
            try:
                ec2.terminate_instances(InstanceIds=[old_id])
            except Exception as e:
                print(f"   Termination warning: {e}")

    run_res = ec2.run_instances(
        ImageId=ami_id,
        InstanceType="t3.micro",
        MinCount=1,
        MaxCount=1,
        SecurityGroupIds=[sg_id],
        UserData=user_data,
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Name", "Value": "Payaam-Agent-Host"},
                    {"Key": "Project", "Value": "Payaam"},
                    {"Key": "Hackathon", "Value": "AWS-Agents-for-Humans"},
                ],
            }
        ],
    )

    inst_id = run_res["Instances"][0]["InstanceId"]
    print(f"   Instance launched: {inst_id}")
    print("⏳ [6/6] Waiting for instance to enter 'running' state...")

    waiter = ec2.get_waiter("instance_running")
    waiter.wait(InstanceIds=[inst_id])

    info = ec2.describe_instances(InstanceIds=[inst_id])["Reservations"][0]["Instances"][0]
    public_ip = info.get("PublicIpAddress")

    print("\n" + "=" * 65)
    print("🎉 PAYAAM IS OFFICIALLY HOSTED & RUNNING ON AWS!")
    print("=" * 65)
    print(f"• AWS Region:       {AWS_REGION}")
    print(f"• Instance ID:      {inst_id}")
    print(f"• Public IP:        {public_ip}")
    print(f"• Web Sandbox UI:   http://{public_ip}:8000")
    print(f"• Health Endpoint:  http://{public_ip}:8000/api/health")
    print(f"• Email Daemon:     Listening 24/7 on agent@anasriaz.com")
    print("=" * 65)
    print("💡 Cloud-init provisioning takes ~90 seconds to complete pip installs.")
    print("   You can now turn off your local PC; Payaam is running 24/7 in AWS!")
    print("=" * 65 + "\n")


def main():
    print("\n=== Payaam AWS Cloud Deployment ===")
    bundle_bytes = create_code_bundle()
    ensure_dynamodb_tables()
    presigned_url = upload_bundle_to_s3(bundle_bytes)
    sg_id = ensure_security_group()
    user_data = build_user_data_script(presigned_url)
    launch_ec2_instance(sg_id, user_data)


if __name__ == "__main__":
    main()
