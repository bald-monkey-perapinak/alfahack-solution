"""Conservative cross-batch matching of reports about the same event."""

import re

_STOP = {"банк", "россии", "новости", "сообщил", "сообщила", "заявил", "решение", "рынок"}


def _title_terms(title):
    return {word[:6] for word in re.findall(r"[а-яёa-z]{5,}", title.casefold()) if word not in _STOP}


def event_similarity(title, shocks, other_title, other_shocks):
    """Require an identical factor direction and a strongly overlapping headline."""
    current = {(s["factor"], s["direction"]) for s in shocks}
    previous = {(s["factor"], s["direction"]) for s in other_shocks}
    if not current or not previous or not current & previous:
        return 0.0
    if any(f == other_f and d != other_d for f, d in current for other_f, other_d in previous):
        return 0.0
    first, second = _title_terms(title), _title_terms(other_title)
    if len(first) < 2 or len(second) < 2:
        return 0.0
    return len(first & second) / len(first | second)
