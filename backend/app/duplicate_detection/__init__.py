"""Duplicate / related complaint detection (spec L7).

Signals: category compatibility, geographic distance, reporting time, text
similarity and photo similarity (perceptual dHash Hamming distance between the
complaints' images; deterministic, not AI). When an embedding model is configured (app.ai), cosine similarity
of embeddings is used with the 0.85 threshold. Otherwise a deterministic
lexical similarity (token cosine) is used and labelled as such: it is not an
AI result. Suggestions never delete, merge or reject complaints.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta

# Prototype compatibility map (symmetric). Same category is always compatible.
COMPATIBLE_CATEGORIES: dict[str, set[str]] = {
    "DRAINAGE": {"SANITATION", "WATER_SUPPLY"},
    "SANITATION": {"DRAINAGE"},
    "WATER_SUPPLY": {"DRAINAGE"},
    "ROAD_INFRASTRUCTURE": {"PUBLIC_INFRASTRUCTURE"},
    "PUBLIC_INFRASTRUCTURE": {"ROAD_INFRASTRUCTURE", "STREETLIGHT"},
    "STREETLIGHT": {"PUBLIC_INFRASTRUCTURE"},
}

_STOPWORDS = set(
    "a an the and or but is are was were be been being of in on at to for from by with near this that there "
    "it its i we my our me you he she they them his her their very so not no as has have had do does did "
    "since please also just still".split()
)


def categories_compatible(a: str, b: str) -> bool:
    return a == b or b in COMPATIBLE_CATEGORIES.get(a, set()) or a in COMPATIBLE_CATEGORIES.get(b, set())


def _tokens(text: str) -> Counter:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return Counter(w for w in words if w not in _STOPWORDS and len(w) > 1)


def lexical_similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    dot = sum(ta[t] * tb[t] for t in ta.keys() & tb.keys())
    norm = math.sqrt(sum(v * v for v in ta.values())) * math.sqrt(sum(v * v for v in tb.values()))
    return round(dot / norm, 4) if norm else 0.0


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return round(dot / (na * nb), 4) if na and nb else 0.0


@dataclass
class CandidateInput:
    complaint_id: str
    category: str
    created_at: datetime
    distance_m: float
    text: str
    image_hashes: list[str] = field(default_factory=list)


def image_similarity(a: list[str], b: list[str]) -> tuple[float, int | None]:
    """Best match between two sets of 64-bit image hashes: (1 - distance/64, distance)."""
    best: int | None = None
    for x in a:
        for y in b:
            d = bin(int(x, 16) ^ int(y, 16)).count("1")
            best = d if best is None else min(best, d)
    return (round(1 - best / 64, 4), best) if best is not None else (0.0, None)


@dataclass
class DuplicateCandidate:
    complaint_id: str
    distance_m: float
    text_similarity: float
    text_similarity_method: str
    similarity_score: float
    match_reasons: list[str] = field(default_factory=list)
    image_distance: int | None = None


def detect_duplicate_candidates(
    *,
    category: str,
    created_at: datetime,
    text: str,
    candidates: list[CandidateInput],
    radius_m: float = 100.0,
    window_days: int = 30,
    text_threshold: float = 0.35,
    text_method: str = "lexical-token-cosine",
    similarity_fn=lexical_similarity,
    image_hashes: list[str] | None = None,
    image_max_distance: int = 10,
) -> list[DuplicateCandidate]:
    """Return candidates meeting proximity + time + category rules, with reasons.

    similarity_score = 0.5 * proximity_score + 0.5 * content_similarity, where
    proximity_score = 1 - distance/radius and content_similarity is the text
    similarity, raised to the photo similarity when the photos match
    (Hamming distance <= image_max_distance). It is a ranking aid only.
    """
    results: list[DuplicateCandidate] = []
    earliest = created_at - timedelta(days=window_days)
    for c in candidates:
        if not categories_compatible(category, c.category):
            continue
        if c.distance_m > radius_m:
            continue
        if not (earliest <= c.created_at <= created_at):
            continue
        sim = similarity_fn(text, c.text)
        reasons = [
            f"Within {c.distance_m:.0f} m (threshold {radius_m:.0f} m)",
            f"Reported within the previous {window_days} days",
            "Same category" if c.category == category else f"Compatible category ({c.category})",
        ]
        if sim >= text_threshold:
            reasons.append(f"Similar description ({text_method} {sim:.2f} >= {text_threshold:.2f})")
        content = sim
        img_sim, img_dist = image_similarity(image_hashes or [], c.image_hashes)
        if img_dist is not None and img_dist <= image_max_distance:
            reasons.append(f"Similar photo (perceptual hash distance {img_dist}/64 <= {image_max_distance})")
            content = max(sim, img_sim)
        proximity = max(0.0, 1 - c.distance_m / radius_m) if radius_m else 0.0
        results.append(
            DuplicateCandidate(
                complaint_id=c.complaint_id,
                distance_m=round(c.distance_m, 1),
                text_similarity=sim,
                text_similarity_method=text_method,
                similarity_score=round(0.5 * proximity + 0.5 * content, 4),
                match_reasons=reasons,
                image_distance=img_dist,
            )
        )
    results.sort(key=lambda r: r.similarity_score, reverse=True)
    return results
