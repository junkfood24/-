#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""报告排版工具：页面、样式、表格、代码块。

供 build_docx.py 之外的文档生成脚本复用，保持与专题报告一致的视觉风格。
"""

import os
import re

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

BODY_FONT_CN = "宋体"
BODY_FONT_EN = "Times New Roman"
HEAD_FONT_CN = "黑体"
CODE_FONT = "Consolas"
CODE_BLOCK_FONT = "NSimSun"
ACCENT = RGBColor(0x1F, 0x3B, 0x63)
GRAY = RGBColor(0x59, 0x59, 0x59)

doc = None


def _force_font(style, name):
    rPr = style.element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    for attr in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
        key = qn("w:" + attr)
        if key in rFonts.attrib:
            del rFonts.attrib[key]
    rFonts.set(qn("w:ascii"), name)
    rFonts.set(qn("w:hAnsi"), name)
    rFonts.set(qn("w:eastAsia"), name)


def _set_heading(style_name, size, before, after):
    st = doc.styles[style_name]
    st.font.name = HEAD_FONT_CN
    st.element.rPr.rFonts.set(qn("w:eastAsia"), HEAD_FONT_CN)
    _force_font(st, HEAD_FONT_CN)
    st.font.size = Pt(size)
    st.font.bold = True
    st.font.color.rgb = RGBColor(0, 0, 0)
    st.paragraph_format.space_before = Pt(before)
    st.paragraph_format.space_after = Pt(after)
    st.paragraph_format.keep_with_next = True
    st.paragraph_format.line_spacing = 1.25


def setup(header_text):
    global doc
    doc = Document()
    sec = doc.sections[0]
    sec.page_width = Cm(21.0)
    sec.page_height = Cm(29.7)
    sec.left_margin = Cm(2.6)
    sec.right_margin = Cm(2.6)
    sec.top_margin = Cm(2.5)
    sec.bottom_margin = Cm(2.4)
    sec.header_distance = Cm(1.3)
    sec.footer_distance = Cm(1.3)

    normal = doc.styles["Normal"]
    normal.font.name = BODY_FONT_EN
    normal.font.size = Pt(10.5)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT_CN)
    normal.paragraph_format.line_spacing = 1.5
    normal.paragraph_format.space_after = Pt(3)

    _set_heading("Heading 1", 16, 20, 10)
    _set_heading("Heading 2", 13, 14, 6)
    _set_heading("Heading 3", 11.5, 10, 4)

    sec.different_first_page_header_footer = True
    hp = sec.header.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    hr = hp.add_run(header_text)
    hr.font.size = Pt(9)
    hr.font.color.rgb = GRAY
    hr.font.name = BODY_FONT_EN
    hr._element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT_CN)

    fp = sec.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = fp.add_run("— ")
    r.font.size = Pt(9)
    add_page_field(fp)
    r = fp.add_run(" —")
    r.font.size = Pt(9)
    return doc


def add_rich(par, text, size=None, color=None):
    """支持 **加粗** 与 `等宽` 的行内标记。"""
    tokens = re.split(r"(\*\*.+?\*\*|`.+?`)", text)
    for tok in tokens:
        if not tok:
            continue
        if tok.startswith("**") and tok.endswith("**"):
            r = par.add_run(tok[2:-2])
            r.bold = True
        elif tok.startswith("`") and tok.endswith("`"):
            r = par.add_run(tok[1:-1])
            r.font.name = CODE_FONT
            r._element.rPr.rFonts.set(qn("w:eastAsia"), CODE_FONT)
            r.font.size = Pt((size or 10.5) - 1)
        else:
            r = par.add_run(tok)
        if size:
            r.font.size = Pt(size)
        if color is not None:
            r.font.color.rgb = color


def body(text, indent=True, size=10.5, after=3, before=0, align="justify"):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    if indent:
        pf.first_line_indent = Pt(size * 2)
    pf.space_after = Pt(after)
    pf.space_before = Pt(before)
    pf.line_spacing = 1.5
    pf.alignment = {"justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
                    "left": WD_ALIGN_PARAGRAPH.LEFT,
                    "center": WD_ALIGN_PARAGRAPH.CENTER}[align]
    add_rich(p, text, size=size)
    return p


def bullet(text, size=10.5):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.left_indent = Cm(0.85)
    pf.first_line_indent = Cm(-0.45)
    pf.space_after = Pt(2)
    pf.line_spacing = 1.4
    pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    r = p.add_run("•  ")
    r.font.size = Pt(size)
    r.font.color.rgb = ACCENT
    add_rich(p, text, size=size)
    return p


def numbered(n, text, size=10.5):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.left_indent = Cm(0.95)
    pf.first_line_indent = Cm(-0.55)
    pf.space_after = Pt(2)
    pf.line_spacing = 1.4
    pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    r = p.add_run(f"{n}.  ")
    r.bold = True
    r.font.size = Pt(size)
    add_rich(p, text, size=size)
    return p


def _fix_heading_runs(p):
    for r in p.runs:
        r.font.name = HEAD_FONT_CN
        rf = r._element.get_or_add_rPr().get_or_add_rFonts()
        for attr in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
            key = qn("w:" + attr)
            if key in rf.attrib:
                del rf.attrib[key]
        rf.set(qn("w:ascii"), HEAD_FONT_CN)
        rf.set(qn("w:hAnsi"), HEAD_FONT_CN)
        rf.set(qn("w:eastAsia"), HEAD_FONT_CN)


def h1(text):
    p = doc.add_heading(text, level=1)
    _fix_heading_runs(p)
    return p


def h2(text):
    p = doc.add_heading(text, level=2)
    _fix_heading_runs(p)
    return p


def h3(text):
    p = doc.add_heading(text, level=3)
    _fix_heading_runs(p)
    return p


def equation(text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(6)
    r = p.add_run(text)
    r.font.name = "Cambria Math"
    r._element.rPr.rFonts.set(qn("w:eastAsia"), "Cambria Math")
    r.font.size = Pt(11)
    return p


def caption(text, before=2, after=8):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)
    r = p.add_run(text)
    r.font.size = Pt(9)
    r.font.name = BODY_FONT_EN
    r._element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT_CN)
    r.font.color.rgb = GRAY
    return p


def shade(cell, color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color)
    tcPr.append(shd)


def set_borders(table, color="C9CDD4", sz=4):
    tblPr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(sz))
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), color)
        borders.append(el)
    tblPr.append(borders)


def set_cell_margins(table, top=40, bottom=40, left=80, right=80):
    tblPr = table._tbl.tblPr
    mar = OxmlElement("w:tblCellMar")
    for tag, val in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        el = OxmlElement(f"w:{tag}")
        el.set(qn("w:w"), str(val))
        el.set(qn("w:type"), "dxa")
        mar.append(el)
    tblPr.append(mar)


def _no_split(row):
    trPr = row._tr.get_or_add_trPr()
    cs = OxmlElement("w:cantSplit")
    trPr.append(cs)


def table(headers, rows, widths, caption_text=None, font=9, header_fill="E8EDF5",
          align_center=True):
    if caption_text:
        cp = caption(caption_text, before=8, after=3)
        cp.paragraph_format.keep_with_next = True
    total = sum(widths)
    scale = 15.7 / total
    widths = [w * scale for w in widths]
    t = doc.add_table(rows=1, cols=len(headers))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    set_borders(t)
    set_cell_margins(t)
    hdr = t.rows[0]
    _no_split(hdr)
    trPr = hdr._tr.get_or_add_trPr()
    th = OxmlElement("w:tblHeader")
    th.set(qn("w:val"), "true")
    trPr.append(th)
    for i, h in enumerate(headers):
        cell = hdr.cells[i]
        cell.width = Cm(widths[i])
        shade(cell, header_fill)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.1
        r = p.add_run(h)
        r.bold = True
        r.font.size = Pt(font)
        r.font.name = BODY_FONT_EN
        r._element.rPr.rFonts.set(qn("w:eastAsia"), HEAD_FONT_CN)
    for row in rows:
        cells = t.add_row().cells
        _no_split(t.rows[-1])
        for i, val in enumerate(row):
            cells[i].width = Cm(widths[i])
            p = cells[i].paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.15
            p.alignment = (WD_ALIGN_PARAGRAPH.CENTER if (align_center and i > 0)
                           else WD_ALIGN_PARAGRAPH.LEFT)
            add_rich(p, str(val), size=font)
    caption("", after=2)
    return t


def code_block(text, width=15.6, size=8.4, keep=None):
    t = doc.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    set_borders(t, color="DDE1E6", sz=4)
    set_cell_margins(t, top=80, bottom=80, left=120, right=120)
    cell = t.rows[0].cells[0]
    if keep is None:
        keep = text.count("\n") < 35
    if keep:
        _no_split(t.rows[0])
    cell.width = Cm(width)
    shade(cell, "F7F8FA")
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.12
    for i, line in enumerate(text.split("\n")):
        if i:
            p = cell.add_paragraph()
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.12
        lead = len(line) - len(line.lstrip(" "))
        line = line[lead:]
        if lead:
            # 用段落左缩进表达行首空格：NSimSun 的半角空格宽度为 0.5 em
            p.paragraph_format.left_indent = Pt(lead * size * 0.5)
        r = p.add_run(line if line else " ")
        r.font.name = CODE_BLOCK_FONT
        r._element.rPr.rFonts.set(qn("w:eastAsia"), CODE_BLOCK_FONT)
        r.font.size = Pt(size)
        for tnode in r._r.findall(qn("w:t")):
            tnode.set(qn("xml:space"), "preserve")
    caption("", after=2)
    return t


def figure(name, caption_text, fig_dir, width=15.0):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(2)
    p.add_run().add_picture(os.path.join(fig_dir, name), width=Cm(width))
    p.paragraph_format.keep_with_next = True
    caption(caption_text, before=0, after=10)


def page_break():
    doc.add_page_break()


def add_page_field(par):
    run = par.add_run()
    fld1 = OxmlElement("w:fldChar")
    fld1.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = "PAGE"
    fld2 = OxmlElement("w:fldChar")
    fld2.set(qn("w:fldCharType"), "end")
    run._r.append(fld1)
    run._r.append(instr)
    run._r.append(fld2)