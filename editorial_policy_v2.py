from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import editorial_policy as policy


# Fine-tuning after testing on a 100-channel / 930-post personal snapshot.
# Keep stylistically reported culture in the editorial radar, and increase
# source diversity in the recommendation cards.
policy.TOPIC_STOP.add("самое интересное")


def topic_is_pulse(topic: dict[str, Any]) -> bool:
    term = str(topic.get("term") or "")
    if policy.HARD_NEWS_RE.search(term) or policy.POLITICAL_RE.search(term):
        return True

    examples = topic.get("examples") or []
    pseudo = [
        {
            "text": e.get("text", ""),
            "channel": e.get("channel", ""),
            "channel_title": e.get("channel_title", ""),
            "category": "",
        }
        for e in examples[:5]
    ]
    if not pseudo:
        return False

    total = len(pseudo)
    pulse = sum(policy.is_pulse_post(post) for post in pseudo)
    hard_or_political = sum(
        bool(
            policy.HARD_NEWS_RE.search(str(post.get("text") or ""))
            or policy.POLITICAL_RE.search(str(post.get("text") or ""))
        )
        for post in pseudo
    )
    styled = sum(
        bool(policy.NEWS_STYLE_RE.search(str(post.get("text") or "")))
        for post in pseudo
    )
    editorial = sum(
        bool(policy.EDITORIAL_RE.search(str(post.get("text") or "")))
        for post in pseudo
    )

    if pulse / total >= 0.5:
        return True
    if hard_or_political / total >= 0.5:
        return True

    # News-style wording alone is not enough to demote a cultural/tech story.
    # Example: "Kanye concert will take place — RBC..." is still culture.
    if total >= 2 and styled / total >= 0.6 and editorial / total < 0.5:
        return True

    return False


def editorial_picks(posts: list[dict[str, Any]], limit: int = 15) -> list[dict[str, Any]]:
    rows = []
    for post in posts:
        row = dict(post)
        row["content_fit"] = policy.editorial_fit(post)
        if row["content_fit"] >= 3.15:
            row["_family"] = policy.base.family_for_category(str(row.get("category") or ""))
            rows.append(row)

    rows.sort(
        key=lambda row: (row["content_fit"], float(row.get("signal_score") or 0)),
        reverse=True,
    )

    selected: list[dict[str, Any]] = []
    families: Counter[str] = Counter()
    channels: Counter[str] = Counter()
    seen: set[str] = set()
    caps = {
        "technology": 3,
        "art": 3,
        "ideas": 3,
        "cinema": 3,
        "science": 2,
        "design": 2,
        "media": 2,
        "music": 2,
        "viral": 1,
        "business": 1,
        "misc": 2,
    }

    for row in rows:
        family = row["_family"]
        channel = str(row.get("channel") or "")
        prefix = re.sub(r"\W+", "", str(row.get("text") or "").lower())[:140]

        # One source per top-15 pass: the radar should broaden attention,
        # not return several adjacent posts from the same channel.
        if (
            family == "pulse"
            or families[family] >= caps.get(family, 2)
            or channels[channel] >= 1
            or prefix in seen
        ):
            continue

        selected.append(row)
        families[family] += 1
        channels[channel] += 1
        seen.add(prefix)

        if len(selected) >= limit:
            break

    for row in selected:
        row.pop("_family", None)
    return selected


# Monkey-patch the tested policy module so its existing report builder and
# all callers use the refined behavior.
policy.topic_is_pulse = topic_is_pulse
policy.editorial_picks = editorial_picks


def main() -> None:
    parser = argparse.ArgumentParser(description="Build refined personal editorial report")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    snapshot = json.loads(Path(args.input).read_text(encoding="utf-8"))
    Path(args.output).write_text(policy.build_report(snapshot), encoding="utf-8")


if __name__ == "__main__":
    main()
