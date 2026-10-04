import re


def chunk_text(text: str, size: int = 800, overlap: int = 100) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 <= size:
            current = f"{current}\n\n{para}".strip()
            continue
        if current:
            chunks.append(current)
        tail = current[-overlap:] if (current and overlap) else ""
        candidate = f"{tail} {para}".strip()
        current = candidate if len(candidate) <= size else para
        while len(current) > size:  # one huge paragraph
            chunks.append(current[:size])
            current = current[size - overlap:]
    if current:
        chunks.append(current)
    return chunks


def pick_spread(chunks: list[str], n: int) -> list[str]:
    if len(chunks) <= n:
        return chunks
    step = len(chunks) / n
    return [chunks[int(i * step)] for i in range(n)]
