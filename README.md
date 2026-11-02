# SpendSense

SpendSense is a local-first personal finance tracker for Indian **UPI and credit-card PDF statements**. It extracts transactions from statements, categorizes spending with a hybrid rules + LLM pipeline, lets you correct mistakes, and turns the resulting data into month-wise analytics and Excel reports.

The project is designed around a simple workflow:

**Upload statements → classify transactions → review/correct → analyze by month → export reports**

## Features

### Statement parsing

- Upload one or more PDF statements from the browser.
- Automatic source detection for UPI vs credit-card statements.
- Dedicated Google Pay parser for GPay transaction-statement PDFs.
- Dedicated ICICI credit-card parsing path.
- Generic table/line parser as a fallback for other statement layouts.
- Duplicate detection makes repeated monthly imports safer.
- Google Pay UPI Lite top-ups are ignored as spending so wallet funding is not double-counted.
- Self-transfers remain identifiable instead of being mixed into normal spending.

### Hybrid transaction categorization

SpendSense does not send every transaction directly to an LLM. Classification follows this order:

1. **Personal merchant mappings** — corrections you made earlier are reused first.
2. **Deterministic merchant rules** — obvious merchants such as Swiggy, Zomato, Jubilant Foodworks, VENDX, Amazon, Blinkit, pharmacies, travel services, salons, etc. are handled without an LLM.
3. **LLM cache** — previously classified unknown merchants can reuse a cached result.
4. **Gemini/OpenAI fallback** — genuinely unclear merchants are sent to the configured LLM.
5. **Others** — used only when the transaction still cannot be classified confidently.

The current local setup is optimized for **Gemini 3.5 Flash-Lite** because merchant categorization is a lightweight classification task and benefits from low latency.

For ambiguous UPI payments to personal names, the classifier can also use limited transaction context such as amount, payment source, and time as supporting clues. Manual corrections always take priority over future automatic classification.

### Categories

Current categories include:

- Food & Dining
- Groceries
- Travel
- Salon & Personal Care
- Shopping
- Amazon
- Entertainment
- Utilities & Bills
- Rent / Housing
- Health
- Education
- Credit Card / EMI
- Transfers (Self / Family)
- Income
- Others

### Review & learning

The **Review & correct** page lets you:

- inspect parsed transactions;
- filter transactions;
- manually change a category;
- save merchant mappings automatically from corrections;
- propagate a correction to matching merchant transactions;
- reclassify existing non-manually-corrected transactions after improving rules or enabling an LLM;
- see whether the LLM fallback is active and view classification errors when an API call fails.

### Dashboard

The dashboard is month-driven rather than all-time-only.

- Select any imported month to inspect it.
- View monthly spending totals and credited income.
- View **net transfers** separately from spending.
- See the full monthly spending trend across imported months.
- View category split and category spending for the selected month.

Transfers are treated as balance movement rather than spending/income:

```text
Net transfers = transfers sent - transfers received
```

For example, sending ₹500 and receiving ₹200 as self/family transfers produces **₹300 net transfers**. Transfer transactions are excluded from normal `Spent` and `Credited` totals.

### Excel reports

Excel exports are generated as actual financial reports rather than raw transaction dumps.

Available report periods:

- selected dashboard month;
- current month;
- previous month;
- last 6 months;
- last 12 months;
- custom date range.

The workbook includes:

- an Overview sheet with report-period KPIs;
- period-specific category totals;
- top merchants;
- a labeled top-spending-categories chart;
- monthly summaries where relevant;
- a Categories sheet;
- a supporting Transactions sheet.

All category and merchant totals in the workbook are calculated only for the selected export period.

## Tech stack

### Backend

- FastAPI
- SQLAlchemy
- SQLite
- Pydantic / pydantic-settings
- pdfplumber
- RapidFuzz
- httpx
- openpyxl
- bcrypt + JWT authentication

### Frontend

- React
- Vite
- React Router
- Recharts

## Project structure

```text
SpendSense/
├── backend/
│   ├── app/
│   │   ├── routers/
│   │   ├── services/
│   │   │   ├── classifier.py
│   │   │   ├── llm_transport.py
│   │   │   ├── normalize.py
│   │   │   ├── pdf_parser.py
│   │   │   └── reports.py
│   │   ├── auth.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── main.py
│   │   └── models.py
│   ├── .env.example
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   ├── api.js
│   │   └── App.jsx
│   └── package.json
├── run-dev.ps1
└── README.md
```

## Run locally

### Prerequisites

- Python
- Node.js + npm
- Git

### 1. Clone the repository

```powershell
git clone https://github.com/RohitSuhasReddy/SpendSense.git
cd SpendSense
```

### 2. Set up the backend

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Edit `backend/.env` and configure at least a proper local secret:

```env
SECRET_KEY=replace-with-a-long-random-string
DATABASE_URL=sqlite:///./data/spendsense.db
CORS_ORIGINS=http://localhost:5173

GEMINI_API_KEY=
OPENAI_API_KEY=
LLM_PROVIDER=gemini
GEMINI_MODEL=gemini-3.5-flash-lite

ACCESS_TOKEN_EXPIRE_MINUTES=10080
```

`backend/.env` is ignored by Git and should **never** be committed.

### 3. Configure Gemini (recommended for unclear merchants)

Create a Gemini API key and place it only in `backend/.env`:

```env
GEMINI_API_KEY=your_key_here
LLM_PROVIDER=gemini
GEMINI_MODEL=gemini-3.5-flash-lite
```

SpendSense still works without an LLM key, but unresolved merchants will rely on mappings/rules and may remain in `Others`.

### 4. Set up the frontend

```powershell
cd ..\frontend
npm install
```

### 5. Start SpendSense

From the repository root you can use:

```powershell
.\run-dev.ps1
```

This starts:

- FastAPI backend on `http://localhost:8000`
- Vite frontend on `http://localhost:5173`

Open `http://localhost:5173`, create an account, and upload a statement.

You can also start the services manually:

```powershell
# backend
cd backend
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

```powershell
# frontend
cd frontend
npm run dev
```

## LLM privacy note

The LLM fallback is only used for transactions that remain unresolved after personal mappings and deterministic rules.

For those unresolved transactions, classification context can include:

- merchant/payee name;
- amount;
- transaction source (UPI/credit card);
- transaction time;
- cleaned transaction description.

That information is sent to the configured external LLM provider. If you do not want transaction information leaving your machine, leave the LLM API keys empty and use SpendSense with mappings + rules only.

## Data and secrets

The repository ignores local secrets and generated data including:

- `.env`
- SQLite database files
- `backend/data/`
- Python virtual environments
- `node_modules/`
- frontend build output

Do not place API keys directly in Python, JavaScript, `.env.example`, or committed configuration files.

## Current parser support

The strongest tested paths currently are:

- **Google Pay transaction-statement PDFs**
- **ICICI credit-card statements**

Other UPI/credit-card PDFs can fall back to the generic parser, but bank/app PDF layouts vary significantly. Additional statement formats may require parser-specific tuning.

## Current project status

SpendSense v1 is intended primarily as a **personal/local finance application**. The main workflow is complete:

- PDF import
- deduplication
- hybrid categorization
- learned corrections
- reclassification
- monthly analytics
- transfer handling
- range-based Excel exports

For a public production deployment, additional work such as automated tests, CI, stronger deployment configuration, production database setup, and broader parser coverage would still be recommended.
