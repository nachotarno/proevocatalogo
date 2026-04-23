from flask import Flask, render_template, request, send_file, redirect, url_for
import os
import io
import gc
import time
import sqlite3
import requests

from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageFont
from werkzeug.utils import secure_filename
from openpyxl import Workbook
from rembg import remove as rembg_remove

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB

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

REMOVE_BG_API_KEY = os.environ.get("REMOVE_BG_API_KEY", "").strip()

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
            thumb TEXT DEFAULT ''
        )
    """)
    conn.commit()
    conn.close()

init_db()

# =========================
# HELPERS
# =========================
def cleanup_memory():
    gc.collect()

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

def make_white_transparent(image):
    image = image.convert("RGBA")
    pixels = []

    for red, green, blue, alpha in image.getdata():
        if red > 235 and green > 235 and blue > 235:
            pixels.append((255, 255, 255, 0))
        else:
            pixels.append((red, green, blue, alpha))

    image.putdata(pixels)
    return image

def downscale_before_bg(local_path: str):
    try:
        resample = get_resample()
        with Image.open(local_path) as img:
            img = ImageOps.exif_transpose(img)

            max_side = 1300
            if max(img.size) > max_side:
                img.thumbnail((max_side, max_side), resample)

            img = img.convert("RGB")
            img.save(local_path, format="JPEG", quality=85, optimize=True)
    except Exception as e:
        raise Exception(f"No se pudo preparar la imagen: {e}")

# =========================
# REMOVE BG HIBRIDO
# =========================
def remove_bg_removebg(local_path: str) -> bytes:
    if not REMOVE_BG_API_KEY:
        raise Exception("Falta configurar REMOVE_BG_API_KEY en Render.")

    with open(local_path, "rb") as f:
        response = requests.post(
            "https://api.remove.bg/v1.0/removebg",
            files={"image_file": f},
            data={"size": "auto"},
            headers={"X-Api-Key": REMOVE_BG_API_KEY},
            timeout=90
        )

    if response.status_code == 200:
        return response.content

    try:
        error_json = response.json()
        msg = error_json.get("errors", [{}])[0].get("title", response.text)
    except Exception:
        msg = response.text

    raise Exception(f"remove.bg falló: {msg}")

def remove_bg_rembg(local_path: str) -> bytes:
    with open(local_path, "rb") as f:
        return rembg_remove(f.read())

def remove_bg_hibrido(local_path: str):
    errores = []

    # 1) intenta remove.bg
    try:
        print("Intentando remove.bg...")
        data = remove_bg_removebg(local_path)
        print("remove.bg OK")
        return data, "remove.bg"
    except Exception as e:
        print("remove.bg falló:", e)
        errores.append(f"remove.bg: {e}")

    # 2) fallback rembg
    try:
        print("Intentando rembg...")
        data = remove_bg_rembg(local_path)
        print("rembg OK")
        return data, "rembg"
    except Exception as e:
        print("rembg falló:", e)
        errores.append(f"rembg: {e}")

    raise Exception(" | ".join(errores))

# =========================
# VALIDAR TRANSPARENCIA
# =========================
def validate_background_removed(img: Image.Image):
    if img.mode != "RGBA":
        raise Exception("La imagen procesada no tiene canal alfa.")

    alpha = img.getchannel("A")
    bbox = alpha.getbbox()

    if bbox is None:
        raise Exception("La imagen quedó vacía.")

    total_pixels = img.width * img.height
    transparent_pixels = 0

    for value in alpha.getdata():
        if value < 250:
            transparent_pixels += 1

    ratio = transparent_pixels / total_pixels if total_pixels else 0

    if ratio < 0.03:
        raise Exception("No se detectó suficiente transparencia. El fondo no fue removido correctamente.")

# =========================
# IMAGE PROCESSING
# =========================
def process_catalog_image(input_path: str, output_path: str, thumb_path: str):
    resample = get_resample()
    codigo, descripcion = split_name(os.path.basename(input_path))
    texto_completo = f"{codigo} {descripcion}".strip()

    downscale_before_bg(input_path)
    image_bytes, motor = remove_bg_hibrido(input_path)

    with Image.open(io.BytesIO(image_bytes)) as raw:
        prod = ImageOps.exif_transpose(raw).convert("RGBA")

    validate_background_removed(prod)

    bbox = prod.getbbox()
    if bbox:
        prod = prod.crop(bbox)

    # -------- Imagen final --------
    base_width = 1000
    area_height = 760
    footer_height = 170
    W = base_width
    H = area_height + footer_height

    max_w = 620
    max_h = 520
    prod.thumbnail((max_w, max_h), resample)

    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    x = (W - prod.width) // 2
    y = max(70, (area_height - prod.height) // 2 + 20)

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

    canvas.paste(shadow, (x, y + 28), shadow)
    canvas.paste(prod, (x, y), prod)

    draw = ImageDraw.Draw(canvas)

    logo_path = os.path.join(STATIC_DIR, "logo.png")
    if os.path.exists(logo_path):
        with Image.open(logo_path) as logo_raw:
            logo = make_white_transparent(logo_raw)
            logo_width = int(W * 0.16)
            ratio = logo_width / logo.width
            logo_height = int(logo.height * ratio)
            logo = logo.resize((logo_width, logo_height), resample)

            lx = W - logo.width - 24
            ly = 20
            canvas.paste(logo, (lx, ly), logo)

    font_main = load_font(int(W * 0.04))
    text = texto_completo.upper()

    text_box = draw.textbbox((0, 0), text, font=font_main)
    text_width = text_box[2] - text_box[0]
    text_height = text_box[3] - text_box[1]

    text_x = (W - text_width) // 2
    text_y = area_height + ((footer_height - text_height) // 2) - 4

    draw.text((text_x + 2, text_y + 2), text, fill=(0, 0, 0, 180), font=font_main)
    draw.text((text_x, text_y), text, fill=(255, 255, 255, 255), font=font_main)

    canvas.save(output_path, "PNG", optimize=True)

    # -------- Miniatura --------
    thumb_w = 700
    thumb_h = 520
    thumb_canvas = Image.new("RGBA", (thumb_w, thumb_h), (255, 255, 255, 0))

    thumb_prod = prod.copy()
    thumb_prod.thumbnail((360, 260), resample)

    tx = (thumb_w - thumb_prod.width) // 2
    ty = 54 + (230 - thumb_prod.height) // 2

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
        with Image.open(logo_path) as logo_small_raw:
            logo_small = make_white_transparent(logo_small_raw)
            logo_small.thumbnail((110, 34), resample)
            thumb_canvas.paste(logo_small, (thumb_w - logo_small.width - 14, 14), logo_small)

    thumb_font = load_font(22)
    thumb_text = f"{texto_completo.upper()} · {motor.upper()}"

    thumb_text_box = thumb_draw.textbbox((0, 0), thumb_text, font=thumb_font)
    thumb_text_w = thumb_text_box[2] - thumb_text_box[0]

    thumb_text_x = (thumb_w - thumb_text_w) // 2
    thumb_text_y = 404

    thumb_draw.text((thumb_text_x + 1, thumb_text_y + 1), thumb_text, fill=(0, 0, 0, 140), font=thumb_font)
    thumb_draw.text((thumb_text_x, thumb_text_y), thumb_text, fill=(30, 30, 30), font=thumb_font)

    thumb_canvas.save(thumb_path, "PNG", optimize=True)

    prod.close()
    canvas.close()
    thumb_canvas.close()
    shadow.close()
    thumb_shadow.close()
    cleanup_memory()

# =========================
# ROUTES
# =========================
@app.route("/")
def index():
    conn = get_conn()
    productos = conn.execute("SELECT * FROM productos ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("index.html", productos=productos, error="")

@app.route("/upload", methods=["POST"])
def upload():
    files = request.files.getlist("file")
    if not files:
        return redirect(url_for("index"))

    files = files[:1]  # Render free: más estable
    conn = get_conn()

    try:
        for f in files:
            if not f or not f.filename:
                continue

            original_name = secure_name(f.filename)
            timestamp = int(time.time())
            base_name = f"{os.path.splitext(original_name)[0]}_{timestamp}"

            upload_path = os.path.join(UPLOAD_DIR, f"{base_name}.jpg")
            processed_filename = f"proevo_{base_name}.png"
            processed_path = os.path.join(PROCESSED_DIR, processed_filename)

            thumb_filename = f"thumb_{base_name}.png"
            thumb_path = os.path.join(THUMBS_DIR, thumb_filename)

            f.save(upload_path)

            process_catalog_image(upload_path, processed_path, thumb_path)

            codigo, descripcion = split_name(original_name)

            conn.execute("""
                INSERT INTO productos (nombre, codigo, descripcion, precio, imagen, thumb)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                processed_filename,
                codigo,
                descripcion,
                "",
                processed_filename,
                thumb_filename
            ))
            conn.commit()

            if os.path.exists(upload_path):
                os.remove(upload_path)

        conn.close()
        return redirect(url_for("index"))

    except Exception as e:
        print("ERROR EN UPLOAD:", e)

        try:
            if 'upload_path' in locals() and os.path.exists(upload_path):
                os.remove(upload_path)
            if 'processed_path' in locals() and os.path.exists(processed_path):
                os.remove(processed_path)
            if 'thumb_path' in locals() and os.path.exists(thumb_path):
                os.remove(thumb_path)
        except Exception:
            pass

        conn.close()

        conn2 = get_conn()
        productos = conn2.execute("SELECT * FROM productos ORDER BY id DESC").fetchall()
        conn2.close()
        return render_template(
            "index.html",
            productos=productos,
            error=f"No se pudo procesar la imagen: {e}"
        )

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
        for p in [
            os.path.join(PROCESSED_DIR, row["imagen"]),
            os.path.join(THUMBS_DIR, row["thumb"]),
        ]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

    conn.execute("DELETE FROM productos WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

@app.route("/export-excel")
def export_excel():
    wb = Workbook()
    ws = wb.active
    ws.title = "Catalogo"
    ws.append(["CODIGO", "DESCRIPCION", "PRECIO", "IMAGEN", "MINIATURA"])

    conn = get_conn()
    productos = conn.execute("SELECT * FROM productos ORDER BY id DESC").fetchall()
    conn.close()

    for p in productos:
        ws.append([p["codigo"], p["descripcion"], p["precio"], p["imagen"], p["thumb"]])

    excel_path = os.path.join(BASE_DIR, "catalogo.xlsx")
    wb.save(excel_path)
    return send_file(excel_path, as_attachment=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
