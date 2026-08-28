from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from tg_mcp.server import get_posts


STOPWORDS = {
    "а", "без", "более", "больше", "будет", "будут", "будто", "была", "были",
    "было", "быть", "был", "бы", "в", "вам", "вас", "ваш", "ведь", "весь",
    "во", "вот", "впрочем", "всегда", "всего", "всем", "всех", "всю", "вы",
    "где", "говорит", "года", "году", "да", "даже", "два", "день", "для", "до",
    "другой", "его", "ее", "ей", "если", "есть", "ещё", "же", "жизнь", "за",
    "зачем", "здесь", "и", "из", "из-за", "или", "им", "именно", "иногда", "их",
    "к", "как", "какая", "какой", "когда", "конечно", "которая", "которого",
    "которой", "которые", "который", "кто", "куда", "ли", "лет", "лучше", "между",
    "меня", "мне", "много", "может", "можно", "мой", "моя", "мы", "на", "над",
    "надо", "написал", "написала", "нас", "наш", "нашей", "не", "него", "нее",
    "ней", "нельзя", "несколько", "нет", "ни", "нибудь", "ним", "них", "ничего",
    "но", "новая", "новое", "новые", "новый", "ну", "о", "об", "один", "она",
    "они", "оно", "от", "очень", "перед", "первый", "по", "пока", "после",
    "потом", "потому", "почти", "почему", "при", "про", "просто", "раз", "разве",
    "сам", "самая", "самые", "самый", "своей", "свою", "себе", "себя", "сейчас",
    "сегодня", "сказал", "сказала", "сообщил", "сообщила", "среди", "стал", "стала", "стали", "стало",
    "сделал", "сделала", "сделать", "так", "также", "такая", "такое", "такой",
    "там", "тебя", "тем", "теперь", "то", "того", "тоже", "только", "том", "тот",
    "три", "тут", "ты", "у", "уж", "уже", "хоть", "чего", "чем", "через", "что",
    "чтобы", "чуть", "эта", "эти", "этим", "этого", "этой", "этом", "этот", "эту",
    "я", "about", "after", "again", "also", "been", "before", "being", "could",
    "from", "have", "into", "more", "only", "other", "over", "some", "than", "that",
    "their", "them", "there", "these", "they", "this", "those", "through", "very",
    "what", "when", "where", "which", "with", "would", "your", "https", "telegram",
    "forwarded", "view", "views", "актер", "актёр", "известная", "известно",
    "известный", "какой-то", "лучший", "прекрасный", "ролям", "умер", "умерла",
    "фильмах",
}

AD_PATTERNS = (
    re.compile(r"подробнее\s+по\s+ссылке", re.IGNORECASE),
    re.compile(r"специальн\w*\s+цен", re.IGNORECASE),
    re.compile(r"\bпромокод\w*\b", re.IGNORECASE),
    re.compile(r"\bскидк\w*\b", re.IGNORECASE),
    re.compile(r"\bвсего\s+за\s+[\d\s]+[₽$€]", re.IGNORECASE),
)

TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9-]*")
ENTITY_RE = re.compile(
    r"\b(?:[A-ZА-ЯЁ]{2,}|[A-ZА-ЯЁ][a-zа-яё]{2,})"
    r"(?:[\s-]+(?:[A-ZА-ЯЁ]{2,}|[A-ZА-ЯЁ][a-zа-яё]{2,})){1,3}\b"
)
SENTENCE_SPLIT_RE = re.compile(r"[.!?;\n]+")
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect public Telegram trend signals")
    parser.add_argument("--watchlist", default="watchlist.json")
    parser.add_argument("--hours", type=int, default=48)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--output", default="output")
    return parser.parse_args()


def parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def normalize_token(value: str) -> str:
    return value.lower().replace("ё", "е").strip("-")


def meaningful_token(raw: str) -> tuple[str, str] | None:
    normalized = normalize_token(raw)
    if not normalized or normalized in STOPWORDS or normalized.isdigit():
        return None
    if (
        len(normalized) >= 4
        or (len(normalized) >= 3 and raw[:1].isupper())
        or (len(normalized) >= 2 and (raw.isupper() or any(char.isdigit() for char in raw)))
    ):
        return raw.strip("-"), normalized
    return None


def looks_like_ad(text: str) -> bool:
    return any(pattern.search(text) for pattern in AD_PATTERNS)


def text_for_analysis(text: str, channel_title: str) -> str:
    title = normalize_token(channel_title)
    kept_lines = []
    for line in text.splitlines():
        normalized_line = normalize_token(line)
        if title and title in normalized_line and len(normalized_line) <= len(title) + 20:
            continue
        kept_lines.append(line)
    return "\n".join(kept_lines).strip()


def topic_candidates(text: str) -> dict[str, dict[str, Any]]:
    cleaned = URL_RE.sub(" ", text)
    candidates: dict[str, dict[str, Any]] = {}

    for segment in SENTENCE_SPLIT_RE.split(cleaned):
        items = [item for raw in TOKEN_RE.findall(segment) if (item := meaningful_token(raw))]
        for size in (2, 3):
            if len(items) < size:
                continue
            for start in range(len(items) - size + 1):
                chunk = items[start : start + size]
                normalized = tuple(item[1] for item in chunk)
                key = "ng:" + " ".join(normalized)
                candidates.setdefault(
                    key,
                    {
                        "label": " ".join(item[0] for item in chunk),
                        "terms": frozenset(normalized),
                        "phrase_length": size,
                        "kind": "phrase" if size > 1 else "keyword",
                    },
                )

    for match in ENTITY_RE.finditer(cleaned):
        raw_tokens = TOKEN_RE.findall(match.group(0))
        items = [item for raw in raw_tokens if (item := meaningful_token(raw))]
        if len(items) < 2:
            continue
        last = items[-1][1]
        if len(last) < 4:
            continue
        key = "entity:" + last
        candidates.setdefault(
            key,
            {
                "label": " ".join(item[0] for item in items),
                "terms": frozenset(item[1] for item in items),
                "phrase_length": len(items),
                "kind": "entity",
            },
        )

    return candidates


def extract_topics(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    topic_sources: dict[str, set[str]] = defaultdict(set)
    topic_posts: Counter[str] = Counter()
    topic_views: Counter[str] = Counter()
    topic_signal: Counter[str] = Counter()
    topic_labels: dict[str, Counter[str]] = defaultdict(Counter)
    topic_meta: dict[str, dict[str, Any]] = {}
    topic_examples: dict[str, list[dict[str, Any]]] = defaultdict(list)

    seen_texts: set[tuple[str, str]] = set()
    for post in posts:
        original_text = str(post.get("text") or "").strip()
        text = text_for_analysis(original_text, str(post.get("channel_title") or ""))
        if not text or post.get("is_probable_ad") or looks_like_ad(text):
            continue
        fingerprint = re.sub(r"\W+", "", normalize_token(text))
        fingerprint_key = (post["channel"], fingerprint)
        if fingerprint_key in seen_texts:
            continue
        seen_texts.add(fingerprint_key)
        for key, candidate in topic_candidates(text).items():
            channel_title = normalize_token(str(post.get("channel_title") or ""))
            if channel_title and channel_title in normalize_token(candidate["label"]):
                continue
            topic_sources[key].add(post["channel"])
            topic_posts[key] += 1
            topic_views[key] += safe_int(post.get("views"))
            topic_signal[key] += float(post.get("signal_score") or 0)
            topic_labels[key][candidate["label"]] += 1
            topic_meta.setdefault(key, candidate)
            topic_examples[key].append(post)

    topics: list[dict[str, Any]] = []
    for key, post_count in topic_posts.items():
        meta = topic_meta[key]
        source_count = len(topic_sources[key])
        if source_count < 2 and not (meta["phrase_length"] >= 2 and post_count >= 3):
            continue
        label = max(topic_labels[key], key=lambda value: (topic_labels[key][value], len(value)))
        score = (
            4.0 * max(source_count - 1, 0)
            + 2.0 * min(post_count, 5)
            + 2.5 * max(meta["phrase_length"] - 1, 0)
            + math.log10(topic_views[key] + 10)
            + min(topic_signal[key], 25.0) / 10.0
        )
        examples = sorted(
            topic_examples[key], key=lambda row: float(row.get("signal_score") or 0), reverse=True
        )[:3]
        topics.append(
            {
                "term": label,
                "source_count": source_count,
                "post_count": post_count,
                "views": topic_views[key],
                "score": round(score, 3),
                "sources": sorted(topic_sources[key]),
                "kind": meta["kind"],
                "examples": [
                    {
                        "channel": row["channel"],
                        "channel_title": row["channel_title"],
                        "link": row.get("link"),
                        "text": str(row.get("text") or "")[:240],
                    }
                    for row in examples
                ],
                "_terms": meta["terms"],
                "_post_keys": frozenset(
                    (row["channel"], str(row.get("id") or row.get("link") or ""))
                    for row in topic_examples[key]
                ),
            }
        )

    topics.sort(
        key=lambda row: (row["score"], row["source_count"], row["post_count"], row["views"]),
        reverse=True,
    )

    selected: list[dict[str, Any]] = []
    seen_labels: set[str] = set()
    for topic in topics:
        normalized_label = normalize_token(topic["term"])
        if normalized_label in seen_labels:
            continue
        duplicate = False
        for accepted in selected:
            if (
                topic["_post_keys"] <= accepted["_post_keys"]
                or (
                    topic["_terms"] < accepted["_terms"]
                    and topic["sources"] == accepted["sources"]
                    and topic["post_count"] <= accepted["post_count"] + 1
                )
            ):
                duplicate = True
                break
        if duplicate:
            continue
        seen_labels.add(normalized_label)
        selected.append(topic)
        if len(selected) >= 50:
            break
    for topic in selected:
        topic.pop("_terms", None)
        topic.pop("_post_keys", None)
    return selected


async def fetch_channel(
    channel: dict[str, Any], limit: int, semaphore: asyncio.Semaphore
) -> tuple[dict[str, Any], dict[str, Any]]:
    async with semaphore:
        result = await get_posts(channel["username"], limit=limit)
        return channel, result


def markdown_escape(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def build_markdown(
    generated_at: datetime,
    hours: int,
    posts: list[dict[str, Any]],
    topics: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    channel_stats: list[dict[str, Any]],
) -> str:
    channels_with_posts = sum(1 for row in channel_stats if row["posts_in_window"] > 0)
    hot_posts = [
        post for post in posts if str(post.get("text") or "").strip() and not post.get("is_probable_ad")
    ]
    lines = [
        "# Telegram trend signals",
        "",
        f"Сформировано: {generated_at.strftime('%Y-%m-%d %H:%M UTC')}",
        f"Окно наблюдения: последние {hours} ч.",
        "",
        "> Это сигналы внутри заданного watchlist, а не статистика всего Telegram.",
        "",
        "## Покрытие",
        "",
        f"- Запрошено каналов: {len(channel_stats)}",
        f"- Каналов с публикациями в окне: {channels_with_posts}",
        f"- Собрано публикаций: {len(posts)}",
        f"- Ошибок источников: {len(errors)}",
        "",
        "## Растущие сюжеты",
        "",
        "| Сюжет | Каналов | Постов | Просмотров | Сигнал | Примеры |",
        "|---|---:|---:|---:|---:|---|",
    ]
    if topics:
        for topic in topics[:25]:
            examples = " · ".join(
                f"[{markdown_escape(example['channel_title'])}]({example['link']})"
                for example in topic.get("examples", [])
                if example.get("link")
            )
            lines.append(
                f"| {markdown_escape(topic['term'])} | {topic['source_count']} | "
                f"{topic['post_count']} | {topic['views']} | {topic['score']:.2f} | {examples} |"
            )
    else:
        lines.append("| Недостаточно повторений | 0 | 0 | 0 | 0 | |")

    lines.extend([
        "",
        "## Горячие публикации",
        "",
        "| Канал | Возраст, ч | Просмотры | Сигнал | Текст |",
        "|---|---:|---:|---:|---|",
    ])
    for post in hot_posts[:25]:
        text = markdown_escape(post["text"])[:220]
        label = f"[{markdown_escape(post['channel_title'])}]({post['link']})" if post.get("link") else markdown_escape(post["channel_title"])
        lines.append(
            f"| {label} | {post['age_hours']:.1f} | {post['views']} | "
            f"{post['signal_score']:.3f} | {text} |"
        )

    if errors:
        lines.extend(["", "## Ошибки источников", ""])
        for error in errors:
            lines.append(f"- @{error['username']}: {markdown_escape(error['error'])}")

    lines.append("")
    return "\n".join(lines)


async def collect(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    watchlist_path = Path(args.watchlist).resolve()
    payload = json.loads(watchlist_path.read_text(encoding="utf-8"))
    channels = [row for row in payload["channels"] if row.get("enabled", True)]
    generated_at = datetime.now(timezone.utc)
    cutoff = generated_at - timedelta(hours=max(args.hours, 1))
    semaphore = asyncio.Semaphore(max(args.concurrency, 1))

    fetched = await asyncio.gather(
        *(fetch_channel(channel, args.limit, semaphore) for channel in channels)
    )

    posts: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    channel_stats: list[dict[str, Any]] = []

    for channel, result in fetched:
        if result.get("error"):
            errors.append({"username": channel["username"], "error": result["error"]})
        posts_in_window = 0
        for post in result.get("posts", []):
            published_at = parse_date(post.get("date"))
            if published_at is None or published_at < cutoff:
                continue
            posts_in_window += 1
            views = safe_int(post.get("views"))
            age_hours = max((generated_at - published_at).total_seconds() / 3600, 0.25)
            weight = float(channel.get("weight", 1.0))
            signal_score = weight * math.log1p(views) / math.sqrt(max(age_hours, 1.0))
            text = str(post.get("text") or "").strip()
            record = {
                "channel": channel["username"],
                "channel_title": channel["title"],
                "category": channel["category"],
                "tier": channel["tier"],
                "id": post.get("id"),
                "date": published_at.isoformat(),
                "age_hours": round(age_hours, 3),
                "views": views,
                "signal_score": round(signal_score, 6),
                "text": text,
                "link": post.get("link") or f"https://t.me/{channel['username']}/{post.get('id', '')}",
                "is_probable_ad": looks_like_ad(text),
            }
            posts.append(record)
        channel_stats.append(
            {
                "username": channel["username"],
                "title": channel["title"],
                "category": channel["category"],
                "tier": channel["tier"],
                "posts_returned": len(result.get("posts", [])),
                "posts_in_window": posts_in_window,
                "error": result.get("error"),
            }
        )

    posts.sort(key=lambda row: row["signal_score"], reverse=True)
    topics = extract_topics(posts)

    snapshot = {
        "generated_at": generated_at.isoformat(),
        "window_hours": args.hours,
        "watchlist": str(watchlist_path),
        "channels_requested": len(channels),
        "channels_failed": len(errors),
        "channels_with_posts": sum(1 for row in channel_stats if row["posts_in_window"] > 0),
        "posts_collected": len(posts),
        "channel_stats": channel_stats,
        "topics": topics,
        "posts": posts,
        "errors": errors,
    }
    report = build_markdown(generated_at, args.hours, posts, topics, errors, channel_stats)
    return snapshot, report


def main() -> int:
    args = parse_args()
    snapshot, report = asyncio.run(collect(args))
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    json_path = output_dir / f"snapshot_{stamp}.json"
    md_path = output_dir / f"report_{stamp}.md"
    json_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(report, encoding="utf-8")
    (output_dir / "latest.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "latest.md").write_text(report, encoding="utf-8")
    print(f"Collected {snapshot['posts_collected']} posts; failed channels: {snapshot['channels_failed']}")
    print(md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
