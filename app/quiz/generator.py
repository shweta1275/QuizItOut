from app.quiz.validator import validate
from app.rag.chunker import pick_spread
from app.schemas import MCQ

PROMPT = """You are a quiz writer. Using ONLY the passage below, write ONE multiple-choice question
that tests a single fact stated in the passage.
Rules:
- Exactly one option is correct. The other three must be plausible but clearly FALSE according to the passage.
- The correct option must be directly supported by the source_snippet.
- Do not copy other true sentences from the passage as wrong options.
Return JSON with exactly these keys:
"question" (string),
"options" (list of 4 distinct strings),
"answer_index" (integer 0-3, the position of the correct option),
"source_snippet" (one complete sentence copied word for word from the passage that proves the answer).

Passage:
{chunk}
"""


def generate_quiz(chunks: list[str], client, n: int, max_retries: int = 1) -> list[MCQ]:
    questions: list[MCQ] = []
    for chunk in pick_spread(chunks, n):
        for _ in range(max_retries + 1):
            mcq = validate(client.generate_json(PROMPT.format(chunk=chunk)), chunk)
            if mcq:
                questions.append(mcq)
                break
    return questions
