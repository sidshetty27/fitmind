"""Pydantic request/response schemas — the API's contract, kept separate from ORM.

Why these exist as their own layer rather than returning ORM models directly:
  - They are the *public shape* of the API. Decoupling them from the SQLAlchemy
    models means a column can be added, renamed, or made internal without silently
    changing (or breaking) the JSON every client depends on.
  - They validate input at the edge. Constraints here mirror the database CHECKs,
    so a bad payload is rejected as a clean 422 before it ever reaches Postgres —
    the DB constraint remains the last line of defence, not the first.
  - They stop internals leaking: `clerk_id`, raw FKs, and unloaded relationships
    never accidentally serialize into a response.
"""
