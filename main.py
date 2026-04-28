from flask import Flask, render_template, request, send_file, redirect, url_for
import os
import io
import time
import sqlite3

from PIL import Image
from werkzeug.utils import secure_filename

from google import genai
from google.genai import types

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOAD_DIR = os.path.join(STATIC_DIR, "uploads")
PROCESSED_DIR = os.path.join(STATIC_DIR, "processed")
DB_PATH = os.path.join(BASE_DIR, "catalogo.db")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()


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


def make_magenta_transparent(image):
    image = image.convert("RGBA")
    pixels = []

    for r, g, b, a in image.getdata():
        if r > 200 and g < 90 and b > 200:
            pixels.append((255, 0, 255, 0))
        else:
            pixels.append((r, g, b, a))

    image.putdata(pixels)
    return image


def prepare_image(path):
    img = Image.open(path).convert("RGB")
    img.thumbnail((1200, 1200))
    img.save(path, "JPEG", quality=85, optimize=True)


def remove_bg_nanobanana(local_path):
    if not GEMINI_API_KEY:
        raise Exception("Falta configurar GEMINI_API_KEY en Render")

    client = genai.Client(api_key=GEMINI_API_KEY)

    prepare_image(local_path)

    with open(local_path, "rb") as f:
        image_bytes = f.read()

    prompt = """
Remove the background from this product image.
Keep only the real product/object.
Do not change the object shape, color, details, holes, screws or proportions.
Place the isolated object on a pure solid magenta background (#FF00FF).
No text. No logos. No extra objects.
Return one clean realistic image.
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

    if not response.candidates:
        raise Exception("Nano Banana no devolvió respuesta")

    for part in response.candidates[0].content.parts:
        if getattr(part, "inline_data", None) and part.inline_data.data:
            return part.inline_data.data

    raise Exception("Nano Banana no devolvió imagen")


def procesar(input_path, output_path):
    data = remove_bg_nanobanana(input_path)

    img = Image.open(io.BytesIO(data)).convert("RGBA")
    img = make_magenta_transparent(img)

    img.save(output_path, "PNG")


@app.route("/")
def index():
    conn = get_conn()
    productos = conn.execute("SELECT * FROM productos ORDER BY id DESC").fetchall()
    conn.close()
    error = request.args.get("error", "")
    return render_template("index.html", productos=productos, error=error)


@app.route("/upload", methods=["POST"])
def upload():
    try:
        if "file" not in request.files:
            return redirect(url_for("index", error="No se recibió imagen"))

        file = request.files["file"]

        if not file or not file.filename:
            return redirect(url_for("index", error="Seleccioná una imagen"))

        filename = secure_filename(file.filename)
        timestamp = int(time.time())

        upload_name = f"{timestamp}_{filename}"
        upload_path = os.path.join(UPLOAD_DIR, upload_name)

        output_name = f"proevo_{timestamp}.png"
        output_path = os.path.join(PROCESSED_DIR, output_name)

        file.save(upload_path)

        procesar(upload_path, output_path)

        conn = get_conn()
        conn.execute(
            "INSERT INTO productos (nombre, imagen) VALUES (?, ?)",
            (filename, output_name)
        )
        conn.commit()
        conn.close()

        try:
            os.remove(upload_path)
        except Exception:
            pass

        return redirect(url_for("index"))

    except Exception as e:
        print("ERROR UPLOAD:", e)
        return redirect(url_for("index", error=str(e)))


@app.route("/download/<filename>")
def download(filename):
    path = os.path.join(PROCESSED_DIR, filename)

    if not os.path.exists(path):
        return redirect(url_for("index", error="Archivo no encontrado"))

    return send_file(path, as_attachment=True, download_name=filename)


@app.route("/delete/<int:item_id>")
def delete(item_id):
    conn = get_conn()
    row = conn.execute("SELECT imagen FROM productos WHERE id=?", (item_id,)).fetchone()

    if row:
        path = os.path.join(PROCESSED_DIR, row["imagen"])
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass

    conn.execute("DELETE FROM productos WHERE id=?", (item_id,))
    conn.commit()
    conn.close()

    return redirect(url_for("index"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
