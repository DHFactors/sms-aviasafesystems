from pathlib import Path
from dotenv import load_dotenv

from pydantic_settings import BaseSettings
from typing import List, Optional
from enum import Enum

# Ensure .env is loaded into os.environ regardless of pydantic-settings path resolution
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path, override=False)


class AuthRole(str, Enum):
    # Legacy tenant-admin role (kept for backward compatibility).
    AIRLINE_ADMIN = "AIRLINE_ADMIN"
    # Canonical tenant admin (Safety Manager); AIRLINE_ADMIN is its legacy alias.
    TENANT_ADMIN = "TENANT_ADMIN"
    # Department-scoped administrator (Head of Department).
    DEPT_ADMIN = "DEPT_ADMIN"
    # Operational safety review role (cross-department review within tenant).
    SAFETY_OFFICER = "SAFETY_OFFICER"
    # Legacy least-privilege member role.
    USER = "USER"
    # Canonical least-privilege member role; USER is its legacy alias.
    STAFF = "STAFF"
    CAAN_SMD = "CAAN_SMD"
    SUPER_ADMIN = "SUPER_ADMIN"


class Settings(BaseSettings):
    # ── API ──
    API_VERSION: str = "1.0.0"
    API_PREFIX_AUTH: str = "/api/v1/auth"
    API_PREFIX_REPORTS: str = "/api/v1/reports"
    API_PREFIX_DASHBOARD: str = "/api/v1/dashboard"
    API_PREFIX_ADMIN: str = "/api/v1/admin"
    API_PREFIX_HAZARDS: str = "/api/v1/hazards"
    API_PREFIX_CAN_CAP: str = "/api/v1/cans"
    API_PREFIX_VERIFICATION: str = "/api/v1/verification"
    API_PREFIX_REPORTING: str = "/api/v1/reporting"
    API_PREFIX_FLIGHT_DIVERSIONS: str = "/api/v1/flight-diversions"
    API_PREFIX_STATE_RISK: str = "/api/v1/state-risk"
    API_PREFIX_SURVEYS: str = "/api/v1/surveys"
    API_PREFIX_TENANTS: str = "/api/v1/tenants"
    API_PREFIX_REGULATORS: str = "/api/v1/regulators"
    API_PREFIX_CONTACT: str = "/api/v1/contact"
    API_PREFIX_FEEDBACK: str = "/api/v1/feedback"
    API_PREFIX_COPILOT: str = "/api/v1/copilot"
    API_PREFIX_PSOE: str = "/api/v1/psoe"
    API_PREFIX_AUTH_LEGACY: str = "/api/auth"
    API_PREFIX_REPORTS_LEGACY: str = "/api/reports"
    API_PREFIX_DASHBOARD_LEGACY: str = "/api/dashboard"
    API_PREFIX_ADMIN_LEGACY: str = "/api/admin"
    API_PREFIX_HAZARDS_LEGACY: str = "/api/hazards"
    API_PREFIX_CAN_CAP_LEGACY: str = "/api/cans"
    API_PREFIX_VERIFICATION_LEGACY: str = "/api/verification"
    API_PREFIX_REPORTING_LEGACY: str = "/api/reporting"
    API_PREFIX_FLIGHT_DIVERSIONS_LEGACY: str = "/api/flight-diversions"
    API_PREFIX_STATE_RISK_LEGACY: str = "/api/state-risk"
    API_PREFIX_SURVEYS_LEGACY: str = "/api/surveys"
    API_PREFIX_TENANTS_LEGACY: str = "/api/tenants"
    API_PREFIX_PSOE_LEGACY: str = "/api/psoe"
    DEBUG: bool = False
    # Deployment environment: "production" (default), "beta", "staging",
    # "development". Drives self-service registration gating (production
    # requires the enterprise access key / admin invite code) and beta sandbox
    # tagging (is_beta_sandbox + auto_expire_days on self-service tenants).
    ENVIRONMENT: str = "production"

    # ── CORS ──
    # Single-canonical-domain origin list (betasms.* decommissioned 2026-08).
    ALLOWED_ORIGINS: str = "https://sms.aviasafesystems.com,https://aerosafety-sms-prod.web.app,https://aerosafety-sms-beta.web.app,https://sms-beta.web.app,http://localhost:3000,http://localhost:8000,http://localhost:5000,http://localhost:5005,http://127.0.0.1:5005,http://127.0.0.1:5500"
    # When set, takes precedence over ALLOWED_ORIGINS (Render-env friendly).
    CORS_ORIGINS: Optional[str] = None

    # ── PostgreSQL ──
    # asyncpg-compatible connection URL. Production points at the Supabase
    # TRANSACTION pooler (PgBouncer, host *.pooler.supabase.com, port 6543)
    # so bursty Render instances do not overwhelm the free-tier connection
    # budget. sslmode=require / pgbouncer hints are normalised by
    # app/db/session.py.
    # Empty by default so the app boots on Firestore-only deployments; the async
    # SQLAlchemy engine is created lazily in app/db/session.py.
    DATABASE_URL: Optional[str] = None

    # ── Firebase ──
    FIREBASE_PROJECT_ID: Optional[str] = None
    FIREBASE_PRIVATE_KEY: Optional[str] = None
    FIREBASE_CLIENT_EMAIL: Optional[str] = None
    FIREBASE_DATABASE_ID: str = "sms-db"
    # Public Firebase Web API key used by the server-side login endpoint
    # (app/services/login_service.py) to verify credentials against the
    # Identity Toolkit REST API. It is the same public key shipped in
    # public/js/firebase.js — not a secret — but is configurable here for
    # non-default projects.
    FIREBASE_WEB_API_KEY: str = "AIzaSyCdCtUuyOcUIoCBEaiWGbhp6_XwZKHsicc"
    FIREBASE_COLLECTION_TENANTS: str = "tenants"
    FIREBASE_COLLECTION_REPORTS: str = "reports"
    FIREBASE_COLLECTION_METADATA: str = "metadata"
    FIREBASE_COLLECTION_USERS: str = "users"
    FIREBASE_COLLECTION_REGULATORS: str = "regulators"
    FIREBASE_COLLECTION_AUDIT_LOGS: str = "audit_logs"
    FIREBASE_DOCUMENT_INFO: str = "info"
    FIREBASE_TOKEN_URI: str = "https://oauth2.googleapis.com/token"

    # ── JWT ──
    JWT_ALGORITHM: str = "RS256"
    JWT_EXPIRES_IN: int = 3600

    # ── AI / Gemini ──
    AI_MODEL: str = "gemini-2.0-pro-exp-02-05"
    AI_PROMPT_VERSION: str = "2.0"
    AI_NARRATIVE_TRUNCATE: int = 5000
    AI_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None

    # ── AI / Groq Copilot ──
    # Groq API key for the Safety & Compliance Copilot chat assistant. When
    # unset the chat endpoint degrades to a helpful offline response (200).
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    GROQ_MAX_TOKENS: int = 900
    GROQ_TEMPERATURE: float = 0.4

    # ── Repository / Pagination ──
    REPO_CACHE_TTL_SECONDS: int = 60
    REPO_DEFAULT_PAGE_SIZE: int = 20
    REPO_MAX_PAGE_SIZE: int = 100
    REPO_QUERY_LIMIT: int = 5000

    # ── Dashboard defaults ──
    DASHBOARD_DEFAULT_DAYS: int = 90
    DASHBOARD_TREND_DAYS: int = 180
    DASHBOARD_RECENT_PAGE_SIZE: int = 10
    DASHBOARD_ADMIN_USAGE_DAYS: int = 30
    DASHBOARD_ADMIN_SYSTEM_DAYS: int = 7
    DASHBOARD_ADMIN_TENANT_DAYS: int = 30

    # ── Roles ──
    ROLE_DEFAULT: str = "USER"
    ROLE_DEFAULT_REGISTRATION: str = "AIRLINE_ADMIN"
    CROSS_TENANT_ROLES: List[str] = ["CAAN_SMD", "SUPER_ADMIN"]
    SUPER_ADMIN_ROLES: List[str] = ["SUPER_ADMIN"]
    # Canonical role constants for the delegated admin hierarchy.
    ROLE_TENANT_ADMIN: str = "TENANT_ADMIN"
    ROLE_DEPT_ADMIN: str = "DEPT_ADMIN"
    ROLE_SAFETY_OFFICER: str = "SAFETY_OFFICER"
    ROLE_STAFF: str = "STAFF"
    # Role-alias groups so existing AIRLINE_ADMIN/USER checks recognize the new
    # canonical names (TENANT_ADMIN == AIRLINE_ADMIN, STAFF == USER).
    TENANT_ADMIN_ROLES: List[str] = ["AIRLINE_ADMIN", "TENANT_ADMIN"]
    DEPT_ADMIN_ROLES: List[str] = ["DEPT_ADMIN"]
    SAFETY_OFFICER_ROLES: List[str] = ["SAFETY_OFFICER"]
    STAFF_ROLES: List[str] = ["USER", "STAFF"]
    # Roles permitted to act across the whole tenant (tenant admins + cross-tenant).
    TENANT_WIDE_ROLES: List[str] = ["AIRLINE_ADMIN", "TENANT_ADMIN", "CAAN_SMD", "SUPER_ADMIN"]

    # ── Upstash Redis (enabled when REDIS_URL is non-empty) ──
    REDIS_URL: str = ""
    REDIS_ENABLED: bool = True

    # ── Rate limiting ──
    RATE_LIMIT_PER_MINUTE: int = 60
    # Per-tenant daily survey submission cap (configurable per deployment).
    SURVEY_RATE_LIMIT: int = 5

    # ── Admin security (env-only; RC-1) ──
    # Setup key used as a second factor on admin provisioning endpoints. Never
    # hardcoded; must be provided via the environment. Access is never granted
    # by the key alone — a SUPER_ADMIN Firebase ID token is always required.
    SETUP_SECRET: Optional[str] = None
    # Shared secret for internal scheduled tasks (e.g. the Cloud Scheduler job
    # that runs the overdue/escalation check). Sent as the X-Task-Key header.
    TASK_API_KEY: Optional[str] = None
    # Password used by /provision-airlines. No hardcoded fallback.
    DEFAULT_PROVISION_PASSWORD: Optional[str] = None
    # Password used by the seed data pipeline (backend/seed). No hardcoded fallback.
    DEFAULT_SEED_PASSWORD: Optional[str] = None
    # When True (default), data-destructive endpoints (/seed-demo-data,
    # /create-seed-users) return 404. Disable only in non-production environments.
    DISABLE_DESTRUCTIVE_ENDPOINTS: bool = True

    # ── Self-service onboarding ──
    # Access key required for public tenant registration on the beta portal.
    # A blank / missing field on the form falls back to this default; a
    # provided key must match exactly.
    BETA_ACCESS_KEY: str = "AVIASAFE-BETA-2026"

    # ── Tenant credentials / welcome email ──
    # Provider: none (log + preview only), smtp, or sendgrid.
    EMAIL_PROVIDER: str = "none"
    EMAIL_FROM: Optional[str] = None
    EMAIL_FROM_NAME: str = "AviaSAFE SMS Team"
    APP_LOGIN_URL: str = "https://sms.aviasafesystems.com"
    APP_SUPPORT_EMAIL: str = "info@aviasafesystems.com"
    SENDGRID_API_KEY: Optional[str] = None
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASS: Optional[str] = None

    # ── Gmail REST API dispatcher (registration intake acknowledgments) ──
    # Dedicated Gmail channel used by app/services/gmail_dispatcher.py to send
    # self-service registration acknowledgments over HTTPS (port 443) via the
    # Gmail REST API with an OAuth2 refresh-token flow. Leave
    # GMAIL_CLIENT_ID / GMAIL_REFRESH_TOKEN empty to skip delivery (the
    # acknowledgment is logged only and the provisioned tenant record is never
    # rolled back).
    GMAIL_CLIENT_ID: Optional[str] = None
    GMAIL_CLIENT_SECRET: Optional[str] = None
    GMAIL_REFRESH_TOKEN: Optional[str] = None
    GMAIL_SENDER_EMAIL: Optional[str] = None
    GMAIL_NOTIFICATION_BCC: Optional[str] = None

    # ── Contact form / Sender.net ──
    # Sender.net REST API v2. The key must be set via the environment (Render
    # dashboard); never commit the key to the repository.
    SENDER_API_KEY: Optional[str] = None
    # Email the contact form submissions are associated with.
    SENDER_FROM_EMAIL: str = "info@aviasafesystems.com"
    # Optional Sender list/group id to add contacts to. Empty = account default.
    SENDER_LIST_ID: Optional[str] = None
    SENDER_API_BASE_URL: str = "https://api.sender.net/v2"

    # ── Server ──
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 1

    model_config = {"env_file": "backend/.env", "env_file_encoding": "utf-8", "case_sensitive": True, "extra": "ignore"}


settings = Settings()
