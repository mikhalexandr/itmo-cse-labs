from __future__ import annotations

import argparse
import base64
import configparser
import hashlib
import math
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape


# ---------------------------------------------------------------------------
# 1. Конфигурация предметов
# ---------------------------------------------------------------------------
# Новый сабмодуль подхватывается автоматически из .gitmodules: он попадает в
# таблицу «Структура материалов» (курс берется из пути вида 1_course/...),
# в обзорную сводку и график активности. Запись здесь нужна для красивого
# русского названия, закрепленного цвета, семестра и стека; без нее предмет
# получит имя из названия папки, цвет из fallback-палитры и «—» в таблице.
# Новые технологии для колонки «Стек» добавляются в STACK_BADGES ниже.


@dataclass(frozen=True)
class SubjectMeta:
    title: str
    short_title: str
    light_color: str
    dark_color: str
    semester: str = "—"
    stack: tuple[str, ...] = ()


SUBJECTS: dict[str, SubjectMeta] = {
    "bpa": SubjectMeta(
        "Основы профессиональной деятельности", "ОПД", "#BF3989", "#DB61A2",
        semester="1-2", stack=("shell", "assembly"),
    ),
    "informatics": SubjectMeta(
        "Информатика", "Информатика", "#0969DA", "#4493F8",
        semester="1", stack=("python", "latex"),
    ),
    "programming": SubjectMeta(
        "Программирование", "Программирование", "#BC4C00", "#F0883E",
        semester="1-2", stack=("java",),
    ),
    "databases": SubjectMeta(
        "Базы данных", "Базы данных", "#1A7F37", "#3FB950",
        semester="2", stack=("postgresql",),
    ),
    "linear-algebra": SubjectMeta(
        "Линейная алгебра", "Линейная алгебра", "#8250DF", "#A371F7",
        semester="1-2", stack=("python", "latex"),
    ),
}

# Бейджи технологий для колонки «Стек» в таблице структуры.
STACK_BADGES: dict[str, str] = {
    "python": "![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white)",
    "latex": "![LaTeX](https://img.shields.io/badge/LaTeX-008080?style=flat&logo=latex&logoColor=white)",
    "shell": "![Shell](https://img.shields.io/badge/Shell-4EAA25?style=flat&logo=gnubash&logoColor=white)",
    "assembly": "![Assembly](https://img.shields.io/badge/Assembly-6E4C13?style=flat&logo=assemblyscript&logoColor=white)",
    "java": "![Java](https://img.shields.io/badge/Java-ED8B00?style=flat&logo=openjdk&logoColor=white)",
    "postgresql": "![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=flat&logo=postgresql&logoColor=white)",
}


# ---------------------------------------------------------------------------
# 2. Константы генерации
# ---------------------------------------------------------------------------

ROOT_START_MARKER = "<!-- archive-pulse:start -->"
ROOT_END_MARKER = "<!-- archive-pulse:end -->"
ROOT_SECTION_TITLE = "## Пульс архива"

STRUCTURE_START_MARKER = "<!-- archive-structure:start -->"
STRUCTURE_END_MARKER = "<!-- archive-structure:end -->"
STRUCTURE_SECTION_TITLE = "## Структура материалов"

OLD_START_MARKER = "<!-- submodule-stats:start -->"
OLD_END_MARKER = "<!-- submodule-stats:end -->"
OLD_SECTION_TITLE = "## Сводка по сабмодулям"

README_ASSET_DIR = Path("assets/readme")
OVERVIEW_SVG = "archive-overview.svg"
OVERVIEW_SVG_DARK = "archive-overview-dark.svg"
ACTIVITY_SVG = "archive-activity.svg"
ACTIVITY_SVG_DARK = "archive-activity-dark.svg"

# Прозрачный пиксель-спейсер: GitHub не позволяет задавать ширину таблиц CSS,
# поэтому колонки растягиваются невидимыми <img width="..."> в шапке таблицы.
PIXEL_PNG = "pixel.png"
PIXEL_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGNgAAIAAAUAAXpeqz8AAAAASUVORK5CYII="
)

# Ширины колонок таблицы структуры; сумма с внутренними отступами ячеек
# (26px на колонку) подогнана под натуральную ширину SVG-схем (1120px).
STRUCTURE_COLUMNS = (
    ("Семестр", 100),
    ("Предмет", 400),
    ("Папка", 180),
    ("Стек", 334),
)
DEFAULT_PROFILE_ASSET_PREFIX = "assets/itmo-cse-labs"
DEFAULT_REPOSITORY_URL = "https://github.com/mikhalexandr/itmo-cse-labs"

BINARY_EXTENSIONS = {
    ".7z",
    ".class",
    ".db",
    ".gif",
    ".ico",
    ".jar",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".sqlite",
    ".zip",
}

SOURCE_EXTENSIONS = {
    ".asm",
    ".c",
    ".cpp",
    ".css",
    ".dbml",
    ".gradle",
    ".h",
    ".html",
    ".java",
    ".js",
    ".json",
    ".kt",
    ".latex",
    ".md",
    ".py",
    ".s",
    ".sh",
    ".sql",
    ".svg",
    ".tex",
    ".toml",
    ".ts",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}

MONTH_NAMES_RU = {
    "01": "янв",
    "02": "фев",
    "03": "мар",
    "04": "апр",
    "05": "май",
    "06": "июн",
    "07": "июл",
    "08": "авг",
    "09": "сен",
    "10": "окт",
    "11": "ноя",
    "12": "дек",
}

FONT_STACK = (
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', "
    "Helvetica, Arial, sans-serif"
)


# ---------------------------------------------------------------------------
# 3. Темы оформления (палитры GitHub light/dark)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Theme:
    name: str
    panel_bg: str
    panel_border: str
    hairline: str
    grid: str
    track: str
    badge_bg: str
    fg: str
    muted: str
    faint: str
    zero_bar: str
    fallback_colors: list[str]

    def subject_color(self, name: str) -> str:
        meta = SUBJECTS.get(name)
        if meta:
            return meta.dark_color if self.name == "dark" else meta.light_color

        digest = hashlib.sha1(name.encode("utf-8")).digest()
        return self.fallback_colors[digest[0] % len(self.fallback_colors)]


LIGHT_THEME = Theme(
    name="light",
    panel_bg="#FFFFFF",
    panel_border="#D0D7DE",
    hairline="#E7ECF0",
    grid="#EFF2F6",
    track="#EFF2F5",
    badge_bg="#F6F8FA",
    fg="#1F2328",
    muted="#59636E",
    faint="#818B98",
    zero_bar="#D8DEE4",
    fallback_colors=[
        "#0969DA",
        "#1A7F37",
        "#BC4C00",
        "#8250DF",
        "#CF222E",
        "#9A6700",
        "#BF3989",
        "#1B7C83",
    ],
)

DARK_THEME = Theme(
    name="dark",
    panel_bg="#0D1117",
    panel_border="#30363D",
    hairline="#21262D",
    grid="#1B2128",
    track="#21262D",
    badge_bg="#161B22",
    fg="#E6EDF3",
    muted="#9198A1",
    faint="#6E7681",
    zero_bar="#30363D",
    fallback_colors=[
        "#4493F8",
        "#3FB950",
        "#F0883E",
        "#A371F7",
        "#F85149",
        "#D29922",
        "#DB61A2",
        "#39C5CF",
    ],
)


# ---------------------------------------------------------------------------
# 4. Метрики текста
# ---------------------------------------------------------------------------

WIDE_CYR_LOWER = set("мшщжыюфдё")
WIDE_CYR_UPPER = set("МШЩЖЫЮФДЁ")


def text_width(text: str, size: float, weight: int = 400) -> float:
    """Консервативная оценка ширины строки в пикселях для системных шрифтов."""

    width = 0.0
    for char in text:
        if char == " ":
            width += 0.29
        elif char in ".,:;!'’|":
            width += 0.30
        elif char in "·•":
            width += 0.34
        elif char in "-–—":
            width += 0.40
        elif char == "…":
            width += 0.94
        elif char.isdigit():
            width += 0.60
        elif char in "ilIjt":
            width += 0.33
        elif char.isascii() and char.islower():
            width += 0.55
        elif char.isascii() and char.isupper():
            width += 0.70
        elif char in WIDE_CYR_LOWER:
            width += 0.76
        elif char in WIDE_CYR_UPPER:
            width += 0.90
        elif char.islower():
            width += 0.58
        elif char.isupper():
            width += 0.73
        else:
            width += 0.62

    weight_factor = 1.0 + max(0, weight - 400) / 400 * 0.08
    return width * size * weight_factor * 1.06


def truncate_to_width(text: str, max_width: float, size: float, weight: int = 400) -> str:
    if text_width(text, size, weight) <= max_width:
        return text

    trimmed = text
    while trimmed and text_width(trimmed + "…", size, weight) > max_width:
        trimmed = trimmed[:-1].rstrip()
    return trimmed + "…"


def ru_plural(value: int, one: str, few: str, many: str) -> str:
    tail, last = value % 100, value % 10
    if 11 <= tail <= 14:
        return many
    if last == 1:
        return one
    if 2 <= last <= 4:
        return few
    return many


def format_int(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def format_date(iso_date: str) -> str:
    try:
        return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return iso_date or "—"


def month_label(month: str) -> str:
    year, month_num = month.split("-")
    return f"{MONTH_NAMES_RU.get(month_num, month_num)} {year[-2:]}"


def nice_axis_top(max_value: int, target_ticks: int = 4) -> tuple[int, int]:
    """Подбирает (шаг, максимум) оси Y так, чтобы деления были круглыми."""

    if max_value <= 0:
        return 1, 1

    raw_step = max_value / target_ticks
    magnitude = 10 ** math.floor(math.log10(raw_step)) if raw_step >= 1 else 1
    step = magnitude
    for factor in (1, 2, 2.5, 5, 10):
        candidate = magnitude * factor
        if candidate >= raw_step:
            step = candidate
            break

    step = max(1, int(round(step)))
    top = step * math.ceil(max_value / step)
    return step, top


def xml(value: object) -> str:
    return xml_escape(str(value), {'"': "&quot;"})


# ---------------------------------------------------------------------------
# 5. Данные из git
# ---------------------------------------------------------------------------


def humanize_name(name: str) -> str:
    return name.replace("-", " ").replace("_", " ")


@dataclass(frozen=True)
class Submodule:
    name: str
    path: Path
    url: str

    @property
    def title(self) -> str:
        meta = SUBJECTS.get(self.name)
        return meta.title if meta else humanize_name(self.name)

    @property
    def short_title(self) -> str:
        meta = SUBJECTS.get(self.name)
        return meta.short_title if meta else humanize_name(self.name)

    @property
    def semester(self) -> str:
        meta = SUBJECTS.get(self.name)
        return meta.semester if meta else "—"

    @property
    def stack_badges(self) -> str:
        meta = SUBJECTS.get(self.name)
        if not meta or not meta.stack:
            return "—"
        return " ".join(STACK_BADGES[tech] for tech in meta.stack if tech in STACK_BADGES) or "—"


@dataclass
class SubmoduleStats:
    submodule: Submodule
    initialized: bool
    commit_count: int = 0
    file_count: int = 0
    source_file_count: int = 0
    line_count: int = 0
    lab_count: int = 0
    report_count: int = 0
    monthly_commits: Counter[str] = field(default_factory=Counter)
    head_hash: str = ""
    head_short_hash: str = ""
    head_date: str = ""


@dataclass(frozen=True)
class Totals:
    submodules: int
    commits: int
    files: int
    source_files: int
    lines: int
    labs: int
    reports: int
    latest_date: str


def run(command: list[str], cwd: Path) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def read_submodules(root: Path) -> list[Submodule]:
    config_path = root / ".gitmodules"
    if not config_path.exists():
        return []

    parser = configparser.ConfigParser()
    parser.read(config_path, encoding="utf-8")

    submodules: list[Submodule] = []
    for section in parser.sections():
        if not section.startswith("submodule "):
            continue

        name = section.removeprefix("submodule ").strip().strip('"')
        path = parser[section].get("path")
        url = parser[section].get("url", "")
        if not path:
            continue

        submodules.append(Submodule(name=name, path=Path(path), url=url))

    return submodules


def gitlink_paths(repo: Path) -> set[str]:
    output = run(["git", "ls-files", "-s", "-z"], repo)
    gitlinks: set[str] = set()

    for record in output.split("\0"):
        if not record:
            continue
        metadata, path = record.split("\t", 1)
        mode = metadata.split(" ", 1)[0]
        if mode == "160000":
            gitlinks.add(path)

    return gitlinks


def tracked_files(repo: Path) -> list[Path]:
    output = run(["git", "ls-files", "-z"], repo)
    nested_submodules = gitlink_paths(repo)
    files: list[Path] = []

    for item in output.split("\0"):
        if not item or item in nested_submodules:
            continue
        path = repo / item
        if path.is_file():
            files.append(path)

    return files


def count_lines(path: Path) -> int | None:
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return None

    try:
        content = path.read_bytes()
    except OSError:
        return None

    if b"\0" in content:
        return None
    if not content:
        return 0

    return content.count(b"\n") + (0 if content.endswith(b"\n") else 1)


def collect_monthly_commits(repo: Path) -> Counter[str]:
    output = run(["git", "log", "--date=format:%Y-%m", "--format=%cd"], repo)
    return Counter(line for line in output.splitlines() if line)


def collect_stats(root: Path, submodule: Submodule) -> SubmoduleStats:
    repo = root / submodule.path
    try:
        run(["git", "rev-parse", "--is-inside-work-tree"], repo)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return SubmoduleStats(submodule=submodule, initialized=False)

    files = tracked_files(repo)
    line_count = 0
    source_file_count = 0

    for file_path in files:
        if file_path.suffix.lower() in SOURCE_EXTENSIONS:
            source_file_count += 1

        lines = count_lines(file_path)
        if lines is not None:
            line_count += lines

    lab_count = sum(
        1
        for path in repo.iterdir()
        if path.is_dir() and re.match(r"^lab\d", path.name, flags=re.IGNORECASE)
    )
    report_count = sum(1 for path in files if path.suffix.lower() == ".pdf")
    head_hash = run(["git", "rev-parse", "HEAD"], repo)

    return SubmoduleStats(
        submodule=submodule,
        initialized=True,
        commit_count=int(run(["git", "rev-list", "--count", "HEAD"], repo)),
        file_count=len(files),
        source_file_count=source_file_count,
        line_count=line_count,
        lab_count=lab_count,
        report_count=report_count,
        monthly_commits=collect_monthly_commits(repo),
        head_hash=head_hash,
        head_short_hash=head_hash[:7],
        head_date=run(["git", "log", "-1", "--format=%cs"], repo),
    )


def github_url(url: str) -> str:
    if url.startswith("git@github.com:"):
        url = "https://github.com/" + url.removeprefix("git@github.com:")
    return url.removesuffix(".git")


def repository_url(root: Path) -> str:
    try:
        remote_url = run(["git", "config", "--get", "remote.origin.url"], root)
    except subprocess.CalledProcessError:
        return DEFAULT_REPOSITORY_URL

    normalized = github_url(remote_url)
    if normalized.startswith("https://github.com/"):
        return normalized
    return DEFAULT_REPOSITORY_URL


def compute_totals(stats: list[SubmoduleStats]) -> Totals:
    initialized = [item for item in stats if item.initialized]
    latest_date = max((item.head_date for item in initialized), default="—")
    return Totals(
        submodules=len(initialized),
        commits=sum(item.commit_count for item in initialized),
        files=sum(item.file_count for item in initialized),
        source_files=sum(item.source_file_count for item in initialized),
        lines=sum(item.line_count for item in initialized),
        labs=sum(item.lab_count for item in initialized),
        reports=sum(item.report_count for item in initialized),
        latest_date=latest_date,
    )


def months_ending_at(month: str, count: int = 12) -> list[str]:
    if month == "—":
        today = date.today()
        year = today.year
        month_num = today.month
    else:
        parsed = datetime.strptime(month, "%Y-%m-%d").date()
        year = parsed.year
        month_num = parsed.month

    months: list[str] = []
    for _ in range(count):
        months.append(f"{year:04d}-{month_num:02d}")
        month_num -= 1
        if month_num == 0:
            month_num = 12
            year -= 1

    return list(reversed(months))


# ---------------------------------------------------------------------------
# 6. SVG-примитивы
# ---------------------------------------------------------------------------

CANVAS_WIDTH = 1120
INNER_LEFT = 40
INNER_RIGHT = CANVAS_WIDTH - 40
HEADER_DIVIDER_Y = 104


def color_for(stats: SubmoduleStats, theme: Theme) -> str:
    return theme.subject_color(stats.submodule.name)


def svg_styles(theme: Theme) -> str:
    return f"""  <style>
    text {{ font-family: {FONT_STACK}; }}
    .title {{ font-size: 24px; font-weight: 800; fill: {theme.fg}; }}
    .subtitle {{ font-size: 14px; font-weight: 500; fill: {theme.muted}; }}
    .badge-text {{ font-size: 12.5px; font-weight: 600; fill: {theme.muted}; }}
    .kpi-label {{ font-size: 11px; font-weight: 700; letter-spacing: 1px; fill: {theme.muted}; }}
    .kpi-value {{ font-size: 30px; font-weight: 800; fill: {theme.fg}; }}
    .kpi-note {{ font-size: 12.5px; font-weight: 500; fill: {theme.faint}; }}
    .section-label {{ font-size: 11px; font-weight: 700; letter-spacing: 1px; fill: {theme.muted}; }}
    .row-title {{ font-size: 16px; font-weight: 700; fill: {theme.fg}; }}
    .row-meta {{ font-size: 12.5px; font-weight: 500; fill: {theme.muted}; }}
    .row-number {{ font-size: 16px; font-weight: 700; fill: {theme.fg}; }}
    .row-unit {{ font-size: 11px; font-weight: 500; fill: {theme.faint}; }}
    .row-date-label {{ font-size: 10px; font-weight: 600; letter-spacing: 1px; fill: {theme.faint}; }}
    .row-date {{ font-size: 13px; font-weight: 600; fill: {theme.fg}; }}
    .axis-label {{ font-size: 11px; font-weight: 500; fill: {theme.faint}; }}
    .count {{ font-size: 12px; font-weight: 600; fill: {theme.muted}; }}
    .count-zero {{ font-size: 12px; font-weight: 600; fill: {theme.faint}; }}
    .month {{ font-size: 11.5px; font-weight: 500; fill: {theme.muted}; }}
    .legend {{ font-size: 12.5px; font-weight: 600; fill: {theme.muted}; }}
  </style>"""


def svg_panel(width: int, height: int, theme: Theme) -> str:
    return (
        f'  <rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="16" '
        f'fill="{theme.panel_bg}" stroke="{theme.panel_border}" stroke-width="1.5"/>'
    )


def svg_badge(theme: Theme, text: str, baseline_y: int) -> str:
    """Бейдж-пилюля, прижатая к правому краю; baseline_y — базовая линия текста.

    Текст центрируется по середине пилюли (text-anchor="middle"), поэтому
    остается симметричным даже там, где оценка ширины шрифта неточна.
    """

    badge_width = text_width(text, 12.5, 600) + 24
    badge_x = INNER_RIGHT - badge_width
    center_x = INNER_RIGHT - badge_width / 2
    return f"""  <rect x="{badge_x:.0f}" y="{baseline_y - 17}" width="{badge_width:.0f}" height="26" rx="13" fill="{theme.badge_bg}" stroke="{theme.hairline}" stroke-width="1"/>
  <text x="{center_x:.0f}" y="{baseline_y}" class="badge-text" text-anchor="middle">{xml(text)}</text>"""


def svg_header(theme: Theme, title: str, subtitle: str, badge: str) -> str:
    """Шапка: заголовок и подзаголовок слева, бейдж-пилюля справа, разделитель."""

    return f"""  <text x="{INNER_LEFT}" y="54" class="title">{xml(title)}</text>
  <text x="{INNER_LEFT}" y="80" class="subtitle">{xml(subtitle)}</text>
{svg_badge(theme, badge, 51)}
  <line x1="1.5" y1="{HEADER_DIVIDER_Y}" x2="{CANVAS_WIDTH - 1.5}" y2="{HEADER_DIVIDER_Y}" stroke="{theme.hairline}" stroke-width="1"/>"""


def svg_document(height: int, title: str, desc: str, theme: Theme, body: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_WIDTH}" height="{height}" viewBox="0 0 {CANVAS_WIDTH} {height}" role="img" aria-labelledby="title desc">
  <title id="title">{xml(title)}</title>
  <desc id="desc">{xml(desc)}</desc>
{svg_styles(theme)}
{body}
</svg>
"""


def legend_rows(
    items: list[tuple[str, str]], max_width: float, gap: float = 30
) -> list[list[tuple[str, str, float]]]:
    """Раскладывает элементы легенды по строкам с переносом по ширине."""

    rows: list[list[tuple[str, str, float]]] = []
    current: list[tuple[str, str, float]] = []
    current_width = 0.0

    for color, label in items:
        item_width = 22 + text_width(label, 12.5, 600)
        needed = item_width if not current else current_width + gap + item_width
        if current and needed > max_width:
            rows.append(current)
            current = [(color, label, item_width)]
            current_width = item_width
        else:
            current.append((color, label, item_width))
            current_width = needed

    if current:
        rows.append(current)
    return rows


# ---------------------------------------------------------------------------
# 7. Рендер SVG
# ---------------------------------------------------------------------------


def render_overview_svg(stats: list[SubmoduleStats], totals: Totals, theme: Theme) -> str:
    """Сводка: KPI-колонки сверху, ниже строки предметов с барами строк.

    Заголовок не рисуется: он дублировал бы секцию «Пульс архива» в README.
    Предметы сортируются по дате последнего обновления (свежие сверху),
    неинициализированные сабмодули — в конце; при равных датах порядок
    из .gitmodules сохраняется.
    """

    stats = sorted(stats, key=lambda item: (item.initialized, item.head_date), reverse=True)

    kpi_label_y = 40
    kpi_value_y = 78
    kpi_note_y = 101
    kpi_bottom = 114
    section_label_y = 152
    rows_top = 170
    row_height = 58
    bottom_pad = 26

    height = rows_top + len(stats) * row_height + bottom_pad
    max_lines = max((item.line_count for item in stats if item.initialized), default=1) or 1

    parts: list[str] = [svg_panel(CANVAS_WIDTH, height, theme)]

    # KPI-колонки, разделенные вертикальными линиями.
    kpis = [
        ("ПРЕДМЕТОВ", format_int(totals.submodules), "учебные дисциплины"),
        ("ОТЧЕТОВ", format_int(totals.reports), "PDF-документы в архиве"),
        ("КОММИТОВ", format_int(totals.commits), "суммарная git-история"),
        ("СТРОК ТЕКСТА", format_int(totals.lines), "в текстовых файлах"),
    ]
    column_width = (INNER_RIGHT - INNER_LEFT) / len(kpis)
    for index, (label, value, note) in enumerate(kpis):
        column_x = INNER_LEFT + index * column_width
        if index:
            divider_x = column_x - 26
            parts.append(
                f'  <line x1="{divider_x:.0f}" y1="{kpi_label_y - 12}" x2="{divider_x:.0f}" '
                f'y2="{kpi_bottom - 18}" stroke="{theme.hairline}" stroke-width="1"/>'
            )
        parts.append(f'  <text x="{column_x:.0f}" y="{kpi_label_y}" class="kpi-label">{xml(label)}</text>')
        parts.append(f'  <text x="{column_x:.0f}" y="{kpi_value_y}" class="kpi-value">{xml(value)}</text>')
        note_text = truncate_to_width(note, column_width - 40, 12.5, 500)
        parts.append(f'  <text x="{column_x:.0f}" y="{kpi_note_y}" class="kpi-note">{xml(note_text)}</text>')

    parts.append(
        f'  <line x1="1.5" y1="{kpi_bottom}" x2="{CANVAS_WIDTH - 1.5}" y2="{kpi_bottom}" '
        f'stroke="{theme.hairline}" stroke-width="1"/>'
    )
    parts.append(f'  <text x="{INNER_LEFT}" y="{section_label_y}" class="section-label">ПРЕДМЕТЫ</text>')
    parts.append(svg_badge(theme, f"данные на {format_date(totals.latest_date)}", section_label_y))

    # Строка предмета: точка + название + мета | бар строк | число | дата.
    bar_x = 400
    bar_width = 330
    number_anchor = 858
    title_slot = bar_x - 64 - 24

    for index, item in enumerate(stats):
        row_y = rows_top + index * row_height
        color = color_for(item, theme)

        if index:
            parts.append(
                f'  <line x1="{INNER_LEFT}" y1="{row_y}" x2="{INNER_RIGHT}" y2="{row_y}" '
                f'stroke="{theme.hairline}" stroke-width="1"/>'
            )

        dot_color = color if item.initialized else theme.zero_bar
        parts.append(f'  <circle cx="46" cy="{row_y + 29}" r="5" fill="{dot_color}"/>')

        title = truncate_to_width(item.submodule.short_title, title_slot, 16, 700)
        parts.append(f'  <text x="64" y="{row_y + 24}" class="row-title">{xml(title)}</text>')

        if not item.initialized:
            parts.append(
                f'  <text x="64" y="{row_y + 44}" class="row-meta">материалы еще не подключены</text>'
            )
            continue

        meta = (
            f"отчетов: {item.report_count} · файлов: {item.file_count} · "
            f"коммитов: {item.commit_count}"
        )
        meta = truncate_to_width(meta, title_slot, 12.5, 500)
        parts.append(f'  <text x="64" y="{row_y + 44}" class="row-meta">{xml(meta)}</text>')

        fill_width = max(6, round(bar_width * item.line_count / max_lines)) if item.line_count else 0
        parts.append(
            f'  <rect x="{bar_x}" y="{row_y + 25}" width="{bar_width}" height="8" rx="4" '
            f'fill="{theme.track}"/>'
        )
        if fill_width:
            parts.append(
                f'  <rect x="{bar_x}" y="{row_y + 25}" width="{fill_width}" height="8" rx="4" '
                f'fill="{color}"/>'
            )

        parts.append(
            f'  <text x="{number_anchor}" y="{row_y + 26}" class="row-number" '
            f'text-anchor="end">{format_int(item.line_count)}</text>'
        )
        parts.append(
            f'  <text x="{number_anchor}" y="{row_y + 44}" class="row-unit" '
            f'text-anchor="end">строк</text>'
        )
        parts.append(
            f'  <text x="{INNER_RIGHT}" y="{row_y + 23}" class="row-date-label" '
            f'text-anchor="end">ОБНОВЛЕНО</text>'
        )
        parts.append(
            f'  <text x="{INNER_RIGHT}" y="{row_y + 44}" class="row-date" '
            f'text-anchor="end">{xml(format_date(item.head_date))}</text>'
        )

    return svg_document(
        height,
        "Пульс архива учебных материалов",
        "Сводка по предметам: отчеты, коммиты, строки и даты последних обновлений.",
        theme,
        "\n".join(parts),
    )


def render_activity_svg(stats: list[SubmoduleStats], totals: Totals, theme: Theme) -> str:
    """Стековая диаграмма коммитов по месяцам с осью Y и легендой с переносом."""

    initialized_stats = [item for item in stats if item.initialized]
    months = months_ending_at(totals.latest_date, 12)
    totals_by_month = {
        month: sum(item.monthly_commits.get(month, 0) for item in initialized_stats)
        for month in months
    }
    period_total = sum(totals_by_month.values())

    plot_left = 96
    plot_right = INNER_RIGHT
    plot_top = 150
    plot_height = 210
    baseline = plot_top + plot_height
    month_label_y = baseline + 26
    legend_top = month_label_y + 40
    legend_pitch = 26

    legend = legend_rows(
        [(color_for(item, theme), item.submodule.short_title) for item in initialized_stats],
        max_width=INNER_RIGHT - INNER_LEFT,
    )
    height = legend_top + (len(legend) - 1) * legend_pitch + 30

    step, axis_top = nice_axis_top(max(totals_by_month.values(), default=0))
    scale = plot_height / axis_top

    parts: list[str] = [svg_panel(CANVAS_WIDTH, height, theme)]
    badge = (
        f"{format_int(period_total)} "
        f"{ru_plural(period_total, 'коммит', 'коммита', 'коммитов')} за 12 мес"
    )
    parts.append(
        svg_header(
            theme,
            "Активность коммитов",
            "Последние 12 месяцев · git-история всех предметов",
            badge,
        )
    )

    # Горизонтальная сетка с подписями круглых делений.
    tick = 0
    while tick <= axis_top:
        tick_y = baseline - tick * scale
        line_color = theme.hairline if tick == 0 else theme.grid
        parts.append(
            f'  <line x1="{plot_left}" y1="{tick_y:.1f}" x2="{plot_right}" y2="{tick_y:.1f}" '
            f'stroke="{line_color}" stroke-width="1"/>'
        )
        parts.append(
            f'  <text x="{plot_left - 12}" y="{tick_y + 4:.1f}" class="axis-label" '
            f'text-anchor="end">{format_int(tick)}</text>'
        )
        tick += step

    # Стековые столбцы: сегменты без скруглений, верх бара скруглен clipPath-ом.
    slot_width = (plot_right - plot_left) / len(months)
    bar_width = min(64, round(slot_width - 18))
    defs: list[str] = []

    for index, month in enumerate(months):
        count = totals_by_month[month]
        center_x = plot_left + slot_width * (index + 0.5)
        bar_x = center_x - bar_width / 2

        parts.append(
            f'  <text x="{center_x:.1f}" y="{month_label_y}" class="month" '
            f'text-anchor="middle">{xml(month_label(month))}</text>'
        )

        if count == 0:
            parts.append(
                f'  <rect x="{bar_x:.1f}" y="{baseline - 2}" width="{bar_width}" height="2" '
                f'fill="{theme.zero_bar}"/>'
            )
            parts.append(
                f'  <text x="{center_x:.1f}" y="{baseline - 10}" class="count-zero" '
                f'text-anchor="middle">0</text>'
            )
            continue

        bar_height = max(3, round(count * scale))
        bar_top = baseline - bar_height

        clip_id = f"bar-{theme.name}-{index}"
        use_clip = bar_height >= 8
        if use_clip:
            defs.append(
                f'    <clipPath id="{clip_id}"><rect x="{bar_x:.1f}" y="{bar_top}" '
                f'width="{bar_width}" height="{bar_height + 6}" rx="5"/></clipPath>'
            )

        # Кумулятивное округление: сегменты стыкуются без щелей ровно в высоту бара.
        segments: list[str] = []
        cumulative = 0
        previous_offset = 0
        for item in initialized_stats:
            item_count = item.monthly_commits.get(month, 0)
            if item_count <= 0:
                continue
            cumulative += item_count
            offset = round(bar_height * cumulative / count)
            segment_height = offset - previous_offset
            if segment_height <= 0:
                continue
            segment_y = baseline - offset
            segments.append(
                f'<rect x="{bar_x:.1f}" y="{segment_y}" width="{bar_width}" '
                f'height="{segment_height}" fill="{color_for(item, theme)}"/>'
            )
            previous_offset = offset

        clip_attr = f' clip-path="url(#{clip_id})"' if use_clip else ""
        parts.append(f'  <g{clip_attr}>{"".join(segments)}</g>')
        parts.append(
            f'  <text x="{center_x:.1f}" y="{bar_top - 9}" class="count" '
            f'text-anchor="middle">{format_int(count)}</text>'
        )

    # Легенда: каждая строка центрируется по горизонтали независимо.
    gap = 30
    for row_index, row in enumerate(legend):
        row_width = sum(item_width for _, _, item_width in row) + gap * (len(row) - 1)
        cursor = (CANVAS_WIDTH - row_width) / 2
        row_y = legend_top + row_index * legend_pitch
        for color, label, item_width in row:
            parts.append(f'  <circle cx="{cursor + 5:.1f}" cy="{row_y - 4}" r="5" fill="{color}"/>')
            parts.append(
                f'  <text x="{cursor + 18:.1f}" y="{row_y}" class="legend">{xml(label)}</text>'
            )
            cursor += item_width + gap

    defs_block = "  <defs>\n" + "\n".join(defs) + "\n  </defs>\n" if defs else ""
    return svg_document(
        height,
        "Активность коммитов по месяцам",
        "Количество коммитов по всем предметам за последние двенадцать месяцев относительно последнего обновления архива.",
        theme,
        defs_block + "\n".join(parts),
    )


# ---------------------------------------------------------------------------
# 8. Запись файлов и README-блоков
# ---------------------------------------------------------------------------


def write_file(path: Path, content: str, check: bool) -> bool:
    old = path.read_text(encoding="utf-8") if path.exists() else None
    if old == content:
        return False

    if check:
        return True

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def write_binary_file(path: Path, content: bytes, check: bool) -> bool:
    old = path.read_bytes() if path.exists() else None
    if old == content:
        return False

    if check:
        return True

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return True


def update_assets(root: Path, stats: list[SubmoduleStats], totals: Totals, check: bool) -> bool:
    asset_dir = root / README_ASSET_DIR
    assets = {
        OVERVIEW_SVG: render_overview_svg(stats, totals, LIGHT_THEME),
        OVERVIEW_SVG_DARK: render_overview_svg(stats, totals, DARK_THEME),
        ACTIVITY_SVG: render_activity_svg(stats, totals, LIGHT_THEME),
        ACTIVITY_SVG_DARK: render_activity_svg(stats, totals, DARK_THEME),
    }

    changed = False
    for filename, content in assets.items():
        changed |= write_file(asset_dir / filename, content, check=check)

    changed |= write_binary_file(
        asset_dir / PIXEL_PNG,
        base64.b64decode(PIXEL_PNG_BASE64),
        check=check,
    )
    return changed


def picture_block(prefix: str, light: str, dark: str, alt: str) -> list[str]:
    return [
        "<picture>",
        f'  <source media="(prefers-color-scheme: dark)" srcset="{prefix}/{dark}">',
        f'  <img alt="{alt}" src="{prefix}/{light}">',
        "</picture>",
    ]


def generate_root_block(stats: list[SubmoduleStats], totals: Totals) -> str:
    prefix = README_ASSET_DIR.as_posix()
    rows = [
        *picture_block(prefix, OVERVIEW_SVG, OVERVIEW_SVG_DARK, "Пульс архива"),
        "",
        *picture_block(prefix, ACTIVITY_SVG, ACTIVITY_SVG_DARK, "Активность коммитов"),
    ]
    return "\n".join(rows)


def course_title(course_dir: str) -> str:
    match = re.match(r"^(\d+)_course$", course_dir)
    if match:
        return f"{match.group(1)}-й курс"
    return humanize_name(course_dir) if course_dir else "Прочее"


def semester_sort_key(semester: str) -> tuple[int, int]:
    numbers = [int(number) for number in re.findall(r"\d+", semester)]
    if not numbers:
        return (99, 99)
    return (numbers[0], numbers[-1])


def generate_structure_block(stats: list[SubmoduleStats]) -> str:
    """Таблицы «Структура материалов», сгруппированные по курсам из путей сабмодулей."""

    courses: dict[str, list[SubmoduleStats]] = {}
    for item in stats:
        path_parts = item.submodule.path.parts
        course = path_parts[0] if len(path_parts) > 1 else ""
        courses.setdefault(course, []).append(item)

    def course_order(course: str) -> tuple[int, int, str]:
        match = re.match(r"^(\d+)", course)
        return (0, int(match.group(1)), course) if match else (1, 0, course)

    pixel_src = f"{README_ASSET_DIR.as_posix()}/{PIXEL_PNG}"
    header_cells = " | ".join(
        f'{title}<img src="{pixel_src}" width="{width}" height="1" alt="">'
        for title, width in STRUCTURE_COLUMNS
    )

    blocks: list[str] = []
    for course in sorted(courses, key=course_order):
        rows = sorted(
            courses[course],
            key=lambda item: (semester_sort_key(item.submodule.semester), item.submodule.title),
        )
        lines = [
            f"### {course_title(course)}",
            "",
            f"| {header_cells} |",
            "| --- | --- | --- | --- |",
        ]
        for item in rows:
            submodule = item.submodule
            folder = f"[`{submodule.path.name}/`]({submodule.path.as_posix()}/)"
            lines.append(
                f"| {submodule.semester} | {submodule.title} | {folder} | {submodule.stack_badges} |"
            )
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)


def strip_old_root_section(readme: str) -> str:
    if OLD_SECTION_TITLE not in readme or OLD_START_MARKER not in readme or OLD_END_MARKER not in readme:
        return readme

    heading_index = readme.find(OLD_SECTION_TITLE)
    after_marker = readme.find(OLD_END_MARKER, heading_index)
    if heading_index == -1 or after_marker == -1:
        return readme

    end_index = after_marker + len(OLD_END_MARKER)
    while end_index < len(readme) and readme[end_index] in "\r\n":
        end_index += 1

    return readme[:heading_index].rstrip() + "\n\n" + readme[end_index:].lstrip()


def render_marked_section(
    readme: str,
    title: str,
    start_marker: str,
    end_marker: str,
    block: str,
    insertion_heading: str | None,
) -> str:
    marked_block = f"{start_marker}\n{block}\n{end_marker}"

    if start_marker in readme and end_marker in readme:
        before, rest = readme.split(start_marker, 1)
        _, after = rest.split(end_marker, 1)
        return f"{before}{marked_block}{after}"

    section = f"{title}\n\n{marked_block}\n\n"
    if insertion_heading:
        insertion_point = readme.find(f"\n{insertion_heading}")
        if insertion_point != -1:
            return readme[: insertion_point + 1] + section + readme[insertion_point + 1 :]

    return readme.rstrip() + "\n\n" + section


def render_root_readme(old: str, structure_block: str, pulse_block: str) -> str:
    cleaned = strip_old_root_section(old)
    cleaned = render_marked_section(
        cleaned,
        STRUCTURE_SECTION_TITLE,
        STRUCTURE_START_MARKER,
        STRUCTURE_END_MARKER,
        structure_block,
        insertion_heading=ROOT_SECTION_TITLE,
    )
    return render_marked_section(
        cleaned,
        ROOT_SECTION_TITLE,
        ROOT_START_MARKER,
        ROOT_END_MARKER,
        pulse_block,
        insertion_heading="## Контакты",
    )




def generate_profile_readme(root_readme: str, asset_prefix: str, repo_url: str) -> str:
    """Полное зеркало корневого README для профиля организации.

    Пути картинок пульса переводятся на скопированные ассеты профиля, а все
    относительные ссылки (папки предметов, LICENSE и т.п.) — на абсолютные
    URL архива, чтобы ничего не билось на странице организации.
    """

    prefix = asset_prefix.rstrip("/")
    content = root_readme.replace(f"{README_ASSET_DIR.as_posix()}/", f"{prefix}/")

    def absolutize(match: re.Match[str]) -> str:
        target = match.group(1)
        kind = "tree" if target.endswith("/") else "blob"
        return f"]({repo_url}/{kind}/main/{target})"

    content = re.sub(
        r"\]\((?!https?://|#|mailto:)([^)\s]+)\)",
        absolutize,
        content,
    )
    return content


# ---------------------------------------------------------------------------
# 9. CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Update README.md, SVG pulse assets, and optional organization profile README."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if generated files would change.",
    )
    parser.add_argument(
        "--profile-readme",
        type=Path,
        help="Optional path to an organization profile README.md to update.",
    )
    parser.add_argument(
        "--profile-assets-prefix",
        default=DEFAULT_PROFILE_ASSET_PREFIX,
        help="Image path prefix used inside the organization profile README.",
    )
    parser.add_argument(
        "--repository-url",
        help="Public URL of this archive repository used in generated profile links.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    stats = [collect_stats(root, submodule) for submodule in read_submodules(root)]
    totals = compute_totals(stats)
    repo_url = args.repository_url or repository_url(root)

    changed = False
    changed |= update_assets(root, stats, totals, check=args.check)

    readme_path = root / "README.md"
    new_readme = render_root_readme(
        readme_path.read_text(encoding="utf-8"),
        generate_structure_block(stats),
        generate_root_block(stats, totals),
    )
    changed |= write_file(readme_path, new_readme, check=args.check)

    if args.profile_readme:
        profile_content = generate_profile_readme(
            new_readme,
            asset_prefix=args.profile_assets_prefix,
            repo_url=repo_url,
        )
        changed |= write_file(args.profile_readme, profile_content, check=args.check)

    if args.check and changed:
        print("Generated README pulse files are out of date.", file=sys.stderr)
        return 1

    print("Generated README pulse files are up to date." if not changed else "Generated README pulse files updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
