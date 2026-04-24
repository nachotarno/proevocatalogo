from flask import Flask, render_template, request, send_file, redirect, url_for
import os, io, gc, time, sqlite3

from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageFont
from werkzeug.utils import secure_filename
from openpyxl import Workbook

from google import genai
from google.genai import types

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

# =========================
# PATHS
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOAD_DIR = os.path.join(STATIC_DIR, "uploads")
PROCESSED_DIR = os.path.join(STATIC_DIR, "processed")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

# =========================
# DB
# =========================
DB_PATH = os.path.join(BASE_DIR, "catalogo.db")

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
            imagen TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# =========================
# HELPERS
# =========================
def make_magenta_transparent(image):
    image = image.convert("RGBA")
    pixels = []

    for r, g, b, a in image.getdata():
        if r > 200 and g < 80 and b > 200:
            pixels.append((255, 0, 255, 0))
        else:
            pixels.append((r, g, b, a))

    image.putdata(pixels)
    return image

# =========================
# NANO BANANA
# =========================
def remove_bg_nanobanana(local_path):
    if not GEMINI_API_KEY:
        raise Exception("Falta GEMINI_API_KEY")

    client = genai.Client(api_key=GEMINI_API_KEY)

    with open(local_path, "rb") as f:
        image_bytes = f.read()

    prompt = """
Remove the background from this image.
Keep only the product.
Place the product on a solid magenta background (#FF00FF).
Do not modify the object.
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash-image",
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
            prompt,
        ],
        config=types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"]
        ),
    )

    for part in response.candidates[0].content.parts:
        if getattr(part, "inline_data", None):
            return part.inline_data.data

    raise Exception("Nano Banana no devolvió imagen")

# =========================
# PROCESO
# =========================
def procesar(input_path, output_path):
    data = remove_bg_nanobanana(input_path)

    img = Image.open(io.BytesIO(data)).convert("RGBA")

    img = make_magenta_transparent(img)

    img.save(output_path, "PNG")

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
    file = request.files["file"]

    filename = secure_filename(file.filename)
    path = os.path.join(UPLOAD_DIR, filename)

    file.save(path)

    output_name = f"proevo_{int(time.time())}.png"
    output_path = os.path.join(PROCESSED_DIR, output_name)

    try:
        procesar(path, output_path)

        conn = get_conn()
        conn.execute("INSERT INTO productos (nombre, imagen) VALUES (?, ?)", (filename, output_name))
        conn.commit()
        conn.close()

    except Exception as e:
        print("ERROR:", e)

    return redirect("/")

@app.route("/download/<filename>")
def download(filename):
    path = os.path.join(PROCESSED_DIR, filename)
    return send_file(path, as_attachment=True)

# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run()
