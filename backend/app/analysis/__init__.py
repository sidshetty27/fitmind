"""Training-history analysis — the layer every AI feature and chart reads from.

Deliberately split in two:

  - `metrics` is **pure**. Given numbers, it returns numbers: no session, no
    ORM, no I/O. That is what makes the training maths testable without a
    database, which matters because the integration suite needs a live Postgres
    and is skipped by default.
  - `app.crud.analysis` does the querying and calls into `metrics` to derive.

Nothing here decides *what to say* about the numbers. Plateau wording,
progression advice, and plan generation live above this layer and consume its
output, so the arithmetic can be verified independently of any model call.
"""
