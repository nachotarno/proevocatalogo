from flask import Flask, render_template, request, send_file, redirect
import os
import io
import sqlite3
import requests

from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageFont
from werkzeug.utils import secure_filename
from openpyxl import Workbook

import cloudinary
import cloudinary.uploader

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD = os.path.join(BASE_DIR, "static/uploads")
PROCESSED = os.path.join(BASE_DIR, "static/processed")
DB = os.path.join(BASE_DIR, "catalogo.db")

os.makedirs(UPLOAD, exist_ok=True)
os.makedirs(PROCESSED, exist_ok=True)

API_KEY = os.environ.get("REMOVE_BG_API_KEY")

cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET")
)

# ---------- DB ----------
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        codigo TEXT,
        descripcion TEXT,
        precio TEXT,
        imagen TEXT,
        url TEXT
    )
    """)
    conn.commit()
    conn.close()

init_db()

# ---------- UTIL ----------
def separar(nombre):
    base = os.path.splitext(nombre)[0]
    base = base.replace("_", " ").replace("-", " ")
    base = " ".join(base.split()).upper()

    partes = base.split(" ", 1)
    codigo = partes[0] if len(partes) > 0 else ""
    desc = partes[1] if len(partes) > 1 else ""
    return codigo, desc

# ---------- REMOVE BG ----------
def remove_bg_file(path):
    try:
        with open(path, "rb") as f:
            res = requests.post(
                "https://api.remove.bg/v1.0/removebg",
                files={"image_file": f},
                headers={"X-Api-Key": API_KEY},
            )

        if res.status_code != 200:
            return open(path, "rb").read()

        return res.content

    except:
        return open(path, "rb").read()

# ---------- PROCESAR PRO ----------
def procesar(path, output):
    try:
        img_bytes = remove_bg_file(path)

        prod = Image.open(io.BytesIO(img_bytes))
        prod = ImageOps.exif_transpose(prod).convert("RGBA")

        # recorte exacto
        bbox = prod.getbbox()
        if bbox:
            prod = prod.crop(bbox)

        codigo, descripcion = separar(os.path.basename(path))

        # canvas fijo
        W, H = 1000, 1000
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))  # 🔥 TRANSPARENTE

        # escala inteligente
        max_size = 650
        prod.thumbnail((max_size, max_size), Image.LANCZOS)

        # centrado real
        x = (W - prod.width) // 2
        y = (H - prod.height) // 2

        # sombra tipo catálogo
        shadow = Image.new("RGBA", prod.size, (0, 0, 0, 0))
        draw_shadow = ImageDraw.Draw(shadow)

        draw_shadow.ellipse(
            (
                int(prod.width * 0.2),
                int(prod.height * 0.8),
                int(prod.width * 0.8),
                int(prod.height * 0.95)
            ),
            fill=(0, 0, 0, 120)
        )

        shadow = shadow.filter(ImageFilter.GaussianBlur(25))
        canvas.paste(shadow, (x, y + 40), shadow)

        # producto
        canvas.paste(prod, (x, y), prod)

        draw = ImageDraw.Draw(canvas)

        # fuentes
        try:
            font_codigo = ImageFont.truetype("arial.ttf", 32)
            font_desc = ImageFont.truetype("arial.ttf", 22)
        except:
            font_codigo = ImageFont.load_default()
            font_desc = ImageFont.load_default()

        # texto (blanco tipo tu ejemplo)
        draw.text((50, 900), codigo, fill=(255, 255, 255), font=font_codigo)
        draw.text((50, 940), descripcion, fill=(200, 200, 200), font=font_desc)

        # logo arriba derecha
        logo_path = os.path.join(BASE_DIR, "static/logo.png")

        if os.path.exists(logo_path):
            logo = Image.open(logo_path).convert("RGBA")
            logo.thumbnail((180, 60))
            canvas.paste(logo, (W - logo.width - 20, 20), logo)

        # guardar PNG real
        canvas.save(output, "PNG")

    except Exception as e:
        print("ERROR PROCESAR:", e)

# ---------- ROUTES ----------
@app.route("/")
def index():
    conn = sqlite3.connect(DB)
    productos = conn.execute("SELECT * FROM productos").fetchall()
    conn.close()
    return render_template("index.html", productos=productos)

@app.route("/upload", methods=["POST"])
def upload():
    files = request.files.getlist("file")

    conn = sqlite3.connect(DB)
    c = conn.cursor()

    for f in files:
        name = secure_filename(f.filename)

        up = os.path.join(UPLOAD, name)
        f.save(up)

        out = os.path.join(PROCESSED, name)
        procesar(up, out)

        try:
            result = cloudinary.uploader.upload(out)
            url = result["secure_url"]
        except:
            url = ""

        codigo, desc = separar(name)

        c.execute("""
            INSERT INTO productos (nombre, codigo, descripcion, precio, imagen, url)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, codigo, desc, "", name, url))

    conn.commit()
    conn.close()

    return redirect("/")

@app.route("/download/<filename>")
def download(filename):
    path = os.path.join(PROCESSED, filename)
    return send_file(path, as_attachment=True)

# ---------- RUN ----------
if __name__ == "__main__":
    app.run()
