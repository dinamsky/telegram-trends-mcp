from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from tg_mcp.server import get_posts, search_channels


DEFAULT_MAX_CHANNELS = 100
DEFAULT_RESOLVE_LIMIT = 140

EXCLUDE_RE = re.compile(
    r"(?:proxy|прокси|скидк|халяв|купон|aliexpress|ваканси|удаленк|"
    r"ставк|беттинг|казино|porn|порно|18\+\s*$|shopping|private shopping)",
    re.IGNORECASE,
)

CATEGORY_RULES: list[tuple[str, tuple[str, ...], float]] = [
    ("art_culture", ("искус", "арт", "gallery", "галере", "музей", "авангард", "худож", "малевич"), 1.34),
    ("cinema", ("кино", "cinema", "film", "videodrome", "кроненберг", "сеанс"), 1.30),
    ("technology_ai", ("нейро", "ai", "ии", "tech", "техно", "digital", "дидж", "код", "web", "интернет", "эксплойт"), 1.30),
    ("culture_philosophy", ("философ", "культур", "мамлеев", "южин", "контекст", "гуман", "сюрреал"), 1.28),
    ("history_literature", ("истор", "архив", "литера", "книг", "чехов", "бунин", "гамсун", "совет", "старин"), 1.23),
    ("science_space", ("наук", "science", "космос", "space", "роскосмос", "нейроинтерфейс"), 1.20),
    ("design_fashion", ("design", "дизайн", "fashion", "мода", "архитект", "маржела"), 1.18),
    ("marketing_media", ("маркет", "медиа", "реклам", "пиар", "бренд", "тренд"), 1.12),
    ("music", ("музык", "music", "звук", "techno"), 1.15),
    ("business_economy", ("банк", "business", "бизнес", "эконом", "ритейл", "рынок"), 0.90),
    ("city", ("питер", "петербург", "москва", "город", "фонтанка"), 0.72),
    ("geopolitics", ("военн", "войн", "полит", "геополит", "сво", "z:", "милитар"), 0.58),
    ("news", ("новост", "news", "срочно", "breaking", "readovka", "baza", "mash"), 0.58),
    ("viral", ("мем", "двач", "рифмы", "панчи", "viral", "юмор", "ебобо", "ebobo"), 0.70),
]

ACCELERATOR_CATEGORIES = {"news", "geopolitics", "viral", "city", "business_economy"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a private personalized Telegram watchlist from a Telegram Desktop export."
    )
    parser.add_argument(
        "--analysis-dir",
        required=True,
        help="Folder containing channels.json and forward_stats.json from analyze_telegram_export.py",
    )
    parser.add_argument("--base-watchlist", default="watchlist.json")
    parser.add_argument("--output", default="watchlist.personal.json")
    parser.add_argument("--report", default="output/personalization_report.md")
    parser.add_argument("--max-channels", type=int, default=DEFAULT_MAX_CHANNELS)
    parser.add_argument(
        "--resolve-limit",
        type=int,
        default=DEFAULT_RESOLVE_LIMIT,
        help="How many top unresolved subscriptions to search on Telegram/web (default 140)",
    )
    parser.add_argument("--concurrency", type=int, default=3)
    return parser.parse_args()


def norm(value: str) -> str:
    value = str(value or "").lower().replace("ё", "е")
    value = re.sub(r"https?://\S+", " ", value)
    value = re.sub(r"[^a-zа-я0-9]+", " ", value)
    return " ".join(value.split())


def title_similarity(a: str, b: str) -> float:
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    seq = SequenceMatcher(None, na, nb).ratio()
    ta, tb = set(na.split()), set(nb.split())
    jac = len(ta & tb) / max(len(ta | tb), 1)
    containment = 1.0 if na in nb or nb in na else 0.0
    return 0.55 * seq + 0.30 * jac + 0.15 * containment


def classify(title: str) -> tuple[str, float]:
    low = norm(title)
    for category, needles, fit in CATEGORY_RULES:
        if any(norm(needle) in low for needle in needles):
            return category, fit
    return "culture_misc", 0.88


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def subscription_score(title: str, forwards: int, existing: bool) -> tuple[float, str, float]:
    category, fit = classify(title)
    affinity = min(math.log1p(max(forwards, 0)) / math.log1p(400), 1.0)
    score = fit * 3.0 + affinity * 3.0 + (2.5 if existing else 0.0)
    if category in {"news", "geopolitics", "viral"}:
        score -= 0.5
    return score, category, fit


async def resolve_one(
    candidate: dict[str, Any],
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    title = candidate["title"]
    async with semaphore:
        try:
            found = await search_channels(title, limit=5, verify=False)
        except Exception as exc:
            return {**candidate, "resolved": False, "resolve_error": str(exc)}

        rows = found.get("results") or []
        ranked = []
        for row in rows:
            username = str(row.get("username") or "").lstrip("@")
            if not username:
                continue
            sim = title_similarity(title, str(row.get("name") or ""))
            ranked.append((sim, username, row))

        if not ranked:
            return {**candidate, "resolved": False, "resolve_error": "no search results"}

        ranked.sort(key=lambda x: x[0], reverse=True)
        search_sim, username, search_row = ranked[0]
        if search_sim < 0.42:
            return {
                **candidate,
                "resolved": False,
                "resolve_error": f"weak search match ({search_sim:.2f})",
            }

        try:
            check = await get_posts(username, limit=2)
        except Exception as exc:
            return {**candidate, "resolved": False, "resolve_error": str(exc)}

        actual_title = str(check.get("title") or search_row.get("name") or "")
        actual_sim = title_similarity(title, actual_title)
        if check.get("error") or not check.get("channel"):
            return {
                **candidate,
                "resolved": False,
                "resolve_error": str(check.get("error") or "verification failed"),
            }

        if actual_sim < 0.48 and search_sim < 0.72:
            return {
                **candidate,
                "resolved": False,
                "resolve_error": (
                    f"title mismatch search={search_sim:.2f}, verify={actual_sim:.2f}; "
                    f"got '{actual_title}'"
                ),
            }

        canonical = str(check.get("canonical") or check.get("channel") or f"@{username}")
        canonical = canonical.lstrip("@")
        return {
            **candidate,
            "resolved": True,
            "username": canonical,
            "resolved_title": actual_title or title,
            "match_score": round(max(search_sim, actual_sim), 3),
            "resolution": "search+verify",
        }


def make_watch_entry(row: dict[str, Any], max_forwards: int) -> dict[str, Any]:
    category = row["category"]
    forwards = int(row.get("forwards") or 0)
    affinity = min(math.log1p(forwards) / math.log1p(max(max_forwards, 1)), 1.0)

    if category in ACCELERATOR_CATEGORIES:
        tier = "accelerator"
        weight = 0.30 + 0.25 * affinity
    elif row.get("existing"):
        tier = str(row.get("base_tier") or "core")
        weight = max(0.75, safe_float(row.get("base_weight"), 0.9))
        weight = min(1.25, weight + 0.10 * affinity)
    elif row["score"] >= 6.3:
        tier = "core"
        weight = 0.92 + 0.24 * affinity
    elif row["score"] >= 5.3:
        tier = "niche"
        weight = 0.88 + 0.22 * affinity
    else:
        tier = "radar"
        weight = 0.70 + 0.18 * affinity

    return {
        "username": str(row["username"]).lstrip("@"),
        "title": row.get("resolved_title") or row["title"],
        "category": category,
        "tier": tier,
        "weight": round(min(max(weight, 0.2), 1.25), 2),
        "enabled": True,
        "personal": True,
        "forward_count": forwards,
    }


def select_balanced(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    rows = sorted(rows, key=lambda r: (r["score"], r.get("forwards", 0)), reverse=True)
    accelerator_cap = max(15, int(limit * 0.25))
    accelerators = []
    editorial = []
    seen = set()

    for row in rows:
        username = str(row.get("username") or "").lower()
        if not username or username in seen:
            continue
        seen.add(username)
        if row["category"] in ACCELERATOR_CATEGORIES:
            accelerators.append(row)
        else:
            editorial.append(row)

    selected = editorial[: max(0, limit - accelerator_cap)]
    selected.extend(accelerators[:accelerator_cap])

    if len(selected) < limit:
        already = {str(r["username"]).lower() for r in selected}
        for row in rows:
            key = str(row.get("username") or "").lower()
            if key and key not in already:
                selected.append(row)
                already.add(key)
                if len(selected) >= limit:
                    break

    return sorted(selected[:limit], key=lambda r: (r["score"], r.get("forwards", 0)), reverse=True)


def build_report(
    out_path: Path,
    selected: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
    stats: dict[str, int],
) -> None:
    lines = [
        "# Personal Telegram watchlist",
        "",
        "Персонализация построена локально из Telegram Desktop export.",
        "",
        "## Итог",
        "",
        f"- Публичных подписок в экспорте: {stats['subscriptions']}",
        f"- Рассмотрено кандидатов: {stats['candidates']}",
        f"- Разрешено @username: {stats['resolved']}",
        f"- Не удалось уверенно разрешить: {stats['unresolved']}",
        f"- Выбрано в watchlist: {len(selected)}",
        "",
        "## Выбранные источники",
        "",
        "| # | Канал | @username | Тип | Пересылок | Score |",
        "|---:|---|---|---|---:|---:|",
    ]
    for i, row in enumerate(selected, 1):
        lines.append(
            f"| {i} | {row.get('resolved_title') or row['title']} | "
            f"@{str(row['username']).lstrip('@')} | {row['category']} | "
            f"{row.get('forwards', 0)} | {row['score']:.2f} |"
        )

    if unresolved:
        lines += ["", "## Не удалось уверенно сопоставить", ""]
        for row in unresolved[:50]:
            lines.append(f"- {row['title']} — {row.get('resolve_error', 'not resolved')}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def main_async(args: argparse.Namespace) -> None:
    analysis_dir = Path(args.analysis_dir)
    channels_path = analysis_dir / "channels.json"
    forwards_path = analysis_dir / "forward_stats.json"
    base_path = Path(args.base_watchlist)
    output_path = Path(args.output)
    report_path = Path(args.report)

    channels = load_json(channels_path)
    forward_rows = load_json(forwards_path)
    base = load_json(base_path)

    forward_map = {norm(r.get("source", "")): int(r.get("count") or 0) for r in forward_rows}
    base_by_title = {norm(r.get("title", "")): r for r in base.get("channels", []) if r.get("title")}

    subscriptions = [
        row for row in channels
        if row.get("type") == "public_channel" and row.get("name")
    ]

    candidates = []
    for row in subscriptions:
        title = str(row["name"]).strip()
        if EXCLUDE_RE.search(title):
            continue
        key = norm(title)
        existing_row = base_by_title.get(key)
        forwards = forward_map.get(key, 0)
        score, category, fit = subscription_score(title, forwards, bool(existing_row))
        candidates.append(
            {
                "title": title,
                "forwards": forwards,
                "score": score,
                "category": category,
                "fit": fit,
                "existing": bool(existing_row),
                "username": (existing_row or {}).get("username"),
                "resolved_title": (existing_row or {}).get("title"),
                "base_tier": (existing_row or {}).get("tier"),
                "base_weight": (existing_row or {}).get("weight"),
                "resolved": bool(existing_row and existing_row.get("username")),
                "resolution": "base_watchlist" if existing_row else None,
            }
        )

    candidates.sort(key=lambda r: (r["score"], r["forwards"]), reverse=True)

    known = [r for r in candidates if r.get("resolved")]
    unknown = [r for r in candidates if not r.get("resolved")][: max(args.resolve_limit, 0)]

    print(f"Public subscriptions: {len(subscriptions)}")
    print(f"Already known from base watchlist: {len(known)}")
    print(f"Resolving top unknown subscriptions: {len(unknown)}")
    print("This uses public search and t.me verification; it can take several minutes.")

    sem = asyncio.Semaphore(max(1, args.concurrency))
    resolved_unknown = []
    if unknown:
        tasks = [resolve_one(row, sem) for row in unknown]
        for i, task in enumerate(asyncio.as_completed(tasks), 1):
            result = await task
            resolved_unknown.append(result)
            status = "OK" if result.get("resolved") else "--"
            print(f"[{i:03d}/{len(tasks):03d}] {status} {result['title']}")

    all_resolved = known + [r for r in resolved_unknown if r.get("resolved")]
    unresolved = [r for r in resolved_unknown if not r.get("resolved")]

    selected = select_balanced(all_resolved, args.max_channels)
    max_forwards = max((int(r.get("forwards") or 0) for r in selected), default=1)
    watch_channels = [make_watch_entry(r, max_forwards) for r in selected]

    from datetime import date

    payload = {
        "updated_at": date.today().isoformat(),
        "description": (
            "Private personalized watchlist generated locally from Telegram subscriptions "
            "and forwarding history. Do not commit this file if the repository is public."
        ),
        "channels": watch_channels,
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    build_report(
        report_path,
        selected,
        unresolved,
        {
            "subscriptions": len(subscriptions),
            "candidates": len(candidates),
            "resolved": len(all_resolved),
            "unresolved": len(unresolved),
        },
    )

    print()
    print(f"Done: {output_path.resolve()}")
    print(f"Report: {report_path.resolve()}")
    print("Personal subscription data stays local. Do not commit watchlist.personal.json.")


def main() -> None:
    args = parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
