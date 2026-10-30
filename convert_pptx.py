#!/usr/bin/env python3
"""
Convert CDCI .pptx files to Slidev .md files.

Extracts text, images, and notes from each slide and produces
a Slidev-compatible markdown file with proper frontmatter.
"""

import sys
import os
import re
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.enum.shapes import MSO_SHAPE_TYPE
import base64
import hashlib

PPTX_DIR = Path("/data")
OUT_DIR = Path("/output")

# Mapping from pptx filename to lecture directory name
LECTURES = {
    "CDCI-Lecture01 - Introduction.pptx": "01-introduction",
    "CDCI-Lecture02 - EndPoint detection.pptx": "02-endpoint-detection",
    "CDCI-Lecture03 - Web Security.pptx": "03-web-security",
    "CDCI-Lecture04 - Network security.pptx": "04-network-security",
    "CDCI-Lecture05 - Mobile security.pptx": "05-mobile-security",
    "CDCI-Lecture06 - Cloud security.pptx": "06-cloud-security",
    "CDCI-Lecture07 - (Open) threat intelligence.pptx": "07-threat-intelligence",
    "CDCI-Lecture08 - Online tracking.pptx": "08-online-tracking",
    "CDCI-Lecture09 - Online searching.pptx": "09-online-searching",
    "CDCI-Lecture10 - Social media intelligence.pptx": "10-social-media-intelligence",
    "CDCI-Lecture11 - Dark web.pptx": "11-dark-web",
    "CDCI-Lecture12 - Advanced Persistent Threats.pptx": "12-advanced-persistent-threats",
}


def extract_text_from_shape(shape):
    """Extract text from a shape, preserving basic formatting."""
    if not shape.has_text_frame:
        return ""

    lines = []
    for para in shape.text_frame.paragraphs:
        text = ""
        for run in para.runs:
            run_text = run.text
            if not run_text:
                continue
            # Bold
            if run.font.bold:
                run_text = f"**{run_text}**"
            # Italic
            if run.font.italic:
                run_text = f"*{run_text}*"
            # Code (monospace font)
            if run.font.name and ("mono" in run.font.name.lower() or
                                   "courier" in run.font.name.lower() or
                                   "consolas" in run.font.name.lower()):
                run_text = f"`{run_text}`"
            text += run_text

        # Handle bullet levels via paragraph indentation level
        level = para.level or 0
        # Detect bullets: check XML for buNone (no bullet) vs buChar/buAutoNum
        has_bullet = False
        pPr = para._p.find('.//{http://schemas.openxmlformats.org/drawingml/2006/main}pPr')
        if pPr is not None:
            buNone = pPr.find('{http://schemas.openxmlformats.org/drawingml/2006/main}buNone')
            if buNone is None:
                # No explicit "no bullet" — likely has a bullet if level >= 0
                has_bullet = True
        elif level > 0:
            has_bullet = True

        if text.strip():
            if has_bullet and level >= 0:
                indent = "  " * level
                lines.append(f"{indent}- {text.strip()}")
            else:
                lines.append(text.strip())
        else:
            lines.append("")

    return "\n".join(lines)


def is_title_shape(shape):
    """Check if a shape is likely a title."""
    try:
        pf = shape.placeholder_format
        if pf is not None:
            # 0 = title, 1 = center title, 13 = title
            return pf.idx in (0, 1, 13)
    except (ValueError, AttributeError):
        pass
    return False


def is_subtitle_shape(shape):
    """Check if a shape is a subtitle placeholder."""
    try:
        pf = shape.placeholder_format
        if pf is not None:
            return pf.idx in (2,)  # subtitle
    except (ValueError, AttributeError):
        pass
    return False


def extract_images(slide, slide_idx, images_dir):
    """Extract images from a slide, save to images_dir, return list of (filename, shape)."""
    images = []
    for shape in slide.shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
            image = shape.image
            ext = image.content_type.split("/")[-1]
            if ext == "jpeg":
                ext = "jpg"
            # Create a deterministic filename
            blob_hash = hashlib.md5(image.blob).hexdigest()[:8]
            filename = f"slide{slide_idx:02d}_{blob_hash}.{ext}"
            filepath = images_dir / filename
            with open(filepath, "wb") as f:
                f.write(image.blob)
            images.append((filename, shape))
        elif shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            # Check group shapes for images
            for child in shape.shapes:
                if child.shape_type == MSO_SHAPE_TYPE.PICTURE:
                    image = child.image
                    ext = image.content_type.split("/")[-1]
                    if ext == "jpeg":
                        ext = "jpg"
                    blob_hash = hashlib.md5(image.blob).hexdigest()[:8]
                    filename = f"slide{slide_idx:02d}_{blob_hash}.{ext}"
                    filepath = images_dir / filename
                    with open(filepath, "wb") as f:
                        f.write(image.blob)
                    images.append((filename, child))
    return images


def get_slide_notes(slide):
    """Extract notes from a slide."""
    if slide.has_notes_slide:
        notes = slide.notes_slide.notes_text_frame
        if notes and notes.text.strip():
            return notes.text.strip()
    return ""


def guess_layout(slide, title, body_text, images, slide_idx, total_slides):
    """Guess the best Slidev layout for a slide."""
    # First slide is always cover
    if slide_idx == 0:
        return "cover"

    # Last slide might be an end/thank you slide
    body_lower = body_text.lower() if body_text else ""
    title_lower = title.lower() if title else ""

    if any(w in title_lower or w in body_lower for w in ["thank", "questions", "q&a", "end"]):
        return "focus"

    # If title only, no body content -> section divider
    if title and not body_text.strip() and not images:
        return "section"

    # If there are images alongside text -> two-cols
    if images and body_text.strip():
        return "two-cols"

    # Default
    return "default"


def convert_pptx(pptx_path, lecture_name, lecture_num):
    """Convert a single .pptx to a Slidev .md file."""
    print(f"  Converting: {pptx_path.name} -> {lecture_name}/slides.md")

    prs = Presentation(str(pptx_path))
    out_dir = OUT_DIR / lecture_name
    images_dir = out_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    # Extract human-readable title from filename
    match = re.match(r'CDCI-Lecture\d+ - (.+)\.pptx', pptx_path.name)
    lecture_title = match.group(1) if match else lecture_name

    total_slides = len(prs.slides)
    md_parts = []

    # Frontmatter
    md_parts.append(f"""---
layout: cover
routerMode: hash
download: 'slides.pdf'
theme: ../../cdci-theme
colorSchema: light
selectable: false
touying:
  preset: cdci
title: "Lecture {lecture_num} — {lecture_title}"
info: |
  ## CDCI — Lecture {lecture_num} · {lecture_title}
  [ocw.cs.pub.ro/courses/cdci](https://ocw.cs.pub.ro/courses/cdci)
transition: slide-left
footer: "CDCI — Lecture {lecture_num}: {lecture_title}"
src: ../_shared/intro.md#1
---""")

    for slide_idx, slide in enumerate(prs.slides):
        title = ""
        body_parts = []
        subtitle = ""

        # Extract title and body
        for shape in slide.shapes:
            if is_title_shape(shape):
                title = extract_text_from_shape(shape).strip()
            elif is_subtitle_shape(shape):
                subtitle = extract_text_from_shape(shape).strip()
            elif shape.has_text_frame:
                text = extract_text_from_shape(shape)
                if text.strip():
                    body_parts.append(text)

        body_text = "\n\n".join(body_parts)

        # Extract images
        images = extract_images(slide, slide_idx, images_dir)

        # Get notes
        notes = get_slide_notes(slide)

        # Determine layout
        layout = guess_layout(slide, title, body_text, images, slide_idx, total_slides)

        # Build slide markdown
        slide_parts = []

        # Cover slide
        if layout == "cover" and slide_idx == 0:
            slide_parts.append("---")
            slide_parts.append("layout: cover")
            slide_parts.append(f'title: "Lecture {lecture_num}: {lecture_title}"')
            if subtitle:
                slide_parts.append(f'subtitle: "{subtitle}"')
            slide_parts.append("---")
            if body_text.strip():
                slide_parts.append("")
                slide_parts.append("::default::")
                slide_parts.append("")
                slide_parts.append(body_text)
            continue  # Already handled in frontmatter

        elif layout == "section":
            slide_parts.append("---")
            slide_parts.append("layout: section")
            slide_parts.append("class: text-center")
            slide_parts.append("---")
            if title:
                slide_parts.append(f"# {title}")
            if subtitle:
                slide_parts.append("")
                slide_parts.append(subtitle)

        elif layout == "focus":
            slide_parts.append("---")
            slide_parts.append("layout: focus")
            slide_parts.append("---")
            if title:
                slide_parts.append(f"# {title}")
            if body_text.strip():
                slide_parts.append("")
                slide_parts.append(body_text)

        elif layout == "two-cols":
            slide_parts.append("---")
            slide_parts.append("layout: two-cols")
            slide_parts.append("---")
            if title:
                slide_parts.append("")
                slide_parts.append(f"# {title}")
            if body_text.strip():
                slide_parts.append("")
                slide_parts.append(body_text)
            if images:
                slide_parts.append("")
                slide_parts.append("::right::")
                for fname, _ in images:
                    slide_parts.append("")
                    slide_parts.append(f"![](./images/{fname})")

        else:  # default
            slide_parts.append("---")
            slide_parts.append("")
            if title:
                slide_parts.append(f"# {title}")
                slide_parts.append("")
            if body_text.strip():
                slide_parts.append(body_text)
                slide_parts.append("")
            if images:
                slide_parts.append('<div class="img-col">')
                for fname, _ in images:
                    slide_parts.append(f'<img src="./images/{fname}" />')
                slide_parts.append("</div>")

        # Add notes
        if notes:
            slide_parts.append("")
            slide_parts.append("<!--")
            slide_parts.append(notes)
            slide_parts.append("-->")

        md_parts.append("\n".join(slide_parts))

    # Write output
    output_path = out_dir / "slides.md"
    with open(output_path, "w") as f:
        f.write("\n".join(md_parts))

    # Check if images dir is empty, remove it
    if not list(images_dir.iterdir()):
        images_dir.rmdir()

    print(f"    -> {len(prs.slides)} slides, {len(list(images_dir.iterdir()) if images_dir.exists() else [])} images")


def main():
    print("=== CDCI PPTX to Slidev Converter ===\n")

    pptx_files = sorted(PPTX_DIR.glob("CDCI-Lecture*.pptx"))
    print(f"Found {len(pptx_files)} PPTX files\n")

    for pptx_path in pptx_files:
        if pptx_path.name not in LECTURES:
            print(f"  SKIP (unknown): {pptx_path.name}")
            continue

        lecture_name = LECTURES[pptx_path.name]
        # Extract lecture number
        num_match = re.match(r'CDCI-Lecture(\d+)', pptx_path.name)
        lecture_num = int(num_match.group(1)) if num_match else 0

        try:
            convert_pptx(pptx_path, lecture_name, lecture_num)
        except Exception as e:
            print(f"  ERROR converting {pptx_path.name}: {e}")
            import traceback
            traceback.print_exc()

    print("\n=== Conversion complete ===")


if __name__ == "__main__":
    main()
