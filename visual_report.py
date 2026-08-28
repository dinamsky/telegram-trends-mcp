from __future__ import annotations

import argparse
import html
import json
from collections import Counter
from pathlib import Path
from typing import Any

from editorial_report import editorial_picks, editorial_reason, hot_posts, real_trends


def h(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def compact(value: int) -> str:
    value = int(value or 0)
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def category_label(value: str) -> str:
    labels = {
        "art_history": "Искусство",
        "art_counterculture": "Контркультура",
        "art_memes": "Арт-мемы",
        "soviet_art": "Советское искусство",
        "visual_culture": "Визуальная культура",
        "culture": "Культура",
        "culture_philosophy": "Культура / философия",
        "culture_science_society": "Культура / наука",
        "culture_media": "Медиа / культура",
        "technology": "Технологии",
        "technology_culture": "Технологии / культура",
        "technology_science": "Технологии / наука",
        "technology_internet_culture": "Интернет / технологии",
        "technology_memes": "IT-мемы",
        "philosophy_art": "Философия",
        "history_society": "История / общество",
        "fashion_history": "Мода / история",
        "fashion_culture": "Мода / культура",
        "cinema": "Кино",
        "architecture_history": "Архитектура",
        "marketing": "Маркетинг",
        "viral": "Вирусное",
        "news": "Новости",
        "breaking_news": "Breaking news",
        "news_viral": "Новости / вирусное",
        "geopolitics": "Геополитика",
    }
    return labels.get(value, value.replace("_", " "))


def category_stats(posts: list[dict[str, Any]]) -> list[tuple[str, int]]:
    counts = Counter(category_label(str(post.get("category") or "other")) for post in posts)
    return counts.most_common(10)


def bar_rows(items: list[tuple[str, int]]) -> str:
    maximum = max((value for _, value in items), default=1)
    rows = []
    for label, value in items:
        width = max(4.0, 100.0 * value / maximum)
        rows.append(
            f'<div class="bar-row"><div class="bar-label">{h(label)}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{width:.1f}%"></div></div>'
            f'<div class="bar-value">{value}</div></div>'
        )
    return "".join(rows)


def trend_cards(topics: list[dict[str, Any]]) -> str:
    cards = []
    for index, topic in enumerate(topics[:8], 1):
        title = topic.get("display_title") or topic.get("term") or "Сюжет"
        examples = []
        for example in (topic.get("examples") or [])[:3]:
            link = example.get("link")
            name = example.get("channel_title") or example.get("channel") or "Источник"
            if link:
                examples.append(f'<a href="{h(link)}" target="_blank">{h(name)}</a>')
        cards.append(
            '<article class="trend-card">'
            f'<div class="trend-index">{index:02d}</div>'
            f'<h3>{h(title)}</h3>'
            '<div class="trend-metrics">'
            f'<span>{topic.get("source_count", 0)} кан.</span>'
            f'<span>{topic.get("post_count", 0)} пост.</span>'
            f'<span>{compact(int(topic.get("views") or 0))} просм.</span>'
            f'<span>conf {float(topic.get("confidence") or 0):.1f}</span>'
            '</div>'
            f'<div class="sources">{" · ".join(examples)}</div>'
            '</article>'
        )
    return "".join(cards)


def pick_cards(posts: list[dict[str, Any]]) -> str:
    cards = []
    for post in posts[:12]:
        link = post.get("link") or "#"
        text = str(post.get("text") or "").replace("\n", " ").strip()
        if len(text) > 300:
            text = text[:297] + "…"
        cards.append(
            '<article class="pick-card">'
            '<div class="pick-top">'
            f'<span class="pill">{h(editorial_reason(post))}</span>'
            f'<span class="fit">FIT {float(post.get("content_fit") or 0):.2f}</span>'
            '</div>'
            f'<h3><a href="{h(link)}" target="_blank">{h(post.get("channel_title") or post.get("channel"))}</a></h3>'
            f'<p>{h(text)}</p>'
            '<div class="pick-meta">'
            f'<span>{compact(int(post.get("views") or 0))} просмотров</span>'
            f'<span>{float(post.get("age_hours") or 0):.1f} ч назад</span>'
            '</div>'
            '</article>'
        )
    return "".join(cards)


def hot_table(posts: list[dict[str, Any]]) -> str:
    rows = []
    for post in posts[:12]:
        link = post.get("link") or "#"
        text = str(post.get("text") or "").replace("\n", " ").strip()
        if len(text) > 120:
            text = text[:117] + "…"
        rows.append(
            '<tr>'
            f'<td><a href="{h(link)}" target="_blank">{h(post.get("channel_title") or post.get("channel"))}</a></td>'
            f'<td>{compact(int(post.get("views") or 0))}</td>'
            f'<td>{float(post.get("signal_score") or 0):.2f}</td>'
            f'<td>{h(text)}</td>'
            '</tr>'
        )
    return "".join(rows)


def build_html(snapshot: dict[str, Any]) -> str:
    posts = snapshot.get("posts") or []
    topics = real_trends(snapshot.get("topics") or [])
    picks = editorial_picks(posts)
    hot = hot_posts(posts)
    categories = category_stats(posts)
    generated = str(snapshot.get("generated_at") or "")[:16].replace("T", " ")

    return f'''<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Telegram Editorial Radar</title>
<style>
:root{{--bg:#0b0d12;--panel:#121621;--panel2:#171c29;--text:#f5f7fb;--muted:#8e99ad;--line:#252c3b;--accent:#7c5cff;--accent2:#25d0ab;--hot:#ff8a5b}}
*{{box-sizing:border-box}} body{{margin:0;background:radial-gradient(circle at 15% 0,#202845 0,transparent 30%),var(--bg);color:var(--text);font-family:Inter,Segoe UI,Arial,sans-serif}}
a{{color:inherit;text-decoration:none}} .wrap{{max-width:1440px;margin:auto;padding:36px}}
.hero{{display:flex;justify-content:space-between;align-items:flex-end;gap:30px;margin-bottom:28px}} .eyebrow{{color:var(--accent2);font-weight:700;letter-spacing:.16em;text-transform:uppercase;font-size:12px}} h1{{font-size:48px;line-height:1;margin:8px 0 10px;letter-spacing:-.04em}} .sub{{color:var(--muted);max-width:760px}}
.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:24px 0 30px}} .metric{{background:linear-gradient(145deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:18px;padding:20px}} .metric b{{display:block;font-size:30px}} .metric span{{color:var(--muted);font-size:13px}}
.grid2{{display:grid;grid-template-columns:1.35fr .65fr;gap:18px;margin-bottom:30px}} .panel{{background:rgba(18,22,33,.94);border:1px solid var(--line);border-radius:20px;padding:22px}} .panel h2{{margin:0 0 16px;font-size:22px}}
.trends{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}} .trend-card{{position:relative;background:var(--panel2);border:1px solid var(--line);border-radius:16px;padding:18px;overflow:hidden}} .trend-index{{position:absolute;right:14px;top:9px;color:#30384a;font-size:40px;font-weight:800}} .trend-card h3{{position:relative;margin:0 54px 15px 0;font-size:18px}} .trend-metrics{{display:flex;gap:8px;flex-wrap:wrap}} .trend-metrics span{{font-size:12px;color:#c6cedd;background:#202638;padding:5px 8px;border-radius:999px}} .sources{{margin-top:12px;color:var(--muted);font-size:12px}} .sources a{{color:#b9aaff}}
.bar-row{{display:grid;grid-template-columns:130px 1fr 32px;gap:10px;align-items:center;margin:11px 0}} .bar-label{{color:#c9d1df;font-size:12px}} .bar-track{{height:9px;background:#222838;border-radius:99px;overflow:hidden}} .bar-fill{{height:100%;background:linear-gradient(90deg,var(--accent),var(--accent2));border-radius:99px}} .bar-value{{font-size:12px;color:var(--muted);text-align:right}}
.section-head{{display:flex;justify-content:space-between;align-items:end;margin:32px 0 14px}} .section-head h2{{margin:0;font-size:28px}} .section-head span{{color:var(--muted);font-size:13px}}
.picks{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}} .pick-card{{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:18px;min-height:220px;display:flex;flex-direction:column}} .pick-top{{display:flex;justify-content:space-between;gap:8px;align-items:center}} .pill{{font-size:11px;padding:5px 8px;background:#1c2c2b;color:#79e6ca;border-radius:999px}} .fit{{font-size:11px;color:#aa9cff}} .pick-card h3{{font-size:16px;margin:16px 0 8px}} .pick-card p{{color:#c3cad7;font-size:13px;line-height:1.55;margin:0;flex:1}} .pick-meta{{display:flex;justify-content:space-between;color:var(--muted);font-size:11px;margin-top:15px}}
table{{width:100%;border-collapse:collapse}} th,td{{padding:12px 10px;border-bottom:1px solid var(--line);text-align:left;font-size:12px;vertical-align:top}} th{{color:var(--muted);font-weight:600}} td:nth-child(2),td:nth-child(3){{white-space:nowrap}} .footer{{color:#596579;font-size:11px;margin:26px 0 8px}}
@media(max-width:1000px){{.grid2{{grid-template-columns:1fr}}.picks{{grid-template-columns:1fr 1fr}}.metrics{{grid-template-columns:1fr 1fr}}}} @media(max-width:650px){{.wrap{{padding:18px}}h1{{font-size:36px}}.picks,.trends{{grid-template-columns:1fr}}.metrics{{grid-template-columns:1fr 1fr}}.hero{{display:block}}}}
</style></head>
<body><main class="wrap">
<div class="hero"><div><div class="eyebrow">Dead Inside · Telegram Radar</div><h1>Editorial Pulse</h1><div class="sub">Визуальная сводка по вашему watchlist. Окно: {snapshot.get('window_hours',48)} ч · Сформировано: {h(generated)} UTC</div></div></div>
<section class="metrics">
<div class="metric"><b>{snapshot.get('channels_requested',0)}</b><span>каналов в watchlist</span></div>
<div class="metric"><b>{snapshot.get('channels_with_posts',0)}</b><span>активных каналов</span></div>
<div class="metric"><b>{snapshot.get('posts_collected',len(posts))}</b><span>публикаций собрано</span></div>
<div class="metric"><b>{len(topics)}</b><span>подтверждённых сюжетов</span></div>
</section>
<section class="grid2">
<div class="panel"><h2>Реально растёт</h2><div class="trends">{trend_cards(topics)}</div></div>
<div class="panel"><h2>Где сейчас шум</h2>{bar_rows(categories)}</div>
</section>
<div class="section-head"><h2>Стоит написать пост</h2><span>редакционный fit × скорость сигнала</span></div>
<section class="picks">{pick_cards(picks)}</section>
<div class="section-head"><h2>Просто горячее</h2><span>самая высокая скорость набора сигнала</span></div>
<section class="panel"><table><thead><tr><th>Канал</th><th>Просмотры</th><th>Сигнал</th><th>Публикация</th></tr></thead><tbody>{hot_table(hot)}</tbody></table></section>
<div class="footer">Локальный отчёт. Данные не отправляются наружу; ссылки ведут на публичные Telegram-посты.</div>
</main></body></html>'''


def truncate_svg(text: str, limit: int = 42) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def build_svg(snapshot: dict[str, Any]) -> str:
    topics = real_trends(snapshot.get("topics") or [])[:5]
    picks = editorial_picks(snapshot.get("posts") or [])[:5]
    width, height = 1200, 1500
    topic_lines = []
    y = 420
    for index, topic in enumerate(topics, 1):
        title = h(truncate_svg(topic.get("display_title") or topic.get("term"), 52))
        topic_lines.append(f'<text x="92" y="{y}" class="idx">{index:02d}</text>')
        topic_lines.append(f'<text x="160" y="{y}" class="topic">{title}</text>')
        topic_lines.append(f'<text x="160" y="{y+28}" class="meta">{topic.get("source_count",0)} каналов · {compact(int(topic.get("views") or 0))} просмотров</text>')
        y += 112
    pick_lines = []
    y = 1020
    for post in picks:
        title = h(truncate_svg(post.get("text") or "", 72))
        channel = h(post.get("channel_title") or post.get("channel") or "")
        pick_lines.append(f'<circle cx="100" cy="{y-7}" r="6" class="dot"/>')
        pick_lines.append(f'<text x="126" y="{y}" class="pick">{title}</text>')
        pick_lines.append(f'<text x="126" y="{y+27}" class="meta">{channel} · FIT {float(post.get("content_fit") or 0):.2f}</text>')
        y += 92
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#11172b"/><stop offset="1" stop-color="#080a10"/></linearGradient><linearGradient id="accent" x1="0" y1="0" x2="1" y2="0"><stop stop-color="#7c5cff"/><stop offset="1" stop-color="#25d0ab"/></linearGradient></defs>
<style>.eyebrow{{font:700 20px 'Segoe UI',Arial;letter-spacing:4px;fill:#25d0ab}}.title{{font:800 68px 'Segoe UI',Arial;fill:#f7f8fb}}.sub{{font:24px 'Segoe UI',Arial;fill:#8e99ad}}.big{{font:800 44px 'Segoe UI',Arial;fill:#fff}}.small{{font:18px 'Segoe UI',Arial;fill:#8e99ad}}.section{{font:700 28px 'Segoe UI',Arial;fill:#fff}}.idx{{font:800 34px 'Segoe UI',Arial;fill:#4b5369}}.topic{{font:700 25px 'Segoe UI',Arial;fill:#f3f5f9}}.meta{{font:18px 'Segoe UI',Arial;fill:#8e99ad}}.pick{{font:22px 'Segoe UI',Arial;fill:#e4e8ef}}.dot{{fill:#7c5cff}}</style>
<rect width="1200" height="1500" rx="34" fill="url(#bg)"/><rect x="56" y="56" width="1088" height="1388" rx="28" fill="none" stroke="#242b3a"/>
<text x="88" y="118" class="eyebrow">DEAD INSIDE · TELEGRAM RADAR</text><text x="88" y="205" class="title">Editorial Pulse</text><text x="88" y="248" class="sub">{h(snapshot.get('window_hours',48))} ч · {h(str(snapshot.get('generated_at') or '')[:16].replace('T',' '))} UTC</text>
<rect x="88" y="286" width="1024" height="92" rx="18" fill="#141a27"/><text x="118" y="340" class="big">{snapshot.get('posts_collected',0)}</text><text x="225" y="340" class="small">постов</text><text x="420" y="340" class="big">{snapshot.get('channels_with_posts',0)}</text><text x="505" y="340" class="small">активных каналов</text><text x="820" y="340" class="big">{len(real_trends(snapshot.get('topics') or []))}</text><text x="872" y="340" class="small">трендов</text>
<text x="88" y="405" class="section">Реально растёт</text>{''.join(topic_lines)}<line x1="88" x2="1112" y1="950" y2="950" stroke="#252c3b"/><text x="88" y="995" class="section">Стоит написать</text>{''.join(pick_lines)}
<rect x="88" y="1390" width="360" height="5" rx="3" fill="url(#accent)"/><text x="88" y="1428" class="small">Локальный редакционный радар</text></svg>'''


def main() -> int:
    parser = argparse.ArgumentParser(description="Build graphical Telegram reports")
    parser.add_argument("--input", default="output/latest.json")
    parser.add_argument("--html", default="output/latest.html")
    parser.add_argument("--svg", default="output/latest.svg")
    args = parser.parse_args()
    snapshot = json.loads(Path(args.input).read_text(encoding="utf-8"))
    html_path = Path(args.html)
    svg_path = Path(args.svg)
    html_path.write_text(build_html(snapshot), encoding="utf-8")
    svg_path.write_text(build_svg(snapshot), encoding="utf-8")
    print(f"Visual HTML: {html_path}")
    print(f"Visual SVG:  {svg_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
