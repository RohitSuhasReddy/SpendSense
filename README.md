# SpendSense

Local-first personal finance tracker for **Indian UPI and credit-card PDF statements**.

Upload statements → extract & categorize transactions → review/correct → view monthly analytics → export Excel reports.

Built for personal use. Strongest support currently for **Google Pay** transaction statements and **ICICI** credit-card statements (other PDFs fall back to a generic parser).

---

## Features

- PDF statement upload with source detection (UPI / credit card)
- Hybrid categorization: personal mappings → deterministic rules → LLM cache → Gemini/OpenAI fallback
- Review & correct page (manual overrides are remembered and reused)
- Month-driven dashboard (spending, income, net transfers, category split)
- Excel reports for selected month, last 6/12 months, or custom range

**Transfers** are treated as balance movement (not spending/income):  
`Net transfers = transfers sent − transfers received`

---

## Requirements

- Python 3.10+
- Node.js + npm
- Git

---

## Setup

```bash
git clone https://github.com/RohitSuhasReddy/SpendSense.git
cd SpendSense
```

### Backend

```bash
cd backend
python -m venv venv

# Windows
.\venv\Scripts\Activate.ps1

# Linux / macOS
source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env   # or: copy .env.example .env on Windows
```

Edit `backend/.env`:

```env
SECRET_KEY=replace-with-a-long-random-string
DATABASE_URL=sqlite:///./data/spendsense.db
CORS_ORIGINS=http://localhost:5173

# Optional – only needed for unclear merchants
GEMINI_API_KEY=
OPENAI_API_KEY=
LLM_PROVIDER=gemini
GEMINI_MODEL=gemini-3.5-flash-lite

ACCESS_TOKEN_EXPIRE_MINUTES=10080
```

### Frontend

```bash
cd ../frontend
npm install
```

---

## Run

From the repository root (Windows):

```powershell
.\run-dev.ps1
```

Or start services manually:

```bash
# Backend (from backend/ with venv active)
uvicorn app.main:app --reload --port 8000

# Frontend (from frontend/)
npm run dev
```

- Backend: http://localhost:8000  
- Frontend: http://localhost:5173  

Create an account and upload a statement.

---

## LLM usage (optional)

The LLM is used **only** for merchants that remain unclassified after personal mappings and deterministic rules.

If you leave the API keys empty, SpendSense still works using mappings + rules only (unresolved items stay in `Others`).

Recommended (lightweight & fast):

```env
LLM_PROVIDER=gemini
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_API_KEY=your_key_here
```

Context sent to the LLM (when used): merchant/payee name, amount, source (UPI/CC), time, cleaned description.

---

## Project layout

```text
SpendSense/
├── backend/
│   ├── app/
│   │   ├── routers/
│   │   ├── services/          # classifier, pdf_parser, reports, etc.
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

---

## Notes

- Local data and secrets (`.env`, SQLite DB, `backend/data/`) are gitignored.
- Never commit API keys.
- Additional statement formats may need parser tuning beyond the current GPay / ICICI paths.

---

## License

See [LICENSE](LICENSE).
