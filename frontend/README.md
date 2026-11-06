# MeterMind AI Frontend 🧠⚡💳

> Modern, usage-based AI billing platform dashboard developed for the **PayPal Hackathon**.  
> Designed to pair seamlessly with the **MeterMind AI FastAPI Backend** (`http://localhost:8000`).

---

## 🌟 Overview

**MeterMind AI Frontend** is a full-featured dashboard for AI service providers (LLM wrappers, agent platforms, SaaS APIs) to:
- 📊 **Track Real-Time Token & Request Ingestion**: Test live payload ingestion for models like GPT-4o, Claude 3.5 Sonnet, Gemini 1.5 Pro, and Llama 3.1 70B.
- 🛡️ **Verify Idempotency Deduplication**: Test replay requests with identical keys to verify database-level protection against double-billing.
- 🧮 **Inspect Zero-Drift Decimal Billing**: Real-time formula visualization: $\text{Bill} = \left(\frac{\text{Requests}}{100}\right) \times 1.00\text{ USD}$.
- 🧾 **Generate Invoices**: Atomically transition unbilled usage records into certified pending invoices.
- 💳 **PayPal REST API v2 Settlements**: Create PayPal orders (`/payments/create-order`) and execute idempotent captures (`/payments/capture`) with immediate receipt generation and confetti celebration.
- 🔄 **Dual Operational Mode**: Connects directly to the live FastAPI backend, with a zero-setup **Standalone Demo/Mock Simulator** toggle for instant hackathon evaluation without spinning up local databases.

---

## 🛠 Tech Stack

| Layer | Technology |
|---|---|
| **Framework** | React 19 + TypeScript |
| **Bundler & Dev Server** | [Vite 8](https://vitejs.dev/) (Runs on `http://localhost:5173` matching backend CORS) |
| **Styling & Design** | [Tailwind CSS v3](https://tailwindcss.com/) with custom dark neon glassmorphism |
| **Icons** | [Lucide React](https://lucide.dev/) |
| **Data Visualization** | [Recharts](https://recharts.org/) (Real-time velocity and token area charts) |
| **Effects** | Canvas Confetti (Checkout celebration) |
| **API Client** | Typed Fetch Client with JWT Bearer Token injection & auto-retry |

---

## 📁 Directory Structure

```text
frontend/
├── src/
│   ├── api/
│   │   ├── client.ts             # API Client, JWT auth headers & health check
│   │   ├── auth.ts               # /auth/login, /auth/register, /auth/me
│   │   ├── usage.ts              # /usage/track, /usage/history
│   │   ├── billing.ts            # /billing/summary
│   │   ├── invoices.ts           # /invoices/generate, /invoices
│   │   └── payments.ts           # /payments/create-order, /payments/capture
│   ├── components/
│   │   ├── Navbar.tsx            # Header, live status pill, mode switcher
│   │   ├── MetricCard.tsx        # Glowing KPI metric cards
│   │   ├── UsageChart.tsx        # Recharts token ingestion velocity chart
│   │   ├── UsageSimulator.tsx    # Interactive API tester & batch generator
│   │   ├── UsageHistoryTable.tsx # Paginated & filterable usage feed
│   │   ├── InvoiceList.tsx       # Invoice settlements table
│   │   ├── PayPalModal.tsx       # PayPal REST API v2 checkout dialog
│   │   └── ApiSettingsModal.tsx  # API Base URL & JWT inspection modal
│   ├── context/
│   │   ├── AuthContext.tsx       # JWT state, demo user quick login
│   │   └── ToastContext.tsx      # Custom toast notification system
│   ├── pages/
│   │   ├── Dashboard.tsx         # Overview, KPI metrics & engine math
│   │   ├── UsagePage.tsx         # Ingestion playground & historical feed
│   │   ├── InvoicesPage.tsx      # Invoices & PayPal settlements
│   │   └── LoginPage.tsx         # Provider authentication & demo 1-click login
│   ├── types/
│   │   └── index.ts              # Full TypeScript models & response interfaces
│   ├── utils/
│   │   ├── formatters.ts         # Currency, date, and number formatters
│   │   └── mockData.ts           # 30-day realistic seed data for standalone mode
│   ├── App.tsx                   # Main router & layout shell
│   ├── main.tsx                  # Root entrypoint
│   └── index.css                 # Custom glassmorphism, glowing gradients & fonts
├── index.html                    # HTML shell
├── tailwind.config.js            # Tailwind custom brand & paypal colors
├── tsconfig.json                 # TypeScript project configuration
├── package.json                  # Pinned dependencies
├── .env.example                  # Environment configuration template
└── README.md                     # Documentation
```

---

## 🚀 Quickstart & Setup

### 1. Prerequisites
- **Node.js** v18+ or v20+ (`node -v`)
- **npm** or **pnpm** / **yarn**

### 2. Installation
```bash
# Navigate to the frontend directory
cd frontend

# Install dependencies
npm install
```

### 3. Environment Configuration
Create a `.env` file (copied from `.env.example`):
```bash
cp .env.example .env
```

Default content:
```env
VITE_API_BASE_URL=http://localhost:8000
```

### 4. Run Development Server
```bash
npm run dev
```
The application will launch on **`http://localhost:5173`** (the exact origin configured in FastAPI backend CORS).

---

## 🔑 Demo Credentials

To test immediately, click **"Sign in as Demo User"** on the login screen, or use the pre-seeded credentials matching `scripts/seed.py`:

- **Email**: `demo@metermind.ai`
- **Password**: `metermind123`

---

## 🔌 Backend API Integration

The frontend maps directly to the FastAPI backend endpoints:

| Feature | Backend Endpoint | Method | Role in Frontend |
|---|---|:---:|---|
| **Authentication** | `/auth/login` | `POST` | Authenticates and persists JWT Bearer token |
| **Profile** | `/auth/me` | `GET` | Fetches active user name, email, and ID |
| **Usage Tracking** | `/usage/track` | `POST` | Dispatches model token usage with UUID idempotency key |
| **Usage History** | `/usage/history` | `GET` | Populates the live historical audit feed |
| **Billing Summary** | `/billing/summary` | `GET` | Computes unbilled requests and current accrued bill |
| **Invoicing** | `/invoices/generate` | `POST` | Atomically transitions unbilled requests to a pending invoice |
| **Invoices List** | `/invoices` | `GET` | Displays all historical and pending invoices |
| **Create PayPal Order** | `/payments/create-order` | `POST` | Locks invoice amount and generates PayPal `order_id` & `approval_url` |
| **Capture PayPal Order** | `/payments/capture` | `POST` | Reconciles captured funds and marks invoice as `paid` |

---

## 📦 How to Push this Frontend to GitHub

You can push this frontend either as its own repository or inside your project repository.

### Option A: Create a Standalone Frontend GitHub Repo
```bash
cd frontend

# Initialize Git
git init

# Add all files
git add .

# Initial commit
git commit -m "feat: complete MeterMind AI usage billing frontend with PayPal REST integration"

# Set main branch
git branch -M main

# Link to your new GitHub repository
git remote add origin https://github.com/<YOUR-USERNAME>/metermind-frontend.git

# Push
git push -u origin main
```

### Option B: Monorepo alongside `backend/`
If you already have a repository with `backend/`:
```bash
# In the parent project root:
# Root
# ├── backend/
# └── frontend/

git add frontend
git commit -m "feat: add MeterMind AI frontend dashboard"
git push origin main
```

---

## 🏆 Hackathon Highlights
- **1-Click Live Replay Attack Testing**: In the Ingestion Playground, click *"Test Replay Attack / Double Click"* to demonstrate the backend's unique MongoDB index on `idempotency_key` rejecting duplicate billings.
- **Pure Decimal Precision**: Displays real-time dollar accrued amounts calculated on Python's `decimal.Decimal` engine with `ROUND_HALF_UP`.
- **Integrated PayPal Experience**: Supports direct redirect to PayPal Sandbox Checkout and instant capture reconciliation.
