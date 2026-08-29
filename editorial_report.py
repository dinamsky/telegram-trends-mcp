from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any


GENERIC_TOPIC_WORDS = {
    "речь", "идет", "идёт", "этому", "поводу", "нынешней", "ситуации", "первую", "очередь",
    "часть", "средств", "стоимостью", "рублей", "сентября", "товары", "покупатели", "остается",
    "остаётся", "уповать", "чудо", "данные", "стало", "стали", "может", "будет", "после",
    "перед", "теперь", "сегодня", "вчера", "людей", "человек", "время", "года", "году", "мире",
    "россии", "россия", "истории", "жизни", "работы", "работа", "главное", "новые", "новой",
    "сообщил", "заявил", "заявила", "рассказал", "рассказала", "около", "число", "погибших",
    "московской", "области", "самом", "деле", "очень", "большие", "усилия", "сейчас",
    "сосредоточены", "изучении", "таким", "образом", "данный", "момент", "настоящее",
    "своего", "рода", "друг", "другу", "всему", "миру", "большая", "нашем", "канале",
    "канал", "мах", "тысяч", "млрд",
}

GENERIC_TOPIC_PHRASES = {
    "самом деле", "искусственного интеллекта", "речь идет", "этому поводу",
    "первую очередь", "нынешней ситуации", "часть средств", "стоимостью рублей",
    "московской области", "число погибших", "таким образом", "данный момент",
    "настоящее время", "друг другу", "всему миру", "большая часть", "нашем канале",
    "канал мах", "тысяч рублей", "млрд рублей", "своего рода",
    "банка россии", "государственной думы", "the new york times", "vk видео",
    "боевых действий", "военного врача", "главного героя",
}

CATEGORY_FIT = {
    "art_history": 1.35, "art_counterculture": 1.40, "art_memes": 1.25,
    "soviet_art": 1.30, "visual_culture": 1.25, "art_culture": 1.38,
    "culture": 1.25, "culture_philosophy": 1.32, "culture_science_society": 1.28,
    "culture_media": 1.12, "culture_misc": 1.02,
    "technology": 1.30, "technology_ai": 1.42, "technology_culture": 1.40,
    "technology_science": 1.28, "technology_internet_culture": 1.35,
    "technology_memes": 1.20, "data_ai": 1.32, "ai_technology": 1.40,
    "science": 1.28, "science_space": 1.30, "science_technology": 1.28,
    "philosophy_art": 1.28, "history_society": 1.20, "history_literature": 1.26,
    "literature": 1.26, "literature_culture": 1.28,
    "fashion_history": 1.22, "fashion_culture": 1.18, "design_fashion": 1.22,
    "design_culture": 1.22, "cinema": 1.30, "cinema_industry": 1.25,
    "cinema_popculture": 1.18, "architecture_history": 1.20,
    "marketing": 1.12, "marketing_media": 1.12, "media": 1.03, "media_data": 1.08,
    "music": 1.18, "business_technology": 1.06, "business_media": 0.98,
    "business_economy": 0.90, "economy_society": 0.90, "city_culture": 1.05,
    "history_city": 1.05, "city": 0.78, "city_news": 0.52,
    "viral": 0.72, "news": 0.55, "breaking_news": 0.42,
    "news_viral": 0.50, "geopolitics": 0.58, "news_geopolitics": 0.48,
}

TIER_FIT = {"niche": 1.20, "core": 1.10, "radar": 1.00, "accelerator": 0.72}

PULSE_CATEGORIES = {
    "news", "breaking_news", "news_viral", "geopolitics", "news_geopolitics",
    "city_news",
}

INTEREST_RE = re.compile(
    r"\b(ai|ии|нейросет\w*|искусственн\w+ интеллект\w*|робот\w*|модель\w*|open.?source|"
    r"опенсорс\w*|искусств\w*|худож\w*|галере\w*|музе\w*|архитектур\w*|дизайн\w*|"
    r"кино|фильм\w*|сериал\w*|игр\w*|gta|музык\w*|техно|философ\w*|истори\w*|"
    r"литератур\w*|культур\w*|эксперимент\w*|исследован\w*|наук\w*|космос\w*|"
    r"необыч\w*|перв\w+ в мире|впервые|странн\w*|абсурд\w*|мем\w*)\b",
    re.IGNORECASE,
)

NEWSY_RE = re.compile(
    r"\b(путин|трамп|зеленск\w*|медведев|минобороны|совбез|цру|нато|войн\w*|"
    r"удар\w*|бпла|мобилизац\w*|военн\w*|украин\w*|российск\w+ войск\w*|"
    r"погиб\w*|пострадал\w*|взрыв\w*|атака|обстрел\w*)\b",
    re.IGNORECASE,
)

PULSE_SOURCE_RE = re.compile(
    r"(?:bbbreaking|bloodysx|bazabazon|rybar|mig41|sashakots|new_militarycolumnist|"
    r"infantmilitario|dimsmirnov175|warhistoryalconafter|mash|lentach|rhymes|dvach|"
    r"readovka|brief|militar|kots)",
    re.IGNORECASE,
)

AD_RE = re.compile(
    r"(промокод|скидк|специальн\w* цен|подробнее по ссылке|купить|заказать|реклама)",
    re.I,
)
WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9-]+")
TECH_RE = re.compile(
    r"нейросет|искусственн\w+ интеллект|\bAI\b|модель|опенсорс|open.?source|робот|"
    r"транзистор|процессор|чип|нанометр|3d|кодинг|агентск|gpu|монитор|герц|hz|hugging face",
    re.I,
)
ART_RE = re.compile(r"искусств|худож|галере|музе|авангард|живопис|скульптур|вернисаж", re.I)
CINEMA_RE = re.compile(r"кино|фильм|сериал|режисс|акт[её]р|сценар", re.I)
SCIENCE_RE = re.compile(r"эксперимент|исследован|уч[её]н|университет|лаборатор|наук|космос", re.I)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build editorial Markdown from collector JSON")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def esc(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def norm(value: str) -> str:
    return " ".join(word.lower().replace("ё", "е") for word in WORD_RE.findall(value))


def family_for_category(category: str) -> str:
    c = str(category or "")
    if c in PULSE_CATEGORIES or c.startswith("news") or c == "geopolitics":
        return "pulse"
    if c.startswith("art") or c in {"soviet_art", "visual_culture"}:
        return "art"
    if c.startswith("cinema") or c == "games_cinema":
        return "cinema"
    if c.startswith("technology") or c.startswith("ai_") or c in {"data_ai"}:
        return "technology"
    if c.startswith("science") or c == "culture_science_society":
        return "science"
    if c.startswith("design") or c.startswith("fashion") or c == "architecture_history":
        return "design"
    if c.startswith("marketing") or c.startswith("media") or c == "culture_media":
        return "media"
    if c == "music":
        return "music"
    if c.startswith("history") or c.startswith("literature") or c.startswith("philosophy") or c in {
        "culture_philosophy", "philosophy_art",
    }:
        return "ideas"
    if c.startswith("business") or c.startswith("econom"):
        return "business"
    if c.startswith("city"):
        return "city"
    if c == "viral":
        return "viral"
    return "misc"


def is_pulse_post(post: dict[str, Any]) -> bool:
    return family_for_category(str(post.get("category") or "")) == "pulse"


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
        confidence += 1.4
    if re.search(r"[A-ZА-ЯЁ]{2,}|[A-Za-z]+\s+[A-Za-z]+|\d", term):
        confidence += 0.7
    if len(words) >= 2 and generic_ratio == 0:
        confidence += 0.6
    confidence -= generic_ratio * 3.0
    return round(confidence, 3)


def topic_title(topic: dict[str, Any]) -> str:
    term = str(topic.get("term") or "").strip()
    words = WORD_RE.findall(term)
    if 1 <= len(words) <= 8 and len(term) <= 90:
        return term
    return " ".join(words[:8])


def topic_is_pulse(topic: dict[str, Any]) -> bool:
    sources = [str(v or "") for v in (topic.get("sources") or [])]
    pulse_sources = sum(bool(PULSE_SOURCE_RE.search(source)) for source in sources)
    text = " ".join(
        [str(topic.get("term") or "")]
        + [str(e.get("text") or "") for e in (topic.get("examples") or [])[:3]]
    )
    interest = bool(INTEREST_RE.search(text))
    newsy = bool(NEWSY_RE.search(text))
    term = str(topic.get("term") or "")
    term_newsy = bool(NEWSY_RE.search(term))
    term_interest = bool(INTEREST_RE.search(term))

    if term_newsy and not term_interest:
        return True
    if sources and pulse_sources / len(sources) >= 0.6 and not interest:
        return True
    if newsy and not interest and pulse_sources >= 1:
        return True
    return False


def dedupe_trends(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for row in rows:
        row_sources = set(str(v) for v in (row.get("sources") or []))
        row_links = set(
            str(e.get("link")) for e in (row.get("examples") or []) if e.get("link")
        )
        row_tokens = {
            w for w in norm(str(row.get("term") or "")).split()
            if len(w) >= 4 and w not in GENERIC_TOPIC_WORDS
        }
        duplicate = False
        for accepted in selected:
            acc_sources = set(str(v) for v in (accepted.get("sources") or []))
            union = row_sources | acc_sources
            source_jaccard = len(row_sources & acc_sources) / max(len(union), 1)
            acc_links = set(
                str(e.get("link")) for e in (accepted.get("examples") or []) if e.get("link")
            )
            acc_tokens = {
                w for w in norm(str(accepted.get("term") or "")).split()
                if len(w) >= 4 and w not in GENERIC_TOPIC_WORDS
            }
            if row_links & acc_links and (source_jaccard >= 0.25 or row_tokens & acc_tokens):
                duplicate = True
                break
            if row_tokens & acc_tokens and source_jaccard >= 0.65:
                duplicate = True
                break
        if not duplicate:
            selected.append(row)
        if len(selected) >= limit:
            break
    return selected


def real_trends(topics: list[dict[str, Any]], limit: int = 15) -> list[dict[str, Any]]:
    editorial: list[dict[str, Any]] = []
    pulse: list[dict[str, Any]] = []

    for topic in topics:
        if int(topic.get("source_count") or 0) < 2 or not topic_quality(topic):
            continue
        confidence = topic_confidence(topic)
        if confidence < 3.2:
            continue
        row = dict(topic)
        row["confidence"] = confidence
        row["display_title"] = topic_title(topic)
        row["pulse"] = topic_is_pulse(topic)

        combined = " ".join(
            [str(row.get("term") or "")]
            + [str(e.get("text") or "") for e in (row.get("examples") or [])[:3]]
        )
        interest_bonus = 0.9 if INTEREST_RE.search(combined) else 0.0
        row["_rank"] = confidence + interest_bonus
        (pulse if row["pulse"] else editorial).append(row)

    key = lambda row: (
        float(row.get("_rank") or 0),
        float(row.get("score") or 0),
        int(row.get("views") or 0),
    )
    editorial.sort(key=key, reverse=True)
    pulse.sort(key=key, reverse=True)

    pulse_cap = min(3, max(1, limit // 5))
    result = editorial[:limit]
    remaining_pulse = min(pulse_cap, max(0, limit - len(result)))
    result.extend(pulse[:remaining_pulse])
    result = dedupe_trends(result, limit)
    for row in result:
        row.pop("_rank", None)
    return result[:limit]


def pulse_trends(topics: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    rows = []
    for topic in topics:
        if not topic_quality(topic) or not topic_is_pulse(topic):
            continue
        confidence = topic_confidence(topic)
        if confidence < 3.0:
            continue
        row = dict(topic)
        row["confidence"] = confidence
        row["display_title"] = topic_title(topic)
        rows.append(row)
    rows.sort(
        key=lambda row: (
            row["confidence"], float(row.get("score") or 0), int(row.get("views") or 0)
        ),
        reverse=True,
    )
    return rows[:limit]


def editorial_reason(post: dict[str, Any]) -> str:
    text = str(post.get("text") or "")
    category = str(post.get("category") or "")
    family = family_for_category(category)

    if TECH_RE.search(text) or family == "technology":
        return "AI / технология" if re.search(
            r"нейросет|искусственн\w+ интеллект|\bAI\b|модель|опенсорс|open.?source|агентск|hugging face",
            text, re.I
        ) else "технология / инженерия"
    if SCIENCE_RE.search(text) or family == "science":
        return "странная наука / исследование"
    if CINEMA_RE.search(text) or family == "cinema":
        return "кино / поп-культура"
    if ART_RE.search(text) or family == "art":
        return "искусство / культурный контекст"
    if family == "ideas":
        return "идея / исторический контекст"
    if family == "design":
        return "дизайн / визуальная культура"
    if family == "media":
        return "медиа / маркетинг"
    if family == "music":
        return "музыка / сцена"
    if re.search(r"впервые|первый в мире|необыч|странн|абсурд", text, re.I):
        return "необычный факт / сюжет"
    if family == "viral":
        return "вирусный сюжет"
    if family == "pulse":
        return "новостной / геополитический сигнал"
    if family == "business":
        return "бизнес / экономика"
    return "культура / наблюдение"


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
    length_bonus = 1.10 if 90 <= len(text) <= 1400 else (0.88 if len(text) < 35 else 1.0)
    velocity = math.log1p(views) / math.sqrt(max(age, 1.0))
    pulse_penalty = 0.70 if is_pulse_post(post) else 1.0
    raw = (1.8 * fit + 0.82 * topical + 0.13 * signal + 0.055 * velocity) * length_bonus * pulse_penalty
    return round(raw, 3)


def dedupe_posts(posts: list[dict[str, Any]], limit: int, per_channel_limit: int = 2) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    per_channel: dict[str, int] = {}
    seen_prefixes: set[str] = set()
    for post in posts:
        if len(selected) >= limit:
            break
        channel = str(post.get("channel") or "")
        if per_channel.get(channel, 0) >= per_channel_limit:
            continue
        prefix = re.sub(r"\W+", "", str(post.get("text") or "").lower())[:120]
        if prefix and prefix in seen_prefixes:
            continue
        selected.append(post)
        per_channel[channel] = per_channel.get(channel, 0) + 1
        if prefix:
            seen_prefixes.add(prefix)
    return selected


def editorial_picks(posts: list[dict[str, Any]], limit: int = 15) -> list[dict[str, Any]]:
    rows = []
    for post in posts:
        row = dict(post)
        row["content_fit"] = editorial_fit(post)
        if row["content_fit"] >= 3.0:
            row["_family"] = family_for_category(str(row.get("category") or ""))
            rows.append(row)
    rows.sort(
        key=lambda row: (row["content_fit"], float(row.get("signal_score") or 0)),
        reverse=True,
    )

    selected: list[dict[str, Any]] = []
    family_counts: Counter[str] = Counter()
    channel_counts: Counter[str] = Counter()
    seen_prefixes: set[str] = set()

    for row in rows:
        if len(selected) >= limit:
            break
        family = row["_family"]
        family_cap = 2 if family == "pulse" else 3
        if family_counts[family] >= family_cap:
            continue
        channel = str(row.get("channel") or "")
        if channel_counts[channel] >= 2:
            continue
        prefix = re.sub(r"\W+", "", str(row.get("text") or "").lower())[:120]
        if prefix and prefix in seen_prefixes:
            continue
        selected.append(row)
        family_counts[family] += 1
        channel_counts[channel] += 1
        if prefix:
            seen_prefixes.add(prefix)

    if len(selected) < limit:
        chosen = {str(r.get("link") or "") for r in selected}
        for row in rows:
            if len(selected) >= limit:
                break
            if str(row.get("link") or "") in chosen:
                continue
            if row["_family"] == "pulse" and family_counts["pulse"] >= 2:
                continue
            selected.append(row)
            family_counts[row["_family"]] += 1
            chosen.add(str(row.get("link") or ""))

    for row in selected:
        row.pop("_family", None)
    return selected[:limit]


def hot_posts(posts: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    rows = [
        post for post in posts
        if str(post.get("text") or "").strip()
        and not post.get("is_probable_ad")
        and not AD_RE.search(str(post.get("text") or ""))
        and not is_pulse_post(post)
    ]
    rows.sort(key=lambda row: float(row.get("signal_score") or 0), reverse=True)
    return dedupe_posts(rows, limit)


def pulse_posts(posts: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    rows = [
        post for post in posts
        if str(post.get("text") or "").strip()
        and not post.get("is_probable_ad")
        and not AD_RE.search(str(post.get("text") or ""))
        and is_pulse_post(post)
    ]
    rows.sort(key=lambda row: float(row.get("signal_score") or 0), reverse=True)
    return dedupe_posts(rows, limit, per_channel_limit=1)


def examples_md(topic: dict[str, Any]) -> str:
    parts = []
    for example in (topic.get("examples") or [])[:3]:
        title = esc(example.get("channel_title") or example.get("channel"))
        link = example.get("link")
        parts.append(f"[{title}]({link})" if link else title)
    return " · ".join(parts)


def post_line(post: dict[str, Any], include_fit: bool = False) -> str:
    channel = esc(post.get("channel_title") or post.get("channel"))
    link = post.get("link")
    title = f"[{channel}]({link})" if link else channel
    text = esc(str(post.get("text") or "")[:260])
    extra = f" · fit {float(post.get('content_fit') or 0):.2f}" if include_fit else ""
    return f"- **{title}** — {editorial_reason(post)}{extra}: {text}"


def build_report(snapshot: dict[str, Any]) -> str:
    raw_topics = snapshot.get("topics") or []
    posts = snapshot.get("posts") or []
    topics = real_trends(raw_topics)
    pulse_topic_rows = pulse_trends(raw_topics)
    picks = editorial_picks(posts)
    hot = hot_posts(posts)
    pulse = pulse_posts(posts)
    errors = snapshot.get("errors") or []
    channel_stats = snapshot.get("channel_stats") or []
    channels_with_posts = snapshot.get("channels_with_posts")
    if channels_with_posts is None:
        channels_with_posts = sum(1 for row in channel_stats if int(row.get("posts_in_window") or 0) > 0)

    lines = [
        "# Telegram editorial radar", "",
        f"Сформировано: {str(snapshot.get('generated_at') or '')[:16].replace('T', ' ')} UTC",
        f"Окно наблюдения: последние {snapshot.get('window_hours', 48)} ч.", "",
        "> Основной радар намеренно смещён от новостной ленты к темам для авторского поста. Массовые новости вынесены отдельно.", "",
        "## Покрытие", "",
        f"- Запрошено каналов: {snapshot.get('channels_requested', len(channel_stats))}",
        f"- Каналов с публикациями в окне: {channels_with_posts}",
        f"- Собрано публикаций: {snapshot.get('posts_collected', len(posts))}",
        f"- Ошибок источников: {snapshot.get('channels_failed', len(errors))}", "",
        "## Реально растёт — редакционные темы", "",
    ]

    if topics:
        lines += [
            "| Тема | Каналы | Посты | Просмотры | Confidence | Примеры |",
            "|---|---:|---:|---:|---:|---|",
        ]
        for topic in topics:
            lines.append(
                f"| {esc(topic.get('display_title') or topic.get('term'))} | "
                f"{topic.get('source_count', 0)} | {topic.get('post_count', 0)} | "
                f"{topic.get('views', 0)} | {float(topic.get('confidence') or 0):.2f} | "
                f"{examples_md(topic)} |"
            )
    else:
        lines.append("Нет достаточно сильных редакционных сюжетов в этом окне.")

    lines += ["", "## Стоит написать пост", ""]
    if picks:
        lines.extend(post_line(post, include_fit=True) for post in picks)
    else:
        lines.append("Нет публикаций с достаточным editorial fit.")

    lines += ["", "## Горячее вне новостной ленты", ""]
    if hot:
        lines.extend(post_line(post) for post in hot[:15])
    else:
        lines.append("Нет подходящих публикаций.")

    lines += ["", "## Новостной пульс — отдельно", ""]
    if pulse_topic_rows:
        lines += [
            "| Сюжет | Каналы | Посты | Просмотры |",
            "|---|---:|---:|---:|",
        ]
        for topic in pulse_topic_rows:
            lines.append(
                f"| {esc(topic.get('display_title') or topic.get('term'))} | "
                f"{topic.get('source_count', 0)} | {topic.get('post_count', 0)} | {topic.get('views', 0)} |"
            )
    if pulse:
        lines += ["", "Самые быстрые публикации:"]
        lines.extend(post_line(post) for post in pulse[:8])

    if errors:
        lines += ["", "## Ошибки источников", ""]
        for err in errors[:20]:
            lines.append(f"- {esc(err.get('channel') or err.get('username'))}: {esc(err.get('error'))}")

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    args = parse_args()
    snapshot = json.loads(Path(args.input).read_text(encoding="utf-8"))
    Path(args.output).write_text(build_report(snapshot), encoding="utf-8")


if __name__ == "__main__":
    main()
