# FitMind AI 🧠💪

> An AI-powered fitness coaching platform that analyzes your real training history to detect plateaus, recommend progressive overload, and generate personalized weekly plans — not a generic chatbot.

FitMind AI is a full-stack SaaS application built as a production-quality portfolio project. It demonstrates full-stack development, AI integration, authentication, relational database design, REST API design, data visualization, subscription billing, and cloud deployment.

---

## ✨ Features

### Free plan
- Email/social authentication
- User profile (height, weight, goal, experience level)
- Workout & exercise logging
- Exercise history and personal-record (PR) tracking
- Progress charts and dashboard
- Workout streaks
- Basic AI workout summaries (usage-limited)

### Premium plan
- Unlimited AI coaching
- Personalized workout plans
- Nutrition recommendations
- Recovery analysis
- Strength-progression predictions
- Form analysis from uploaded videos
- Advanced analytics & report export
- Premium dashboard

---

## 🏗️ Tech Stack

| Layer          | Technology                                  |
| -------------- | ------------------------------------------- |
| Frontend       | Next.js (App Router), React, TypeScript, Tailwind CSS, Recharts |
| Backend        | FastAPI, Python                             |
| Database       | PostgreSQL (hosted on Supabase)             |
| ORM            | SQLAlchemy + Alembic (migrations)           |
| Authentication | Clerk                                       |
| Payments       | Stripe                                       |
| AI             | OpenAI API                                  |
| Deploy (FE)    | Vercel                                      |
| Deploy (BE)    | Railway or Render                           |
| Version control| Git + GitHub                                |

See [`docs/architecture.md`](docs/architecture.md) for how these fit together and the deliberate tradeoffs behind the stack.

---

## 📁 Repository Structure

```
FitMind/
├── frontend/        # Next.js + TypeScript app  → deploys to Vercel
├── backend/         # FastAPI service + SQLAlchemy models + Alembic
│   ├── Dockerfile           # the deployed artifact
│   └── docker-entrypoint.sh # migrate, then serve
├── docs/            # Architecture, database, deployment, phase checklists
│   ├── architecture.md
│   ├── database.md
│   ├── deployment.md
│   ├── phase-5-testing.md
│   ├── phase-7-testing.md
│   ├── phase-8-testing.md
│   └── phase-9-testing.md
├── render.yaml      # API deployment as infrastructure-as-code
├── LICENSE
├── .gitignore
└── README.md
```

---

## 🗺️ Build Roadmap

This project is built in incremental, reviewable milestones:

- **Phase 0 — Foundation** ✅ Folder structure, Git, README, docs
- **Phase 1 — Scaffolding** ✅ Next.js + FastAPI, connected and verified
- **Phase 2 — Auth** ✅ Clerk, user accounts, protected routes
- **Phase 3 — Database** ✅ PostgreSQL schema, SQLAlchemy ORM, Alembic migrations
- **Phase 4 — Core API** ✅ Clerk-authenticated CRUD (profile, workouts, progress), exercise catalog, user-sync webhook
- **Phase 5 — Workout logging** ✅ Dashboard shell, workout CRUD UI, exercise search, reusable templates
- **Phase 6 — Analysis** ✅ Training-history aggregation, personal records, the Progress page
- **Phase 7 — AI coach** ✅ Deterministic findings from logged sets, written up by a model
- **Phase 8 — Billing** ✅ Stripe subscriptions, premium gating, free-tier AI metering
- **Phase 9 — Deployment** ✅ Containerised API on Render, frontend on Vercel, security headers

Deployment is a runbook, not a description: see [`docs/deployment.md`](docs/deployment.md)
for the steps and [`docs/phase-9-testing.md`](docs/phase-9-testing.md) to verify
a deploy end to end.

---

## 🚀 Getting Started

```bash
git clone https://github.com/sidshetty27/fitmind.git
cd fitmind

# Enable the secret-scanning pre-commit hook (once per clone)
git config core.hooksPath .githooks
```

Then bring up each half. They are independent processes and want their own terminal:

```bash
# Backend — needs a Postgres URL in backend/.env (copy from .env.example)
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python run.py            # http://localhost:8000/docs

# Frontend — needs Clerk keys in frontend/.env.local (copy from .env.example)
cd frontend
npm install
npm run dev                            # http://localhost:3000
```

Every environment variable is documented inline in `backend/.env.example` and
`frontend/.env.example`, including which ones are optional. The app boots
without Stripe or Anthropic configured — billing and the AI narrative simply
turn themselves off rather than erroring — so the smallest working setup is a
database plus Clerk.

To deploy, follow [`docs/deployment.md`](docs/deployment.md).

That last line is worth running before your first commit. `.githooks/pre-commit`
blocks a commit whose staged changes contain a Stripe, Clerk, or Anthropic key,
or that would commit a `.env`. A published key cannot be un-published — rewriting
history afterwards does not help — so the only cheap moment to catch one is
before the commit exists.

It scans added lines only, ignores the `xxxx` placeholders in `.env.example`,
and redacts anything it reports. `--no-verify` overrides it for the false
positive you will eventually hit.

---

## 📄 License

MIT — see [`LICENSE`](LICENSE).
