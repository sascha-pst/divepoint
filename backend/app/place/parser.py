"""Conservative local parser. No model/key is required for the playable prototype."""

import re

MONTHS = [
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
]


def parse_request(prompt: str, depth: float, month: int | None) -> dict:
    name = prompt.strip().lower()
    if match := re.search(r"\b(-?\d+(?:\.\d+)?)\s*(?:m\b|metres?\b|meters?\b)", name):
        depth = float(match.group(1))
        name = name[: match.start()] + name[match.end() :]
    months = [month] if month else []
    for index, label in enumerate(MONTHS, 1):
        if re.search(rf"\b{label}\b", name):
            months = [index]
            name = re.sub(rf"\b{label}\b", "", name)
    season = None
    for label in ["spring", "summer", "autumn", "fall", "winter"]:
        if re.search(rf"\b{label}\b", name):
            season = label
            name = re.sub(rf"\b{label}\b", "", name)
    name = re.sub(
        r"\b(take me to|dive in|dive at|show me|kelp forest|coral reef|wreck dive|wreck|the|off|in|at|a|an)\b",
        " ",
        name,
    )
    name = re.sub(r"[,.;:!?]+", " ", name)
    name = " ".join(name.split())
    if not name or not 1 <= depth <= 60:
        raise ValueError("Enter a marine place and choose a depth between 1 and 60 metres.")
    return {"place": name, "depth_m": [0, depth], "months": months, "season": season}


def season_months(season: str | None, latitude: float) -> list[int]:
    months = {
        "spring": [3, 4, 5],
        "summer": [6, 7, 8],
        "autumn": [9, 10, 11],
        "fall": [9, 10, 11],
        "winter": [12, 1, 2],
    }.get(season, [])
    return [((month + 5) % 12) + 1 for month in months] if latitude < 0 else months
