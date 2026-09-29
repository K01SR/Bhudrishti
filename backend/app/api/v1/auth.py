from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    verify_password,
    create_access_token,
    get_current_user_payload,
    TokenPayload,
    RoleEnum,
)
from app.models.user import User
from app.schemas.auth_schema import TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["Authentication & RBAC"])

# Demo password for the in-memory evaluation accounts. Real users come from DB.
DEMO_PASSWORD = getattr(settings, "DEMO_PASSWORD", "demo@2026") or "demo@2026"

# In-memory demo credentials for instant zero-friction evaluation
DEMO_USERS = {
    "state.admin": {
        "id": "usr-state-admin",
        "username": "state.admin",
        "full_name": "Demo Reviewer A (prototype account, not a real official)",
        "role_name": RoleEnum.STATE_ADMIN,
        "email": "reviewer.a@example.invalid",
        "jurisdiction_id": None,
    },
    "district.admin": {
        "id": "usr-district-admin",
        "username": "district.admin",
        "full_name": "Demo Reviewer B (prototype account, not a real official)",
        "role_name": RoleEnum.DISTRICT_VERIFIER,
        "email": "reviewer.b@example.invalid",
        "jurisdiction_id": "jur-airoli-sec08",
    },
    "taluka.verifier": {
        "id": "usr-taluka-verifier",
        "username": "taluka.verifier",
        "full_name": "Demo Reviewer C (prototype account, not a surveyor)",
        "role_name": RoleEnum.TALUKA_VERIFIER,
        "email": "reviewer.c@example.invalid",
        "jurisdiction_id": "jur-airoli-sec08",
    },
    "builder.demo": {
        "id": "usr-builder-demo",
        "username": "builder.demo",
        "full_name": "Apex InfraProjects Ltd (Registered Builder)",
        "role_name": RoleEnum.BUILDER,
        "email": "submissions@apexinfra.in",
        "jurisdiction_id": "jur-airoli-sec08",
    },
    "citizen.demo": {
        "id": "usr-citizen-demo",
        "username": "citizen.demo",
        "full_name": "Karan Malhotra (Property Buyer / Flat Owner)",
        "role_name": RoleEnum.CITIZEN,
        "email": "karan.malhotra@gmail.com",
        "jurisdiction_id": "jur-airoli-sec08",
    },
}


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    username = form_data.username.strip()

    # Check demo users (password enforced, not any-password)
    if username in DEMO_USERS:
        if form_data.password != DEMO_PASSWORD:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect password for demo account.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        u_info = DEMO_USERS[username]
        access_token = create_access_token(
            subject=u_info["id"],
            role=u_info["role_name"],
            jurisdiction_id=u_info["jurisdiction_id"],
        )
        user_resp = UserResponse(
            id=u_info["id"],
            username=u_info["username"],
            email=u_info["email"],
            full_name=u_info["full_name"],
            role_name=u_info["role_name"],
            jurisdiction_id=u_info["jurisdiction_id"],
            is_active=True,
        )
        return TokenResponse(access_token=access_token, user=user_resp)

    # Check database
    stmt = select(User).where(User.username == username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password. You can use demo accounts: state.admin, district.admin, taluka.verifier, builder.demo, citizen.demo",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        subject=user.id,
        role=user.role_name,
        jurisdiction_id=user.jurisdiction_id,
    )
    return TokenResponse(
        access_token=access_token,
        user=UserResponse.from_orm(user),
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: TokenPayload = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db),
):
    # Check if demo user
    for u_info in DEMO_USERS.values():
        if u_info["id"] == current_user.sub:
            return UserResponse(**u_info, is_active=True)

    if current_user.role == RoleEnum.PUBLIC:
        return UserResponse(
            id="public-anonymous",
            username="public",
            email="public@example.invalid",
            full_name="Public Citizen (Unauthenticated Guest)",
            role_name=RoleEnum.PUBLIC,
            jurisdiction_id=None,
            is_active=True,
        )

    stmt = select(User).where(User.id == current_user.sub)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse.from_orm(user)


@router.get("/demo-accounts")
def get_demo_accounts():
    """Returns list of pre-configured demo roles and accounts."""
    return [
        {
            "role": u["role_name"],
            "username": u["username"],
            "full_name": u["full_name"],
            "description": f"Role account for {u['role_name']}",
            "password": DEMO_PASSWORD,
        }
        for u in DEMO_USERS.values()
    ]
