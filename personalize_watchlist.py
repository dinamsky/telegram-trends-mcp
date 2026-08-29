from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
from collections import Counter, defaultdict
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

# Strong title-level rules. Patterns use token/word boundaries so short markers
# such as AI/ИИ do not fire inside cAVIAr/РоссИИ.
TITLE_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("news", re.compile(
        r"(?:\bnews\b|\bновост\w*\b|\bbreaking\b|\breadovka\b|\bbaza\b|\bmash\b|"
        r"раньше всех|кровавая барыня|пул\s*n?3|лентач|миг россии|карточный домик|"
        r"медиакиллер|москва онлайн|московская хроника)", re.I)),
    ("geopolitics", re.compile(
        r"(?:\bвоенн\w*\b|\bвойн\w*\b|\bгеополит\w*\b|\bсво\b|милитар|рыбарь|"
        r"kotsnews|военный обозреватель|сыны монархии|китайская угроза|"
        r"спутник и погром|divgen|war.?gonzo|colonelcassad|военкор)", re.I)),
    ("art_culture", re.compile(
        r"(?:\bискусств\w*\b|\bхудож\w*\b|\bгалере\w*\b|\bмузе\w*\b|\bавангард\w*\b|"
        r"\bмалевич\w*\b|\bart\b|annushka|мальцовская|фрида кало|русский арт)", re.I)),
    ("cinema", re.compile(
        r"(?:\bкино\b|\bfilm\w*\b|\bcinema\w*\b|videodrome|кроненберг|сеанс|"
        r"артхаус|кинопоиск|cinemasha)", re.I)),
    ("technology_ai", re.compile(
        r"(?:\bии\b|\bai\b|\bнейро\w*\b|\bтехнолог\w*\b|\btech\w*\b|\bdigital\b|"
        r"\bдиджитал\b|\bкод\b|\bweb\b|\bинтернет\b|эксплойт|securitylab|хабр|"
        r"бэкдор|нейроинтерфейс|openai)", re.I)),
    ("culture_philosophy", re.compile(
        r"(?:\bфилософ\w*\b|\bкультур\w*\b|мамлеев|южин|гуманитар|сюрреал|"
        r"бахчисарайские гвоздики|толкователь|мортиры и перелески)", re.I)),
    ("history_literature", re.compile(
        r"(?:\bистор\w*\b|\bархив\w*\b|\bлитера\w*\b|\bкниг\w*\b|чехов|бунин|"
        r"гамсун|советск\w*|старин\w*|газетная пыль|общество распространения полезных книг)", re.I)),
    ("science_space", re.compile(
        r"(?:\bнаук\w*\b|\bscience\b|\bкосмос\w*\b|\bspace\b|роскосмос|астрон|"
        r"физик\w*|биолог\w*)", re.I)),
    ("design_fashion", re.compile(
        r"(?:\bdesign\w*\b|\bдизайн\w*\b|\bfashion\b|\bмод\w*\b|\bархитект\w*\b|"
        r"маржела|golden chihuahua)", re.I)),
    ("marketing_media", re.compile(
        r"(?:\bмаркет\w*\b|\bмедиа\b|\bреклам\w*\b|\bпиар\w*\b|\bбренд\w*\b|"
        r"зашкваркетинг|беспощадный пиарщик)", re.I)),
    ("music", re.compile(r"(?:\bмузык\w*\b|\bmusic\b|\bзвук\w*\b|\btechno\b)", re.I)),
    ("business_economy", re.compile(
        r"(?:\bбанк\w*\b|\bbusiness\b|\bбизнес\w*\b|\bэконом\w*\b|\bритейл\w*\b|"
        r"\bрын\w*\b|proeconomics|the bell)", re.I)),
    ("city", re.compile(
        r"(?:\bпитер\w*\b|\bпетербург\w*\b|\bгород\w*\b|фонтанка|мегаполис|"
        r"как дела санкт петербург)", re.I)),
    ("viral", re.compile(
        r"(?:\bмем\w*\b|\bдвач\b|рифмы и панчи|\bviral\b|\bюмор\w*\b|\bebobo\b|"
        r"лепра|fytw|yoba media|гиг пиг ниг)", re.I)),
]

CONTENT_RULES: dict[str, re.Pattern[str]] = {
    "art_culture": re.compile(r"\b(искусств\w*|худож\w*|галере\w*|музе\w*|живопис\w*|скульптур\w*|выставк\w*)\b", re.I),
    "cinema": re.compile(r"\b(кино|фильм\w*|сериал\w*|режисс\w*|акт[её]р\w*|сценар\w*)\b", re.I),
    "technology_ai": re.compile(r"\b(ии|ai|нейросет\w*|модель\w*|технолог\w*|код\w*|программ\w*|робот\w*|чип\w*|gpu|open.?source)\b", re.I),
    "culture_philosophy": re.compile(r"\b(философ\w*|культур\w*|идеолог\w*|семиот\w*|эстетик\w*)\b", re.I),
    "history_literature": re.compile(r"\b(истор\w*|архив\w*|литератур\w*|писател\w*|книг\w*|поэт\w*|советск\w*)\b", re.I),
    "science_space": re.compile(r"\b(исследован\w*|уч[её]н\w*|наук\w*|лаборатор\w*|космос\w*|спутник\w*|астроном\w*)\b", re.I),
    "design_fashion": re.compile(r"\b(дизайн\w*|архитектур\w*|мод\w*|fashion|одежд\w*|бренд\w*)\b", re.I),
    "marketing_media": re.compile(r"\b(маркетинг\w*|реклам\w*|медиа\b|пиар\w*|аудитор\w*|бренд\w*)\b", re.I),
    "music": re.compile(r"\b(музык\w*|альбом\w*|трек\w*|концерт\w*|дидже\w*|techno)\b", re.I),
    "business_economy": re.compile(r"\b(банк\w*|эконом\w*|рынок\w*|бизнес\w*|инвестиц\w*|ритейл\w*)\b", re.I),
    "city": re.compile(r"\b(петербург\w*|москв\w*|город\w*|район\w*|улиц\w*)\b", re.I),
    "geopolitics": re.compile(r"\b(войн\w*|военн\w*|сво|нато|армия|фронт\w*|удар\w*|бпла|минобороны)\b", re.I),
    "news": re.compile(r"\b(срочно|сообщил\w*|заявил\w*|произошл\w*|погиб\w*|пострадал\w*)\b", re.I),
    "viral": re.compile(r"\b(мем\w*|завирус\w*|форс\w*|тикток\w*|tiktok)\b", re.I),
}

CATEGORY_FIT = {
    "art_culture": 1.34, "cinema": 1.30, "technology_ai": 1.30,
    "culture_philosophy": 1.28, "history_literature": 1.23, "science_space": 1.20,
    "design_fashion": 1.18, "marketing_media": 1.12, "music": 1.15,
    "business_economy": 0.90, "city": 0.72, "geopolitics": 0.58,
    "news": 0.58, "viral": 0.70, "culture_misc": 0.88,
}

PULSE_CATEGORIES = {
    "news", "breaking_news", "news_viral", "geopolitics", "viral", "city_news",
}

FAMILY_TARGETS = {
    "art": 12,
    "cinema": 9,
    "technology": 13,
    "ideas": 12,
    "science": 7,
    "design": 6,
    "media": 7,
    "music": 4,
    "business": 5,
    "misc": 10,
    "pulse": 15,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a private personalized Telegram watchlist from a Telegram Desktop export."
    )
    parser.add_argument("--analysis-dir", required=True)
    parser.add_argument("--base-watchlist", default="watchlist.json")
    parser.add_argument("--output", default="watchlist.personal.json")
    parser.add_argument("--report", default="output/personalization_report.md")
    parser.add_argument("--max-channels", type=int, default=DEFAULT_MAX_CHANNELS)
    parser.add_argument("--resolve-limit", type=int, default=DEFAULT_RESOLVE_LIMIT)
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


def classify_title(title: str) -> str:
    for category, pattern in TITLE_RULES:
        if pattern.search(title):
            return category
    return "culture_misc"


def classify_content(title: str, posts: list[dict[str, Any]]) -> str:
    title_category = classify_title(title)
    if title_category != "culture_misc":
        return title_category

    text = "\n".join(str(p.get("text") or "") for p in posts[:5] if p.get("text"))
    if not text:
        return "culture_misc"

    scores: dict[str, float] = {}
    for category, pattern in CONTENT_RULES.items():
        hits = len(pattern.findall(text))
        if hits:
            scores[category] = float(hits)

    if not scores:
        return "culture_misc"

    # News/geopolitics need a clearly dominant signal; otherwise an analytical
    # channel discussing current events would be mislabeled as a newswire.
    best_category, best_score = max(scores.items(), key=lambda kv: kv[1])
    editorial_best = max(
        ((cat, score) for cat, score in scores.items() if cat not in {"news", "geopolitics", "viral", "city"}),
        key=lambda kv: kv[1],
        default=(None, 0.0),
    )
    if best_category in {"news", "geopolitics", "viral", "city"}:
        if best_score < max(4.0, editorial_best[1] * 1.6):
            return editorial_best[0] or "culture_misc"
    return best_category


def family_for_category(category: str) -> str:
    c = str(category or "")
    if c in PULSE_CATEGORIES or c.startswith("news") or c == "geopolitics":
        return "pulse"
    if c.startswith("art") or c in {"soviet_art", "visual_culture"}:
        return "art"
    if c.startswith("cinema") or c in {"games_cinema"}:
        return "cinema"
    if c.startswith("technology") or c.startswith("ai_") or c in {"data_ai", "technology_ai"}:
        return "technology"
    if c.startswith("science") or c in {"culture_science_society"}:
        return "science"
    if c.startswith("design") or c.startswith("fashion") or c == "architecture_history":
        return "design"
    if c.startswith("marketing") or c.startswith("media") or c in {"culture_media"}:
        return "media"
    if c == "music":
        return "music"
    if c.startswith("business") or c.startswith("econom") or c in {"business_economy"}:
        return "business"
    if c.startswith("history") or c.startswith("literature") or c.startswith("philosophy") or c in {
        "culture_philosophy", "philosophy_art", "history_society", "fashion_history",
    }:
        return "ideas"
    return "misc"


def fit_for_category(category: str) -> float:
    if category in CATEGORY_FIT:
        return CATEGORY_FIT[category]
    family = family_for_category(category)
    return {
        "art": 1.30, "cinema": 1.28, "technology": 1.28, "ideas": 1.22,
        "science": 1.20, "design": 1.16, "media": 1.08, "music": 1.12,
        "business": 0.90, "misc": 0.92, "pulse": 0.58,
    }.get(family, 0.9)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def score_candidate(category: str, forwards: int, existing: bool) -> float:
    fit = fit_for_category(category)
    affinity = min(math.log1p(max(forwards, 0)) / math.log1p(400), 1.0)
    score = fit * 3.0 + affinity * 2.25 + (2.5 if existing else 0.0)
    if family_for_category(category) == "pulse":
        score -= 1.15
    return round(score, 4)


async def resolve_one(candidate: dict[str, Any], semaphore: asyncio.Semaphore) -> dict[str, Any]:
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
            return {**candidate, "resolved": False, "resolve_error": f"weak search match ({search_sim:.2f})"}

        try:
            check = await get_posts(username, limit=5)
        except Exception as exc:
            return {**candidate, "resolved": False, "resolve_error": str(exc)}

        actual_title = str(check.get("title") or search_row.get("name") or "")
        actual_sim = title_similarity(title, actual_title)
        if check.get("error") or not check.get("channel"):
            return {**candidate, "resolved": False, "resolve_error": str(check.get("error") or "verification failed")}

        if actual_sim < 0.48 and search_sim < 0.72:
            return {
                **candidate,
                "resolved": False,
                "resolve_error": (
                    f"title mismatch search={search_sim:.2f}, verify={actual_sim:.2f}; got '{actual_title}'"
                ),
            }

        canonical = str(check.get("canonical") or check.get("channel") or f"@{username}").lstrip("@")
        category = classify_content(actual_title or title, check.get("posts") or [])
        result = {
            **candidate,
            "resolved": True,
            "username": canonical,
            "resolved_title": actual_title or title,
            "category": category,
            "family": family_for_category(category),
            "match_score": round(max(search_sim, actual_sim), 3),
            "resolution": "search+verify",
        }
        result["score"] = score_candidate(category, int(result.get("forwards") or 0), False)
        return result


def make_watch_entry(row: dict[str, Any], max_forwards: int) -> dict[str, Any]:
    category = row["category"]
    forwards = int(row.get("forwards") or 0)
    affinity = min(math.log1p(forwards) / math.log1p(max(max_forwards, 1)), 1.0)
    family = family_for_category(category)

    if family == "pulse":
        tier = "accelerator"
        weight = 0.24 + 0.18 * affinity
    elif row.get("existing"):
        tier = str(row.get("base_tier") or "core")
        if tier == "accelerator":
            tier = "radar"
        weight = max(0.75, safe_float(row.get("base_weight"), 0.9))
        weight = min(1.25, weight + 0.08 * affinity)
    elif row["score"] >= 6.0:
        tier = "core"
        weight = 0.92 + 0.20 * affinity
    elif row["score"] >= 5.0:
        tier = "niche"
        weight = 0.86 + 0.18 * affinity
    else:
        tier = "radar"
        weight = 0.70 + 0.16 * affinity

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

    unique = []
    seen = set()
    for row in rows:
        username = str(row.get("username") or "").lower()
        if not username or username in seen:
            continue
        seen.add(username)
        row = dict(row)
        row["family"] = family_for_category(row.get("category", ""))
        unique.append(row)

    # Scale the desired mix for non-100 watchlists.
    target_total = max(1, sum(FAMILY_TARGETS.values()))
    targets = {
        family: max(0, round(limit * count / target_total))
        for family, count in FAMILY_TARGETS.items()
    }
    # Ensure exact total by adjusting misc first, then the largest editorial families.
    delta = limit - sum(targets.values())
    for family in ("misc", "technology", "art", "ideas", "pulse"):
        if delta == 0:
            break
        targets[family] = max(0, targets.get(family, 0) + delta)
        delta = limit - sum(targets.values())

    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in unique:
        by_family[row["family"]].append(row)

    selected: list[dict[str, Any]] = []
    selected_ids = set()
    for family, target in targets.items():
        for row in by_family.get(family, [])[:target]:
            key = str(row["username"]).lower()
            if key not in selected_ids:
                selected.append(row)
                selected_ids.add(key)

    pulse_cap = targets.get("pulse", max(1, round(limit * 0.15)))

    # Fill shortages from editorial sources first. This is the important part:
    # a shortage in cinema/science never becomes 20 more breaking-news channels.
    for row in unique:
        if len(selected) >= limit:
            break
        key = str(row["username"]).lower()
        if key in selected_ids or row["family"] == "pulse":
            continue
        selected.append(row)
        selected_ids.add(key)

    # Only after editorial pool is exhausted may pulse sources fill, and never
    # beyond the hard cap.
    pulse_count = sum(1 for row in selected if row["family"] == "pulse")
    for row in unique:
        if len(selected) >= limit or pulse_count >= pulse_cap:
            break
        key = str(row["username"]).lower()
        if key in selected_ids or row["family"] != "pulse":
            continue
        selected.append(row)
        selected_ids.add(key)
        pulse_count += 1

    return sorted(selected[:limit], key=lambda r: (r["score"], r.get("forwards", 0)), reverse=True)


def build_report(out_path: Path, selected: list[dict[str, Any]], unresolved: list[dict[str, Any]], stats: dict[str, int]) -> None:
    families = Counter(family_for_category(row.get("category", "")) for row in selected)

    lines = [
        "# Personal Telegram watchlist", "",
        "Персонализация построена локально из Telegram Desktop export.", "",
        "## Итог", "",
        f"- Публичных подписок в экспорте: {stats['subscriptions']}",
        f"- Рассмотрено кандидатов: {stats['candidates']}",
        f"- Разрешено @username: {stats['resolved']}",
        f"- Не удалось уверенно разрешить: {stats['unresolved']}",
        f"- Выбрано в watchlist: {len(selected)}", "",
        "## Баланс", "",
        *[f"- {family}: {count}" for family, count in families.most_common()],
        "", "## Выбранные источники", "",
        "| # | Канал | @username | Семья | Категория | Пересылок | Score |",
        "|---:|---|---|---|---|---:|---:|",
    ]
    for i, row in enumerate(selected, 1):
        lines.append(
            f"| {i} | {row.get('resolved_title') or row['title']} | "
            f"@{str(row['username']).lstrip('@')} | {family_for_category(row['category'])} | "
            f"{row['category']} | {row.get('forwards', 0)} | {row['score']:.2f} |"
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

    # Reuse already resolved private mappings when possible. This makes a second
    # personalization run after a scoring tweak much faster.
    personal_by_title: dict[str, dict[str, Any]] = {}
    if output_path.exists():
        try:
            old_personal = load_json(output_path)
            personal_by_title = {
                norm(r.get("title", "")): r
                for r in old_personal.get("channels", [])
                if r.get("title") and r.get("username")
            }
        except Exception:
            personal_by_title = {}

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
        reused_row = personal_by_title.get(key)
        forwards = forward_map.get(key, 0)

        if existing_row:
            category = str(existing_row.get("category") or classify_title(title))
            resolved = bool(existing_row.get("username"))
            username = existing_row.get("username")
            resolved_title = existing_row.get("title") or title
            resolution = "base_watchlist"
        elif reused_row:
            category = classify_title(reused_row.get("title") or title)
            resolved = True
            username = reused_row.get("username")
            resolved_title = reused_row.get("title") or title
            resolution = "previous_personal"
        else:
            category = classify_title(title)
            resolved = False
            username = None
            resolved_title = None
            resolution = None

        score = score_candidate(category, forwards, bool(existing_row))
        candidates.append({
            "title": title,
            "forwards": forwards,
            "score": score,
            "category": category,
            "family": family_for_category(category),
            "fit": fit_for_category(category),
            "existing": bool(existing_row),
            "username": username,
            "resolved_title": resolved_title,
            "base_tier": (existing_row or {}).get("tier"),
            "base_weight": (existing_row or {}).get("weight"),
            "resolved": resolved,
            "resolution": resolution,
        })

    candidates.sort(key=lambda r: (r["score"], r["forwards"]), reverse=True)
    known = [r for r in candidates if r.get("resolved")]
    unknown = [r for r in candidates if not r.get("resolved")][: max(args.resolve_limit, 0)]

    print(f"Public subscriptions: {len(subscriptions)}")
    print(f"Already resolved/reused: {len(known)}")
    print(f"Resolving top unknown subscriptions: {len(unknown)}")
    if unknown:
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
            "Private personalized editorial watchlist generated locally from Telegram subscriptions "
            "and forwarding history. Editorial families are quota-balanced; mass news/geopolitics "
            "are capped so they cannot dominate the radar. Do not commit this file."
        ),
        "channels": watch_channels,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    build_report(
        report_path, selected, unresolved,
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
