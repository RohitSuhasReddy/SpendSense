# SpendSense

Personal finance tracker for Indian **credit card** and **UPI PDF** statements. It extracts transactions, classifies them with a hybrid engine (personal mappings → keyword rules → optional LLM), and lets you correct categories so the next upload is more accurate.

## Stack

- Backend: FastAPI + SQLite (switch `DATABASE_URL` to PostgreSQL later)
- Frontend: React + Vite
- PDF parsing: pdfplumber
- Reports: pandas / openpyxl + dashboard charts

## Run locally

### Backend

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173, register an account, then upload a statement PDF.

Optional: put `GEMINI_API_KEY` (or `OPENAI_API_KEY`) in `backend/.env` so unknown merchants can be classified by an LLM. Without a key, mapping + rules still work.

## Classification order

1. Personal merchant mappings (from your corrections, exact + fuzzy)
2. Keyword rules (Swiggy, Uber, Amazon, Blinkit, …)
3. LLM, if an API key is configured (results are cached)
4. Fallback: `Others`

## What to send next

Parser quality depends on real statement layouts. Upload your own PDFs in the app, and if extraction looks wrong, share **redacted** sample PDFs (hide account numbers) so bank-specific parsers can be added.
