# ============================================================================
# FILE: tenant_seeder.py
# PATH: backend/seeders/tenants/tenant_seeder.py
# PURPOSE: Seed / unseed the generic demo tenants, regulators, and their
#          role-based users.
#
# Seeding:
#   * creates each regulator document in Firestore regulators collection
#   * creates each tenant document in Firestore (idempotent, is_demo=True)
#     with regulator_id + country linking operators to their regulator
#   * creates each role-based user in Firebase Auth with role + tenant_id
#     claims and the deterministic password {role_token}_{shorthand}_2026
#
# Unseeding:
#   * removes every regulator EXCEPT protected_regulators
#   * removes every tenant EXCEPT protected_tenants
#   * removes every Auth user EXCEPT ezondiza.dhf@gmail.com (SUPER_ADMIN)
#
# Reference logic lives in backend/seed/seeder.py (seed) and
# backend/scripts/wipe_tenant_data.py (unseed).
# ============================================================================

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from seeders import BaseSeeder
from app.core.config import settings

SUPER_ADMIN_EMAIL = "ezondiza.dhf@gmail.com"
SUPER_ADMIN_UID = "hLXs4mvtf5bb1hRSifnh6HuUHpC2"

# Tenants that must NEVER be removed by unseed().
PROTECTED_TENANTS: List[str] = []

# Regulators that must NEVER be removed by unseed().
PROTECTED_REGULATORS: List[str] = []

TENANTS: List[Dict[str, Any]] = [
    {"id": "fixedwing", "name": "Fixed-Wing Operator", "shorthand": "fw", "classification": "AIRLINE_FIXED_WING", "regulator_id": "demostate", "country": "Nepal"},
    {"id": "rotarywing", "name": "Rotary-Wing Operator", "shorthand": "rw", "classification": "AIRLINE_ROTARY", "regulator_id": "demostate", "country": "Nepal"},
    {"id": "demoairport", "name": "Demo Airport", "shorthand": "ap", "classification": "AERODROME", "regulator_id": "demostate", "country": "Nepal"},
]

REGULATORS: List[Dict[str, Any]] = [
    {
        "id": "demostate",
        "name": "Demo State Regulator",
        "short_name": "DSR",
        "country_code": "NP",
        "country_name": "Nepal",
        "operator_tenant_ids": ["fixedwing", "rotarywing", "demoairport"],
        "status": "active",
        "is_demo": True,
    },
]

# role_token metadata: (role, full_name, department)
_USER_ROLE_META: Dict[str, Dict[str, str]] = {
    "ae": {"role": "AIRLINE_ADMIN", "full_name": "Accountable Executive", "department": "Executive"},
    "safety": {"role": "AIRLINE_ADMIN", "full_name": "Safety Manager", "department": "Safety"},
    "camo": {"role": "DEPT_ADMIN", "full_name": "CAMO Manager", "department": "CAMO"},
    "145": {"role": "DEPT_ADMIN", "full_name": "Part-145 Maintenance Manager", "department": "Part-145"},
    "ops": {"role": "DEPT_ADMIN", "full_name": "Operations Manager", "department": "Flight Operations"},
    "staff": {"role": "USER", "full_name": "Staff Member", "department": ""},
    "smd": {"role": "CAAN_SMD", "full_name": "State Regulator (SMD)", "department": ""},
}

USERS: Dict[str, List[Dict[str, str]]] = {
    "fixedwing": [
        {"email": "ae@fixedwing.test", "role": "AIRLINE_ADMIN", "department": "Executive"},
        {"email": "safety@fixedwing.test", "role": "AIRLINE_ADMIN", "department": "Safety"},
        {"email": "camo@fixedwing.test", "role": "DEPT_ADMIN", "department": "CAMO"},
        {"email": "145@fixedwing.test", "role": "DEPT_ADMIN", "department": "Part-145"},
        {"email": "ops@fixedwing.test", "role": "DEPT_ADMIN", "department": "Flight Operations"},
        {"email": "staff@fixedwing.test", "role": "USER", "department": ""},
    ],
    "rotarywing": [
        {"email": "ae@rotarywing.test", "role": "AIRLINE_ADMIN", "department": "Executive"},
        {"email": "safety@rotarywing.test", "role": "AIRLINE_ADMIN", "department": "Safety"},
        {"email": "camo@rotarywing.test", "role": "DEPT_ADMIN", "department": "CAMO"},
        {"email": "145@rotarywing.test", "role": "DEPT_ADMIN", "department": "Part-145"},
        {"email": "ops@rotarywing.test", "role": "DEPT_ADMIN", "department": "Flight Operations"},
        {"email": "staff@rotarywing.test", "role": "USER", "department": ""},
    ],
    "demoairport": [
        {"email": "ae@demoairport.test", "role": "AIRLINE_ADMIN", "department": "Executive"},
        {"email": "safety@demoairport.test", "role": "AIRLINE_ADMIN", "department": "Safety"},
        {"email": "ops@demoairport.test", "role": "DEPT_ADMIN", "department": "Flight Operations"},
        {"email": "staff@demoairport.test", "role": "USER", "department": ""},
    ],
}


def _role_token_for_email(email: str) -> str:
    """Derive the role token from the email local part (e.g. ae -->

    ae, 145 --> 145)."""
    return email.split("@")[0]


def _tenant_by_id(tenant_id: str) -> Optional[Dict[str, Any]]:
    for t in TENANTS:
        if t["id"] == tenant_id:
            return t
    return None


class TenantSeeder(BaseSeeder):
    """Seeds/unseeds demo tenants, regulators, and their role-based users."""

    def __init__(self, tenant_ids: Optional[List[str]] = None, dry_run: bool = False):
        super().__init__(tenant_ids=tenant_ids, dry_run=dry_run)
        self._db = None
        self._auth = None

    # ------------------------------------------------------------------
    # Firebase accessors (lazy so construction never needs credentials)
    # ------------------------------------------------------------------

    @property
    def db(self):
        if self._db is None:
            from app.firebase import get_db
            self._db = get_db()
        return self._db

    @property
    def auth(self):
        if self._auth is None:
            from app.firebase import get_auth
            self._auth = get_auth()
        return self._auth

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _generate_password(self, role_token: str, shorthand: str) -> str:
        return f"{role_token}_{shorthand}_2026"

    def _create_tenant_doc(self, tenant: Dict[str, Any]) -> bool:
        """Create a tenant document if it does not exist. Returns True if created."""
        tenant_id = tenant["id"]
        now = datetime.now(timezone.utc)
        ref = self.db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(tenant_id)

        if ref.get().exists:
            self.log_info(f"Tenant already exists, skipping: {tenant_id}")
            return False

        doc = {
            "name": tenant["name"],
            "type": tenant["classification"],
            "tenant_type": tenant["classification"],
            "classification": tenant["classification"],
            "shorthand": tenant["shorthand"],
            "category": "DEMO",
            "status": "ACTIVE",
            "active": True,
            "is_demo": True,
            "created_at": now,
            "updated_at": now,
            "seed_version": "2.4.0",
        }
        if tenant.get("regulator_id"):
            doc["regulator_id"] = tenant["regulator_id"]
        if tenant.get("country"):
            doc["country"] = tenant["country"]

        ref.set(doc)
        self.log_info(f"Created tenant: {tenant['name']} ({tenant_id})")
        return True

    def _create_regulator_doc(self, regulator: Dict[str, Any]) -> bool:
        """Create a regulator document if it does not exist. Returns True if created."""
        reg_id = regulator["id"]
        now = datetime.now(timezone.utc)
        ref = self.db.collection(settings.FIREBASE_COLLECTION_REGULATORS).document(reg_id)

        if ref.get().exists:
            self.log_info(f"Regulator already exists, skipping: {reg_id}")
            return False

        ref.set({
            "name": regulator["name"],
            "short_name": regulator.get("short_name", ""),
            "country_code": regulator.get("country_code", ""),
            "country_name": regulator.get("country_name", ""),
            "operator_tenant_ids": list(regulator.get("operator_tenant_ids", [])),
            "status": regulator.get("status", "active"),
            "is_demo": regulator.get("is_demo", True),
            "created_at": now,
            "updated_at": now,
            "seed_version": "2.4.0",
        })
        self.log_info(f"Created regulator: {regulator['name']} ({reg_id})")
        return True

    def _create_user(
        self,
        tenant: Dict[str, Any],
        tenant_id: str,
        email: str,
        role: str,
        department: str,
    ) -> bool:
        """Create an Auth user if it does not exist. Returns True if created."""
        role_token = _role_token_for_email(email)
        shorthand = tenant["shorthand"]
        password = self._generate_password(role_token, shorthand)
        uid = f"{role_token}-{tenant_id}-001"
        meta = _USER_ROLE_META.get(role_token, {})
        full_name = meta.get("full_name", email.split("@")[0])

        # Skip if already exists (by uid or email).
        if self._user_exists(uid, email):
            self.log_info(f"User already exists, skipping: {email}")
            return False

        try:
            record = self.auth.create_user(
                uid=uid,
                email=email,
                password=password,
                display_name=full_name,
                email_verified=True,
            )
        except self.auth.EmailAlreadyExistsError:
            record = self.auth.get_user_by_email(email)
            self.log_warning(f"Adopted existing account by email {email} (uid {record.uid})")

        claims = {"role": role, "tenant_id": tenant_id}
        if department:
            claims["department"] = department
        self.auth.set_custom_user_claims(record.uid, claims)

        self.log_info(f"Created user: {email} ({role}, tenant={tenant_id})")
        return True

    def _user_exists(self, uid: str, email: str) -> bool:
        try:
            self.auth.get_user(uid)
            return True
        except Exception:
            pass
        try:
            self.auth.get_user_by_email(email)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # BaseSeeder interface
    # ------------------------------------------------------------------

    def seed(self) -> Dict[str, Any]:
        """Create regulators, tenants, and users for all configured demo data."""
        self.created_count = 0
        self.skipped_count = 0
        self.errors = []

        # 1) Regulators first (tenants reference them)
        for reg in REGULATORS:
            reg_id = reg["id"]
            if self.dry_run:
                self.log_info(f"[dry-run] would create regulator {reg_id}")
                continue
            if self._create_regulator_doc(reg):
                self.created_count += 1
            else:
                self.skipped_count += 1

        # 2) Tenants + users
        target_ids = self._get_tenant_ids()
        for tenant in TENANTS:
            tenant_id = tenant["id"]
            if target_ids and tenant_id not in target_ids:
                continue
            if self.dry_run:
                self.log_info(f"[dry-run] would create tenant {tenant_id}")
                continue
            if self._create_tenant_doc(tenant):
                self.created_count += 1
            else:
                self.skipped_count += 1

            for user in USERS.get(tenant_id, []):
                if self.dry_run:
                    self.log_info(
                        f"[dry-run] would create user {user['email']} ({user['role']})"
                    )
                    continue
                if self._create_user(
                    tenant,
                    tenant_id,
                    user["email"],
                    user["role"],
                    user.get("department", ""),
                ):
                    self.created_count += 1
                else:
                    self.skipped_count += 1

        return self.get_summary()

    def _delete_user_except_super_admin(self) -> int:
        """Delete every Auth user except the Super Admin. Returns count removed."""
        removed = 0
        for record in self.auth.list_users().iterate_all():
            email = (record.email or "").lower()
            if email == SUPER_ADMIN_EMAIL.lower() or record.uid == SUPER_ADMIN_UID:
                self.log_info(f"Protected, skipping: {email}")
                continue
            if self.dry_run:
                self.log_info(f"[dry-run] would delete user {email}")
                removed += 1
                continue
            try:
                self.db.collection(settings.FIREBASE_COLLECTION_USERS).document(record.uid).delete()
            except Exception:
                pass
            try:
                self.auth.delete_user(record.uid)
            except Exception as e:
                self.log_error(f"Failed to delete user {email}: {e}")
                continue
            removed += 1
            self.log_info(f"Deleted user {email}")
        return removed

    def unseed(self) -> Dict[str, Any]:
        """Remove all tenants, regulators, and users except the Super Admin."""
        self.created_count = 0
        self.skipped_count = 0
        self.errors = []

        # 1) Tenants
        removed_tenants = 0
        target_ids = self._get_tenant_ids()
        for doc in self.db.collection(settings.FIREBASE_COLLECTION_TENANTS).stream():
            if doc.id in PROTECTED_TENANTS:
                self.log_info(f"Protected tenant, skipping: {doc.id}")
                continue
            if target_ids and doc.id not in target_ids:
                continue
            if self.dry_run:
                self.log_info(f"[dry-run] would delete tenant {doc.id}")
                removed_tenants += 1
                continue
            self._delete_doc_tree(doc.reference)
            doc.reference.delete()
            removed_tenants += 1
            self.log_info(f"Deleted tenant {doc.id}")

        # 2) Regulators
        removed_regulators = 0
        for doc in self.db.collection(settings.FIREBASE_COLLECTION_REGULATORS).stream():
            if doc.id in PROTECTED_REGULATORS:
                self.log_info(f"Protected regulator, skipping: {doc.id}")
                continue
            if target_ids and doc.id not in target_ids:
                continue
            if self.dry_run:
                self.log_info(f"[dry-run] would delete regulator {doc.id}")
                removed_regulators += 1
                continue
            doc.reference.delete()
            removed_regulators += 1
            self.log_info(f"Deleted regulator {doc.id}")

        self.created_count = removed_tenants + removed_regulators

        removed_users = self._delete_user_except_super_admin()
        self.skipped_count = removed_users  # tracked for reporting clarity

        return self.get_summary()

    def _delete_doc_tree(self, reference) -> int:
        removed = 0
        for coll in reference.collections():
            for sub in coll.stream():
                removed += self._delete_doc_tree(sub.reference)
                sub.reference.delete()
                removed += 1
        return removed


if __name__ == "__main__":
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "seed"
    dry_run = "--dry-run" in sys.argv
    seeder = TenantSeeder(dry_run=dry_run)
    result = seeder.seed() if mode == "seed" else seeder.unseed()
    print(result)
