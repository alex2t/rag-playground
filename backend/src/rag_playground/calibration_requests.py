"""Request bodies of /api/calibration (T48), as strict as run requests (D27)."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

# SQLite integers stop at 64 bits, and a larger number crashes the query instead of finding nothing.
DbId = Annotated[int, Field(ge=1, le=2**63 - 1)]


class OpenCalibration(BaseModel):
    """The two full S0 runs to calibrate the judge on."""

    model_config = ConfigDict(extra="forbid", strict=True)

    run_a: DbId
    run_b: DbId


class GradeRequest(BaseModel):
    """The user's accuracy score for one answer of the sample."""

    model_config = ConfigDict(extra="forbid", strict=True)

    position: DbId
    grade: int = Field(ge=1, le=5)
