from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError
import socketio
import os

# Core imports
import models, database

# Router imports
from routers import auth_router, requests_router, messages_router, admin_router, users_router


# ---------------------------
# Database Initialization
# ---------------------------
def initialize_database() -> None:
    try:
        models.Base.metadata.create_all(bind=database.engine)
    except SQLAlchemyError:
        database_url = os.getenv("DATABASE_URL", "<not set>")
        safe_target = database_url.split("@")[-1] if "@" in database_url else database_url
        raise RuntimeError(
            "Database initialization failed. Ensure PostgreSQL is running and "
            f"`DATABASE_URL` is correct. Current target: {safe_target}"
        ) from None


# ---------------------------
# Create FastAPI App
# ---------------------------
fastapi_app = FastAPI(title="AcadMate API")


# ---------------------------
# Startup Event
# ---------------------------
@fastapi_app.on_event("startup")
def startup_event():
    initialize_database()


# ---------------------------
# CORS Configuration
# ---------------------------
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------
# Uploads Directory Setup
# ---------------------------
if not os.path.exists("uploads"):
    os.makedirs("uploads")

fastapi_app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


# ---------------------------
# Include Routers
# ---------------------------
fastapi_app.include_router(auth_router.router, prefix="/api/v1/auth")
fastapi_app.include_router(users_router.router, prefix="/api/v1/users")
fastapi_app.include_router(requests_router.router, prefix="/api/v1")
fastapi_app.include_router(messages_router.router, prefix="/api/v1")
fastapi_app.include_router(admin_router.admin_router, prefix="/api/v1")


# ---------------------------
# Root Route
# ---------------------------
@fastapi_app.get("/")
def read_root():
    return {"message": "Welcome to AcadMate API", "status": "running"}


# ---------------------------
# Socket.IO Setup
# ---------------------------
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")

# Final ASGI app exposed to uvicorn
app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)


# ---------------------------
# Socket Events
# ---------------------------
@sio.event
async def join_room(sid, data):
    room = data["request_id"]
    await sio.enter_room(sid, str(room))


@sio.event
async def send_message(sid, data):
    db = database.SessionLocal()
    try:
        new_msg = models.Message(
            request_id=data["request_id"],
            sender_id=data["sender_id"],
            content=data["content"],
        )
        db.add(new_msg)
        db.commit()
    except Exception as e:
        print(f"Error saving message: {e}")
    finally:
        db.close()

    await sio.emit("new_message", data, room=str(data["request_id"]))
