# FitMind API (backend)

FastAPI service. Python 3.11+.

## Local development

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env            # then edit values
uvicorn app.main:app --reload --port 8000
```

- API: http://localhost:8000
- Interactive docs (Swagger): http://localhost:8000/docs
- Health check: http://localhost:8000/health
