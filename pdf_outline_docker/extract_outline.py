import pdfplumber
import os
import json
import re
from collections import Counter

def clean_ocr_text(text):
    return re.sub(r'(.)\1{1,}', r'\1', text)

def normalize_text(text):
    return clean_ocr_text(text.strip().replace('\n', ' '))

def group_text_blocks(chars, y_tolerance=3):
    blocks = []
    if not chars:
        return blocks

    chars = sorted(chars, key=lambda c: (c['top'], c['x0']))
    current_line_top = None
    current = None

    for ch in chars:
        ch_size = round(ch["size"], 1)
        ch_font = ch["fontname"]
        ch_bold = "Bold" in ch_font
        ch_italic = "Italic" in ch_font or "Oblique" in ch_font

        if current_line_top is None or abs(ch["top"] - current_line_top) > y_tolerance:
            if current:
                blocks.append(current)
            current_line_top = ch["top"]
            current = {
                "text": ch["text"],
                "size": ch_size,
                "font": ch_font,
                "top": ch["top"],
                "bold": ch_bold,
                "italic": ch_italic,
                "fonts_in_line": set([ch_font]),
                "line_top": ch["top"]
            }
        else:
            current["text"] += ch["text"]
            current["fonts_in_line"].add(ch_font)

    if current:
        blocks.append(current)
    return blocks

def extract_outline_from_pdf(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        outline = []
        non_passage_blocks = []
        extra_headings = []
        title = ""
        title_fonts = set()
        heading_buffer = None
        page_12_candidates = []

        first_page_blocks = group_text_blocks(pdf.pages[0].chars)
        sorted_blocks = sorted(first_page_blocks, key=lambda b: -b["size"])

        for block in sorted_blocks:
            text = normalize_text(block["text"])
            font = block["font"]
            if len(text.split()) > 40:
                continue
            if text in title:
                continue
            title += ("  " if title else "") + text
            title_fonts.add(font)
            if len(title.split()) > 40:
                break
        title = re.sub(r'(\b\w+\b)(?=.*\b\1\b)', '', title).strip()

        for page_idx, page in enumerate(pdf.pages[1:], start=1):
            blocks = group_text_blocks(page.chars)
            font_counter = Counter(b["size"] for b in blocks if len(b["text"].strip()) > 3)
            top_sizes = [fs for fs, _ in font_counter.most_common(4)]

            def get_level(size, font, bold):
                if size <= 11:
                    return None
                if size == max(top_sizes):
                    return "H1" if font in title_fonts else "H2"
                elif size == sorted(set(top_sizes), reverse=True)[1]:
                    return "H3"
                elif len(top_sizes) > 2 and size == sorted(set(top_sizes), reverse=True)[2]:
                    return "H4" if bold else None
                return None

            for i, block in enumerate(blocks):
                text = normalize_text(block["text"])
                size = block["size"]
                font = block["font"]
                bold = block["bold"]
                italic = block["italic"]
                fonts_in_line = block.get("fonts_in_line", set())

                if page_idx == 10:
                    if len(fonts_in_line) == 1 and (bold or italic) and len(text.split()) <= 12:
                        prev = blocks[i - 1] if i > 0 else None
                        next_ = blocks[i + 1] if i + 1 < len(blocks) else None
                        if (not prev or prev["font"] != font or (prev["bold"] != bold and prev["italic"] != italic)) and \
                           (not next_ or next_["font"] != font or (next_["bold"] != bold and next_["italic"] != italic)):
                            page_12_candidates.append({
                                "text": text,
                                "page": page_idx,
                                "size": size,
                                "font": font,
                                "bold": bold,
                                "italic": italic
                            })

                if len(text) < 4 or not text[0].isalpha() or size < 10:
                    continue

                word_count = len(text.split())

                if size <= 11:
                    prev_font = blocks[i - 1]["font"] if i > 0 else None
                    next_font = blocks[i + 1]["font"] if i + 1 < len(blocks) else None
                    prev_bold = blocks[i - 1]["bold"] if i > 0 else None
                    next_bold = blocks[i + 1]["bold"] if i + 1 < len(blocks) else None
                    prev_italic = blocks[i - 1]["italic"] if i > 0 else None
                    next_italic = blocks[i + 1]["italic"] if i + 1 < len(blocks) else None

                    if (len(fonts_in_line) > 1 or
                        (prev_font == font and (prev_bold == bold or prev_italic == italic)) or
                        (next_font == font and (next_bold == bold or next_italic == italic)) or
                        not (bold or italic) or
                        word_count > 10):
                        continue

                    extra_headings.append({
                        "text": text,
                        "page": page_idx,
                        "size": size,
                        "font": font,
                        "bold": bold,
                        "italic": italic
                    })
                    continue

                if len(fonts_in_line) > 1:
                    continue

                level = get_level(size, font, bold)
                if level:
                    if heading_buffer is None:
                        heading_buffer = {
                            "level": level,
                            "text": text,
                            "page": page_idx,
                            "size": size,
                            "font": font,
                            "bold": bold
                        }
                    else:
                        if (heading_buffer["level"] == level and
                            heading_buffer["page"] == page_idx and
                            heading_buffer["size"] == size and
                            heading_buffer["font"] == font and
                            heading_buffer["bold"] == bold):
                            heading_buffer["text"] += " " + text
                        else:
                            outline.append({
                                "level": heading_buffer["level"],
                                "text": heading_buffer["text"],
                                "page": heading_buffer["page"]
                            })
                            heading_buffer = {
                                "level": level,
                                "text": text,
                                "page": page_idx,
                                "size": size,
                                "font": font,
                                "bold": bold
                            }

                non_passage_blocks.append({
                    "text": text,
                    "font": font,
                    "size": size,
                    "page": page_idx
                })

        if heading_buffer:
            outline.append({
                "level": heading_buffer["level"],
                "text": heading_buffer["text"],
                "page": heading_buffer["page"]
            })

        return {
            "title": title,
            "outline": outline,
            "non_passage_blocks": non_passage_blocks,
            "extra_headings": extra_headings,
            "page_12_candidates": page_12_candidates
        }

# === MAIN EXECUTION ===
input_dir = "./input"
output_dir = "./output"
os.makedirs(output_dir, exist_ok=True)

for file in os.listdir(input_dir):
    if file.lower().endswith(".pdf"):
        input_path = os.path.join(input_dir, file)
        result = extract_outline_from_pdf(input_path)

        output_file = os.path.splitext(file)[0] + ".json"
        output_path = os.path.join(output_dir, output_file)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=4, ensure_ascii=False)

        print(f"✅ Extracted outline → {output_file}")
