"""The AI layer — the only place in this codebase that calls a language model.

Deliberately thin, and deliberately downstream of `app.analysis`. Every number
the coach states is computed there, from the user's own rows, by tested pure
functions. This package takes those findings as given and asks a model to
prioritise and phrase them.

Nothing here may introduce a fact. If a prompt in this package ever asks the
model to work something out from raw sets, that is a bug: the model would
occasionally be confidently wrong about a user's training, which is the one
failure this feature cannot afford.
"""
