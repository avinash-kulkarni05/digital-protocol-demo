"""
Authentication router for backend_vNext.

Simple JWT-based authentication for demo purposes.
Default credentials: demo@saama.com / demo123
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
import jwt

logger = logging.getLogger(__name__)

router = APIRouter()

# Simple JWT configuration
JWT_SECRET = "saama-protocol-digitalization-demo-secret-key-2024"
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# Saama domain authentication
SAAMA_PASSWORD = "$@@m@2025d$p"
SAAMA_DOMAIN = "@saama.com"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    token: str
    user: dict


class TokenRefreshResponse(BaseModel):
    token: str


def create_jwt_token(user_id: str, email: str, name: str) -> str:
    """Create a JWT token for authenticated user."""
    payload = {
        "sub": user_id,
        "email": email,
        "name": name,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_jwt_token(token: str) -> Optional[dict]:
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    Authenticate user and return JWT token.

    Valid credentials:
    - Any email ending with @saama.com
    - Password: $@@m@2025d$p
    """
    email = request.email.lower()

    # Check if email is from Saama domain
    if not email.endswith(SAAMA_DOMAIN):
        logger.warning(f"Login attempt from non-Saama domain: {email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Check password
    if request.password != SAAMA_PASSWORD:
        logger.warning(f"Invalid password for user: {email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Generate user info from email
    username = email.split("@")[0]
    # Convert username to display name (e.g., john.doe -> John Doe)
    display_name = " ".join(word.capitalize() for word in username.replace(".", " ").replace("_", " ").split())
    user_id = f"user-{hash(email) % 100000:05d}"

    # Create token
    token = create_jwt_token(user_id, email, display_name)

    logger.info(f"User logged in: {email}")

    return LoginResponse(
        token=token,
        user={
            "id": user_id,
            "email": email,
            "name": display_name,
        }
    )


@router.post("/logout")
async def logout():
    """
    Logout user (client-side token removal).

    Note: In a production system, you might want to blacklist the token.
    """
    return {"message": "Logged out successfully"}


@router.post("/refresh", response_model=TokenRefreshResponse)
async def refresh_token():
    """
    Refresh JWT token.

    Note: In production, this should validate the existing token from the Authorization header.
    For demo purposes, this is a simplified implementation.
    """
    # In production, validate existing token and issue a new one
    # For demo, we'll just return an error suggesting to login again
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Please login again to refresh your session",
    )
