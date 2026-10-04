from pydantic import BaseModel, field_validator, model_validator


class MCQ(BaseModel):
    question: str
    options: list[str]
    answer_index: int
    source_snippet: str

    @field_validator("options")
    @classmethod
    def four_distinct_options(cls, v: list[str]) -> list[str]:
        if len(v) != 4 or len({o.strip().lower() for o in v}) != 4:
            raise ValueError("need exactly 4 distinct options")
        return v

    @model_validator(mode="after")
    def index_in_range(self):
        if not 0 <= self.answer_index < 4:
            raise ValueError("answer_index must be 0-3")
        return self


class QuizResponse(BaseModel):
    source: str  # "live" or "cached"
    filename: str
    questions: list[MCQ]
