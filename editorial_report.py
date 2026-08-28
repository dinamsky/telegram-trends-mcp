from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

GENERIC_TOPIC_WORDS = {
    "речь", "идет", "идёт", "этому", "поводу", "нынешней", "ситуации", "первую", "очередь",
    "часть", "средств", "стоимостью", "рублей", "сентября", "товары", "покупатели", "остаётся",
    "остается", "уповать", "чудо", "данные", "стало", "стали", "может", "будет", "после",
    "перед", "теперь", "сегодня", "вчера", "людей", "человек", "время", "года", "году", "мире",
    "россии", "россия", "истории", "жизни", "работы", "работа", "главное", "новые", "новой",
    "сообщил", "заявил", "заявила", "рассказал", "рассказала", "около", "число", "погибших",
    "московской", "области", "самом", "деле", "очень", "большие", "усилия", "сейчас",
    "сосредоточены", "изучении",
}

GENERIC_TOPIC_PHRASES = {
    "самом деле",
    "искусственного интеллекта",
    "речь идет",
    "речь идёт",
    "этому поводу",
    "первую очередь",
    "нынешней ситуации",
    "часть средств",
    "стоимостью рублей",
    "московской области",
    "число погибших",
}

CATEGORY_FIT = {
    "art_history": 1.35, "art_counterculture": 1.40, "art_memes": 1.25,
    "soviet_art": 1.30, "visual_culture": 1.20, "culture": 1.25,
    "culture_philosophy": 1.30, "culture_science_society": 1.25, "culture_media": 1.10,
    "technology": 1.30, "technology_culture": 1.40, "technology_science": 1.20,
    "technology_internet_culture": 1.35, "technology_memes": 1.20,
    "philosophy_art": 1.25, "history_society": 1.15, "fashion_history": 1.20,
    "fashion_culture": 1.15, "cinema": 1.25, "architecture_history": 1.15,
    "marketing": 1.10, "viral": 0.78, "news": 0.65, "breaking_news": 0.48,
    "news_viral": 0.55, "geopolitics": 0.70,
}

TIER_FIT = {"niche": 1.18, "core": 1.08, "accelerator": 0.82}

INTEREST_RE = re.compile(
    r"\b(ai|ии|нейросет\w*|искусственн\w+ интеллект\w*|робот\w*|модель\w*|open.?source|опенсорс\w*|"
    r"искусств\w*|худож\w*|галере\w*|музе\w*|архитектур\w*|дизайн\w*|кино|фильм\w*|сериал\w*|"
    r"игр\w*|gta|музык\w*|техно|философ\w*|истори\w*|культур\w*|эксперимент\w*|исследован\w*|"
    r"необыч\w*|перв\w+ в мире|впервые|странн\w*|абсурд\w*|мем\w*)\b",
    re.IGNORECASE,
)
AD_RE = re.compile(r"(промокод|скидк|специальн\w* цен|подробнее по ссылке|купить|заказать|реклама)", re.I)
WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9-]+")
TECH_RE = re.compile(
    r"нейросет|искусственн\w+ интеллект|\bAI\b|модель|опенсорс|open.?source|робот|"
    r"транзистор|процессор|чип|нанометр|3d|кодинг|агентск|gpu|монитор|герц|hz|hugging face",
    re.I,
)
ART_RE = re.compile(r"искусств|худож|галере|музе|авангард|живопис|скульптур|вернисаж", re.I)
CINEMA_RE = re.compile(r"кино|фильм|сериал|режисс|акт[её]р|сценар", re.I)
SCIENCE_RE = re.compile(r"эксперимент|исследован|уч[её]н|университет|лаборатор", re.I)


def esc(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def norm(value: str) -> str:
    return " ".join(word.lower().replace("ё", "е") for word in WORD_RE.findall(value))


def topic_quality(topic: dict[str, Any]) -> bool:
    term = str(topic.get("term") or "").strip()
    words = WORD_RE.findall(term)
    normalized = norm(term)
    kind = str(topic.get("kind") or "")
    sources = int(topic.get("source_count") or 0)

    if not words or normalized in GENERIC_TOPIC_PHRASES:
        return False
    if len(words) > 8 or len(term) > 90:
        return False
    generic_ratio = sum(word.lower().replace("ё", "е") in GENERIC_TOPIC_WORDS for word in words) / len(words)
    if kind != "entity" and generic_ratio >= 0.5:
        return False
    if len(words) <= 2 and kind != "entity" and generic_ratio > 0:
        return False
    if kind != "entity" and sources < 3 and not INTEREST_RE.search(term):
        return False
    return True


def topic_confidence(topic: dict[str, Any]) -> float:
    if not topic_quality(topic):
        return 0.0
    term = str(topic.get("term") or "").strip()
    words = [word.lower().replace("ё", "е") for word in WORD_RE.findall(term)]
    generic_ratio = sum(word in GENERIC_TOPIC_WORDS for word in words) / len(words)
    kind = str(topic.get("kind") or "")
    sources = int(topic.get("source_count") or 0)
    posts = int(topic.get("post_count") or 0)
    score = float(topic.get("score") or 0)

    confidence = min(sources, 4) * 0.8 + min(posts, 5) * 0.25 + min(score / 20.0, 1.0)
    if kind == "entity":
        confidence += 1.7
    if re.search(r"[A-ZА-ЯЁ]{2,}|[A-Za-z]+\s+[A-Za-z]+|\d", term):
        confidence += 0.8
    if len(words) >= 2 and generic_ratio == 0:
        confidence += 0.7
    confidence -= generic_ratio * 3.0
    return round(confidence, 3)


def topic_title(topic: dict[str, Any]) -> str:
    term = str(topic.get("term") or "").strip()
    words = WORD_RE.findall(term)
    if 1 <= len(words) <= 8 and len(term) <= 90:
        return term
    return " ".join(words[:8])


def editorial_reason(post: dict[str, Any]) -> str:
    text = str(post.get("text") or "")
    category = str(post.get("category") or "")

    if TECH_RE.search(text) or category.startswith("technology"):
        return "AI / технология" if re.search(r"нейросет|искусственн\w+ интеллект|\bAI\b|модель|опенсорс|open.?source|агентск|hugging face", text, re.I) else "технология / инженерия"
    if SCIENCE_RE.search(text) or category == "culture_science_society":
        return "странная наука / исследование"
    if CINEMA_RE.search(text) or category == "cinema":
        return "кино / поп-культура"
    if ART_RE.search(text) or category in {"art_history", "art_counterculture", "art_memes", "soviet_art", "visual_culture", "architecture_history"}:
        return "искусство / культурный контекст"
    if category in {"culture_philosophy", "philosophy_art", "history_society"}:
        return "идея / исторический контекст"
    if category in {"fashion_history", "fashion_culture", "culture", "culture_media"}:
        return "культура / медиа"
    if re.search(r"впервые|первый в мире|необыч|странн|абсурд", text, re.I):
        return "необычный факт / сюжет"
    if category in {"viral", "news_viral"}:
        return "вирусный сюжет"
    if category == "geopolitics":
        return "геополитический сигнал"
    return category.replace("_", " ") or "редакционный сигнал"


def editorial_fit(post: dict[str, Any]) -> float:
    text = str(post.get("text") or "").strip()
    if not text or post.get("is_probable_ad") or AD_RE.search(text):
        return -999.0
    category = str(post.get("category") or "")
    tier = str(post.get("tier") or "")
    signal = max(float(post.get("signal_score") or 0), 0.0)
    views = max(int(post.get("views") or 0), 0)
    age = max(float(post.get("age_hours") or 1), 0.25)

    fit = CATEGORY_FIT.get(category, 1.0) * TIER_FIT.get(tier, 1.0)
    topical = 1.35 if INTEREST_RE.search(text) else 1.0
    length_bonus = 1.10 if 90 <= len(text) <= 1200 else (0.90 if len(text) < 35 else 1.0)
    velocity = math.log1p(views) / math.sqrt(max(age, 1.0))
    raw = (1.6 * fit + 0.75 * topical + 0.16 * signal + 0.08 * velocity) * length_bonus
    return round(raw, 3)


def dedupe_posts(posts: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    per_channel: dict[str, int] = {}
    seen_prefixes: set[str] = set()
    for post in posts:
        if len(selected) >= limit:
            break
        channel = str(post.get("channel") or "")
        if per_channel.get(channel, 0) >= 2:
            continue
        prefix = re.sub(r"\W+", "", str(post.get("text") or "").lower())[:100]
        if prefix and prefix in seen_prefixes:
            continue
        selected.append(post)
        per_channel[channel] = per_channel.get(channel, 0) + 1
        if prefix:
            seen_prefixes.add(prefix)
    return selected


def real_trends(topics: list[dict[str, Any]], limit: int = 15) -> list[dict[str, Any]]:
    rows = []
    for topic in topics:
        if int(topic.get("source_count") or 0) < 2 or not topic_quality(topic):
            continue
        confidence = topic_confidence(topic)
        if confidence < 3.2:
            continue
        row = dict(topic)
        row["confidence"] = confidence
        row["display_title"] = topic_title(topic)
        rows.append(row)
    rows.sort(key=lambda row: (row["confidence"], float(row.get("score") or 0), int(row.get("views") or 0)), reverse=True)
    return rows[:limit]


def editorial_picks(posts: list[dict[str, Any]], limit: int = 15) -> list[dict[str, Any]]:
    rows = []
    for post in posts:
        row = dict(post)
        row["content_fit"] = editorial_fit(post)
        if row["content_fit"] >= 3.0:
            rows.append(row)
    rows.sort(key=lambda row: (row["content_fit"], float(row.get("signal_score") or 0)), reverse=True)
    return dedupe_posts(rows, limit)


def hot_posts(posts: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    rows = [post for post in posts if str(post.get("text") or "").strip() and not post.get("is_probable_ad") and not AD_RE.search(str(post.get("text") or ""))]
    rows.sort(key=lambda row: float(row.get("signal_score") or 0), reverse=True)
    return dedupe_posts(rows, limit)


def examples_md(topic: dict[str, Any]) -> str:
    parts = []
    for example in (topic.get("examples") or [])[:3]:
        title = esc(example.get("channel_title") or example.get("channel"))
        link = example.get("link")
        parts.append(f"[{title}]({link})" if link else title)
    return " · ".join(parts)


def build_report(snapshot: dict[str, Any]) -> str:
    topics = real_trends(snapshot.get("topics") or [])
    picks = editorial_picks(snapshot.get("posts") or [])
    hot = hot_posts(snapshot.get("posts") or [])
    errors = snapshot.get("errors") or []
    channel_stats = snapshot.get("channel_stats") or []
    channels_with_posts = snapshot.get("channels_with_posts")
    if channels_with_posts is None:
        channels_with_posts = sum(1 for row in channel_stats if int(row.get("posts_in_window") or 0) > 0)

    lines = [
        "# Telegram editorial radar", "",
        f"Сформировано: {str(snapshot.get('generated_at') or '')[:16].replace('T', ' ')} UTC",
        f"Окно наблюдения: последние {snapshot.get('window_hours', 48)} ч.", "",
        "> Это редакционный радар внутри заданного watchlist, а не статистика всего Telegram.", "",
        "## Покрытие", "",
        f"- Запрошено каналов: {snapshot.get('channels_requested', len(channel_stats))}",
        f"- Каналов с публикациями в окне: {channels_with_posts}",
        f"- Собрано публикаций: {snapshot.get('posts_collected', len(snapshot.get('posts') or []))}",
        f"- Ошибок источников: {snapshot.get('channels_failed', len(errors))}", "",
        "## Реально растёт", "",
        "| Сюжет | Каналов | Постов | Просмотров | Уверенность | Примеры |",
        "|---|---:|---:|---:|---:|---|",
    ]
    if topics:
        for topic in topics:
            lines.append(f"| {esc(topic['display_title'])} | {topic.get('source_count', 0)} | {topic.get('post_count', 0)} | {topic.get('views', 0)} | {topic['confidence']:.2f} | {examples_md(topic)} |")
    else:
        lines.append("| Пока нет достаточно надёжных повторений | 0 | 0 | 0 | 0 | |")

    lines += ["", "## Стоит написать пост", "", "| Канал | Fit | Просмотры | Возраст, ч | Почему интересно | Публикация |", "|---|---:|---:|---:|---|---|"]
    for post in picks:
        title = esc(post.get("channel_title") or post.get("channel"))
        link = post.get("link")
        channel = f"[{title}]({link})" if link else title
        lines.append(f"| {channel} | {post['content_fit']:.2f} | {post.get('views', 0)} | {float(post.get('age_hours') or 0):.1f} | {editorial_reason(post)} | {esc(post.get('text'))[:260]} |")

    lines += ["", "## Просто горячее", "", "| Канал | Сигнал | Просмотры | Возраст, ч | Публикация |", "|---|---:|---:|---:|---|"]
    for post in hot:
        title = esc(post.get("channel_title") or post.get("channel"))
        link = post.get("link")
        channel = f"[{title}]({link})" if link else title
        lines.append(f"| {channel} | {float(post.get('signal_score') or 0):.3f} | {post.get('views', 0)} | {float(post.get('age_hours') or 0):.1f} | {esc(post.get('text'))[:220]} |")

    if errors:
        lines += ["", "## Ошибки источников", ""]
        for error in errors:
            lines.append(f"- @{esc(error.get('username'))}: {esc(error.get('error'))}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build editorial report from Telegram collector snapshot")
    parser.add_argument("--input", default="output/latest.json")
    parser.add_argument("--output", default="output/latest.md")
    args = parser.parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    snapshot = json.loads(input_path.read_text(encoding="utf-8"))
    output_path.write_text(build_report(snapshot), encoding="utf-8")
    print(f"Editorial report: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
