"""Convierte el manual en Markdown (subconjunto sencillo) a PDF con reportlab."""
import re
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable, KeepTogether, ListFlowable, ListItem, PageBreak, Paragraph,
    SimpleDocTemplate, Spacer, Table, TableStyle,
)

sys.stdout.reconfigure(encoding='utf-8')

FONTS = 'C:/Windows/Fonts/'
pdfmetrics.registerFont(TTFont('Segoe', FONTS + 'segoeui.ttf'))
pdfmetrics.registerFont(TTFont('Segoe-Bold', FONTS + 'segoeuib.ttf'))
pdfmetrics.registerFont(TTFont('Segoe-Italic', FONTS + 'segoeuii.ttf'))
pdfmetrics.registerFont(TTFont('Segoe-BoldItalic', FONTS + 'segoeuiz.ttf'))
pdfmetrics.registerFont(TTFont('Mono', FONTS + 'consola.ttf'))
pdfmetrics.registerFont(TTFont('SegoeSym', FONTS + 'seguisym.ttf'))
pdfmetrics.registerFontFamily('Segoe', normal='Segoe', bold='Segoe-Bold',
                              italic='Segoe-Italic', boldItalic='Segoe-BoldItalic')

INK = colors.HexColor('#1f2933')
ACCENT = colors.HexColor('#1d4e89')
MUTED = colors.HexColor('#52606d')
RULE = colors.HexColor('#cbd2d9')
HEAD_BG = colors.HexColor('#e4ecf5')
ZEBRA = colors.HexColor('#f5f7fa')
NOTE_BG = colors.HexColor('#fff7e0')
NOTE_BORDER = colors.HexColor('#e0a800')

def style(name, **kw):
    values = dict(fontName='Segoe', textColor=INK, alignment=TA_LEFT)
    values.update(kw)
    return ParagraphStyle(name, **values)


S = {
    'title': style('title', fontName='Segoe-Bold', fontSize=22, leading=28, textColor=ACCENT,
                   spaceAfter=10),
    'h1': style('h1', fontName='Segoe-Bold', fontSize=16, leading=21, textColor=ACCENT,
                spaceBefore=8, spaceAfter=8, keepWithNext=1),
    'h2': style('h2', fontName='Segoe-Bold', fontSize=12.5, leading=17, textColor=ACCENT,
                spaceBefore=10, spaceAfter=4, keepWithNext=1),
    'body': style('body', fontSize=10, leading=14.5, spaceAfter=6),
    'meta': style('meta', textColor=MUTED, fontSize=10, leading=14),
    'cell': style('cell', fontSize=8.8, leading=12),
    'cellh': style('cellh', fontName='Segoe-Bold', fontSize=8.8, leading=12),
    'note': style('note', fontSize=9.5, leading=13.5),
    'li': style('li', fontSize=10, leading=14),
}


def inline(text):
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    text = re.sub(r'\[(.+?)\]\([^)]*\)', r'\1', text)  # enlaces: solo el texto
    text = text.replace('\ufe0f', '').replace('\u26a0', '<font name="SegoeSym">\u26a0</font>')
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'`(.+?)`', r'<font name="Mono" size="8.8">\1</font>', text)
    return text


def table(rows, width):
    header, body = rows[0], rows[1:]
    ncol = len(header)
    lengths = [max(len(r[i]) if i < len(r) else 0 for r in rows) for i in range(ncol)]
    weights = [min(max(n, 12), 70) for n in lengths]
    total = sum(weights)
    widths = [width * w / total for w in weights]
    data = [[Paragraph(inline(c), S['cellh']) for c in header]]
    data += [[Paragraph(inline(c), S['cell']) for c in r] for r in body]
    t = Table(data, colWidths=widths, repeatRows=1)
    style = [
        ('BACKGROUND', (0, 0), (-1, 0), HEAD_BG),
        ('LINEBELOW', (0, 0), (-1, 0), 0.8, ACCENT),
        ('LINEBELOW', (0, 1), (-1, -1), 0.3, RULE),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]
    for i in range(2, len(data), 2):
        style.append(('BACKGROUND', (0, i), (-1, i), ZEBRA))
    t.setStyle(TableStyle(style))
    return t


def note(text, width):
    t = Table([[Paragraph(inline(text), S['note'])]], colWidths=[width])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), NOTE_BG),
        ('LINEBEFORE', (0, 0), (0, -1), 3, NOTE_BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 9),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    return t


LIST_RE = re.compile(r'^( *)(-|\d+\.) (.*)$')


def build_list(items):
    """items: [(indent, ordered, text)] -> ListFlowable anidado."""
    def make(idx, level):
        flow, ordered = [], items[idx][1]
        while idx < len(items) and items[idx][0] >= level:
            indent, _ord, text = items[idx]
            if indent > level:
                sub, idx = make(idx, indent)
                flow[-1].append(sub)
                continue
            flow.append([Paragraph(inline(text), S['li'])])
            idx += 1
        lst = ListFlowable(
            [ListItem(parts if len(parts) > 1 else parts[0], leftIndent=14)
             for parts in flow],
            bulletType='1' if ordered else 'bullet',
            bulletFontName='Segoe', bulletFontSize=9.5 if ordered else 7,
            bulletColor=ACCENT, leftIndent=14, start='1' if ordered else '•',
        )
        return lst, idx
    return make(0, items[0][0])[0]


def es_especial(line):
    return (not line.strip() or line.startswith(('#', '>', '|', '```'))
            or line.strip() == '---' or LIST_RE.match(line))


def convert(md_path, pdf_path, title, saltos=True):
    lines = open(md_path, encoding='utf-8').read().splitlines()
    doc = SimpleDocTemplate(pdf_path, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=20 * mm, bottomMargin=18 * mm, title=title,
                            author='Enteza')
    width = doc.width
    story, i, first_h1 = [], 0, True
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith('# '):
            story.append(Paragraph(inline(line[2:]), S['title']))
        elif line.startswith('## '):
            if not first_h1 and saltos:
                story.append(PageBreak())
            first_h1 = False
            story.append(Paragraph(inline(line[3:]), S['h1']))
            story.append(HRFlowable(width='100%', thickness=0.8, color=ACCENT, spaceAfter=6))
        elif line.startswith('### '):
            story.append(Paragraph(inline(line[4:]), S['h2']))
        elif line.strip() == '---':
            story.append(Spacer(1, 4))
        elif line.startswith('>'):
            block = []
            while i < len(lines) and lines[i].startswith('>'):
                block.append(lines[i].lstrip('>').strip())
                i += 1
            story.append(Spacer(1, 3))
            story.append(note(' '.join(block), width))
            story.append(Spacer(1, 6))
            continue
        elif line.startswith('```'):
            i += 1
            block = []
            while i < len(lines) and not lines[i].startswith('```'):
                block.append(inline(lines[i]))
                i += 1
            story.append(Paragraph('<font name="Mono">%s</font>' % '<br/>'.join(block),
                                   S['body']))
        elif line.startswith('|'):
            rows = []
            while i < len(lines) and lines[i].startswith('|'):
                cells = [c.strip() for c in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?', c) for c in cells):
                    rows.append(cells)
                i += 1
            story.append(table(rows, width))
            story.append(Spacer(1, 8))
            continue
        elif LIST_RE.match(line):
            items = []
            while i < len(lines) and LIST_RE.match(lines[i]):
                m = LIST_RE.match(lines[i])
                items.append((len(m.group(1)), m.group(2) != '-', m.group(3)))
                i += 1
                # Continuación de la línea anterior del elemento (texto con sangría).
                while i < len(lines) and lines[i].startswith('  ')                         and lines[i].strip() and not LIST_RE.match(lines[i]):
                    items[-1] = items[-1][:2] + (items[-1][2] + ' ' + lines[i].strip(),)
                    i += 1
            story.append(build_list(items))
            story.append(Spacer(1, 6))
            continue
        else:
            style = S['meta'] if first_h1 and story else S['body']
            # Un párrafo que es solo una pregunta o un título en negrita va con el siguiente.
            if line.startswith('**') and line.rstrip().endswith('**'):
                style = ParagraphStyle('kwn', parent=style, keepWithNext=1, spaceAfter=2)
            # Un párrafo partido en varias líneas del .md es un solo párrafo.
            while i + 1 < len(lines) and not es_especial(lines[i + 1]):
                i += 1
                line += ' ' + lines[i].strip()
            story.append(Paragraph(inline(line), style))
        i += 1

    def decorate(canvas, doc_):
        canvas.saveState()
        canvas.setFont('Segoe', 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(doc_.leftMargin, 10 * mm, title)
        canvas.drawRightString(A4[0] - doc_.rightMargin, 10 * mm, 'Página %d' % doc_.page)
        canvas.setStrokeColor(RULE)
        canvas.line(doc_.leftMargin, 13 * mm, A4[0] - doc_.rightMargin, 13 * mm)
        canvas.restoreState()

    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)


if __name__ == '__main__':
    # Cuarto argumento opcional `--sin-saltos`: sin salto de página en cada sección.
    convert(sys.argv[1], sys.argv[2], sys.argv[3], saltos='--sin-saltos' not in sys.argv[4:])
