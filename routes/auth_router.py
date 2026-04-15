from fastapi import APIRouter, HTTPException, Depends, status
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
def login_json(payload: LoginRequest):

    user = authenticate_user(payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = generate_token_for_user(user)
    return {"access_token": token, "token_type": "bearer"}

@router.post("/login-form", response_model=TokenResponse)
def login_form(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = generate_token_for_user(user)
    return {"access_token": token, "token_type": "bearer"}

@router.get("/me", response_model=UserResponse)
def get_me(current_user: dict = Depends(get_current_user)):
    return user_to_response(current_user)