import math
from typing import Any, Dict


def execute(state: Dict[str, Any], config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    inputs = (context or {}).get("inputs") or {}
    text = inputs.get("text") or ""
    wpm = inputs.get("wpm", 200)

    try:
        wpm_value = float(wpm)
        if wpm_value <= 0:
            wpm_value = 200.0
    except (TypeError, ValueError):
        wpm_value = 200.0

    words = [word for word in str(text).split() if word]
    word_count = len(words)

    minutes = word_count / wpm_value if wpm_value else 0.0
    minutes_rounded = round(minutes, 2)
    seconds = int(math.ceil(minutes * 60))

    summary = f"{word_count} words, ~{minutes_rounded} min read"

    return {
        "artifact_id": (context or {}).get("artifact_id"),
        "word_count": word_count,
        "minutes": minutes_rounded,
        "seconds": seconds,
        "summary": summary,
    }
