from flask import Flask, render_template, request, send_file
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps
from io import BytesIO
from PyPDF2 import PdfWriter
import os

app = Flask(__name__)

# Standard paper sizes in points (1 point = 1/72 inch)
PAPER_SIZES = {
    "A4": (595, 842),       # 8.27 × 11.69 inches
    "Letter": (612, 792),   # 8.5 × 11 inches
}

def parse_aspect_ratio(ratio_str):
    if ratio_str == "original":
        return None
    w, h = map(int, ratio_str.split(":"))
    return w / h

def resize_image(img, target_aspect, mode, paper_size=None):
    original_width, original_height = img.size
    original_aspect = original_width / original_height

    # If paper size is provided, use that as the canvas
    if paper_size and paper_size != "fit":
        target_width, target_height = PAPER_SIZES.get(paper_size, img.size)
    else:
        target_width, target_height = original_width, original_height

    # Maintain aspect ratio
    if target_aspect:
        new_height = int(original_width / target_aspect)
        if new_height <= original_height:
            img = img.crop((0, (original_height - new_height) // 2, original_width, (original_height + new_height) // 2))
        else:
            new_width = int(original_height * target_aspect)
            img = img.crop(((original_width - new_width) // 2, 0, (original_width + new_width) // 2, original_height))

    if paper_size and paper_size != "fit":
        img = img.resize((target_width, target_height), Image.LANCZOS)
        canvas = Image.new("RGB", (target_width, target_height), "white")

        if mode == "pad":
            img = ImageOps.contain(img, (target_width, target_height), method=Image.LANCZOS)
            offset = ((target_width - img.size[0]) // 2, (target_height - img.size[1]) // 2)
            canvas.paste(img, offset)
        else:  # crop
            img = ImageOps.fit(img, (target_width, target_height), method=Image.LANCZOS)
            canvas = img

        return canvas
    else:
        return img

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        files = request.files.getlist("images")
        order = request.form.get("order", "").split(",")
        aspect_ratio = parse_aspect_ratio(request.form.get("aspect_ratio", "original"))
        resize_mode = request.form.get("resize_mode", "crop")
        paper_size = request.form.get("paper_size", "fit")
        compress_ratio = int(request.form.get("compress_ratio", "100"))
        pdf_password = request.form.get("pdf_password", "").strip()

        # Map by original filenames (no secure_filename here to avoid mismatch)
        file_dict = {file.filename: file for file in files}

        # Arrange according to user-selected order
        if order and order != ['']:
            ordered_files = [file_dict[name] for name in order if name in file_dict]
        else:
            ordered_files = files  # fallback to upload order

        pdf_io = BytesIO()
        pdf_writer = PdfWriter()

        for file in ordered_files:
            img = Image.open(file.stream).convert("RGB")
            img = resize_image(img, aspect_ratio, resize_mode, paper_size)

            if compress_ratio < 100:
                compressed_io = BytesIO()
                img.save(compressed_io, format="JPEG", quality=compress_ratio)
                img = Image.open(compressed_io)

            page_io = BytesIO()
            img.save(page_io, format="PDF")
            page_io.seek(0)

            pdf_writer.append(page_io)

        if pdf_password:
            pdf_writer.encrypt(pdf_password)

        pdf_writer.write(pdf_io)
        pdf_io.seek(0)

        return send_file(
            pdf_io,
            as_attachment=True,
            download_name="converted.pdf",
            mimetype="application/pdf"
        )

    return render_template("index.html")

if __name__ == "__main__":
    import webbrowser, threading
    threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:5000/")).start()
    app.run(debug=False)
