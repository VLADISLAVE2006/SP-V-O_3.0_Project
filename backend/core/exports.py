import csv
import io
import os
from pathlib import Path
from xml.sax.saxutils import escape

from django.http import HttpResponse
from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from rest_framework.exceptions import ValidationError

from .services import results


def safe_cell(value):
    text = str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else text


def export_results(poll, format):
    if format not in {"csv", "xlsx", "pdf"}:
        raise ValidationError({"format": "Допустимо csv, xlsx или pdf."})
    summary = results(poll)
    rows = [["Вопрос", "Вариант", "Голосов", "Процент", "Всего прохождений"]]
    for q in summary["questions"]:
        for option in q["options"]:
            rows.append(
                [q["text"], option["text"], option["votes"], option["percent"], summary["total_responses"]]
            )
    # Never include participant identifiers in anonymous exports.
    if poll.access_mode == "registered":
        rows.append([])
        rows.append(["Участник", "Никнейм", "Вопрос", "Выбранный вариант", "Дата прохождения"])
        for response in (
            poll.responses.select_related("user")
            .prefetch_related("answers__question", "answers__option")
            .order_by("pk")
        ):
            for answer in response.answers.all():
                rows.append(
                    [
                        response.user_id,
                        response.user.nickname,
                        answer.question.text,
                        answer.option.text,
                        response.created_at.isoformat(),
                    ]
                )
    if format == "csv":
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerows([[safe_cell(v) for v in row] for row in rows])
        content = stream.getvalue().encode("utf-8-sig")
        mime = "text/csv; charset=utf-8"
    elif format == "xlsx":
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Результаты"
        for row in rows:
            sheet.append(row)
        # Force user text to strings: never export executable formulas.
        for row in sheet:
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = "s"
        for key, width in {"A": 50, "B": 40, "C": 35, "D": 40, "E": 32}.items():
            sheet.column_dimensions[key].width = width
        sheet.freeze_panes = "A2"
        stream = io.BytesIO()
        workbook.save(stream)
        content = stream.getvalue()
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        font_path = next(
            (
                p
                for p in [
                    os.environ.get("PDF_FONT_PATH", ""),
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                    "C:/Windows/Fonts/arial.ttf",
                ]
                if p and Path(p).is_file()
            ),
            None,
        )
        if not font_path:
            raise RuntimeError("Install DejaVu Sans or set PDF_FONT_PATH.")
        if "PollsFont" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("PollsFont", font_path))
        styles = getSampleStyleSheet()
        for name in ["Normal", "Title"]:
            styles[name].fontName = "PollsFont"
        styles["Normal"].fontSize = 8
        styles["Normal"].leading = 11
        stream = io.BytesIO()
        document = SimpleDocTemplate(
            stream, pagesize=landscape(A4), leftMargin=28, rightMargin=28, topMargin=28, bottomMargin=28
        )
        cells = [
            [Paragraph(escape(str(v)), styles["Normal"]) for v in row] if row else [""] * 5 for row in rows
        ]
        table = Table(cells, colWidths=[215, 160, 120, 160, 130], repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        document.build([Paragraph(escape(poll.title), styles["Title"]), Spacer(1, 12), table])
        content = stream.getvalue()
        mime = "application/pdf"
    response = HttpResponse(content, content_type=mime)
    response["Content-Disposition"] = f'attachment; filename="poll-{poll.slug}.{format}"'
    return response
