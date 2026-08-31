LENGTH_INSTRUCTIONS = {
    "short": "Сделай краткое резюме в 1-2 предложениях.",
    "medium": "Составь среднее резюме в 3-5 предложений.",
    "long": "Подготовь развёрнутое резюме ключевых идей (до 7 предложений).",
}


def build_summarize_prompt(text: str, length: str = "medium") -> str:
    instruction = LENGTH_INSTRUCTIONS.get(length, LENGTH_INSTRUCTIONS["medium"])
    return f"{instruction}\n\nТекст для суммаризации:\n---\n{text}\n---"
