from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status, Depends
from pymongo.errors import DuplicateKeyError

from app.db import users_collection
from app.models import UserRegisterRequest, UserLoginRequest, UserResponse, TokenResponse
from app.auth import hash_password, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(request: UserRegisterRequest):
    users = users_collection()
    
    # Check if email is already taken
    existing_user = users.find_one({"email": request.email.lower()})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    new_user = {
        "name": request.name.strip(),
        "email": request.email.lower(),
        "password_hash": hash_password(request.password),
        "created_at": datetime.now(timezone.utc)
    }
    
    try:
        result = users.insert_one(new_user)
        return UserResponse(
            id=str(result.inserted_id),
            name=new_user["name"],
            email=new_user["email"],
            created_at=new_user["created_at"]
        )
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

@router.post("/login", response_model=TokenResponse)
def login(request: UserLoginRequest):
    users = users_collection()
    user = users.find_one({"email": request.email.lower()})
    if not user or not verify_password(request.password, user.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    token = create_access_token(data={"sub": str(user["_id"]), "email": user["email"]})
    return TokenResponse(access_token=token, token_type="bearer")

@router.get("/me", response_model=UserResponse)
def get_me(current_user: dict = Depends(get_current_user)):
    """Helper route to inspect the currently logged-in user profile."""
    return UserResponse(
        id=str(current_user["_id"]),
        name=current_user["name"],
        email=current_user["email"],
        created_at=current_user["created_at"]
    )
