from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import editorial_report as base

# Post-level news classifier. Channel category is only a hint; the actual text wins.
HARD_NEWS_RE = re.compile(
    r"\b(войн\w*|военн\w*|бпла|обстрел\w*|удар\w*|атака|взрыв\w*|пожар\w*|"
    r"погиб\w*|пострадал\w*|мобилизац\w*|минобороны|министерств\w+ оборон\w*|"
    r"пентагон|нато|цру|совбез|вс\s*рф|фронт\w*|детонац\w*|ракет\w*|дрон\w*)\b",
    re.I,
)
POLITICAL_RE = re.compile(
    r"\b(путин|трамп|зеленск\w*|медведев|лавров|рэтклифф|хегсет|президент\w*|"
    r"премьер\w*|министр\w*|госдум\w*|кремл\w*|белый дом)\b",
    re.I,
)
NEWS_STYLE_RE = re.compile(
    r"\b(сообщил\w*|заявил\w*|объявил\w*|подписал\w*|задержан\w*|арестован\w*|"
    r"произош[её]л\w*|срочно|официальн\w+ лиц\w*|власти|правительств\w*|"
    r"прокуратур\w*|состоится|подтвердил\w*|по данным|со ссылкой|признал\w*)\b",
    re.I,
)
CURRENT_AFFAIRS_RE = re.compile(
    r"\b(киев\w*|украин\w*|росси\w*|сша|евросоюз|ес|китай\w*|британи\w*|"
    r"германи\w*|франци\w*|израил\w*|иран\w*|армени\w*|москв\w*)\b",
    re.I,
)
NEWS_SOURCE_RE = re.compile(
    r"(?:bbbreaking|bloodysx|bazabazon|rybar|mig41|sashakots|new_militarycolumnist|"
    r"infantmilitario|mash|lentach|rhymes|readovka|brief|militar|kots|stranaua|karaulny)",
    re.I,
)
EDITORIAL_RE = re.compile(
    r"\b(ai|ии|нейросет\w*|искусственн\w+ интеллект\w*|chatgpt|claude|hugging face|"
    r"искусств\w*|худож\w*|галере\w*|музе\w*|авангард\w*|архитектур\w*|дизайн\w*|"
    r"кино|фильм\w*|сериал\w*|gta|игр\w*|музык\w*|концерт\w*|театр\w*|"
    r"философ\w*|истори\w*|литератур\w*|культур\w*|исследован\w*|наук\w*|космос\w*|"
    r"fashion|мод\w*|бренд\w*|ювелир\w*|колье|памятник\w*|маркетинг\w*|мем\w*)\b",
    re.I,
)
TOPIC_STOP = {
    "самом деле", "таким образом", "данный момент", "настоящее время", "первую очередь",
    "речь идет", "искусственный интеллект", "искусственного интеллекта", "реальном времени",
    "крайней мере", "первом полугодии", "крупных городах", "радио россии", "точки зрения",
    "аналитического центра", "годовом выражении", "продавцы смогут самостоятельно",
    "банка россии", "государственной думы", "vk видео", "главного героя", "никаких планов",
}


def post_pulse_score(post: dict[str, Any]) -> float:
    text = str(post.get("text") or "").strip()
    source = f"{post.get('channel','')} {post.get('channel_title','')}"
    category = str(post.get("category") or "")
    hard = len(HARD_NEWS_RE.findall(text))
    political = len(POLITICAL_RE.findall(text))
    style = len(NEWS_STYLE_RE.findall(text))
    source_hint = bool(NEWS_SOURCE_RE.search(source))
    category_hint = base.family_for_category(category) == "pulse"
    editorial = bool(EDITORIAL_RE.search(text))

    score = min(hard, 3) * 1.25 + min(political, 2) * 0.75 + min(style, 2) * 0.65
    score += 0.55 if source_hint else 0.0
    score += 0.35 if category_hint else 0.0
    if source_hint and (hard or political or style):
        score = max(score, 2.45)
    if source_hint and CURRENT_AFFAIRS_RE.search(text) and not editorial:
        score = max(score, 2.30)
    if hard >= 2 or (hard and style) or (political and style):
        score = max(score, 2.60)
    if editorial and not hard and not political:
        score -= 0.85
    return round(score, 3)


def is_pulse_post(post: dict[str, Any]) -> bool:
    return post_pulse_score(post) >= 2.2


# Make the original scorer use the new post-level classifier too.
base.is_pulse_post = is_pulse_post


def topic_is_pulse(topic: dict[str, Any]) -> bool:
    term = str(topic.get("term") or "")
    if HARD_NEWS_RE.search(term) or POLITICAL_RE.search(term):
        return True
    examples = topic.get("examples") or []
    pseudo = [
        {"text": e.get("text", ""), "channel": e.get("channel", ""), "channel_title": e.get("channel_title", ""), "category": ""}
        for e in examples[:5]
    ]
    if not pseudo:
        return False
    pulse = sum(is_pulse_post(p) for p in pseudo)
    styled = sum(bool(NEWS_STYLE_RE.search(str(p.get("text") or ""))) for p in pseudo)
    return pulse / len(pseudo) >= 0.5 or (len(pseudo) >= 2 and styled / len(pseudo) >= 0.6)


def real_trends(topics: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    rows = []
    for topic in topics:
        term = base.norm(str(topic.get("term") or ""))
        if term in TOPIC_STOP or int(topic.get("source_count") or 0) < 2 or not base.topic_quality(topic):
            continue
        if topic_is_pulse(topic):
            continue
        combined = " ".join([str(topic.get("term") or "")] + [str(e.get("text") or "") for e in (topic.get("examples") or [])[:3]])
        if not EDITORIAL_RE.search(combined):
            continue
        confidence = base.topic_confidence(topic)
        if confidence < 3.0:
            continue
        row = dict(topic)
        row["confidence"] = confidence
        row["display_title"] = base.topic_title(topic)
        row["_rank"] = confidence + min(int(row.get("source_count") or 0), 6) * 0.08
        rows.append(row)
    rows.sort(key=lambda r: (r["_rank"], float(r.get("score") or 0), int(r.get("views") or 0)), reverse=True)
    rows = base.dedupe_trends(rows, limit)
    for row in rows:
        row.pop("_rank", None)
    return rows[:limit]


def pulse_trends(topics: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    rows = []
    for topic in topics:
        if not base.topic_quality(topic) or not topic_is_pulse(topic):
            continue
        confidence = base.topic_confidence(topic)
        if confidence < 2.8:
            continue
        row = dict(topic)
        row["confidence"] = confidence
        row["display_title"] = base.topic_title(topic)
        rows.append(row)
    rows.sort(key=lambda r: (r["confidence"], float(r.get("score") or 0), int(r.get("views") or 0)), reverse=True)
    return base.dedupe_trends(rows, limit)[:limit]


def editorial_fit(post: dict[str, Any]) -> float:
    text = str(post.get("text") or "").strip()
    if len(text) < 24 or is_pulse_post(post):
        return -999.0
    score = base.editorial_fit(post)
    family = base.family_for_category(str(post.get("category") or ""))
    if EDITORIAL_RE.search(text):
        score += 0.22
    if family in {"art", "ideas", "cinema", "science", "technology"}:
        score += 0.12
    return round(score, 3)


def editorial_reason(post: dict[str, Any]) -> str:
    if is_pulse_post(post):
        return "новостной / геополитический фон"
    return base.editorial_reason(post)


def editorial_picks(posts: list[dict[str, Any]], limit: int = 15) -> list[dict[str, Any]]:
    rows = []
    for post in posts:
        row = dict(post)
        row["content_fit"] = editorial_fit(post)
        if row["content_fit"] >= 3.15:
            row["_family"] = base.family_for_category(str(row.get("category") or ""))
            rows.append(row)
    rows.sort(key=lambda r: (r["content_fit"], float(r.get("signal_score") or 0)), reverse=True)
    selected, families, channels, seen = [], Counter(), Counter(), set()
    caps = {"technology": 3, "art": 3, "ideas": 3, "cinema": 3, "science": 2, "design": 2, "media": 2, "music": 2, "viral": 1, "business": 1, "misc": 2}
    for row in rows:
        family, channel = row["_family"], str(row.get("channel") or "")
        prefix = re.sub(r"\W+", "", str(row.get("text") or "").lower())[:140]
        if family == "pulse" or families[family] >= caps.get(family, 2) or channels[channel] >= 2 or prefix in seen:
            continue
        selected.append(row); families[family] += 1; channels[channel] += 1; seen.add(prefix)
        if len(selected) >= limit:
            break
    for row in selected:
        row.pop("_family", None)
    return selected


def hot_posts(posts: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    rows = []
    for post in posts:
        text = str(post.get("text") or "").strip()
        family = base.family_for_category(str(post.get("category") or ""))
        if len(text) < 24 or is_pulse_post(post) or post.get("is_probable_ad") or base.AD_RE.search(text):
            continue
        if not EDITORIAL_RE.search(text) and family not in {"viral", "art", "ideas", "cinema", "technology", "science", "design", "media", "music"}:
            continue
        rows.append(post)
    rows.sort(key=lambda r: float(r.get("signal_score") or 0), reverse=True)
    return base.dedupe_posts(rows, limit)


def pulse_posts(posts: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    rows = [p for p in posts if len(str(p.get("text") or "").strip()) >= 20 and is_pulse_post(p) and not p.get("is_probable_ad")]
    rows.sort(key=lambda r: (post_pulse_score(r), float(r.get("signal_score") or 0)), reverse=True)
    return base.dedupe_posts(rows, limit, per_channel_limit=1)


def post_line(post: dict[str, Any], fit: bool = False) -> str:
    channel = base.esc(post.get("channel_title") or post.get("channel"))
    link = post.get("link")
    title = f"[{channel}]({link})" if link else channel
    text = base.esc(str(post.get("text") or "")[:280])
    extra = f" · fit {float(post.get('content_fit') or 0):.2f}" if fit else ""
    return f"- **{title}** — {editorial_reason(post)}{extra}: {text}"


def build_report(snapshot: dict[str, Any]) -> str:
    posts, raw_topics = snapshot.get("posts") or [], snapshot.get("topics") or []
    picks, trends, hot = editorial_picks(posts), real_trends(raw_topics), hot_posts(posts)
    pulse, pulse_topics = pulse_posts(posts), pulse_trends(raw_topics)
    errors = snapshot.get("errors") or []
    active = snapshot.get("channels_with_posts")
    if active is None:
        active = sum(int(x.get("posts_in_window") or 0) > 0 for x in snapshot.get("channel_stats") or [])
    pulse_count = sum(is_pulse_post(p) for p in posts)
    lines = [
        "# Telegram editorial radar", "",
        f"Сформировано: {str(snapshot.get('generated_at') or '')[:16].replace('T',' ')} UTC",
        f"Окно наблюдения: последние {snapshot.get('window_hours',48)} ч.", "",
        "> Сначала — сюжеты, которые стоит заметить. Повторяемая новостная повестка вынесена в отдельный фон дня.", "",
        "## Покрытие", "",
        f"- Запрошено каналов: {snapshot.get('channels_requested',0)}",
        f"- Каналов с публикациями: {active}",
        f"- Собрано публикаций: {snapshot.get('posts_collected',len(posts))}",
        f"- Новостной фон: {pulse_count}",
        f"- Ошибок источников: {snapshot.get('channels_failed',len(errors))}", "",
        "## Что стоит заметить", "",
    ]
    lines += [post_line(p, True) for p in picks] or ["Нет публикаций с достаточным editorial fit."]
    lines += ["", "## Растёт в твоём поле", ""]
    if trends:
        lines += ["| Тема | Каналы | Посты | Просмотры | Confidence | Примеры |", "|---|---:|---:|---:|---:|---|"]
        for t in trends:
            lines.append(f"| {base.esc(t.get('display_title') or t.get('term'))} | {t.get('source_count',0)} | {t.get('post_count',0)} | {t.get('views',0)} | {float(t.get('confidence') or 0):.2f} | {base.examples_md(t)} |")
    else:
        lines.append("Нет достаточно сильных редакционных сюжетов в этом окне.")
    lines += ["", "## Горячее вне новостной ленты", ""]
    lines += [post_line(p) for p in hot[:15]] or ["Нет подходящих публикаций."]
    lines += ["", "## Фон дня — новости отдельно", ""]
    if pulse_topics:
        lines += ["| Сюжет | Каналы | Посты | Просмотры |", "|---|---:|---:|---:|"]
        for t in pulse_topics:
            lines.append(f"| {base.esc(t.get('display_title') or t.get('term'))} | {t.get('source_count',0)} | {t.get('post_count',0)} | {t.get('views',0)} |")
    if pulse:
        lines += ["", "Самые быстрые публикации:"] + [post_line(p) for p in pulse[:8]]
    if errors:
        lines += ["", "## Ошибки источников", ""] + [f"- {base.esc(e.get('channel') or e.get('username'))}: {base.esc(e.get('error'))}" for e in errors[:20]]
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build post-level editorial report")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    snapshot = json.loads(Path(args.input).read_text(encoding="utf-8"))
    Path(args.output).write_text(build_report(snapshot), encoding="utf-8")


if __name__ == "__main__":
    main()
