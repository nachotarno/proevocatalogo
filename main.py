from flask import Flask, render_template, request, send_file, redirect, url_for
import os
import io
import gc
import time
import sqlite3
import requests

from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageFont
from werkzeug.utils import secure_filename

# 🔥 IA LOCAL
from rembg import remove

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

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

# ================= DB =================
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT,
            codigo TEXT,
            descripcion TEXT,
            precio TEXT,
            imagen TEXT,
            thumb TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ================= HELPERS =================
def cleanup():
    gc.collect()

def split_name(filename):
    base = os.path.splitext(filename)[0]
    base = base.replace("_", " ").replace("-", " ").upper()
    parts = base.split(" ", 1)
    codigo = parts[0]
    descripcion = parts[1] if len(parts) > 1 else ""
    return codigo, descripcion

def remove_bg_hibrido(path):
    """
    1. Intenta remove.bg
    2. fallback rembg
    3. valida transparencia
    """

    # -------- TRY REMOVE.BG --------
    if REMOVE_BG_API_KEY:
        try:
            with open(path, "rb") as f:
                res = requests.post(
                    "https://api.remove.bg/v1.0/removebg",
                    files={"image_file": f},
                    headers={"X-Api-Key": REMOVE_BG_API_KEY},
                    timeout=60
                )

            if res.status_code == 200:
                print("✔ remove.bg OK")
                return res.content
            else:
                print("⚠ remove.bg falló:", res.text)

        except Exception as e:
            print("⚠ remove.bg error:", e)

    # -------- FALLBACK REMBG --------
    try:
        print("🔥 usando rembg fallback")

        with open(path, "rb") as f:
            output = remove(f.read())

        return output

    except Exception as e:
        raise Exception(f"Falló IA local: {e}")

def validar_transparencia(img):
    if img.mode != "RGBA":
        raise Exception("Sin canal alfa")

    alpha = img.getchannel("A")

    total = img.width * img.height
    transparent = sum(1 for v in alpha.getdata() if v < 250)

    ratio = transparent / total if total else 0

    if ratio < 0.03:
        raise Exception("No se detectó fondo removido correctamente")

# ================= PROCESO =================
def procesar(path, output, thumb):
    img_bytes = remove_bg_hibrido(path)

    prod = Image.open(io.BytesIO(img_bytes))
    prod = ImageOps.exif_transpose(prod).convert("RGBA")

    # 🔥 VALIDACIÓN
    validar_transparencia(prod)

    bbox = prod.getbbox()
    if bbox:
        prod = prod.crop(bbox)

    W, H = 1000, 1000
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    prod.thumbnail((650, 650))

    x = (W - prod.width) // 2
    y = (H - prod.height) // 2

    # sombra
    shadow = Image.new("RGBA", (prod.width, prod.height), (0, 0, 0, 0))
    d = ImageDraw.Draw(shadow)
    d.ellipse(
        (prod.width*0.2, prod.height*0.8, prod.width*0.8, prod.height),
        fill=(0,0,0,100)
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(20))

    canvas.paste(shadow, (x, y+30), shadow)
    canvas.paste(prod, (x, y), prod)

    # logo
    logo_path = os.path.join(STATIC_DIR, "logo.png")
    if os.path.exists(logo_path):
        logo = Image.open(logo_path).convert("RGBA")
        logo.thumbnail((200, 80))
        canvas.paste(logo, (W-logo.width-20, 20), logo)

    # texto
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()

    nombre = os.path.basename(path).split(".")[0].upper()

    draw.text((W//2-100, H-80), nombre, fill=(255,255,255), font=font)

    canvas.save(output)

    # thumb
    t = canvas.copy()
    t.thumbnail((400, 400))
    t.save(thumb)

# ================= ROUTES =================
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
        return "No hay archivos"

    conn = get_conn()

    try:
        for f in files[:1]:  # 🔥 estabilidad
            name = secure_filename(f.filename)
            ts = str(int(time.time()))

            upload_path = os.path.join(UPLOAD_DIR, ts + name)
            out_path = os.path.join(PROCESSED_DIR, ts + ".png")
            thumb_path = os.path.join(THUMBS_DIR, ts + ".png")

            f.save(upload_path)

            procesar(upload_path, out_path, thumb_path)

            codigo, descripcion = split_name(name)

            conn.execute("""
                INSERT INTO productos (nombre, codigo, descripcion, precio, imagen, thumb)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                name,
                codigo,
                descripcion,
                "",
                os.path.basename(out_path),
                os.path.basename(thumb_path)
            ))
            conn.commit()

            os.remove(upload_path)

        conn.close()
        return redirect("/")

    except Exception as e:
        print("🔥 ERROR:", e)
        conn.close()
        return f"ERROR: {str(e)}"

@app.route("/download/<filename>")
def download(filename):
    return send_file(os.path.join(PROCESSED_DIR, filename), as_attachment=True)

@app.route("/delete/<int:id>")
def delete(id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM productos WHERE id=?", (id,)).fetchone()

    if row:
        try:
            os.remove(os.path.join(PROCESSED_DIR, row["imagen"]))
            os.remove(os.path.join(THUMBS_DIR, row["thumb"]))
        except:
            pass

    conn.execute("DELETE FROM productos WHERE id=?", (id,))
    conn.commit()
    conn.close()

    return redirect("/")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
