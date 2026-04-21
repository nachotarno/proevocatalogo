from flask import Flask, render_template, request, send_file, redirect
import os
import io
import sqlite3
import requests

from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageFont
from werkzeug.utils import secure_filename
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.pagesizes import letter
from openpyxl import Workbook

import cloudinary
import cloudinary.uploader

app = Flask(__name__)

# ---------- PATHS ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD = os.path.join(BASE_DIR, "static", "uploads")
PROCESSED = os.path.join(BASE_DIR, "static", "processed")
DB = os.path.join(BASE_DIR, "catalogo.db")

os.makedirs(UPLOAD, exist_ok=True)
os.makedirs(PROCESSED, exist_ok=True)

# ---------- ENV ----------
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

def get_resample():
    try:
        return Image.Resampling.LANCZOS
    except AttributeError:
        return Image.LANCZOS

def get_text_size(draw, text, font):
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        return w, h
    except Exception:
        return (len(text) * 10, 20)

def wrap_text(draw, text, font, max_width):
    words = text.split()
    if not words:
        return [""]

    lines = []
    current = words[0]

    for word in words[1:]:
        test_line = current + " " + word
        w, _ = get_text_size(draw, test_line, font)
        if w <= max_width:
            current = test_line
        else:
            lines.append(current)
            current = word

    lines.append(current)
    return lines

# ---------- REMOVE BG ----------
def remove_bg_file(path):
    try:
        if not API_KEY:
            print("FALTA REMOVE_BG_API_KEY")
            with open(path, "rb") as f:
                return f.read()

        with open(path, "rb") as f:
            res = requests.post(
                "https://api.remove.bg/v1.0/removebg",
                files={"image_file": f},
                headers={"X-Api-Key": API_KEY},
                timeout=120
            )

        if res.status_code != 200:
            print("REMOVE.BG ERROR:", res.text)
            with open(path, "rb") as f:
                return f.read()

        return res.content

    except Exception as e:
        print("ERROR REMOVE.BG:", e)
        with open(path, "rb") as f:
            return f.read()

# ---------- PROCESAR IMAGEN ----------
def procesar(path, output):
    try:
        img_bytes = remove_bg_file(path)

        prod = Image.open(io.BytesIO(img_bytes))
        prod = ImageOps.exif_transpose(prod).convert("RGBA")

        # recorte automático real
        bbox = prod.getbbox()
        if bbox:
            prod = prod.crop(bbox)

        # nombre -> código + descripción
        codigo, descripcion = separar(os.path.basename(path))

        # lienzo fijo para consistencia
        W, H = 1000, 1000
        canvas = Image.new("RGBA", (W, H), (255, 255, 255, 255))

        resample = get_resample()

        # uniformidad de tamaño
        # dejamos un área central reservada para el producto
        max_w = 680
        max_h = 620
        prod.thumbnail((max_w, max_h), resample)

        # centrado
        x = (W - prod.width) // 2
        y = 130 + (max_h - prod.height) // 2

        # sombra
        shadow = Image.new("RGBA", (prod.width, prod.height), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)

        shadow_draw.ellipse(
            (
                int(prod.width * 0.18),
                int(prod.height * 0.80),
                int(prod.width * 0.82),
                int(prod.height * 0.96)
            ),
            fill=(0, 0, 0, 95)
        )

        shadow = shadow.filter(ImageFilter.GaussianBlur(22))
        canvas.paste(shadow, (x, y + 38), shadow)

        # producto
        canvas.paste(prod, (x, y), prod)

        draw = ImageDraw.Draw(canvas)

        # fuentes
        try:
            font_codigo = ImageFont.truetype("arial.ttf", 34)
            font_desc = ImageFont.truetype("arial.ttf", 24)
        except Exception:
            font_codigo = ImageFont.load_default()
            font_desc = ImageFont.load_default()

        # logo arriba derecha
        logo_path = os.path.join(BASE_DIR, "static", "logo.png")
        if os.path.exists(logo_path):
            try:
                logo = Image.open(logo_path).convert("RGBA")
                logo.thumbnail((180, 60), resample)
                lx = W - logo.width - 24
                ly = 24
                canvas.paste(logo, (lx, ly), logo)
            except Exception as e:
                print("ERROR LOGO:", e)

        # texto abajo
        margen_x = 50
        codigo_y = 885
        desc_y = 930

        draw.text(
            (margen_x, codigo_y),
            codigo,
            fill=(20, 20, 20),
            font=font_codigo
        )

        # descripción en una o dos líneas
        desc_max_width = W - 100
        desc_lines = wrap_text(draw, descripcion, font_desc, desc_max_width)
        desc_lines = desc_lines[:2]

        line_height = 28
        for i, line in enumerate(desc_lines):
            draw.text(
                (margen_x, desc_y + i * line_height),
                line,
                fill=(80, 80, 80),
                font=font_desc
            )

        # guardar final
        canvas.convert("RGB").save(output, "PNG")

    except Exception as e:
        print("ERROR PROCESAR:", e)

# ---------- ROUTES ----------
@app.route("/")
def index():
    conn = sqlite3.connect(DB)
    productos = conn.execute("SELECT * FROM productos ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("index.html", productos=productos)

@app.route("/upload", methods=["POST"])
def upload():
    try:
        files = request.files.getlist("file")

        if not files:
            return redirect("/")

        conn = sqlite3.connect(DB)
        c = conn.cursor()

        for f in files:
            try:
                if not f or not f.filename:
                    continue

                name = secure_filename(f.filename)

                up = os.path.join(UPLOAD, name)
                f.save(up)

                out = os.path.join(PROCESSED, name)
                procesar(up, out)

                url = ""
                try:
                    if os.path.exists(out):
                        result = cloudinary.uploader.upload(out)
                        url = result.get("secure_url", "")
                except Exception as e:
                    print("CLOUDINARY ERROR:", e)

                codigo, desc = separar(name)

                c.execute("""
                    INSERT INTO productos (nombre, codigo, descripcion, precio, imagen, url)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (name, codigo, desc, "", name, url))

            except Exception as e:
                print("ERROR ARCHIVO:", e)

        conn.commit()
        conn.close()

        return redirect("/")

    except Exception as e:
        print("ERROR GENERAL:", e)
        return redirect("/")

@app.route("/precio/<int:id>", methods=["POST"])
def precio(id):
    try:
        precio_val = request.form.get("precio", "")

        conn = sqlite3.connect(DB)
        conn.execute("UPDATE productos SET precio=? WHERE id=?", (precio_val, id))
        conn.commit()
        conn.close()

        return redirect("/")
    except Exception as e:
        print("ERROR PRECIO:", e)
        return redirect("/")

@app.route("/delete/<int:id>")
def delete(id):
    try:
        conn = sqlite3.connect(DB)
        c = conn.cursor()

        row = c.execute("SELECT imagen FROM productos WHERE id=?", (id,)).fetchone()
        if row:
            imagen = row[0]
            local_path = os.path.join(PROCESSED, imagen)
            if os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except Exception as e:
                    print("ERROR BORRANDO ARCHIVO:", e)

        c.execute("DELETE FROM productos WHERE id=?", (id,))
        conn.commit()
        conn.close()
        return redirect("/")
    except Exception as e:
        print("ERROR DELETE:", e)
        return redirect("/")

@app.route("/download/<filename>")
def download(filename):
    try:
        path = os.path.join(PROCESSED, filename)

        if not os.path.exists(path):
            print("NO EXISTE PARA DESCARGA:", path)
            return redirect("/")

        return send_file(
            path,
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        print("ERROR DOWNLOAD:", e)
        return redirect("/")

@app.route("/export")
def export():
    try:
        pdf_path = os.path.join(BASE_DIR, "catalogo.pdf")

        doc = SimpleDocTemplate(pdf_path, pagesize=letter)
        elements = []

        conn = sqlite3.connect(DB)
        productos = conn.execute("SELECT * FROM productos ORDER BY id DESC").fetchall()
        conn.close()

        for p in productos:
            codigo = p[2] or ""
            descripcion = p[3] or ""
            precio = p[4] or ""
            link = p[6] or ""

            elements.append(Paragraph(f"{codigo} - {descripcion}"))
            elements.append(Paragraph(f"Precio: {precio}"))
            if link:
                elements.append(Paragraph(f"Link: {link}"))
            elements.append(Spacer(1, 20))

        doc.build(elements)

        return send_file(pdf_path, as_attachment=True)
    except Exception as e:
        print("ERROR PDF:", e)
        return redirect("/")

@app.route("/export-excel")
def export_excel():
    try:
        wb = Workbook()
        ws = wb.active
        ws.title = "Catalogo"

        ws.append(["CODIGO", "DESCRIPCION", "PRECIO", "LINK"])

        conn = sqlite3.connect(DB)
        productos = conn.execute("SELECT * FROM productos ORDER BY id DESC").fetchall()
        conn.close()

        for p in productos:
            ws.append([p[2], p[3], p[4], p[6]])

        file_path = os.path.join(BASE_DIR, "catalogo.xlsx")
        wb.save(file_path)

        return send_file(file_path, as_attachment=True)
    except Exception as e:
        print("ERROR EXCEL:", e)
        return redirect("/")
