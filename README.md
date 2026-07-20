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
├── frontend/        # Next.js + TypeScript app (Phases 1–2)
├── backend/         # FastAPI service + SQLAlchemy models + Alembic (Phases 1, 3)
├── docs/            # Architecture, database, and API documentation
│   ├── architecture.md
│   └── database.md
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
- **Phase 4 — Core API** Workout & exercise CRUD, REST endpoints
- **Phase 5 — Dashboard** Charts and analytics
- **Phase 6 — AI** Workout analysis, recommendations, weekly plan generation
- **Phase 7 — Billing** Premium gating + Stripe subscriptions
- **Phase 8 — Deployment** Production config, testing, performance

---

## 🚀 Getting Started

> Full setup instructions are added phase by phase. As of Phase 0, this repo contains the documentation and structure only.

```bash
git clone https://github.com/<your-username>/FitMind.git
cd FitMind
```

---

## 📄 License

MIT — see `LICENSE` (added in a later phase).
