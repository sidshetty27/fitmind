"""ORM models.

Importing every model here is not stylistic — it is what makes Alembic work.
`alembic/env.py` imports this package so that all classes are registered on
`Base.metadata` before autogenerate compares it against the live database. A
model that is never imported is invisible to autogenerate, and the resulting
migration silently omits its table.
"""

from app.models.enums import Equipment, ExperienceLevel, Goal, MuscleGroup
from app.models.exercise import Exercise
from app.models.progress import ProgressEntry
from app.models.user import User
from app.models.workout import Workout
from app.models.workout_exercise import WorkoutExercise

__all__ = [
    "Equipment",
    "Exercise",
    "ExperienceLevel",
    "Goal",
    "MuscleGroup",
    "ProgressEntry",
    "User",
    "Workout",
    "WorkoutExercise",
]
