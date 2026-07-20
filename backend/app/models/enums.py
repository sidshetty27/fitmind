"""Controlled vocabularies shared by the ORM models.

These are native Postgres ENUM types, not free-text columns with a CHECK.
Rationale:
  - The database rejects a typo'd `"beginer"` no matter which client wrote it.
  - The set of values is discoverable from the schema itself.
Tradeoff: adding a value needs a migration (`ALTER TYPE ... ADD VALUE`, cheap and
non-blocking on PG12+); *removing* or renaming one needs a type rewrite. So these
are for vocabularies we expect to grow slowly. Anything genuinely open-ended
(exercise names) stays a table, not an enum — see `exercises`.

Each member's *value* is what is stored in Postgres. SQLAlchemy's `Enum` type
persists the member NAME by default, so every model column below passes
`values_callable=lambda e: [m.value for m in e]` to store these lowercase values
instead of `STRENGTH`, `FAT_LOSS`, ...
"""

import enum

from sqlalchemy import Enum as SAEnum


def pg_enum(enum_cls: type[enum.Enum], name: str) -> SAEnum:
    """Build a native Postgres ENUM column type from a Python enum.

    `values_callable` is the important part: without it SQLAlchemy stores member
    names (`FAT_LOSS`), which is ugly in psql, awkward in JSON, and diverges from
    the values the API layer speaks.
    """
    return SAEnum(
        enum_cls,
        name=name,
        values_callable=lambda e: [member.value for member in e],
        native_enum=True,
    )


class Goal(str, enum.Enum):
    """What the user is training for. Drives AI plan generation in Phase 6."""

    STRENGTH = "strength"
    HYPERTROPHY = "hypertrophy"
    FAT_LOSS = "fat_loss"
    ENDURANCE = "endurance"
    GENERAL_FITNESS = "general_fitness"


class ExperienceLevel(str, enum.Enum):
    """Training age. Gates how aggressive progressive-overload advice should be."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class MuscleGroup(str, enum.Enum):
    """Primary mover for a catalog exercise. Powers volume-per-muscle analytics."""

    CHEST = "chest"
    BACK = "back"
    SHOULDERS = "shoulders"
    QUADS = "quads"
    HAMSTRINGS = "hamstrings"
    GLUTES = "glutes"
    CALVES = "calves"
    BICEPS = "biceps"
    TRICEPS = "triceps"
    FOREARMS = "forearms"
    CORE = "core"
    FULL_BODY = "full_body"


class Equipment(str, enum.Enum):
    """What the movement requires — lets us substitute exercises by availability."""

    BARBELL = "barbell"
    DUMBBELL = "dumbbell"
    MACHINE = "machine"
    CABLE = "cable"
    BODYWEIGHT = "bodyweight"
    KETTLEBELL = "kettlebell"
    BAND = "band"
    OTHER = "other"
