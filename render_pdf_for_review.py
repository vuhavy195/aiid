from pathlib import Path
import json
import pymupdf
from PIL import Image, ImageOps, ImageDraw

src = Path(r"H:\AIID_DTA_GPR\.review\Draft_FullPaper_CIEMB.pdf")
out = Path(r"H:\AIID_DTA_GPR\.review\pages")
out.mkdir(parents=True, exist_ok=True)

doc = pymupdf.open(src)
page_index = []
images = []
for i, page in enumerate(doc):
    pix = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
    path = out / f"page-{i + 1}.png"
    pix.save(path)
    text = page.get_text("text")
    (out / f"page-{i + 1}.txt").write_text(text, encoding="utf-8")
    first_lines = [line.strip() for line in text.splitlines() if line.strip()][:8]
    page_index.append({"page": i + 1, "first_lines": first_lines})
    images.append(Image.open(path).convert("RGB"))

thumb_w = 650
margin = 30
label_h = 34
for start in range(0, len(images), 4):
    group = images[start:start + 4]
    thumbs = []
    for j, im in enumerate(group):
        h = round(im.height * thumb_w / im.width)
        thumb = im.resize((thumb_w, h))
        canvas = Image.new("RGB", (thumb_w + 2 * margin, h + label_h + 2 * margin), "white")
        canvas.paste(thumb, (margin, margin + label_h))
        ImageDraw.Draw(canvas).text((margin, margin), f"Page {start + j + 1}", fill="black")
        thumbs.append(ImageOps.expand(canvas, border=2, fill="#808080"))
    max_w = max(t.width for t in thumbs)
    max_h = max(t.height for t in thumbs)
    sheet = Image.new("RGB", (max_w * 2, max_h * 2), "#d0d0d0")
    for j, thumb in enumerate(thumbs):
        sheet.paste(thumb, ((j % 2) * max_w, (j // 2) * max_h))
    sheet.save(out / f"contact-{start + 1}-{start + len(group)}.jpg", quality=88)

(out / "page-index.json").write_text(json.dumps(page_index, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"pages": len(doc), "contact_sheets": (len(images) + 3) // 4}))
