# FitMind AI — Architecture

This document explains how the pieces fit together and, more importantly, **why** — including the deliberate tradeoffs we accepted.

## High-level diagram

```
                       ┌──────────────────────┐
                       │        Clerk         │  Identity provider
                       │  (issues JWTs/JWKS)  │
                       └──────────┬───────────┘
                                  │ 1. sign in, get JWT
                                  ▼
┌───────────────────┐   2. API calls w/ JWT   ┌────────────────────┐
│   Next.js (FE)    │ ──────────────────────► │    FastAPI (BE)    │
│  React/TS/Tailwind│ ◄────────────────────── │      Python        │
│  Recharts, Vercel │      JSON responses     │  Railway / Render  │
└───────────────────┘                         └─────────┬──────────┘
                                                        │ 3. verify JWT
                                                        │    via Clerk JWKS
                                          ┌─────────────┼──────────────┐
                                          ▼             ▼              ▼
                                  ┌──────────────┐ ┌─────────┐ ┌─────────────┐
                                  │ PostgreSQL   │ │ OpenAI  │ │   Stripe    │
                                  │ (Supabase)   │ │  API    │ │  (billing)  │
                                  │ SQLAlchemy   │ │         │ │  webhooks   │
                                  └──────────────┘ └─────────┘ └─────────────┘
```

## Request lifecycle

1. The user authenticates in the Next.js app via **Clerk**. Clerk returns a session JWT.
2. The frontend attaches that JWT (`Authorization: Bearer <token>`) to every call to the **FastAPI** backend.
3. FastAPI verifies the JWT signature against **Clerk's JWKS** endpoint (public keys), extracts the Clerk user ID, and maps it to our internal `users` row.
4. FastAPI performs business logic, talks to **Postgres** (via SQLAlchemy), calls **OpenAI** for AI features, and handles **Stripe** billing + webhooks.

## Key architectural decisions & tradeoffs

### 1. Clerk is the single source of truth for identity — Supabase Auth is NOT used
- **Decision:** We use Supabase purely as managed PostgreSQL. We do not use Supabase Auth, nor Supabase Row-Level Security tied to Supabase users.
- **Why:** Two auth systems fighting over "who is the user" is a classic source of bugs. Clerk gives us polished sign-in UIs, social login, and session management out of the box.
- **Tradeoff:** We give up Supabase's built-in RLS. Instead, **all authorization happens in FastAPI** — every query is scoped to the authenticated user's `id`. This is a well-understood, common pattern.

### 2. FastAPI sits in front of Postgres even though Supabase can auto-generate a REST API
- **Decision:** All data access goes through our own FastAPI service.
- **Why:** The AI features (analyzing history, generating plans, enforcing free-tier usage limits), Stripe webhook handling, and premium feature gating require real server-side logic that does not belong in an auto-generated CRUD layer. A hand-written API also demonstrates backend design skill for a portfolio.
- **Tradeoff:** Slightly more code than using Supabase's auto REST API for simple CRUD. Accepted intentionally.

### 3. Separate frontend and backend deployments
- **Decision:** Next.js on Vercel; FastAPI on Railway/Render.
- **Why:** Plays to each platform's strengths (Vercel for edge/SSR React; Railway/Render for long-running Python). Mirrors real production topologies.
- **Tradeoff:** We must configure CORS and manage two environments. Documented in the deployment phase.

## Environments & secrets
Secrets live in `.env` files (git-ignored). Each service has an `.env.example` documenting required variables:
- Frontend: Clerk publishable key, backend API URL, Stripe publishable key.
- Backend: database URL, Clerk secret/JWKS, OpenAI key, Stripe secret + webhook secret.

## Folder layout rationale
- `frontend/` and `backend/` are independent, independently deployable apps in one monorepo for easy review.
- `docs/` holds living documentation, updated every phase.
