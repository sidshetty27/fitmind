"""Training-history analysis — the layer every AI feature and chart reads from.

Deliberately split in two:

  - `metrics` is **pure**. Given numbers, it returns numbers: no session, no
    ORM, no I/O. That is what makes the training maths testable without a
    database, which matters because the integration suite needs a live Postgres
    and is skipped by default.
  - `app.crud.analysis` does the querying and calls into `metrics` to derive.

  - `findings` (Phase 7) turns those derived numbers into *observations* —
    plateaus, volume drops, neglected muscle groups, movements with room to
    progress. Also pure, and also fully tested, because these are the sentences
    the AI coach is handed as fact.

Nothing here calls a language model. The model consumes `findings` output and is
responsible for prioritising and phrasing it, never for computing it: a model
doing arithmetic on a set log will eventually state a wrong number confidently,
and a wrong number is worse than no coaching. Keeping the maths here also means
the feature still works with no API key and for users over their quota.
"""
