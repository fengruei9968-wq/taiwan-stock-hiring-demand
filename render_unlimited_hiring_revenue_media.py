#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render unlimited-hiring revenue report artifacts to PDF and PNG."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from generate_unlimited_hiring_revenue_report import (
    build_report_rows,
    load_revenue_summary,
    read_hiring_rows,
    select_unlimited_rows,
    to_float_or_none,
)
from hiring_anomaly_detector import HIRING_DEMAND_WEB_URL


DEFAULT_MANIFEST = Path("data/reports/latest_unlimited_hiring_revenue_report_manifest.json")
PDF_FONT = "STHeiti"
PDF_FONT_PATH = "/System/Library/Fonts/STHeiti Medium.ttc"
PNG_MODE = "anomaly_detection_summary"
PNG_FOOTER_TEXT = "同步更新至徵人需求度網頁"
REVENUE_WINDOW_MONTHS = 6
PNG_FONT_PROFILE_DEFAULT = "hiragino_mixed"
PNG_FONT_CANDIDATES = [
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
]
PNG_FONT_PROFILES = {
    "system_heiti": {
        "chinese": PNG_FONT_CANDIDATES,
        "latin": PNG_FONT_CANDIDATES,
        "number": PNG_FONT_CANDIDATES,
        "mono": PNG_FONT_CANDIDATES,
    },
    "sf_mixed": {
        "chinese": [
            "/System/Library/Fonts/STHeiti Medium.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        ],
        "latin": [
            "/System/Library/Fonts/SFNS.ttf",
            "/System/Library/Fonts/HelveticaNeue.ttc",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        ],
        "number": [
            "/System/Library/Fonts/SFNS.ttf",
            "/System/Library/Fonts/HelveticaNeue.ttc",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        ],
        "mono": [
            "/System/Library/Fonts/SFNSMono.ttf",
            "/System/Library/Fonts/SFNS.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        ],
    },
    "sf_mono_numbers": {
        "chinese": [
            "/System/Library/Fonts/STHeiti Medium.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        ],
        "latin": [
            "/System/Library/Fonts/SFNS.ttf",
            "/System/Library/Fonts/HelveticaNeue.ttc",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        ],
        "number": [
            "/System/Library/Fonts/SFNSMono.ttf",
            "/System/Library/Fonts/SFNS.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        ],
        "mono": [
            "/System/Library/Fonts/SFNSMono.ttf",
            "/System/Library/Fonts/SFNS.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        ],
    },
    "hiragino_mixed": {
        "chinese": [
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
            "/System/Library/Fonts/STHeiti Medium.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
        ],
        "latin": [
            "/System/Library/Fonts/SFNS.ttf",
            "/System/Library/Fonts/HelveticaNeue.ttc",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        ],
        "number": [
            "/System/Library/Fonts/SFNS.ttf",
            "/System/Library/Fonts/HelveticaNeue.ttc",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        ],
        "mono": [
            "/System/Library/Fonts/SFNSMono.ttf",
            "/System/Library/Fonts/SFNS.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        ],
    },
}


def register_pdf_font() -> str:
    if Path(PDF_FONT_PATH).exists():
        pdfmetrics.registerFont(TTFont(PDF_FONT, PDF_FONT_PATH, subfontIndex=0))
        return PDF_FONT
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    return "STSong-Light"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_new_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def format_num(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{number:.2f}"


def display_ratio(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value or "")
    if number == 999.0:
        return "人數不限"
    if number == 998.0:
        return "未標示"
    return f"{number:.2f}%"


def revenue_months(row: dict[str, Any]) -> list[str]:
    return [
        "" if row.get(f"m{index}_label") in (None, "") else str(row.get(f"m{index}_label"))
        for index in range(1, REVENUE_WINDOW_MONTHS + 1)
    ]


def revenue_values(row: dict[str, Any], metric: str) -> list[float | None]:
    return [to_float_or_none(row.get(f"m{index}_{metric}")) for index in range(1, REVENUE_WINDOW_MONTHS + 1)]


def revenue_chart_scale(*rows: dict[str, Any]) -> float:
    values: list[float] = []
    for row in rows:
        for metric in ("mom", "yoy"):
            values.extend(abs(value) for value in revenue_values(row, metric) if value is not None)
    return max(values + [5.0])


def make_pdf_revenue_chart(row: dict[str, Any], metric: str, font_name: str) -> Drawing:
    width = 68 * mm
    height = 21 * mm
    base_y = 10 * mm
    bar_width = 4.8 * mm
    gap = 5.2 * mm
    start_x = 5 * mm
    values = revenue_values(row, metric)
    months = revenue_months(row)
    max_abs = max([abs(value) for value in values if value is not None] + [5.0])
    drawing = Drawing(width, height)
    drawing.add(Line(3 * mm, base_y, width - 3 * mm, base_y, strokeColor=colors.HexColor("#CBD5E1"), strokeWidth=0.4))
    for index, value in enumerate(values):
        x = start_x + index * (bar_width + gap)
        label = months[index].split("/")[-1] + "月" if months[index] else "-"
        if value is None:
            drawing.add(Rect(x + bar_width / 2 - 1, base_y - 2, 2, 4, fillColor=colors.HexColor("#94A3B8"), strokeColor=None))
            drawing.add(String(x + bar_width / 2, 1.5 * mm, label, textAnchor="middle", fontName=font_name, fontSize=5, fillColor=colors.HexColor("#64748B")))
            continue
        bar_h = max(2 * mm, min(8 * mm, abs(value) / max_abs * 8 * mm))
        is_pos = value >= 0
        y = base_y if is_pos else base_y - bar_h
        color = colors.HexColor("#EF4444" if is_pos else "#14B8A6")
        drawing.add(Rect(x, y, bar_width, bar_h, rx=1.8, ry=1.8, fillColor=color, strokeColor=None))
        text_y = base_y + bar_h + 1.2 * mm if is_pos else base_y - bar_h - 2.6 * mm
        text_y = max(1.5 * mm, min(height - 2 * mm, text_y))
        if abs(value) >= 8 or index == len(values) - 1:
            drawing.add(String(x + bar_width / 2, text_y, f"{value:+.0f}", textAnchor="middle", fontName=font_name, fontSize=4.3, fillColor=colors.HexColor("#334155")))
        drawing.add(String(x + bar_width / 2, 1.5 * mm, label, textAnchor="middle", fontName=font_name, fontSize=4.7, fillColor=colors.HexColor("#64748B")))
    return drawing


def get_report_rows(manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    latest_rows = read_hiring_rows(Path(manifest["latest_csv"]))
    previous_rows = read_hiring_rows(Path(manifest["previous_csv"]))
    latest_unlimited = select_unlimited_rows(latest_rows)
    stock_codes = sorted({row.get("股票代碼", "") for row in latest_unlimited if row.get("股票代碼", "")})
    revenue_by_code = load_revenue_summary(Path(manifest["db_path"]), stock_codes)
    report_rows, new_rows, current_month_rows, revenue_turnaround_rows, revenue_growth_rows, _ = build_report_rows(latest_rows, previous_rows, revenue_by_code)
    return report_rows, new_rows, current_month_rows, revenue_turnaround_rows, revenue_growth_rows


def write_pdf(
    path: Path,
    manifest: dict[str, Any],
    report_rows: list[dict[str, Any]],
    new_rows: list[dict[str, Any]],
    current_month_rows: list[dict[str, Any]],
    revenue_turnaround_rows: list[dict[str, Any]],
    revenue_growth_rows: list[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    font_name = register_pdf_font()
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="CJKTitle",
            parent=styles["Title"],
            fontName=font_name,
            fontSize=18,
            leading=24,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CJKBody",
            parent=styles["BodyText"],
            fontName=font_name,
            fontSize=9,
            leading=12,
        )
    )
    doc = SimpleDocTemplate(
        str(path),
        pagesize=landscape(A4),
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title=f"徵人需求度異常偵測摘要 {manifest['report_date']}",
    )
    story: list[Any] = [
        Paragraph(f"徵人需求度異常偵測摘要 {manifest['report_date']}", styles["CJKTitle"]),
        Paragraph(
            (
                f"前一日：{manifest['previous_date']}　"
                f"今日人數不限：{manifest['latest_unlimited_count']}　"
                f"今日新增：{manifest['new_unlimited_count']}　"
                f"營收轉正觀察：{manifest.get('revenue_turnaround_count', 0)}　"
                f"營收雙指標改善觀察：{manifest.get('current_month_revenue_increase_count', 0)}　"
                f"營收強勢延續公司：{manifest.get('revenue_growth_count', 0)}　"
                f"營收覆蓋：{manifest['revenue_covered_count']}/{manifest['latest_unlimited_count']}"
            ),
            styles["CJKBody"],
        ),
        Paragraph(f"回網頁查看：{HIRING_DEMAND_WEB_URL}", styles["CJKBody"]),
        Paragraph("紅色為正成長率，綠色為負成長率；每格長條以該公司該指標近六個月最大絕對值縮放，缺值以 - 呈現。", styles["CJKBody"]),
        Spacer(1, 6),
    ]

    def make_table(rows: list[dict[str, Any]]) -> Table:
        data: list[list[Any]] = [["代碼", "公司", "市場", "不限", "明確", "需求度", "MoM 長條", "YoY 長條", "新增"]]
        for row in rows:
            data.append(
                [
                    str(row.get("股票代碼", "")),
                    str(row.get("公司簡稱", "")),
                    str(row.get("市場類別", "")),
                    str(row.get("不限職缺數", "")),
                    str(row.get("明確需求人數", "")),
                    display_ratio(row.get("徵人需求度", "")),
                    make_pdf_revenue_chart(row, "mom", font_name),
                    make_pdf_revenue_chart(row, "yoy", font_name),
                    str(row.get("今日新增公司", "")),
                ]
            )
        if len(data) == 1:
            data.append(["無資料", "", "", "", "", "", "", "", ""])
        table = Table(
            data,
            repeatRows=1,
            colWidths=[15 * mm, 26 * mm, 14 * mm, 11 * mm, 11 * mm, 18 * mm, 70 * mm, 70 * mm, 10 * mm],
        )
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), font_name),
                    ("FONTSIZE", (0, 0), (-1, -1), 7.2),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6edf5")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1f2933")),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#b8c2cc")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fb")]),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (3, 1), (5, -1), "RIGHT"),
                    ("ALIGN", (6, 1), (7, -1), "CENTER"),
                ]
            )
        )
        return table

    def add_section(title: str, rows: list[dict[str, Any]], *, page_break: bool = False) -> None:
        if page_break and len(story) > 0:
            story.append(PageBreak())
        story.append(Paragraph(title, styles["CJKBody"]))
        story.append(make_table(rows))
        story.append(Spacer(1, 8))

    add_section("今日新增不限徵才", new_rows)
    add_section("營收轉正觀察", revenue_turnaround_rows, page_break=True)
    add_section("營收雙指標改善觀察", current_month_rows, page_break=True)
    add_section("營收強勢延續公司", revenue_growth_rows, page_break=True)
    doc.build(story)


def resolve_png_font_path(profile: str, role: str) -> str:
    profile_spec = PNG_FONT_PROFILES.get(profile)
    if profile_spec is None:
        raise ValueError(f"Unknown PNG font profile: {profile}")
    candidates = profile_spec.get(role, PNG_FONT_CANDIDATES)
    for font_path in candidates:
        path = Path(font_path)
        if path.exists():
            return str(path)
    return ""


def load_png_font(size: int, *, profile: str = PNG_FONT_PROFILE_DEFAULT, role: str = "chinese") -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_path = resolve_png_font_path(profile, role)
    if font_path:
        try:
            return ImageFont.truetype(font_path, size=size)
        except OSError:
            pass
    return ImageFont.load_default()


def png_font_paths(profile: str) -> dict[str, str]:
    return {
        "chinese": resolve_png_font_path(profile, "chinese"),
        "latin": resolve_png_font_path(profile, "latin"),
        "number": resolve_png_font_path(profile, "number"),
        "mono": resolve_png_font_path(profile, "mono"),
        "chart_value": resolve_png_font_path(profile, "latin"),
        "chart_month": resolve_png_font_path(profile, "chinese"),
    }


def draw_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font: ImageFont.ImageFont, fill: str = "#1f2933") -> None:
    draw.text(xy, text, font=font, fill=fill)


def truncate_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
        return text
    suffix = "..."
    while text and draw.textbbox((0, 0), text + suffix, font=font)[2] > max_width:
        text = text[:-1]
    return text + suffix if text else suffix


def draw_png_revenue_chart(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    row: dict[str, Any],
    metric: str,
    value_font: ImageFont.ImageFont,
    month_font: ImageFont.ImageFont,
) -> None:
    chart_w, chart_h = 280, 82
    base_y = y + 43
    draw.line((x, base_y, x + chart_w, base_y), fill="#CBD5E1", width=2)
    values = revenue_values(row, metric)
    months = revenue_months(row)
    max_abs = max([abs(value) for value in values if value is not None] + [5.0])
    bar_w, gap = 22, 20
    start_x = x + 14
    for index, value in enumerate(values):
        bx = start_x + index * (bar_w + gap)
        month = (months[index].split("/")[-1] + "月") if months[index] else "-"
        if value is None:
            draw.rounded_rectangle((bx + 8, base_y - 4, bx + 14, base_y + 4), radius=3, fill="#94A3B8")
            draw_text(draw, (bx - 1, y + chart_h - 18), month, month_font, "#64748B")
            continue
        bar_h = max(7, min(34, round(abs(value) / max_abs * 34)))
        positive = value >= 0
        by0 = base_y - bar_h if positive else base_y
        by1 = base_y if positive else base_y + bar_h
        color = "#EF4444" if positive else "#14B8A6"
        draw.rounded_rectangle((bx, by0, bx + bar_w, by1), radius=5, fill=color)
        value_label = f"{value:+.1f}"
        label_y = max(y, by0 - 22) if positive else min(y + chart_h - 36, by1 + 4)
        if abs(value) >= 8 or index == len(values) - 1:
            draw_text(draw, (bx - 5, label_y), value_label, value_font, "#334155")
        draw_text(draw, (bx - 1, y + chart_h - 18), month, month_font, "#64748B")


def build_png_section_specs(
    new_rows: list[dict[str, Any]],
    current_month_rows: list[dict[str, Any]],
    revenue_turnaround_rows: list[dict[str, Any]],
    revenue_growth_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "key": "today_new_unlimited",
            "kind": "company_cards",
            "title": "今日新增不限徵才",
            "subtitle": "今日新增進入不限職缺觀察名單",
            "rows": new_rows,
            "accent": "#EF4444",
            "empty": "今日沒有新增公司",
        },
        {
            "key": "revenue_turnaround",
            "kind": "company_cards",
            "title": "營收轉正觀察",
            "subtitle": "不限徵才，YoY 由負轉正且最新月 MoM 仍為正",
            "rows": revenue_turnaround_rows,
            "accent": "#2563EB",
            "empty": "目前沒有營收轉正觀察公司",
        },
        {
            "key": "current_month_revenue_increase",
            "kind": "company_cards",
            "title": "營收雙指標改善觀察",
            "subtitle": "不限徵才，且本月 MoM、YoY 均較上月走升",
            "rows": current_month_rows,
            "accent": "#CA8A04",
            "empty": "目前沒有營收雙指標改善公司",
        },
        {
            "key": "three_month_revenue_growth",
            "kind": "company_cards",
            "title": "營收強勢延續公司",
            "subtitle": "不限徵才，且 MoM、YoY 近三個月同步走升",
            "rows": revenue_growth_rows,
            "accent": "#14B8A6",
            "empty": "目前沒有營收強勢延續公司",
        },
    ]


def build_png_section_metadata(section_specs: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    metadata: dict[str, dict[str, int]] = {}
    for spec in section_specs:
        row_count = len(spec["rows"])
        metadata[spec["key"]] = {
            "total_count": row_count,
            "displayed_count": row_count,
        }
    return metadata


def draw_chip(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    *,
    fill: str,
    text_fill: str,
) -> int:
    x, y = xy
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0] + 24
    draw.rounded_rectangle((x, y, x + width, y + 30), radius=15, fill=fill)
    draw_text(draw, (x + 12, y + 6), text, font, text_fill)
    return x + width + 8


def draw_metric_card(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    size: tuple[int, int],
    *,
    label: str,
    value: str,
    caption: str,
    accent: str,
    value_font: ImageFont.ImageFont,
    label_font: ImageFont.ImageFont,
    small_font: ImageFont.ImageFont,
) -> None:
    x, y = xy
    width, height = size
    draw.rounded_rectangle((x, y, x + width, y + height), radius=18, fill="#FFFFFF", outline="#DFE6EE", width=2)
    draw.rounded_rectangle((x, y, x + 9, y + height), radius=5, fill=accent)
    draw_text(draw, (x + 28, y + 18), label, label_font, "#4B5563")
    # SFNS looks good for digits but does not cover CJK. Draw the numeric part
    # and the Chinese unit / 中文單位 separately so units like "家" never render as tofu.
    value_parts = value.split(" ", 1)
    draw_text(draw, (x + 28, y + 48), value_parts[0], value_font, "#111827")
    if len(value_parts) > 1:
        number_bbox = draw.textbbox((x + 28, y + 48), value_parts[0], font=value_font)
        draw_text(draw, (number_bbox[2] + 12, y + 61), value_parts[1], label_font, "#111827")
    draw_text(draw, (x + 28, y + 103), caption, small_font, "#64748B")


def draw_row_card(
    draw: ImageDraw.ImageDraw,
    row: dict[str, Any],
    *,
    x: int,
    y: int,
    width: int,
    accent: str,
    body_font: ImageFont.ImageFont,
    code_font: ImageFont.ImageFont,
    small_font: ImageFont.ImageFont,
    tiny_font: ImageFont.ImageFont,
    chart_font: ImageFont.ImageFont,
    chart_month_font: ImageFont.ImageFont,
) -> None:
    draw.rounded_rectangle((x, y, x + width, y + 112), radius=18, fill="#FFFFFF", outline="#E1E7EF", width=1)
    draw.rounded_rectangle((x, y, x + 7, y + 112), radius=4, fill=accent)
    code = str(row.get("股票代碼", ""))
    name = truncate_text(draw, str(row.get("公司簡稱", "")), body_font, 210)
    draw_text(draw, (x + 26, y + 18), code, code_font, "#111827")
    draw_text(draw, (x + 118, y + 18), name, body_font, "#111827")
    chip_x = x + 26
    chip_x = draw_chip(draw, (chip_x, y + 63), str(row.get("市場類別", "")), tiny_font, fill="#EEF2FF", text_fill="#3730A3")
    chip_x = draw_chip(draw, (chip_x, y + 63), f"不限 {row.get('不限職缺數', '')}", tiny_font, fill="#FEF2F2", text_fill="#B91C1C")
    draw_chip(draw, (chip_x, y + 63), display_ratio(row.get("徵人需求度", "")), tiny_font, fill="#ECFDF5", text_fill="#047857")
    if row.get("今日新增公司") == "YES":
        draw_chip(draw, (x + 410, y + 18), "今日新增", tiny_font, fill="#FEE2E2", text_fill="#B91C1C")

    draw_text(draw, (x + 560, y + 14), "MoM", chart_font, "#334155")
    draw_png_revenue_chart(draw, x + 610, y + 18, row, "mom", chart_font, chart_month_font)
    draw_text(draw, (x + 920, y + 14), "YoY", chart_font, "#334155")
    draw_png_revenue_chart(draw, x + 970, y + 18, row, "yoy", chart_font, chart_month_font)


def write_png(
    path: Path,
    manifest: dict[str, Any],
    section_specs: list[dict[str, Any]],
    *,
    png_scale: float = 1.0,
    png_dpi: int = 144,
    png_font_profile: str = PNG_FONT_PROFILE_DEFAULT,
) -> None:
    if png_scale < 1:
        raise ValueError("png_scale must be >= 1")
    if png_dpi < 1:
        raise ValueError("png_dpi must be >= 1")
    path.parent.mkdir(parents=True, exist_ok=True)
    width = 1680
    row_h = 126
    section_gap = 34
    section_heights = []
    for spec in section_specs:
        section_heights.append(128 + max(1, len(spec["rows"])) * row_h + 42)
    height = 430 + sum(section_heights) + section_gap * (len(section_specs) - 1) + 82
    image = Image.new("RGB", (width, height), "#F6F8FB")
    draw = ImageDraw.Draw(image)
    title_font = load_png_font(48, profile=png_font_profile, role="chinese")
    metric_font = load_png_font(46, profile=png_font_profile, role="number")
    heading_font = load_png_font(30, profile=png_font_profile, role="chinese")
    body_font = load_png_font(23, profile=png_font_profile, role="chinese")
    code_font = load_png_font(23, profile=png_font_profile, role="number")
    small_font = load_png_font(18, profile=png_font_profile, role="chinese")
    tiny_font = load_png_font(15, profile=png_font_profile, role="chinese")
    chart_font = load_png_font(15, profile=png_font_profile, role="latin")
    chart_month_font = load_png_font(15, profile=png_font_profile, role="chinese")

    draw.rounded_rectangle((42, 36, width - 42, 386), radius=26, fill="#FFFFFF", outline="#DCE3EC", width=2)
    draw.rounded_rectangle((42, 36, width - 42, 104), radius=26, fill="#111827")
    draw.rectangle((42, 72, width - 42, 104), fill="#111827")
    draw_text(draw, (76, 53), f"徵人需求度異常偵測摘要 {manifest['report_date']}", title_font, "#FFFFFF")
    draw_text(draw, (78, 126), "有新增不限人數公司，或不限人數公司營收動能轉強時提醒回網頁查看。", body_font, "#475569")
    draw_text(draw, (78, 162), "紅色為正成長率，綠色為負成長率；長條以該公司該指標近六個月最大絕對值縮放，缺值以 - 呈現。", small_font, "#64748B")

    metric_y = 214
    metric_w = 360
    metric_gap = 24
    metric_xs = [78 + index * (metric_w + metric_gap) for index in range(4)]
    draw_metric_card(
        draw,
        (metric_xs[0], metric_y),
        (metric_w, 132),
        label="今日新增不限徵才",
        value=f"{manifest['new_unlimited_count']} 家",
        caption=f"昨日不限 {manifest['previous_unlimited_count']} 家",
        accent="#EF4444",
        value_font=metric_font,
        label_font=small_font,
        small_font=tiny_font,
    )
    draw_metric_card(
        draw,
        (metric_xs[1], metric_y),
        (metric_w, 132),
        label="營收轉正",
        value=f"{manifest.get('revenue_turnaround_count', 0)} 家",
        caption="YoY 轉正且 MoM 正",
        accent="#2563EB",
        value_font=metric_font,
        label_font=small_font,
        small_font=tiny_font,
    )
    draw_metric_card(
        draw,
        (metric_xs[2], metric_y),
        (metric_w, 132),
        label="營收雙指標改善",
        value=f"{manifest.get('current_month_revenue_increase_count', 0)} 家",
        caption="MoM、YoY 均較上月走升",
        accent="#CA8A04",
        value_font=metric_font,
        label_font=small_font,
        small_font=tiny_font,
    )
    draw_metric_card(
        draw,
        (metric_xs[3], metric_y),
        (metric_w, 132),
        label="營收強勢延續",
        value=f"{manifest.get('revenue_growth_count', 0)} 家",
        caption="MoM、YoY 近三月同步走升",
        accent="#14B8A6",
        value_font=metric_font,
        label_font=small_font,
        small_font=tiny_font,
    )

    y = 430
    for spec, section_h in zip(section_specs, section_heights):
        rows = spec["rows"]
        accent = spec["accent"]
        draw.rounded_rectangle((42, y, width - 42, y + section_h), radius=24, fill="#FFFFFF", outline="#DCE3EC", width=2)
        draw.rounded_rectangle((42, y, width - 42, y + 82), radius=24, fill="#FAFBFC")
        draw.rectangle((42, y + 40, width - 42, y + 82), fill="#FAFBFC")
        draw.rounded_rectangle((66, y + 25, 78, y + 59), radius=6, fill=accent)
        draw_text(draw, (94, y + 18), f"{spec['title']}（{len(rows)} 家）", heading_font, "#111827")
        draw_text(draw, (94, y + 56), spec["subtitle"], small_font, "#64748B")
        row_y = y + 104
        if not rows:
            draw.rounded_rectangle((66, row_y, width - 66, row_y + 112), radius=18, fill="#F8FAFC", outline="#E1E7EF", width=1)
            draw_text(draw, (92, row_y + 40), spec["empty"], body_font, "#64748B")
        else:
            for row in rows:
                draw_row_card(
                    draw,
                    row,
                    x=66,
                    y=row_y,
                    width=width - 132,
                    accent=accent,
                    body_font=body_font,
                    code_font=code_font,
                    small_font=small_font,
                    tiny_font=tiny_font,
                    chart_font=chart_font,
                    chart_month_font=chart_month_font,
                )
                row_y += row_h
        y += section_h + section_gap

    footer = f"{PNG_FOOTER_TEXT}：{HIRING_DEMAND_WEB_URL}"
    draw_text(draw, (70, height - 48), footer, small_font, "#475569")
    if png_scale != 1:
        resampling = getattr(Image, "Resampling", Image).LANCZOS
        image = image.resize((round(width * png_scale), round(height * png_scale)), resampling)
    image.save(path, dpi=(png_dpi, png_dpi))


def build_receipt(
    *,
    manifest_path: Path,
    pdf_path: Path,
    png_path: Path,
    manifest: dict[str, Any],
    png_sections: dict[str, dict[str, int]],
    png_scale: float,
    png_dpi: int,
    png_font_profile: str,
) -> dict[str, Any]:
    png_pixel_width = 0
    png_pixel_height = 0
    if png_path.exists():
        with Image.open(png_path) as image:
            png_pixel_width, png_pixel_height = image.size
    return {
        "receipt_type": "unlimited_hiring_revenue_media_render",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "manifest_path": str(manifest_path),
        "report_date": manifest.get("report_date", ""),
        "pdf_path": str(pdf_path),
        "png_path": str(png_path),
        "pdf_exists": pdf_path.exists(),
        "png_exists": png_path.exists(),
        "anomaly_summary_path": manifest.get("outputs", {}).get("anomaly_summary_json", ""),
        "primary_human_artifact": "png",
        "png_mode": PNG_MODE,
        "png_footer_text": PNG_FOOTER_TEXT,
        "png_scale": png_scale,
        "png_dpi": png_dpi,
        "png_pixel_width": png_pixel_width,
        "png_pixel_height": png_pixel_height,
        "png_font_profile": png_font_profile,
        "png_fonts": png_font_paths(png_font_profile),
        "revenue_window_months": REVENUE_WINDOW_MONTHS,
        "png_chart_bar_count": REVENUE_WINDOW_MONTHS,
        "pdf_chart_bar_count": REVENUE_WINDOW_MONTHS,
        "png_sections": png_sections,
        "web_review_url": HIRING_DEMAND_WEB_URL,
        "telegram_sent": False,
        "telegram_send_authorized": False,
        "renderer": {
            "pdf": "reportlab",
            "png": "pillow",
        },
    }


def render_media(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = Path(args.manifest)
    manifest = load_json(manifest_path)
    report_rows, new_rows, current_month_rows, revenue_turnaround_rows, revenue_growth_rows = get_report_rows(manifest)
    output_dir = Path(args.output_dir) if args.output_dir else Path(manifest["outputs"]["output_dir"])
    report_key = manifest["report_yyyymmdd"]
    pdf_path = output_dir / f"unlimited_hiring_revenue_report_{report_key}.pdf"
    png_path = output_dir / f"unlimited_hiring_revenue_report_{report_key}.png"
    receipt_path = output_dir / f"unlimited_hiring_revenue_media_receipt_{report_key}.json"
    section_specs = build_png_section_specs(new_rows, current_month_rows, revenue_turnaround_rows, revenue_growth_rows)
    write_pdf(pdf_path, manifest, report_rows, new_rows, current_month_rows, revenue_turnaround_rows, revenue_growth_rows)
    write_png(
        png_path,
        manifest,
        section_specs,
        png_scale=args.png_scale,
        png_dpi=args.png_dpi,
        png_font_profile=args.png_font_profile,
    )
    receipt = build_receipt(
        manifest_path=manifest_path,
        pdf_path=pdf_path,
        png_path=png_path,
        manifest=manifest,
        png_sections=build_png_section_metadata(section_specs),
        png_scale=args.png_scale,
        png_dpi=args.png_dpi,
        png_font_profile=args.png_font_profile,
    )
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    receipt["receipt_path"] = str(receipt_path)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render unlimited-hiring revenue report to PDF and PNG.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Report manifest path.")
    parser.add_argument("--output-dir", default="", help="Output directory. Defaults to manifest output_dir.")
    parser.add_argument("--png-scale", type=float, default=1.0, help="PNG pixel scale. Use 1.5 or 2 for Telegram document mode.")
    parser.add_argument("--png-dpi", type=int, default=144, help="PNG DPI metadata. Use 300 for Telegram document mode.")
    parser.add_argument(
        "--png-font-profile",
        choices=sorted(PNG_FONT_PROFILES.keys()),
        default=PNG_FONT_PROFILE_DEFAULT,
        help="PNG typography profile for visual A/B tests.",
    )
    return parser


def main() -> int:
    receipt = render_media(build_parser().parse_args())
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
