# MeterMind AI Backend 🧠⚡

**MeterMind AI** is a usage-based AI billing platform prototype developed for the PayPal Hackathon. It enables AI service providers to track token usage, aggregate unbilled requests, generate invoices, and process payments via the PayPal REST API.

---

## 🛠 Tech Stack

- **Runtime & Framework:** Python 3.11+, [FastAPI](https://fastapi.tiangolo.com/), [Uvicorn](https://www.uvicorn.org/)
- **Database:** [MongoDB](https://www.mongodb.com/) via [PyMongo](https://pymongo.readthedocs.io/)
- **Authentication & Security:** Salty `bcrypt` password hashing, `python-jose` signed JWT Bearer tokens
- **Pricing Engine:** High-precision Python `Decimal` with `ROUND_HALF_UP` (zero float drift)
- **External API:** [httpx](https://www.python-httpx.org/) for PayPal REST API v2 (Orders & OAuth2)
- **Validation:** [Pydantic v2](https://docs.pydantic.dev/) & [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- **Testing:** [pytest](https://docs.pytest.org/), [mongomock](https://github.com/mongomock/mongomock)

---

## 📁 Directory Structure

```text
backend/
├── app/
│   ├── main.py              # FastAPI application, CORS (http://localhost:5173), lifespan DB setup
│   ├── config.py            # Pydantic Settings & environment variables
│   ├── db.py                # PyMongo client, collection handlers, indexes
│   ├── auth.py              # bcrypt, JWT tokens, get_current_user dependency
│   ├── models.py            # Pydantic request/response schemas
│   ├── billing.py           # Pure Decimal pricing engine & rate configuration
│   ├── paypal.py            # PayPal REST client (OAuth2 cache, create-order, capture)
│   └── routers/
│       ├── auth.py          # /auth/register, /auth/login, /auth/me
│       ├── usage.py         # /usage/track, /usage/history
│       ├── billing.py       # /billing/summary
│       ├── invoices.py      # /invoices/generate, /invoices
│       └── payments.py      # /payments/create-order, /payments/capture
├── scripts/
│   ├── seed.py              # Demo user + 30 days of simulated AI usage
│   └── verify_step1_to_3.py # Live integration verification script
├── tests/
│   ├── test_auth.py         # Registration, login, invalid credentials
│   ├── test_usage.py        # Token calculation, idempotency deduplication, history
│   ├── test_billing.py      # Decimal math, invoice generation, user isolation
│   └── test_payments.py     # PayPal order creation, mocked capture, duplicate prevention
├── requirements.txt         # Pinned backend dependencies
├── .env.example             # Environment variable template
└── README.md
```

---

## 🚀 Quickstart & Setup

### 1. Environment Configuration

Copy `.env.example` to `.env`:
```powershell
cp .env.example .env
```

Variables in `.env`:
```ini
MONGO_URI=mongodb://localhost:27017
DB_NAME=metermind
JWT_SECRET=super-secret-jwt-token-change-in-production-123456789
JWT_EXPIRE_MINUTES=1440
PAYPAL_CLIENT_ID=your_paypal_client_id_here
PAYPAL_CLIENT_SECRET=your_paypal_client_secret_here
PAYPAL_BASE_URL=https://api-m.sandbox.paypal.com
```

### 2. Install Dependencies

Activate your Python virtual environment and install dependencies:
```powershell
cd D:\projects\paypal\backend
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Seed Demo Data

Run the seed script to create a demo account with 30 days of realistic usage history and past paid invoices:
```powershell
python scripts/seed.py
```
**Demo Credentials created:**
- **Email:** `demo@metermind.ai`
- **Password:** `metermind123`

### 4. Run Development Server

```powershell
uvicorn app.main:app --reload
```
The server will start on **[http://127.0.0.1:8000](http://127.0.0.1:8000)** with hot reloading enabled.

---

## 📖 Interactive API Documentation

FastAPI auto-generates interactive Swagger UI and OpenAPI documentation:
- **Swagger UI:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc:** [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## 🔌 API Endpoints Summary

### Authentication (`/auth`)
| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `POST` | `/auth/register` | Register user (`name`, `email`, `password`) | No |
| `POST` | `/auth/login` | Login and obtain JWT `{ access_token, token_type }` | No |
| `GET` | `/auth/me` | Fetch authenticated user profile | Bearer JWT |

### Usage Tracking (`/usage`)
| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `POST` | `/usage/track` | Ingest AI usage (`service_name`, `request_count`, `input_tokens`, `output_tokens`, `idempotency_key`). Computes `total_tokens` server-side. Idempotency key deduplication prevents double counts. | Bearer JWT |
| `GET` | `/usage/history` | Historical usage records sorted newest first. Supports `start_date`, `end_date`, `limit`, `skip`. | Bearer JWT |

### Billing & Invoices (`/billing`, `/invoices`)
| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `GET` | `/billing/summary` | Aggregates unbilled usage (`total_requests`, `total_tokens`, `unbilled_usage`, `current_bill`). | Bearer JWT |
| `POST` | `/invoices/generate` | Atomically transitions unbilled records to `"billed"`, assigns `invoice_id`, and creates a `"pending"` invoice. Refuses with `400` if no unbilled usage. | Bearer JWT |
| `GET` | `/invoices` | Lists all invoices belonging to current user. | Bearer JWT |

### Payments (`/payments`)
| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `POST` | `/payments/create-order` | Takes `invoice_id`, verifies ownership and pending status, fetches invoice amount from DB, and creates PayPal order returning `order_id` & `approval_url`. | Bearer JWT |
| `POST` | `/payments/capture` | Takes `order_id`, captures via PayPal, validates status is `COMPLETED` and amount matches invoice. Stores payment in `payments` collection and sets invoice to `"paid"`. Idempotent: safe against double captures. | Bearer JWT |

---

## 🧮 Billing Engine Logic

Defined in [`app/billing.py`](file:///d:/projects/paypal/backend/app/billing.py):
$$\text{Bill} = \left(\frac{\text{total\_requests}}{100}\right) \times \$1.00\text{ USD}$$
- Computed using standard `decimal.Decimal` with `ROUND_HALF_UP` to 2 decimal places.
- Rates stored in a configurable dictionary `PRICING_CONFIG` to easily accommodate tiered pricing in the future.

---

## 🔒 Security & Data Integrity

1. **Strict User Scoping:** Every query and modification is filtered by `current_user["id"]`. Attempts to access or pay for other users' records return `403 Forbidden` or `404 Not Found`.
2. **Server-Enforced Pricing:** Orders are priced strictly from the database invoice, preventing client-side price tampering.
3. **Idempotency Protection:**
   - Sparse unique DB index on `idempotency_key` in `usage_records`.
   - Unique DB index on `paypal_order_id` in `payments`. Capturing twice never executes duplicate PayPal transactions or state mutations.
4. **Credential Safety:** PayPal client secrets and tokens remain server-side only and are never exposed in logs or client responses.

---

## 🧪 Running Automated Tests

Run the full pytest suite:
```powershell
cd D:\projects\paypal\backend
.\.venv\Scripts\pytest.exe tests -v
```
All tests run with isolated mock databases (`mongomock`) and mocked PayPal REST calls (`httpx`).
