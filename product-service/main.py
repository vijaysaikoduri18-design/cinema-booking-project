import hmac
import os
import re
from datetime import datetime, timezone
from typing import Optional

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, create_engine, delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

DATABASE_URL = os.environ["DATABASE_URL"]
JWT_SECRET = os.environ["JWT_SECRET"]
INTERNAL_KEY = os.environ["INTERNAL_KEY"]
engine = create_engine(DATABASE_URL, pool_pre_ping=True)


class Base(DeclarativeBase):
    pass


class Movie(Base):
    __tablename__ = "movies"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_min: Mapped[Optional[int]] = mapped_column(nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    poster_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)


class Show(Base):
    __tablename__ = "shows"
    id: Mapped[int] = mapped_column(primary_key=True)
    movie_id: Mapped[int] = mapped_column(ForeignKey("movies.id"))
    screen: Mapped[str] = mapped_column(String(50), default="Screen 1")
    starts_at: Mapped[datetime] = mapped_column(DateTime)  # stored as naive UTC
    price: Mapped[float] = mapped_column(Numeric(8, 2))
    seat_rows: Mapped[int] = mapped_column(default=8)
    seats_per_row: Mapped[int] = mapped_column(default=10)


class ShowSeat(Base):
    """Primary key (show_id, seat) is what makes double-booking impossible."""
    __tablename__ = "show_seats"
    show_id: Mapped[int] = mapped_column(ForeignKey("shows.id"), primary_key=True)
    seat: Mapped[str] = mapped_column(String(5), primary_key=True)


Base.metadata.create_all(engine)
app = FastAPI(title="Product Service")


def get_db():
    with Session(engine) as db:
        yield db


def admin_only(authorization: str = Header(default="")):
    try:
        claims = jwt.decode(authorization.removeprefix("Bearer "), JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or missing token")
    if claims.get("role") != "admin":
        raise HTTPException(403, "Admin only")


def internal_only(x_internal_key: str = Header(default="")):
    if not hmac.compare_digest(x_internal_key, INTERNAL_KEY):
        raise HTTPException(403, "Forbidden")


def to_utc_naive(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def movie_out(m: Movie):
    return {"id": m.id, "title": m.title, "description": m.description,
            "duration_min": m.duration_min, "language": m.language, "poster_url": m.poster_url}


def show_out(s: Show, title: str):
    return {"id": s.id, "movie_id": s.movie_id, "title": title, "screen": s.screen,
            "starts_at": s.starts_at.isoformat() + "Z", "price": float(s.price),
            "seat_rows": s.seat_rows, "seats_per_row": s.seats_per_row}


class MovieIn(BaseModel):
    title: str
    description: Optional[str] = None
    duration_min: Optional[int] = None
    language: Optional[str] = None
    poster_url: Optional[str] = None


class ShowIn(BaseModel):
    movie_id: int
    starts_at: datetime
    price: float
    screen: str = "Screen 1"
    seat_rows: int = 8
    seats_per_row: int = 10


class SeatsIn(BaseModel):
    seats: list[str]


@app.get("/health")
def health():
    return {"status": "UP"}


# ---------- Movies ----------
@app.get("/movies")
def list_movies(db: Session = Depends(get_db)):
    return [movie_out(m) for m in db.scalars(select(Movie).order_by(Movie.id.desc()))]


@app.get("/movies/{movie_id}")
def get_movie(movie_id: int, db: Session = Depends(get_db)):
    m = db.get(Movie, movie_id)
    if not m:
        raise HTTPException(404, "Movie not found")
    return movie_out(m)


@app.post("/movies", status_code=201, dependencies=[Depends(admin_only)])
def add_movie(body: MovieIn, db: Session = Depends(get_db)):
    m = Movie(**body.model_dump())
    db.add(m)
    db.commit()
    return movie_out(m)


# ---------- Shows ----------
@app.get("/shows")
def list_shows(movieId: Optional[int] = None, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    q = select(Show, Movie.title).join(Movie, Movie.id == Show.movie_id).where(Show.starts_at > now)
    if movieId:
        q = q.where(Show.movie_id == movieId)
    return [show_out(s, t) for s, t in db.execute(q.order_by(Show.starts_at))]


@app.get("/shows/{show_id}")
def get_show(show_id: int, db: Session = Depends(get_db)):
    show = db.get(Show, show_id)
    if not show:
        raise HTTPException(404, "Show not found")
    movie = db.get(Movie, show.movie_id)
    booked = db.scalars(select(ShowSeat.seat).where(ShowSeat.show_id == show_id)).all()
    return {**show_out(show, movie.title), "booked_seats": sorted(booked)}


@app.post("/shows", status_code=201, dependencies=[Depends(admin_only)])
def add_show(body: ShowIn, db: Session = Depends(get_db)):
    if not db.get(Movie, body.movie_id):
        raise HTTPException(404, "Movie not found")
    s = Show(movie_id=body.movie_id, screen=body.screen, starts_at=to_utc_naive(body.starts_at),
             price=body.price, seat_rows=body.seat_rows, seats_per_row=body.seats_per_row)
    db.add(s)
    db.commit()
    return show_out(s, db.get(Movie, s.movie_id).title)


# ---------- Internal: called by order-service only ----------
def valid_seat(seat: str, show: Show) -> bool:
    m = re.fullmatch(r"([A-Z])(\d{1,2})", seat)
    return bool(m) and ord(m[1]) - 64 <= show.seat_rows and 1 <= int(m[2]) <= show.seats_per_row


@app.post("/shows/{show_id}/reserve", dependencies=[Depends(internal_only)])
def reserve(show_id: int, body: SeatsIn, db: Session = Depends(get_db)):
    show = db.get(Show, show_id)
    if not show:
        raise HTTPException(404, "Show not found")
    seats = sorted(set(body.seats))
    if not seats or not all(valid_seat(s, show) for s in seats):
        raise HTTPException(400, "Invalid seat(s)")
    db.add_all([ShowSeat(show_id=show_id, seat=s) for s in seats])
    try:
        db.commit()  # all-or-nothing: any taken seat violates the primary key
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Some seats already booked")
    return {"reserved": seats}


@app.post("/shows/{show_id}/release", dependencies=[Depends(internal_only)])
def release(show_id: int, body: SeatsIn, db: Session = Depends(get_db)):
    db.execute(delete(ShowSeat).where(ShowSeat.show_id == show_id, ShowSeat.seat.in_(body.seats)))
    db.commit()
    return {"released": body.seats}
