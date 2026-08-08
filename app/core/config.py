"""CortexCloud Optimization Network — settings.

Environment names for everything the running service depends on are
kept byte-for-byte identical to the pre-refactor .env (POSTGRES_*,
WALLET_ADDRESS*, CDP_*, X402_*), so production keeps working without
editing .env. Provider/registry/Redis/JWT settings are gone; anything
left over in .env is ignored (extra='ignore').
"""
import os
from typing import Any, List, Optional
from pydantic import BeforeValidator, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Annotated


def parse_cors(v: Any) -> List[str]:
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",")]
    elif isinstance(v, (list, str)):
        return v
    raise ValueError(v)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    ENV: str = Field(default="development", env="ENV")
    PROJECT_NAME: str = "CortexCloud Optimization Network"
    API_V1_STR: str = "/v1"

    # PostgreSQL
    POSTGRES_HOST: str = Field(default="localhost", env="POSTGRES_HOST")
    POSTGRES_PORT: int = Field(default=5432, env="POSTGRES_PORT")
    POSTGRES_USER: str = Field(default="postgres", env="POSTGRES_USER")
    POSTGRES_PASSWORD: str = Field(default="postgres", env="POSTGRES_PASSWORD")
    POSTGRES_DB: str = Field(default="cortexcloud", env="POSTGRES_DB")
    DATABASE_URL: Optional[str] = Field(default=None, env="DATABASE_URL")

    # CORS
    BACKEND_CORS_ORIGINS: Annotated[List[str], BeforeValidator(parse_cors)] = ["*"]

    # x402 payment configuration (env names unchanged from the original)
    X402_ENABLED: bool = Field(default=True, env="X402_ENABLED")
    WALLET_ADDRESS: Optional[str] = Field(default=None, env="WALLET_ADDRESS")
    WALLET_ADDRESS_2: Optional[str] = Field(default=None, env="WALLET_ADDRESS_2")
    CDP_WALLET_SECRET: Optional[str] = Field(default=None, env="CDP_WALLET_SECRET")
    X402_FACILITATOR_URL: str = Field(
        default="https://api.cdp.coinbase.com/platform/v2/x402", env="X402_FACILITATOR_URL"
    )
    X402_FACILITATOR_API_KEY_ID: Optional[str] = Field(default=None, env="X402_FACILITATOR_API_KEY_ID")
    X402_FACILITATOR_API_KEY_SECRET: Optional[str] = Field(default=None, env="X402_FACILITATOR_API_KEY_SECRET")
    X402_NETWORK: str = Field(default="eip155:8453", env="X402_NETWORK")
    X402_RATE_LIMIT: int = Field(default=60, env="X402_RATE_LIMIT")
    X402_RESOURCE_BASE: str = Field(default="https://api.cortexcloud.org", env="X402_RESOURCE_BASE")

    # Optimization engine
    MAX_OPTIMIZE_VARS: int = Field(default=5000, env="MAX_OPTIMIZE_VARS")
    QAOA_LOCAL_MAX_N: int = Field(default=12, env="QAOA_LOCAL_MAX_N")

    # Origin Quantum (optional; adapter only activates when both set)
    ORIGINQ_API_TOKEN: Optional[str] = Field(default=None, env="ORIGINQ_API_TOKEN")
    ORIGINQ_BACKEND: Optional[str] = Field(default=None, env="ORIGINQ_BACKEND")

    # Amazon Braket (optional multi-provider quantum). Live QPU execution
    # is opt-in: solve() refuses while QUANTUM_LIVE_EXECUTION=false
    # (credential + capability checks are still reported honestly).
    QUANTUM_LIVE_EXECUTION: bool = Field(default=False, env="QUANTUM_LIVE_EXECUTION")
    BRAKET_REGIONS: str = Field(default="us-east-1,us-west-1", env="BRAKET_REGIONS")
    AWS_ACCESS_KEY_ID: Optional[str] = Field(default=None, env="AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY: Optional[str] = Field(default=None, env="AWS_SECRET_ACCESS_KEY")

    # Gate for /internal/metrics (revenue aggregates). Leave unset to
    # disable the endpoint entirely — never expose money figures publicly.
    INTERNAL_TOKEN: Optional[str] = Field(default=None, env="INTERNAL_TOKEN")

    @model_validator(mode="after")
    def enforce_secrets_in_production(self) -> "Settings":
        """Fail fast: never boot prod without real payment credentials."""
        if self.ENV == "development":
            return self
        if not self.DATABASE_URL and self.POSTGRES_PASSWORD in (None, "", "postgres"):
            raise ValueError("[S7] ENV=production requires a real POSTGRES_PASSWORD.")
        critical = [
            "WALLET_ADDRESS", "CDP_WALLET_SECRET",
            "X402_FACILITATOR_API_KEY_ID", "X402_FACILITATOR_API_KEY_SECRET",
        ]
        for var in critical:
            if getattr(self, var, None) in (None, ""):
                raise ValueError(f"[S7] ENV=production requires {var} in environment.")
        return self

    @model_validator(mode="after")
    def assemble_db_connection(self) -> "Settings":
        if not self.DATABASE_URL:
            self.DATABASE_URL = (
                f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )
        return self


settings = Settings()
