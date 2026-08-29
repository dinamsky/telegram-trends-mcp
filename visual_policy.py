from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

import editorial_policy as policy
import visual_report as ui

# Reuse the existing visual design, but feed it the post-level editorial policy.
ui.editorial_picks = policy.editorial_picks
ui.editorial_reason = policy.editorial_reason
ui.hot_posts = policy.hot_posts
ui.real_trends = policy.real_trends


def category_stats(posts):
    labels = {
        "art": "Искусство", "cinema": "Кино", "technology": "AI / технологии",
        "science": "Наука", "design": "Дизайн / мода", "media": "Медиа / маркетинг",
        "music": "Музыка", "ideas": "Идеи / история", "business": "Бизнес",
        "city": "Город", "viral": "Интернет-культура", "misc": "Культура / другое",
    }
    counts = Counter()
    for post in posts:
        if policy.is_pulse_post(post):
            continue
        family = policy.base.family_for_category(str(post.get("category") or ""))
        counts[labels.get(family, family)] += 1
    return counts.most_common(10)


ui.category_stats = category_stats


def build_html(snapshot):
    html = ui.build_html(snapshot)
    posts = snapshot.get("posts") or []
    pulse = policy.pulse_posts(posts, 10)
    pulse_topics = policy.pulse_trends(snapshot.get("topics") or [], 6)
    pulse_count = sum(policy.is_pulse_post(p) for p in posts)

    html = html.replace("<h1>Editorial Pulse</h1>", "<h1>Editorial Radar</h1>")
    html = html.replace("Реально растёт", "Растёт в твоём поле")
    html = html.replace("Где сейчас шум", "Тематический баланс")
    html = html.replace("Стоит написать пост", "Что стоит заметить")
    html = html.replace("Просто горячее", "Горячее без новостей")
    html = re.sub(
        r"Визуальная сводка по вашему watchlist\. Окно:",
        "Сначала — сюжеты, которые стоит заметить; новости вынесены в фон дня. Окно:",
        html,
    )

    # Move recommendation cards above trend statistics.
    pattern = re.compile(
        r'(?P<trends><section class="grid2">.*?</section>)\s*'
        r'(?P<picks><div class="section-head"><h2>Что стоит заметить</h2>.*?</div>\s*<section class="picks">.*?</section>)\s*'
        r'(?P<hot><div class="section-head"><h2>Горячее без новостей</h2>.*?</div>\s*<section class="panel"><table>.*?</table></section>)',
        re.S,
    )
    match = pattern.search(html)
    if match:
        replacement = match.group("picks") + "\n" + match.group("trends") + "\n" + match.group("hot")
        html = html[:match.start()] + replacement + html[match.end():]

    pulse_html = (
        '<div class="section-head"><h2>Фон дня</h2>'
        '<span>виден, но не управляет редакционным рейтингом</span></div>'
        '<section class="grid2">'
        '<div class="panel"><h2>Повторяемые новости</h2><div class="trends">'
        + ui.trend_cards(pulse_topics) + '</div></div>'
        '<div class="panel"><h2>Самые быстрые новости</h2>'
        '<table><thead><tr><th>Канал</th><th>Просмотры</th><th>Сигнал</th><th>Публикация</th></tr></thead>'
        '<tbody>' + ui.hot_table(pulse) + '</tbody></table></div></section>'
    )
    html = html.replace('<div class="footer">', pulse_html + '<div class="footer">')
    html = html.replace(
        "Локальный отчёт. Данные не отправляются наружу; ссылки ведут на публичные Telegram-посты.",
        f"Локальный отчёт. {pulse_count} публикаций отнесены к фону дня по тексту конкретного поста; категория канала используется только как вспомогательный сигнал.",
    )
    return html


def build_svg(snapshot):
    # Existing SVG remains compact, but uses the new filtered picks/trends.
    svg = ui.build_svg(snapshot)
    svg = svg.replace("Editorial Pulse", "Editorial Radar")
    svg = svg.replace("Реально растёт", "Растёт в поле")
    svg = svg.replace("Стоит написать", "Что заметить")
    return svg


def main() -> int:
    parser = argparse.ArgumentParser(description="Build graphical post-level editorial reports")
    parser.add_argument("--input", default="output/latest.json")
    parser.add_argument("--html", default="output/latest.html")
    parser.add_argument("--svg", default="output/latest.svg")
    args = parser.parse_args()
    snapshot = json.loads(Path(args.input).read_text(encoding="utf-8"))
    Path(args.html).write_text(build_html(snapshot), encoding="utf-8")
    Path(args.svg).write_text(build_svg(snapshot), encoding="utf-8")
    print(f"Visual HTML: {args.html}")
    print(f"Visual SVG:  {args.svg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
