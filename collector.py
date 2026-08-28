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
    "более", "будет", "будут", "была", "были", "было", "быть", "вас", "ведь",
    "весь", "всего", "всегда", "всем", "всех", "где", "даже", "день", "для",
    "если", "есть", "ещё", "здесь", "из-за", "или", "именно", "когда", "который",
    "которая", "которые", "между", "меня", "может", "можно", "надо", "написал",
    "нашей", "него", "несколько", "новый", "очень", "первый", "пока", "после",
    "потом", "почему", "просто", "сейчас", "себя", "сегодня", "среди", "стал",
    "стала", "своей", "также", "такое", "такой", "того", "только", "тоже",
    "этого", "этой", "этот", "этим", "about", "after", "again", "also", "been",
    "before", "being", "could", "from", "have", "into", "more", "only", "other",
    "over", "some", "than", "that", "their", "them", "there", "these", "they",
    "this", "those", "through", "very", "what", "when", "where", "which", "with",
    "would", "your", "https", "telegram", "forwarded", "view", "views"
}


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


def terms(text: str) -> set[str]:
    tokens = re.findall(r"[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё-]{3,}", text.lower())
    return {token.strip("-") for token in tokens if token not in STOPWORDS}


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
) -> str:
    lines = [
        "# Telegram trend signals",
        "",
        f"Сформировано: {generated_at.strftime('%Y-%m-%d %H:%M UTC')}",
        f"Окно наблюдения: последние {hours} ч.",
        "",
        "> Это сигналы внутри заданного watchlist, а не статистика всего Telegram.",
        "",
        "## Повторяющиеся темы",
        "",
        "| Тема | Каналов | Постов | Просмотров |",
        "|---|---:|---:|---:|",
    ]
    if topics:
        for topic in topics[:25]:
            lines.append(
                f"| {markdown_escape(topic['term'])} | {topic['source_count']} | "
                f"{topic['post_count']} | {topic['views']} |"
            )
    else:
        lines.append("| Недостаточно повторений | 0 | 0 | 0 |")

    lines.extend([
        "",
        "## Горячие публикации",
        "",
        "| Канал | Возраст, ч | Просмотры | Сигнал | Текст |",
        "|---|---:|---:|---:|---|",
    ])
    for post in posts[:25]:
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
    topic_sources: dict[str, set[str]] = defaultdict(set)
    topic_posts: Counter[str] = Counter()
    topic_views: Counter[str] = Counter()

    for channel, result in fetched:
        if result.get("error"):
            errors.append({"username": channel["username"], "error": result["error"]})
        for post in result.get("posts", []):
            published_at = parse_date(post.get("date"))
            if published_at is None or published_at < cutoff:
                continue
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
            }
            posts.append(record)
            for term in terms(text):
                topic_sources[term].add(channel["username"])
                topic_posts[term] += 1
                topic_views[term] += views

    posts.sort(key=lambda row: row["signal_score"], reverse=True)
    topics = [
        {
            "term": term,
            "source_count": len(topic_sources[term]),
            "post_count": topic_posts[term],
            "views": topic_views[term],
            "sources": sorted(topic_sources[term]),
        }
        for term in topic_posts
        if len(topic_sources[term]) >= 2 or topic_posts[term] >= 3
    ]
    topics.sort(
        key=lambda row: (row["source_count"], row["post_count"], row["views"]),
        reverse=True,
    )

    snapshot = {
        "generated_at": generated_at.isoformat(),
        "window_hours": args.hours,
        "watchlist": str(watchlist_path),
        "channels_requested": len(channels),
        "channels_failed": len(errors),
        "posts_collected": len(posts),
        "topics": topics,
        "posts": posts,
        "errors": errors,
    }
    report = build_markdown(generated_at, args.hours, posts, topics, errors)
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
