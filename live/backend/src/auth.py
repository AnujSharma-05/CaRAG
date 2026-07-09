from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from jose import jwt, JWTError

from . import models, schemas, config
from .database import get_db

# 1. Create the router (this acts like a mini FastAPI app)
router = APIRouter(
    tags=["Authentication"] # Groups these neatly in Swagger UI
)

# --- Auth Configuration ---
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, config.JWT_SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# --- Middleware Dependency ---
async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, config.JWT_SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception
        
    return user


# --- Routes ---
# Notice we use @router instead of @app now.
# We also drop the "/auth" prefix here because we defined it in the router above.

@router.post("/register")
async def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(models.User).filter(models.User.email == user.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_pwd = pwd_context.hash(user.password)
    
    new_user = models.User(email=user.email, hashed_password=hashed_pwd)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {"message": "User created successfully", "user_id": new_user.id}


@router.post("/login", response_model=schemas.Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
        
    if not pwd_context.verify(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
        
    access_token = create_access_token(data={"sub": str(user.id)})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/mapping")
async def get_users_mapping(db: Session = Depends(get_db)):
    """
    Open endpoint to show the mapping of all users, their details, 
    and the groups they are involved in.
    """
    users = db.query(models.User).all()
    mapping = []
    for user in users:
        user_groups = db.query(models.Group).join(models.GroupMember).filter(
            models.GroupMember.user_id == user.id
        ).all()
        mapping.append({
            "user_id": user.id,
            "email": user.email,
            "groups": [{"group_id": g.id, "name": g.name} for g in user_groups]
        })
    return mapping


@router.post("/reset")
async def reset_live_db(db: Session = Depends(get_db)):
    """
    Reset endpoint that deletes all users, groups, and membership records,
    but keeps the ingested documents intact (clearing their group associations).
    """
    try:
        # 1. Clear group association on all documents so they aren't deleted by CASCADE
        db.query(models.Document).update({models.Document.group_id: None})
        db.commit()

        # 2. Delete all group members
        db.query(models.GroupMember).delete()
        db.commit()

        # 3. Delete all groups
        db.query(models.Group).delete()
        db.commit()

        # 4. Delete all users
        db.query(models.User).delete()
        db.commit()

        return {"message": "Live layer database reset successful. All users and groups deleted. Document files preserved with cleared group associations."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database reset failed: {str(e)}")
