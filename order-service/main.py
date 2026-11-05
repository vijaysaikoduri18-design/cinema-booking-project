import os
from datetime import datetime, timezone
from decimal import Decimal

import httpx
import jwt
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import JSON, DateTime, Numeric, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

DATABASE_URL = os.environ["DATABASE_URL"]
JWT_SECRET = os.environ["JWT_SECRET"]
PRODUCT_URL = os.environ["PRODUCT_SERVICE_URL"].rstrip("/")   # e.g. http://127.0.0.1:8082
INTERNAL_KEY = os.environ["INTERNAL_KEY"]
engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int]
    show_id: Mapped[int]
    movie_title: Mapped[str] = mapped_column(String(200))
    seats: Mapped[list] = mapped_column(JSON)
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    status: Mapped[str] = mapped_column(String(20), default="CONFIRMED")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


Base.metadata.create_all(engine)
app = FastAPI(title="Order Service")
product = httpx.Client(base_url=PRODUCT_URL, timeout=5, headers={"x-internal-key": INTERNAL_KEY})


def get_db():
    with Session(engine) as db:
        yield db


def current_user(authorization: str = Header(default="")):
    try:
        return jwt.decode(authorization.removeprefix("Bearer "), JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or missing token")


def order_out(o: Order):
    return {"id": o.id, "user_id": o.user_id, "show_id": o.show_id, "movie_title": o.movie_title,
            "seats": o.seats, "total": float(o.total), "status": o.status,
            "created_at": o.created_at.isoformat() + "Z"}


class BookIn(BaseModel):
    showId: int
    seats: list[str]


@app.get("/health")
def health():
    return {"status": "UP"}


@app.post("/", status_code=201)
def book(body: BookIn, user: dict = Depends(current_user), db: Session = Depends(get_db)):
    if not body.seats:
        raise HTTPException(400, "seats[] required")
    try:
        r = product.get(f"/shows/{body.showId}")
        if r.status_code != 200:
            raise HTTPException(404, "Show not found")
        show = r.json()
        if datetime.fromisoformat(show["starts_at"].replace("Z", "+00:00")) < datetime.now(timezone.utc):
            raise HTTPException(400, "Show already started")
        r = product.post(f"/shows/{body.showId}/reserve", json={"seats": body.seats})
    except httpx.HTTPError:
        raise HTTPException(503, "Product service unavailable")
    if r.status_code != 200:
        raise HTTPException(r.status_code, r.json().get("detail", "Reservation failed"))

    seats = r.json()["reserved"]
    try:
        order = Order(user_id=user["id"], show_id=body.showId, movie_title=show["title"],
                      seats=seats, total=Decimal(str(show["price"])) * len(seats))
        db.add(order)
        db.commit()
    except Exception:
        db.rollback()
        product.post(f"/shows/{body.showId}/release", json={"seats": seats})  # compensate
        raise HTTPException(500, "Booking failed")
    return order_out(order)


@app.get("/")
def my_orders(user: dict = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Order).where(Order.user_id == user["id"]).order_by(Order.id.desc())
    return [order_out(o) for o in db.scalars(q)]


@app.delete("/{order_id}")
def cancel(order_id: int, user: dict = Depends(current_user), db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order or order.user_id != user["id"] or order.status != "CONFIRMED":
        raise HTTPException(404, "Active booking not found")
    order.status = "CANCELLED"
    db.commit()
    try:
        product.post(f"/shows/{order.show_id}/release", json={"seats": order.seats})
    except httpx.HTTPError:
        pass  # seats stay held; a cleanup job can reconcile CANCELLED orders
    return order_out(order)
