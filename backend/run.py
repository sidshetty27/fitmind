"""Local development server launcher — run with `python run.py`.

Why this exists instead of just `uvicorn app.main:app`:

On Windows, psycopg3's async driver cannot run on the default ProactorEventLoop —
it needs the SelectorEventLoop. The catch is that the loop *policy* has to be set
**before the event loop is created**, and uvicorn's CLI creates the loop before it
imports our app, so setting the policy inside `app.main` is too late. Setting it
here, before `uvicorn` is even imported, guarantees the compatible loop is used.

On Linux/macOS (where the app is deployed) this is a no-op, so `python run.py` is
a safe single command on every platform.

Note: `reload=True` is intentionally left off. uvicorn's reloader runs the server
in a subprocess that re-creates the loop with the default policy, which reintroduces
the Windows issue. For an auto-reloading loop on Windows, run under WSL/Linux.
"""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn  # noqa: E402 — must be imported after the loop policy is set

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
