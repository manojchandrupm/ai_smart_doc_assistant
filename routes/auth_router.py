from fastapi import APIRouter, HTTPException, Depends, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from models.auth_models import RegisterRequest, TokenResponse, UserResponse, LoginRequest
from services.auth_service import (
    get_user_by_email,
    create_user,
    authenticate_user,
    generate_token_for_user,
    user_to_response
)
from core.dependencies import get_current_user
from fastapi.responses import RedirectResponse
from services.google_oauth_service import (
    get_google_auth_url,
    exchange_code_for_token,
    get_google_user_info
)
from services.auth_service import get_or_create_google_user
from core.rate_limiter import limiter

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=UserResponse)
def register_user(payload: RegisterRequest):
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    existing_user = get_user_by_email(payload.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = create_user(payload.email, payload.password)
    return user_to_response(user)

@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
def login_json(request: Request, payload: LoginRequest):
    user = authenticate_user(payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = generate_token_for_user(user)
    return {"access_token": token, "token_type": "bearer"}

@router.post("/login-form", response_model=TokenResponse)
@limiter.limit("5/minute")
def login_form(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = generate_token_for_user(user)
    return {"access_token": token, "token_type": "bearer"}

@router.get("/me", response_model=UserResponse)
def get_me(current_user: dict = Depends(get_current_user)):
    return user_to_response(current_user)


@router.get("/google/login")
def google_login():
    """Redirects the user to Google's OAuth consent screen."""
    url = get_google_auth_url()
    return RedirectResponse(url)

@router.get("/google/callback")
async def google_callback(code: str):
    """
    Google redirects here after user grants access.
    We exchange the code for a token, fetch user info,
    create/find the user in MongoDB, and return our own JWT.
    """
    try:
        token_data   = await exchange_code_for_token(code)
        access_token = token_data["access_token"]
        user_info    = await get_google_user_info(access_token)
        email     = user_info["email"]
        name      = user_info.get("name", "")
        google_id = user_info["id"]
        user = get_or_create_google_user(email=email, name=name, google_id=google_id)
        jwt_token = generate_token_for_user(user)
        # Redirect to frontend with token in query param
        # The frontend will read this and store it in localStorage
        return RedirectResponse(f"/?token={jwt_token}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Google OAuth failed: {str(e)}")