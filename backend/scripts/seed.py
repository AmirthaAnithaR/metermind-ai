import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
import random

# Add project root to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.config import settings
from app.db import (
    init_db,
    users_collection,
    usage_records_collection,
    invoices_collection,
    payments_collection
)
from app.auth import hash_password
from app.billing import calculate_bill

SERVICES = [
    {"name": "gpt-4o", "weight": 40, "in_range": (800, 3000), "out_range": (200, 1000)},
    {"name": "claude-3-5-sonnet", "weight": 30, "in_range": (1000, 4000), "out_range": (300, 1500)},
    {"name": "gemini-1.5-pro", "weight": 15, "in_range": (500, 2500), "out_range": (150, 800)},
    {"name": "deepseek-chat", "weight": 10, "in_range": (400, 2000), "out_range": (100, 600)},
    {"name": "text-embedding-3-small", "weight": 5, "in_range": (100, 1000), "out_range": (0, 0)},
]

DEMO_USER_EMAIL = "demo@metermind.ai"
DEMO_USER_PASSWORD = "metermind123"

def seed():
    print("==================================================")
    print("[*] MeterMind AI - Seeding Database")
    print(f"[*] MongoDB URI: {settings.MONGO_URI}")
    print(f"[*] Database:    {settings.DB_NAME}")
    print("==================================================")

    init_db()
    users_col = users_collection()
    usage_col = usage_records_collection()
    invoices_col = invoices_collection()
    payments_col = payments_collection()

    # 1. Create or Reset Demo User
    existing_user = users_col.find_one({"email": DEMO_USER_EMAIL})
    if existing_user:
        user_id = str(existing_user["_id"])
        print(f"[*] Demo user already exists ({DEMO_USER_EMAIL}). Cleaning up previous demo data...")
        usage_col.delete_many({"user_id": user_id})
        invoices_col.delete_many({"user_id": user_id})
        payments_col.delete_many({"user_id": user_id})
    else:
        new_user = {
            "name": "MeterMind Demo",
            "email": DEMO_USER_EMAIL,
            "password_hash": hash_password(DEMO_USER_PASSWORD),
            "created_at": datetime.now(timezone.utc) - timedelta(days=35)
        }
        res = users_col.insert_one(new_user)
        user_id = str(res.inserted_id)
        print(f"[+] Created demo user: {DEMO_USER_EMAIL} (ID: {user_id})")

    now = datetime.now(timezone.utc)
    seeded_records = []
    
    # 2. Generate 30 days of usage
    # Days 30 down to 8: Past billed usage with a closed invoice
    # Days 7 down to 0 (today): Unbilled usage ready for testing
    print("[*] Generating 30 days of simulated AI usage...")
    
    past_billed_records = []
    unbilled_records = []

    for day_offset in range(30, -1, -1):
        day_date = now - timedelta(days=day_offset)
        # 2 to 5 usage events per day
        events_count = random.randint(2, 5)
        for event_idx in range(events_count):
            service = random.choices(
                SERVICES,
                weights=[s["weight"] for s in SERVICES]
            )[0]

            req_count = random.randint(5, 35)
            input_tokens = random.randint(*service["in_range"]) * req_count
            output_tokens = random.randint(*service["out_range"]) * req_count
            total_tokens = input_tokens + output_tokens

            record_time = day_date + timedelta(
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59)
            )

            is_billed = day_offset > 7

            doc = {
                "user_id": user_id,
                "service_name": service["name"],
                "request_count": req_count,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "status": "billed" if is_billed else "unbilled",
                "invoice_id": None,
                "created_at": record_time
            }

            if is_billed:
                past_billed_records.append(doc)
            else:
                unbilled_records.append(doc)

    # 3. Create a historic paid invoice for past records (>7 days ago)
    if past_billed_records:
        billed_res = usage_col.insert_many(past_billed_records)
        past_record_ids = billed_res.inserted_ids

        total_past_requests = sum(d["request_count"] for d in past_billed_records)
        total_past_tokens = sum(d["total_tokens"] for d in past_billed_records)
        past_amount = float(calculate_bill(total_past_requests))

        historic_invoice = {
            "user_id": user_id,
            "total_requests": total_past_requests,
            "total_tokens": total_past_tokens,
            "amount": past_amount,
            "currency": "USD",
            "status": "paid",
            "created_at": now - timedelta(days=7, hours=2)
        }
        inv_res = invoices_col.insert_one(historic_invoice)
        historic_invoice_id = str(inv_res.inserted_id)

        # Link past usage to historic invoice
        usage_col.update_many(
            {"_id": {"$in": past_record_ids}},
            {"$set": {"invoice_id": historic_invoice_id}}
        )

        # Create historic payment record
        historic_payment = {
            "user_id": user_id,
            "invoice_id": historic_invoice_id,
            "paypal_order_id": f"PAYPAL-SEED-HISTORIC-{historic_invoice_id[:8]}",
            "transaction_id": f"TXN-SEED-{random.randint(100000, 999999)}",
            "amount": past_amount,
            "currency": "USD",
            "payment_status": "COMPLETED",
            "created_at": now - timedelta(days=7, hours=1)
        }
        payments_col.insert_one(historic_payment)
        print(f"[+] Created historic paid invoice #{historic_invoice_id} (${past_amount:.2f} USD)")

    # 4. Insert unbilled records (last 7 days)
    if unbilled_records:
        usage_col.insert_many(unbilled_records)
        unbilled_reqs = sum(d["request_count"] for d in unbilled_records)
        unbilled_tokens = sum(d["total_tokens"] for d in unbilled_records)
        unbilled_bill = float(calculate_bill(unbilled_reqs))

        print(f"[+] Inserted {len(unbilled_records)} unbilled usage events for the last 7 days:")
        print(f"    - Requests:     {unbilled_reqs}")
        print(f"    - Total Tokens: {unbilled_tokens:,}")
        print(f"    - Ready to Bill: ${unbilled_bill:.2f} USD")

    total_records = len(past_billed_records) + len(unbilled_records)
    print("\n==================================================")
    print("[PASS] DATABASE SEEDING COMPLETE")
    print(f"[*] Total usage records generated: {total_records}")
    print(f"[*] Demo User Credentials:")
    print(f"    Email:    {DEMO_USER_EMAIL}")
    print(f"    Password: {DEMO_USER_PASSWORD}")
    print("==================================================")

if __name__ == "__main__":
    seed()
