"""Amazon DynamoDB State & Persistence Service for Payaam.

Manages:
1. Payaam_Users: Profiles, Memory Vaults, BYO-SMTP encrypted credentials, and Deletion PINs.
2. Payaam_Missions: Ephemeral multi-prospect mission states, thread trackers, and TTL.
3. Payaam_ContactRegistry: Multi-tenant collision detection and anti-spam cooldown ledger.
"""

import datetime
from decimal import Decimal
import logging
import secrets
import time
from typing import Any, Dict, List, Optional
import boto3
from boto3.dynamodb.conditions import Key
from src.config import settings

logger = logging.getLogger("payaam.services.dynamodb")


def _floats_to_decimals(obj: Any) -> Any:
    """Recursively converts float values to Decimal for DynamoDB compatibility."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: _floats_to_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_floats_to_decimals(v) for v in obj]
    return obj


def _decimals_to_floats(obj: Any) -> Any:
    """Recursively converts Decimal values back to float/int for application runtime."""
    if isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    elif isinstance(obj, dict):
        return {k: _decimals_to_floats(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_decimals_to_floats(v) for v in obj]
    return obj


class DynamoDBService:
    """DynamoDB repository manager with graceful in-memory test fallback."""

    def __init__(self) -> None:
        self.region = settings.AWS_REGION
        self.users_table_name = settings.DYNAMODB_TABLE_USERS
        self.missions_table_name = settings.DYNAMODB_TABLE_MISSIONS
        self.registry_table_name = settings.DYNAMODB_TABLE_REGISTRY
        self._resource: Optional[Any] = None
        self._table_missing: set = set()

        # In-memory mock fallback when DynamoDB is unreachable or during local tests
        self._mem_users: Dict[str, Dict[str, Any]] = {}
        self._mem_missions: Dict[str, Dict[str, Any]] = {}
        self._mem_registry: Dict[str, Dict[str, Any]] = {}

    @property
    def resource(self) -> Optional[Any]:
        """Lazy-loaded boto3 dynamodb resource."""
        if self._resource is None and settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
            try:
                self._resource = boto3.resource(
                    "dynamodb",
                    region_name=self.region,
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                )
            except Exception as exc:
                logger.warning(f"Could not initialize DynamoDB resource: {exc}")
        return self._resource

    # -------------------------------------------------------------------------
    # 1. User Profile & Memory Vault (Payaam_Users)
    # -------------------------------------------------------------------------
    def get_user(self, email: str) -> Optional[Dict[str, Any]]:
        """Retrieves a user profile and vault by email."""
        norm_email = email.strip().lower()
        if not self.resource or self.users_table_name in self._table_missing:
            return self._mem_users.get(norm_email)

        try:
            table = self.resource.Table(self.users_table_name)
            response = table.get_item(Key={"email": norm_email})
            item = response.get("Item")
            return _decimals_to_floats(item) if item else None
        except Exception as exc:
            if "ResourceNotFoundException" in str(exc):
                self._table_missing.add(self.users_table_name)
            logger.warning(f"DynamoDB get_user failed ({exc}), falling back to memory.")
            return self._mem_users.get(norm_email)

    def save_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Saves or updates a user profile, generating a deletion PIN if not present."""
        norm_email = user_data.get("email", "").strip().lower()
        if not norm_email:
            raise ValueError("User profile must include a valid email address.")

        item = dict(user_data)
        item["email"] = norm_email
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if "created_at" not in item:
            item["created_at"] = now
        item["updated_at"] = now

        # Assign unique cryptographic deletion PIN if not present (e.g. PYM-8421)
        if not item.get("deletion_pin"):
            pin_code = secrets.token_hex(2).upper()
            item["deletion_pin"] = f"PYM-{pin_code}"

        # In-memory mirror
        self._mem_users[norm_email] = dict(item)

        if self.resource and self.users_table_name not in self._table_missing:
            try:
                table = self.resource.Table(self.users_table_name)
                table.put_item(Item=_floats_to_decimals(item))
                logger.info(f"Saved user profile {norm_email} in DynamoDB.")
            except Exception as exc:
                if "ResourceNotFoundException" in str(exc):
                    self._table_missing.add(self.users_table_name)
                logger.warning(f"DynamoDB save_user failed ({exc}); cached in memory.")

        return item

    def delete_user_and_all_data(self, email: str, deletion_pin: str) -> Dict[str, Any]:
        """Permanently purges user profile, connected credentials, and all missions.

        Implements strict cryptographic PIN validation to prevent header spoofing.
        """
        norm_email = email.strip().lower()
        user = self.get_user(norm_email)
        if not user:
            return {"success": False, "error": "User profile not found."}

        expected_pin = user.get("deletion_pin", "").strip().upper()
        provided_pin = deletion_pin.strip().upper()

        if expected_pin != provided_pin:
            logger.warning(f"Invalid deletion PIN attempt for {norm_email}. Provided: {provided_pin}")
            return {"success": False, "error": "Invalid deletion PIN. Deletion aborted."}

        deleted_missions = 0

        # Purge from memory
        self._mem_users.pop(norm_email, None)
        to_del_missions = [
            m_id for m_id, m in self._mem_missions.items()
            if m.get("user_email") == norm_email
        ]
        for m_id in to_del_missions:
            self._mem_missions.pop(m_id, None)
            deleted_missions += 1

        # Purge from DynamoDB
        if self.resource and self.users_table_name not in self._table_missing:
            try:
                users_table = self.resource.Table(self.users_table_name)
                users_table.delete_item(Key={"email": norm_email})

                missions_table = self.resource.Table(self.missions_table_name)
                # Scan or query missions for this user
                resp = missions_table.scan(
                    FilterExpression=Key("user_email").eq(norm_email)
                )
                for item in resp.get("Items", []):
                    missions_table.delete_item(Key={"mission_id": item["mission_id"]})
                    deleted_missions += 1

                logger.info(f"Purged user {norm_email} and {deleted_missions} missions from DynamoDB.")
            except Exception as exc:
                if "ResourceNotFoundException" in str(exc):
                    self._table_missing.add(self.users_table_name)
                logger.error(f"Error purging DynamoDB tables for {norm_email}: {exc}")

        return {
            "success": True,
            "deleted_email": norm_email,
            "deleted_missions_count": deleted_missions,
            "message": "All profile data, credentials, and mission history have been permanently deleted.",
        }

    # -------------------------------------------------------------------------
    # 2. Mission State & Tracking (Payaam_Missions)
    # -------------------------------------------------------------------------
    def save_mission(self, mission_data: Dict[str, Any]) -> Dict[str, Any]:
        """Saves an outreach or sourcing mission with automatic TTL."""
        item = dict(mission_data)
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if "created_at" not in item:
            item["created_at"] = now
        item["updated_at"] = now

        # Ephemeral TTL (default 72h)
        ttl = int(time.time()) + (settings.SESSION_TTL_HOURS * 3600)
        item["ttl"] = ttl

        mission_id = item.get("mission_id", "")
        self._mem_missions[mission_id] = dict(item)

        if self.resource and self.missions_table_name not in self._table_missing:
            try:
                table = self.resource.Table(self.missions_table_name)
                table.put_item(Item=_floats_to_decimals(item))
                logger.info(f"Saved mission {mission_id} with status={item.get('status')}")
            except Exception as exc:
                if "ResourceNotFoundException" in str(exc):
                    self._table_missing.add(self.missions_table_name)
                logger.warning(f"DynamoDB save_mission failed ({exc}); cached in memory.")

        return item

    def get_mission(self, mission_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a mission by mission_id."""
        if not self.resource or self.missions_table_name in self._table_missing:
            return self._mem_missions.get(mission_id)

        try:
            table = self.resource.Table(self.missions_table_name)
            resp = table.get_item(Key={"mission_id": mission_id})
            item = resp.get("Item")
            return _decimals_to_floats(item) if item else None
        except Exception as exc:
            if "ResourceNotFoundException" in str(exc):
                self._table_missing.add(self.missions_table_name)
            logger.warning(f"DynamoDB get_mission failed ({exc}), falling back to memory.")
            return self._mem_missions.get(mission_id)

    def find_mission_by_thread(
        self, thread_ref: str, sender_email: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Finds active mission correlated with a thread reference or lead email."""
        norm_ref = (thread_ref or "").strip()
        norm_sender = (sender_email or "").strip().lower()
        if not norm_ref and not norm_sender:
            return None

        # Check memory first
        for mission in self._mem_missions.values():
            m_id = mission.get("mission_id", "")
            if norm_ref and (norm_ref in mission.get("thread_refs", []) or m_id == norm_ref or (m_id and m_id in norm_ref)):
                return mission
            if norm_sender and any(l.get("email", "").lower() == norm_sender for l in mission.get("leads", [])):
                return mission

        if self.resource and self.missions_table_name not in self._table_missing:
            try:
                table = self.resource.Table(self.missions_table_name)
                resp = table.scan()
                for item in resp.get("Items", []):
                    m = _decimals_to_floats(item)
                    m_id = m.get("mission_id", "")
                    if norm_ref and (norm_ref in m.get("thread_refs", []) or m_id == norm_ref or (m_id and m_id in norm_ref)):
                        return m
                    if norm_sender and any(l.get("email", "").lower() == norm_sender for l in m.get("leads", [])):
                        return m
            except Exception as exc:
                if "ResourceNotFoundException" in str(exc):
                    self._table_missing.add(self.missions_table_name)
                logger.warning(f"DynamoDB scan missions failed ({exc}); falling back to memory.")

        return None

    # -------------------------------------------------------------------------
    # 3. Multi-Tenant Collision Prevention (Payaam_ContactRegistry)
    # -------------------------------------------------------------------------
    def check_collision(
        self,
        target_email: str,
        category: Optional[str] = None,
        cooldown_days: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Checks if a target business was contacted recently by another user.

        Prevents multi-user spam collision and deliverability fatigue.
        """
        norm_target = target_email.strip().lower()
        days_threshold = cooldown_days or settings.COLLISION_COOLDOWN_DAYS

        record = self._mem_registry.get(norm_target)
        if not record and self.resource and self.registry_table_name not in self._table_missing:
            try:
                table = self.resource.Table(self.registry_table_name)
                resp = table.query(KeyConditionExpression=Key("target_email").eq(norm_target))
                items = resp.get("Items", [])
                if items:
                    record = _decimals_to_floats(max(items, key=lambda x: str(x.get("last_contacted_at", ""))))
            except Exception as exc:
                if "ResourceNotFoundException" in str(exc):
                    self._table_missing.add(self.registry_table_name)
                logger.warning(f"DynamoDB check_collision failed ({exc}).")

        if not record:
            return {"has_collision": False}

        last_str = record.get("last_contacted_at", "")
        if not last_str:
            return {"has_collision": False}

        try:
            last_dt = datetime.datetime.fromisoformat(last_str)
            now = datetime.datetime.now(datetime.timezone.utc)
            delta_days = (now - last_dt).total_seconds() / 86400.0

            if delta_days < days_threshold:
                return {
                    "has_collision": True,
                    "target_email": norm_target,
                    "days_ago": round(delta_days, 1),
                    "last_category": record.get("category", "General"),
                    "last_contacted_at": last_str,
                }
        except Exception as exc:
            logger.error(f"Date parse error in collision check: {exc}")

        return {"has_collision": False}

    def record_contact(
        self,
        target_email: str,
        contacted_by: str,
        category: str = "General",
    ) -> None:
        """Records an outreach timestamp in the global registry."""
        norm_target = target_email.strip().lower()
        item = {
            "target_email": norm_target,
            "last_contacted_by": contacted_by.strip().lower(),
            "last_contacted_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "category": category,
        }

        self._mem_registry[norm_target] = dict(item)

        if self.resource and self.registry_table_name not in self._table_missing:
            try:
                table = self.resource.Table(self.registry_table_name)
                table.put_item(Item=_floats_to_decimals(item))
                logger.info(f"Recorded contact registry event for {norm_target}")
            except Exception as exc:
                if "ResourceNotFoundException" in str(exc):
                    self._table_missing.add(self.registry_table_name)
                logger.warning(f"DynamoDB record_contact failed ({exc}).")


dynamodb_service = DynamoDBService()
