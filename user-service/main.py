import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import DateTime, String, create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

DATABASE_URL = os.environ["DATABASE_URL"]
JWT_SECRET = os.environ["JWT_SECRET"]
engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


Base.metadata.create_all(engine)
app = FastAPI(title="User Service")


def get_db():
    with Session(engine) as db:
        yield db


def current_user(authorization: str = Header(default="")):
    try:
        return jwt.decode(authorization.removeprefix("Bearer "), JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or missing token")


class RegisterIn(BaseModel):
    name: str
    email: str
    password: str


class LoginIn(BaseModel):
    email: str
    password: str


@app.get("/health")
def health():
    return {"status": "UP"}


@app.post("/register", status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    hashed = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
    user = User(name=body.name, email=body.email.lower(), password_hash=hashed)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Email already registered")
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role}


@app.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not bcrypt.checkpw(body.password.encode(), user.password_hash.encode()):
        raise HTTPException(401, "Invalid credentials")
    token = jwt.encode(
        {"id": user.id, "email": user.email, "role": user.role,
         "exp": datetime.now(timezone.utc) + timedelta(hours=8)},
        JWT_SECRET, algorithm="HS256")
    return {"token": token}


@app.get("/me")
def me(claims: dict = Depends(current_user), db: Session = Depends(get_db)):
    user = db.get(User, claims["id"])
    if not user:
        raise HTTPException(404, "Not found")
    return {"id": user.id, "name": user.name, "email": user.email,
            "role": user.role, "created_at": user.created_at.isoformat()}
