from flask import Flask, render_template, request, send_file, redirect, url_for
import os
import io
import gc
import sqlite3
import requests

from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageFont
from werkzeug.utils import secure_filename
from openpyxl import Workbook

import cloudinary
import cloudinary.uploader

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024  # 12 MB por request

# =========================
# PATHS
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOAD_DIR = os.path.join(STATIC_DIR, "uploads")
PROCESSED_DIR = os.path.join(STATIC_DIR, "processed")
THUMBS_DIR = os.path.join(STATIC_DIR, "thumbs")
DB_PATH = os.path.join(BASE_DIR, "catalogo.db")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)
os.makedirs(THUMBS_DIR, exist_ok=True)

# =========================
# ENV
# =========================
REMOVE_BG_API_KEY = os.environ.get("REMOVE_BG_API_KEY", "")

cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET")
)

# =========================
# DB
# =========================
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            codigo TEXT,
            descripcion TEXT,
            precio TEXT DEFAULT '',
            imagen TEXT NOT NULL,
            thumb TEXT DEFAULT '',
            url TEXT DEFAULT ''
        )
    """)
    conn.commit()
    conn.close()

init_db()

# =========================
# HELPERS
# =========================
def secure_name(filename: str) -> str:
    return secure_filename(filename).replace(" ", "_")

def split_name(filename: str):
    base = os.path.splitext(filename)[0]
    base = base.replace("_-_", " ")
    base = base.replace("_", " ")
    base = base.replace("-", " ")
    base = " ".join(base.split()).upper()

    parts = base.split(" ", 1)
    codigo = parts[0] if parts else ""
    descripcion = parts[1] if len(parts) > 1 else ""
    return codigo, descripcion

def get_resample():
    try:
        return Image.Resampling.LANCZOS
    except AttributeError:
        return Image.LANCZOS

def load_font(size: int):
    candidates = [
        os.path.join(BASE_DIR, "arial.ttf"),
        os.path.join(STATIC_DIR, "arial.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()

def text_size(draw, text, font):
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        return (len(text) * 10, 20)

def wrap_text(draw, text, font, max_width):
    words = text.split()
    if not words:
        return [""]

    lines = []
    current = words[0]

    for word in words[1:]:
        test = current + " " + word
        w, _ = text_size(draw, test, font)
        if w <= max_width:
            current = test
        else:
            lines.append(current)
            current = word

    lines.append(current)
    return lines

def cleanup_memory():
    gc.collect()

# =========================
# PREPROCESS (baja RAM)
# =========================
def downscale_before_removebg(local_path: str):
    """
    Reduce imágenes gigantes antes de enviarlas a remove.bg.
    Esto baja muchísimo el consumo de RAM en Render.
    """
    try:
        resample = get_resample()
        with Image.open(local_path) as img:
            img = ImageOps.exif_transpose(img)

            max_side = 1800
            if max(img.size) > max_side:
                img.thumbnail((max_side, max_side), resample)

            # guardamos sobre el mismo archivo con compresión razonable
            if img.mode in ("RGBA", "LA"):
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[-1])
                bg.save(local_path, format="JPEG", quality=88, optimize=True)
            else:
                img = img.convert("RGB")
                img.save(local_path, format="JPEG", quality=88, optimize=True)

    except Exception as e:
        print("ERROR DOWNSCALE:", e)

# =========================
# REMOVE BACKGROUND
# =========================
def remove_bg_file(local_path: str) -> bytes:
    try:
        if not REMOVE_BG_API_KEY:
            with open(local_path, "rb") as f:
                return f.read()

        with open(local_path, "rb") as f:
            response = requests.post(
                "https://api.remove.bg/v1.0/removebg",
                files={"image_file": f},
                headers={"X-Api-Key": REMOVE_BG_API_KEY},
                timeout=120
            )

        if response.status_code == 200:
            return response.content

        print("REMOVE.BG ERROR:", response.text)
        with open(local_path, "rb") as f:
            return f.read()

    except Exception as e:
        print("ERROR REMOVE.BG:", e)
        with open(local_path, "rb") as f:
            return f.read()

# =========================
# IMAGE PROCESSING
# =========================
def process_catalog_image(input_path: str, output_path: str, thumb_path: str):
    try:
        resample = get_resample()
        codigo, descripcion = split_name(os.path.basename(input_path))

        # 1) bajar tamaño antes de remove.bg
        downscale_before_removebg(input_path)

        # 2) remove bg
        image_bytes = remove_bg_file(input_path)

        # 3) abrir resultado
        with Image.open(io.BytesIO(image_bytes)) as raw:
            prod = ImageOps.exif_transpose(raw).convert("RGBA")

        bbox = prod.getbbox()
        if bbox:
            prod = prod.crop(bbox)

        # ================= MASTER =================
        W, H = 1000, 1000
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))

        # tamaño visual consistente
        max_w = 620
        max_h = 560
        prod.thumbnail((max_w, max_h), resample)

        x = (W - prod.width) // 2
        y = 160 + (max_h - prod.height) // 2

        # sombra
        shadow = Image.new("RGBA", (prod.width, prod.height), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.ellipse(
            (
                int(prod.width * 0.20),
                int(prod.height * 0.82),
                int(prod.width * 0.80),
                int(prod.height * 0.96),
            ),
            fill=(0, 0, 0, 105),
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(20))
        canvas.paste(shadow, (x, y + 30), shadow)
        canvas.paste(prod, (x, y), prod)

        draw = ImageDraw.Draw(canvas)

        # logo
        logo_path = os.path.join(STATIC_DIR, "logo.png")
        if os.path.exists(logo_path):
            try:
                with Image.open(logo_path) as logo_raw:
                    logo = logo_raw.convert("RGBA")
                    logo.thumbnail((180, 60), resample)
                    lx = W - logo.width - 26
                    ly = 26
                    canvas.paste(logo, (lx, ly), logo)
            except Exception as e:
                print("ERROR LOGO:", e)

        # texto
        font_code = load_font(34)
        font_desc = load_font(20)

        draw.text((50, 840), codigo, fill=(0, 0, 0), font=font_code)

        desc_lines = wrap_text(draw, descripcion, font_desc, 900)[:2]
        start_y = 890
        for i, line in enumerate(desc_lines):
            draw.text((50, start_y + (i * 28)), line, fill=(110, 110, 110), font=font_desc)

        canvas.save(output_path, "PNG", optimize=True)

        # ================= THUMB =================
        thumb_canvas = Image.new("RGBA", (700, 520), (255, 255, 255, 0))

        thumb_prod = prod.copy()
        thumb_prod.thumbnail((360, 280), resample)

        tx = (700 - thumb_prod.width) // 2
        ty = 58 + (250 - thumb_prod.height) // 2

        thumb_shadow = Image.new("RGBA", (thumb_prod.width, thumb_prod.height), (0, 0, 0, 0))
        thumb_shadow_draw = ImageDraw.Draw(thumb_shadow)
        thumb_shadow_draw.ellipse(
            (
                int(thumb_prod.width * 0.20),
                int(thumb_prod.height * 0.82),
                int(thumb_prod.width * 0.80),
                int(thumb_prod.height * 0.96),
            ),
            fill=(0, 0, 0, 85),
        )
        thumb_shadow = thumb_shadow.filter(ImageFilter.GaussianBlur(12))
        thumb_canvas.paste(thumb_shadow, (tx, ty + 18), thumb_shadow)
        thumb_canvas.paste(thumb_prod, (tx, ty), thumb_prod)

        thumb_draw = ImageDraw.Draw(thumb_canvas)

        if os.path.exists(logo_path):
            try:
                with Image.open(logo_path) as logo_small_raw:
                    logo_small = logo_small_raw.convert("RGBA")
                    logo_small.thumbnail((110, 34), resample)
                    thumb_canvas.paste(logo_small, (700 - logo_small.width - 14, 14), logo_small)
            except Exception:
                pass

        thumb_font_code = load_font(22)
        thumb_font_desc = load_font(16)

        thumb_draw.text((24, 390), codigo, fill=(20, 20, 20), font=thumb_font_code)

        thumb_desc_lines = wrap_text(thumb_draw, descripcion, thumb_font_desc, 650)[:2]
        thumb_start_y = 424
        for i, line in enumerate(thumb_desc_lines):
            thumb_draw.text((24, thumb_start_y + (i * 22)), line, fill=(110, 110, 110), font=thumb_font_desc)

        thumb_canvas.save(thumb_path, "PNG", optimize=True)

        # liberar memoria
        prod.close()
        canvas.close()
        thumb_canvas.close()
        shadow.close()
        thumb_shadow.close()
        cleanup_memory()

    except Exception as e:
        print("ERROR PROCESANDO:", e)
        cleanup_memory()

# =========================
# ROUTES
# =========================
@app.route("/")
def index():
    conn = get_conn()
    productos = conn.execute("SELECT * FROM productos ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("index.html", productos=productos)

@app.route("/upload", methods=["POST"])
def upload():
    files = request.files.getlist("file")
    if not files:
        return redirect(url_for("index"))

    # En Render free conviene no mandar 10 enormes de golpe
    files = files[:5]

    conn = get_conn()

    for f in files:
        try:
            if not f or not f.filename:
                continue

            filename = secure_name(f.filename)
            base_name = os.path.splitext(filename)[0]

            upload_path = os.path.join(UPLOAD_DIR, f"{base_name}.jpg")
            processed_path = os.path.join(PROCESSED_DIR, f"{base_name}.png")
            thumb_name = f"thumb_{base_name}.png"
            thumb_path = os.path.join(THUMBS_DIR, thumb_name)

            f.save(upload_path)

            process_catalog_image(upload_path, processed_path, thumb_path)

            cloud_url = ""
            try:
                if os.path.exists(processed_path):
                    result = cloudinary.uploader.upload(processed_path)
                    cloud_url = result.get("secure_url", "")
            except Exception as e:
                print("CLOUDINARY ERROR:", e)

            codigo, descripcion = split_name(filename)

            conn.execute("""
                INSERT INTO productos (nombre, codigo, descripcion, precio, imagen, thumb, url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                f"{base_name}.png",
                codigo,
                descripcion,
                "",
                f"{base_name}.png",
                thumb_name,
                cloud_url
            ))
            conn.commit()

            # borrar upload temporal para ahorrar disco/memoria
            if os.path.exists(upload_path):
                try:
                    os.remove(upload_path)
                except Exception:
                    pass

            cleanup_memory()

        except Exception as e:
            print("ERROR SUBIENDO ARCHIVO:", e)
            cleanup_memory()

    conn.close()
    return redirect(url_for("index"))

@app.route("/precio/<int:item_id>", methods=["POST"])
def actualizar_precio(item_id):
    precio = request.form.get("precio", "")
    conn = get_conn()
    conn.execute("UPDATE productos SET precio=? WHERE id=?", (precio, item_id))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

@app.route("/download/<filename>")
def download(filename):
    path = os.path.join(PROCESSED_DIR, filename)
    if not os.path.exists(path):
        return redirect(url_for("index"))
    return send_file(path, as_attachment=True, download_name=filename)

@app.route("/delete/<int:item_id>")
def delete(item_id):
    conn = get_conn()
    row = conn.execute("SELECT imagen, thumb FROM productos WHERE id=?", (item_id,)).fetchone()

    if row:
        image_name = row["imagen"]
        thumb_name = row["thumb"]

        for p in [
            os.path.join(PROCESSED_DIR, image_name),
            os.path.join(THUMBS_DIR, thumb_name),
        ]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception as e:
                    print("ERROR BORRANDO:", e)

    conn.execute("DELETE FROM productos WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    cleanup_memory()
    return redirect(url_for("index"))

@app.route("/export-excel")
def export_excel():
    wb = Workbook()
    ws = wb.active
    ws.title = "Catalogo"

    ws.append(["CODIGO", "DESCRIPCION", "PRECIO", "IMAGEN_LOCAL", "MINIATURA", "LINK_CLOUD"])

    conn = get_conn()
    productos = conn.execute("SELECT * FROM productos ORDER BY id DESC").fetchall()
    conn.close()

    for p in productos:
        ws.append([
            p["codigo"],
            p["descripcion"],
            p["precio"],
            p["imagen"],
            p["thumb"],
            p["url"]
        ])

    excel_path = os.path.join(BASE_DIR, "catalogo.xlsx")
    wb.save(excel_path)
    return send_file(excel_path, as_attachment=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
    
