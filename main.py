from flask import Flask, render_template, request, send_file, redirect
import os, io, sqlite3
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from werkzeug.utils import secure_filename
from reportlab.platypus import SimpleDocTemplate, Image as RLImage, Paragraph, Spacer
from reportlab.lib.pagesizes import letter

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD = os.path.join(BASE_DIR, "static/uploads")
PROCESSED = os.path.join(BASE_DIR, "static/processed")
DB = os.path.join(BASE_DIR, "catalogo.db")

os.makedirs(UPLOAD, exist_ok=True)
os.makedirs(PROCESSED, exist_ok=True)

API_KEY = os.environ.get("REMOVE_BG_API_KEY")

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
        imagen TEXT
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

# ---------- REMOVE BG ----------
def remove_bg(path):
    with open(path, "rb") as f:
        res = requests.post(
            "https://api.remove.bg/v1.0/removebg",
            files={"image_file": f},
            headers={"X-Api-Key": API_KEY},
        )
    if res.status_code != 200:
        raise Exception(res.text)
    return res.content

# ---------- PROCESAR ----------
def procesar(path, output):
    img_bytes = remove_bg(path)
    prod = Image.open(io.BytesIO(img_bytes)).convert("RGBA")

    bbox = prod.getbbox()
    if bbox:
        prod = prod.crop(bbox)

    canvas = Image.new("RGBA", (1000,1000), (0,0,0,0))

    prod.thumbnail((700,700))
    x = (1000 - prod.width)//2
    y = (1000 - prod.height)//2 - 40

    # sombra
    shadow = Image.new("RGBA", prod.size, (0,0,0,0))
    draw = ImageDraw.Draw(shadow)
    draw.ellipse((50, prod.height*0.7, prod.width-50, prod.height), fill=(0,0,0,120))
    shadow = shadow.filter(ImageFilter.GaussianBlur(25))

    canvas.paste(shadow, (x, y+40), shadow)
    canvas.paste(prod, (x,y), prod)

    canvas.save(output, "PNG")

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

        codigo, desc = separar(name)

        c.execute("INSERT INTO productos (nombre,codigo,descripcion,precio,imagen) VALUES (?,?,?,?,?)",
                  (name, codigo, desc, "", name))

    conn.commit()
    conn.close()

    return redirect("/")

@app.route("/precio/<int:id>", methods=["POST"])
def precio(id):
    precio = request.form.get("precio")

    conn = sqlite3.connect(DB)
    conn.execute("UPDATE productos SET precio=? WHERE id=?", (precio,id))
    conn.commit()
    conn.close()

    return redirect("/")

@app.route("/delete/<int:id>")
def delete(id):
    conn = sqlite3.connect(DB)
    conn.execute("DELETE FROM productos WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect("/")

@app.route("/download/<filename>")
def download(filename):
    return send_file(os.path.join(PROCESSED, filename), as_attachment=True)

@app.route("/export")
def export():
    pdf_path = os.path.join(BASE_DIR, "catalogo.pdf")

    doc = SimpleDocTemplate(pdf_path, pagesize=letter)
    elements = []

    conn = sqlite3.connect(DB)
    productos = conn.execute("SELECT * FROM productos").fetchall()
    conn.close()

    for p in productos:
        img_path = os.path.join(PROCESSED, p[5])

        elements.append(RLImage(img_path, width=200, height=200))
        elements.append(Paragraph(f"{p[2]} - {p[3]}"))
        elements.append(Paragraph(f"Precio: {p[4]}"))
        elements.append(Spacer(1,20))

    doc.build(elements)

    return send_file(pdf_path, as_attachment=True)

# ---------- RUN ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
