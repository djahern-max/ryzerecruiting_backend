# app/services/transcript.py
"""
Transcript formatting.

Stored transcripts are plain text from _parse_vtt_transcript() in
app/services/zoom.py — one line per caption cue:

    Dane Ahern: So, hey, Renata, thanks for joining the call.
    Renata Voss: Okay, well, first of all, thank you so much.

Zoom splits a single sentence across multiple cues, so a real speaking turn
often spans several consecutive lines. parse_transcript() merges consecutive
same-speaker lines into one turn — which is what a human actually wants to read.
"""

from __future__ import annotations

import re

# "Speaker Name: text" — 1–4 capitalized words before the colon.
# Deliberately strict so a mid-sentence colon ("here's the thing: ...")
# is not mistaken for a speaker label.
_SPEAKER_RE = re.compile(r"^([A-Z][\w.'\-]*(?:\s+[A-Z][\w.'\-]*){0,3}):\s+(.+)$")


def parse_transcript(raw: str | None) -> list[dict]:
    """Turn a raw transcript into merged speaker turns.

    Returns [{"speaker": str | None, "text": str}, ...].
    Lines with no speaker prefix are treated as a continuation of the
    previous turn. Returns [] for empty or missing input.
    """
    if not raw or not raw.strip():
        return []

    turns: list[dict] = []

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue

        match = _SPEAKER_RE.match(line)
        if match:
            speaker, text = match.group(1).strip(), match.group(2).strip()
        else:
            speaker, text = None, line

        if not text:
            continue

        # Continuation of the current turn: same speaker, or no label at all.
        if turns and (speaker is None or speaker == turns[-1]["speaker"]):
            turns[-1]["text"] = f"{turns[-1]['text']} {text}".strip()
        else:
            turns.append({"speaker": speaker, "text": text})

    return turns
