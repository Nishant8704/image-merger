from flask import Flask, render_template, request, send_file, abort
from PIL import Image, ImageOps
import io, os, json
from PyPDF2 import PdfWriter, PdfReader

app = Flask(__name__, template_folder="templates")

# Paper sizes (pixels at ~300 DPI)
PAPER_SIZES = {
    "A4": (1240, 1754),
    "Letter": (1275, 1650),
    "fit": None
}

def parse_int_safe(val, default=100):
    """Convert value to int; return default if empty or invalid."""
    try:
        if val is None or str(val).strip() == "":
            return default
        return int(val)
    except Exception:
        return default

def adjust_aspect_ratio(img, ratio, mode):
    if ratio == "original":
        return img

    width, height = img.size
    if ratio == "4:3":
        target_ratio = 4 / 3
    elif ratio == "16:9":
        target_ratio = 16 / 9
    else:
        return img

    current_ratio = width / height

    if mode == "crop":
        # Crop to match target ratio
        if current_ratio > target_ratio:  # too wide
            new_width = int(height * target_ratio)
            left = (width - new_width) // 2
            img = img.crop((left, 0, left + new_width, height))
        else:  # too tall
            new_height = int(width / target_ratio)
            top = (height - new_height) // 2
            img = img.crop((0, top, width, top + new_height))
    elif mode == "pad":
        # Pad with white background to match target ratio
        if current_ratio > target_ratio:  # too wide -> increase height
            target_height = int(width / target_ratio)
            new_img = Image.new("RGB", (width, target_height), (255,255,255))
            top = (target_height - height) // 2
            new_img.paste(img, (0, top))
            img = new_img
        else:  # too tall -> increase width
            target_width = int(height * target_ratio)
            new_img = Image.new("RGB", (target_width, height), (255,255,255))
            left = (target_width - width) // 2
            new_img.paste(img, (left, 0))
            img = new_img

    return img

def resize_to_paper(img, paper_size):
    if paper_size not in PAPER_SIZES or PAPER_SIZES[paper_size] is None:
        return img
    target = PAPER_SIZES[paper_size]
    return ImageOps.fit(img, target, Image.LANCZOS)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        files = request.files.getlist("images")
        order_field = request.form.get("order", "")
        rotations_field = request.form.get("rotations", "{}")
        aspect_ratio = request.form.get("aspect_ratio", "original")
        resize_mode = request.form.get("resize_mode", "crop")
        paper_size = request.form.get("paper_size", "fit")
        compress_ratio = parse_int_safe(request.form.get("compress_ratio"), default=100)
        pdf_password = request.form.get("pdf_password", "").strip()

        # parse rotations JSON (filename -> degrees)
        try:
            rotations = json.loads(rotations_field) if rotations_field else {}
        except Exception:
            rotations = {}

        # Build mapping of uploaded files by filename
        file_map = {f.filename: f for f in files}

        # Build ordered list of file objects according to client order
        ordered_files = []
        if order_field:
            order_names = [n for n in order_field.split(",") if n]
            for name in order_names:
                if name in file_map:
                    ordered_files.append(file_map[name])
            # Append any remaining files that weren't in order list
            for f in files:
                if f not in ordered_files:
                    ordered_files.append(f)
        else:
            ordered_files = files

        if not ordered_files:
            return abort(400, "No images uploaded.")

        processed_imgs = []
        for f in ordered_files:
            try:
                img = Image.open(f.stream).convert("RGB")
            except Exception:
                continue

            # apply rotation if provided (client sends degrees clockwise)
            deg = parse_int_safe(rotations.get(f.filename, 0), default=0)
            if deg:
                # Pillow rotates counter-clockwise; to rotate clockwise use negative angle
                img = img.rotate(-deg, expand=True)

            # aspect ratio and resize/paper
            img = adjust_aspect_ratio(img, aspect_ratio, resize_mode)
            img = resize_to_paper(img, paper_size)

            # compression: if <100 compress to JPEG and reload as Pillow image (keeps memory low)
            if compress_ratio < 100:
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=compress_ratio)
                buf.seek(0)
                img = Image.open(buf).convert("RGB")

            processed_imgs.append(img)

        # Create PDF from processed images using Pillow
        pdf_bytes = io.BytesIO()
        if len(processed_imgs) == 1:
            processed_imgs[0].save(pdf_bytes, format="PDF")
        else:
            processed_imgs[0].save(pdf_bytes, format="PDF", save_all=True, append_images=processed_imgs[1:])
        pdf_bytes.seek(0)

        # If password provided, rewrap with PyPDF2
        if pdf_password:
            reader = PdfReader(pdf_bytes)
            writer = PdfWriter()
            for page in reader.pages:
                writer.add_page(page)
            writer.encrypt(pdf_password)
            out = io.BytesIO()
            writer.write(out)
            out.seek(0)
            return send_file(out, as_attachment=True, download_name="converted.pdf", mimetype="application/pdf")

        pdf_bytes.seek(0)
        return send_file(pdf_bytes, as_attachment=True, download_name="converted.pdf", mimetype="application/pdf")

    # GET
    return render_template("index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
