# backend/config.py
from pydantic_settings import BaseSettings
from typing import List
import secrets
import os

class Settings(BaseSettings):
    """Application settings with environment variable support"""
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))
    SECURITY_MODE: str = "permissive"
    ALLOW_DEFAULT_ADMIN: bool = True
    
    # CORS - simplified parsing
    CORS_ORIGINS: str = "http://localhost:8000,http://localhost:3000"  # String, not List
    CORS_ALLOW_ALL: bool = True
    
    # Session
    SESSION_TIMEOUT_MINUTES: int = 480
    SESSION_ABSOLUTE_TIMEOUT_MINUTES: int = 1440
    
    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 60
    
    # Email
    EMAIL_RETRY_ENABLED: bool = True
    
    # Audit Logging
    AUDIT_LOG_ENABLED: bool = True
    
    # Admin Password Generation
    ADMIN_PASSWORD_MIN_LENGTH: int = 12
    ADMIN_DEFAULT_PASSWORD: str = ""
    
    class Config:
        env_file = ".env"
        case_sensitive = True

    def get_cors_origins(self) -> List[str]:
        """Get CORS origins based on mode"""
        if self.CORS_ALLOW_ALL:
            return ["*"]
        # Split the comma-separated string
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]
    
    def requires_auth(self) -> bool:
        """Check if authentication is required based on security mode"""
        return self.SECURITY_MODE in ["transitional", "strict"]
    
    def allows_default_admin(self) -> bool:
        """Check if default admin login is allowed"""
        return self.ALLOW_DEFAULT_ADMIN and self.SECURITY_MODE != "strict"


settings = Settings()
