# Empirical calibration bounds for cosine similarity between
# text-embedding-3-small profile-vs-job embeddings. Raw cosine similarity
# for strong matches on this data clusters roughly in [0.25, 0.75], so we
# rescale that window to the full 0-1 display range. Tune these two
# constants (only here) if scores start clustering oddly.
SIM_FLOOR = 0.25
SIM_CEIL = 0.75


def compute_match_score(cos_distance: float) -> float:
    """Convert a pgvector cosine distance (`<=>`) into a calibrated 0-1 display score.

    Monotonic in cos_distance, so it never changes ranking — only rescales
    the displayed value.
    """
    cos_sim = 1.0 - cos_distance
    score = (cos_sim - SIM_FLOOR) / (SIM_CEIL - SIM_FLOOR)
    return round(max(0.0, min(1.0, score)), 4)
