from flask import Flask, render_template, request, send_file, redirect
import os, io, sqlite3
import requests
from PIL import Image, ImageDraw, ImageFilter
from werkzeug.utils import secure_filename
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.pagesizes import letter
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

# ---------- CLOUDINARY ----------
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
    base = os.path.splitext(nombre)[0].replace("_", " ").upper()
    partes = base.split(" ", 1)
    codigo = partes[0]
    desc = partes[1] if len(partes) > 1 else ""
    return codigo, desc

# ---------- REMOVE BG (SEGURO) ----------
def remove_bg(path):
    try:
        with open(path, "rb") as f:
            res = requests.post(
                "https://api.remove.bg/v1.0/removebg",
                files={"image_file": f},
                headers={"X-Api-Key": API_KEY},
            )

        if res.status_code != 200:
            print("REMOVE.BG ERROR:", res.text)
            return open(path, "rb").read()

        return res.content

    except Exception as e:
        print("ERROR REMOVE.BG:", e)
        return open(path, "rb").read()

# ---------- PROCESAR ----------
def procesar(path, output):
    try:
        img_bytes = remove_bg(path)
        prod = Image.open(io.BytesIO(img_bytes)).convert("RGBA")

        bbox = prod.getbbox()
        if bbox:
            prod = prod.crop(bbox)

        canvas = Image.new("RGBA", (1000,1000), (0,0,0,0))

        prod.thumbnail((700,700))
        x = (1000 - prod.width)//2
        y = (1000 - prod.height)//2 - 40

        shadow = Image.new("RGBA", prod.size, (0,0,0,0))
        draw = ImageDraw.Draw(shadow)
        draw.ellipse((50, prod.height*0.7, prod.width-50, prod.height), fill=(0,0,0,120))
        shadow = shadow.filter(ImageFilter.GaussianBlur(25))

        canvas.paste(shadow, (x, y+40), shadow)
        canvas.paste(prod, (x,y), prod)

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

# ---------- UPLOAD (BLINDADO) ----------
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
                name = secure_filename(f.filename)

                up = os.path.join(UPLOAD, name)
                f.save(up)

                out = os.path.join(PROCESSED, name)

                procesar(up, out)

                # Cloudinary seguro
                try:
                    result = cloudinary.uploader.upload(out)
                    url = result["secure_url"]
                except Exception as e:
                    print("CLOUDINARY ERROR:", e)
                    url = ""

                codigo, desc = separar(name)

                c.execute("""
                INSERT INTO productos (nombre,codigo,descripcion,precio,imagen,url)
                VALUES (?,?,?,?,?,?)
                """, (name, codigo, desc, "", name, url))

            except Exception as e:
                print("ERROR ARCHIVO:", e)

        conn.commit()
        conn.close()

        return redirect("/")

    except Exception as e:
        print("ERROR GENERAL:", e)
        return redirect("/")

# ---------- PRECIO ----------
@app.route("/precio/<int:id>", methods=["POST"])
def precio(id):
    try:
        precio = request.form.get("precio")

        conn = sqlite3.connect(DB)
        conn.execute("UPDATE productos SET precio=? WHERE id=?", (precio,id))
        conn.commit()
        conn.close()

        return redirect("/")

    except Exception as e:
        print("ERROR PRECIO:", e)
        return redirect("/")

# ---------- DELETE ----------
@app.route("/delete/<int:id>")
def delete(id):
    try:
        conn = sqlite3.connect(DB)
        conn.execute("DELETE FROM productos WHERE id=?", (id,))
        conn.commit()
        conn.close()
        return redirect("/")
    except:
        return redirect("/")

# ---------- DOWNLOAD ----------
@app.route("/download/<filename>")
def download(filename):
    try:
        return send_file(os.path.join(PROCESSED, filename), as_attachment=True)
    except:
        return redirect("/")

# ---------- EXPORT PDF ----------
@app.route("/export")
def export():
    try:
        pdf_path = os.path.join(BASE_DIR, "catalogo.pdf")

        doc = SimpleDocTemplate(pdf_path, pagesize=letter)
        elements = []

        conn = sqlite3.connect(DB)
        productos = conn.execute("SELECT * FROM productos").fetchall()
        conn.close()

        for p in productos:
            elements.append(Paragraph(f"{p[2]} - {p[3]}"))
            elements.append(Paragraph(f"Precio: {p[4]}"))
            elements.append(Paragraph(f"Link: {p[6]}"))
            elements.append(Spacer(1,20))

        doc.build(elements)

        return send_file(pdf_path, as_attachment=True)

    except Exception as e:
        print("ERROR PDF:", e)
        return redirect("/")

# ---------- EXPORT EXCEL ----------
@app.route("/export-excel")
def export_excel():
    try:
        wb = Workbook()
        ws = wb.active

        ws.append(["CODIGO", "DESCRIPCION", "PRECIO", "LINK"])

        conn = sqlite3.connect(DB)
        productos = conn.execute("SELECT * FROM productos").fetchall()
        conn.close()

        for p in productos:
            ws.append([p[2], p[3], p[4], p[6]])

        file_path = os.path.join(BASE_DIR, "catalogo.xlsx")
        wb.save(file_path)

        return send_file(file_path, as_attachment=True)

    except Exception as e:
        print("ERROR EXCEL:", e)
        return redirect("/")

# ---------- RUN ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
