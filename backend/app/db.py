from pymongo import MongoClient, ASCENDING, DESCENDING
from app.config import settings
import logging

logger = logging.getLogger("metermind.db")

class Database:
    client: MongoClient = None
    db = None

db_instance = Database()

def get_client() -> MongoClient:
    if db_instance.client is None:
        db_instance.client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=5000)
        db_instance.db = db_instance.client[settings.DB_NAME]
    return db_instance.client

def get_db():
    if db_instance.db is None:
        get_client()
    return db_instance.db

def users_collection():
    return get_db()["users"]

def usage_records_collection():
    return get_db()["usage_records"]

def invoices_collection():
    return get_db()["invoices"]

def payments_collection():
    return get_db()["payments"]

def init_db():
    """Ensure all required collections and indexes exist."""
    try:
        db = get_db()
        # Users indexes
        db["users"].create_index("email", unique=True)

        # Usage records indexes
        db["usage_records"].create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
        db["usage_records"].create_index("idempotency_key", unique=True, sparse=True)
        db["usage_records"].create_index([("user_id", ASCENDING), ("status", ASCENDING)])

        # Invoices indexes
        db["invoices"].create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])

        # Payments indexes
        db["payments"].create_index("paypal_order_id", unique=True)
        db["payments"].create_index("invoice_id")
        logger.info("Database indexes successfully initialized.")
    except Exception as e:
        logger.warning(f"Database index initialization encountered an issue: {e}")
