# backend/config.py
from pydantic_settings import BaseSettings
from typing import List
import secrets
import os

class Settings(BaseSettings):
    """Application settings with environment variable support"""
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))
    SECURITY_MODE: str = os.getenv("SECURITY_MODE", "permissive")  # permissive, transitional, strict
    ALLOW_DEFAULT_ADMIN: bool = os.getenv("ALLOW_DEFAULT_ADMIN", "true").lower() == "true"
    
    # CORS
    CORS_ORIGINS: List[str] = os.getenv(
        "CORS_ORIGINS", 
        "http://localhost:3000,http://localhost:8000"
    ).split(",")
    CORS_ALLOW_ALL: bool = os.getenv("CORS_ALLOW_ALL", "true").lower() == "true"
    
    # Session
    SESSION_TIMEOUT_MINUTES: int = int(os.getenv("SESSION_TIMEOUT_MINUTES", "480"))  # 8 hours
    SESSION_ABSOLUTE_TIMEOUT_MINUTES: int = int(os.getenv("SESSION_ABSOLUTE_TIMEOUT_MINUTES", "1440"))  # 24 hours
    
    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
    
    # Email
    EMAIL_RETRY_ENABLED: bool = os.getenv("EMAIL_RETRY_ENABLED", "true").lower() == "true"
    
    # Audit Logging
    AUDIT_LOG_ENABLED: bool = os.getenv("AUDIT_LOG_ENABLED", "true").lower() == "true"
    
    # Admin Password Generation
    ADMIN_PASSWORD_MIN_LENGTH: int = 12
    ADMIN_DEFAULT_PASSWORD: str = os.getenv("ADMIN_DEFAULT_PASSWORD", "")  # Only used if ALLOW_DEFAULT_ADMIN=true
    
    class Config:
        env_file = ".env"
        case_sensitive = True

    def get_cors_origins(self) -> List[str]:
        """Get CORS origins based on mode"""
        if self.CORS_ALLOW_ALL:
            return ["*"]
        return self.CORS_ORIGINS
    
    def requires_auth(self) -> bool:
        """Check if authentication is required based on security mode"""
        return self.SECURITY_MODE in ["transitional", "strict"]
    
    def allows_default_admin(self) -> bool:
        """Check if default admin login is allowed"""
        return self.ALLOW_DEFAULT_ADMIN and self.SECURITY_MODE != "strict"


settings = Settings()
