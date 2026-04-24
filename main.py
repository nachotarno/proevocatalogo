from flask import Flask, render_template, request, send_file, redirect, url_for
import os, io, gc, time, sqlite3, requests

from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageFont
from werkzeug.utils import secure_filename
from openpyxl import Workbook

from google import genai
from google.genai import types

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

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
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

NANO_MODEL = "gemini-3.1-flash-image-preview"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            codigo TEXT,
            descripcion TEXT,
            precio TEXT DEFAULT '',
            imagen TEXT NOT NULL,
            thumb TEXT DEFAULT '',
            motor TEXT DEFAULT ''
        )
    """)

    cols = [row[1] for row in c.execute("PRAGMA table_info(productos)").fetchall()]
    if "motor" not in cols:
        c.execute("ALTER TABLE productos ADD COLUMN motor TEXT DEFAULT ''")

    conn.commit()
    conn.close()


init_db()


def cleanup_memory():
    gc.collect()


def secure_name(filename):
    return secure_filename(filename).replace(" ", "_")


def split_name(filename):
    base = os.path.splitext(filename)[0]
    base = base.replace("_-_", " ").replace("_", " ").replace("-", " ")
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


def load_font(size):
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
    for r, g, b, a in image.getdata():
        if r > 245 and g > 245 and b > 245:
            pixels.append((255, 255, 255, 0))
        else:
            pixels.append((r, g, b, a))
    image.putdata(pixels)
    return image


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


def downscale_before_processing(local_path):
    resample = get_resample()
    with Image.open(local_path) as img:
        img = ImageOps.exif_transpose(img)
        if max(img.size) > 1200:
            img.thumbnail((1200, 1200), resample)
        img = img.convert("RGB")
        img.save(local_path, format="JPEG", quality=82, optimize=True)


def validate_background_removed(img):
    if img.mode != "RGBA":
        raise Exception("La imagen no tiene transparencia.")

    alpha = img.getchannel("A")
    total = img.width * img.height
    transparent = sum(1 for v in alpha.getdata() if v < 250)
    ratio = transparent / total if total else 0

    if ratio < 0.03:
        raise Exception("No se detectó suficiente transparencia.")


def remove_bg_removebg(local_path):
    if not REMOVE_BG_API_KEY:
        raise Exception("Falta REMOVE_BG_API_KEY.")

    with open(local_path, "rb") as f:
        response = requests.post(
            "https://api.remove.bg/v1.0/removebg",
            files={"image_file": f},
            data={"size": "auto"},
            headers={"X-Api-Key": REMOVE_BG_API_KEY},
            timeout=60,
        )

    if response.status_code == 200:
        return response.content

    try:
        error_json = response.json()
        msg = error_json.get("errors", [{}])[0].get("title", response.text)
    except Exception:
        msg = response.text

    raise Exception(f"remove.bg falló: {msg}")


def extract_gemini_image_bytes(response):
    if hasattr(response, "candidates") and response.candidates:
        for candidate in response.candidates:
            if candidate.content and candidate.content.parts:
                for part in candidate.content.parts:
                    if getattr(part, "inline_data", None) and part.inline_data.data:
                        return part.inline_data.data

    if hasattr(response, "parts"):
        for part in response.parts:
            try:
                img = part.as_image()
                if img:
                    out = io.BytesIO()
                    img.save(out, format="PNG")
                    return out.getvalue()
            except Exception:
                pass

    raise Exception("Nano Banana no devolvió imagen.")


def remove_bg_nanobanana(local_path):
    if not GEMINI_API_KEY:
        raise Exception("Falta GEMINI_API_KEY.")

    client = genai.Client(api_key=GEMINI_API_KEY)

    with open(local_path, "rb") as f:
        image_bytes = f.read()

    prompt = """
Edit this product photo for ecommerce.

Keep only the real mechanical spare part/product.
Remove the full background: table, green cutting mat, hands, labels, floor, wall, shadows, and any non-product object.
Do not change the product shape, holes, screws, color, rust, scratches, marks, or proportions.
Place the isolated product centered on a pure solid magenta background (#FF00FF).
No text. No logo. No new objects. No frame. No decoration.
Return one clean realistic product image.
"""

    response = client.models.generate_content(
        model=NANO_MODEL,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
            prompt,
        ],
        config=types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"]
        ),
    )

    return extract_gemini_image_bytes(response)


def remove_bg_hibrido(local_path):
    errores = []

    try:
        print("Intentando remove.bg...")
        data = remove_bg_removebg(local_path)
        print("remove.bg OK")
        return data, "remove.bg"
    except Exception as e:
        print("remove.bg falló:", e)
        errores.append(str(e))

    try:
        print("Intentando Nano Banana...")
        data = remove_bg_nanobanana(local_path)

        img = Image.open(io.BytesIO(data)).convert("RGBA")

        # Nano Banana no siempre devuelve alfa real.
        # Por eso pedimos fondo magenta y lo convertimos a transparente.
        img = make_magenta_transparent(img)
        img = make_white_transparent(img)

        out = io.BytesIO()
        img.save(out, format="PNG")

        print("Nano Banana OK")
        return out.getvalue(), "nano-banana"

    except Exception as e:
        print("Nano Banana falló:", e)
        errores.append(str(e))

    raise Exception(" | ".join(errores))


def process_catalog_image(input_path, output_path, thumb_path):
    resample = get_resample()
    codigo, descripcion = split_name(os.path.basename(input_path))
    texto = f"{codigo} {descripcion}".strip().upper()

    downscale_before_processing(input_path)

    image_bytes, motor = remove_bg_hibrido(input_path)

    with Image.open(io.BytesIO(image_bytes)) as raw:
        prod = ImageOps.exif_transpose(raw).convert("RGBA")

    prod = make_magenta_transparent(prod)
    prod = make_white_transparent(prod)

    validate_background_removed(prod)

    bbox = prod.getbbox()
    if bbox:
        prod = prod.crop(bbox)

    W = 1000
    area_height = 760
    footer_height = 170
    H = area_height + footer_height

    prod.thumbnail((620, 520), resample)

    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    x = (W - prod.width) // 2
    y = max(70, (area_height - prod.height) // 2 + 20)

    shadow = Image.new("RGBA", (prod.width, prod.height), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.ellipse(
        (
            int(prod.width * 0.20),
            int(prod.height * 0.82),
            int(prod.width * 0.80),
            int(prod.height * 0.96),
        ),
        fill=(0, 0, 0, 105),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))

    canvas.paste(shadow, (x, y + 24), shadow)
    canvas.paste(prod, (x, y), prod)

    draw = ImageDraw.Draw(canvas)

    logo_path = os.path.join(STATIC_DIR, "logo.png")
    if os.path.exists(logo_path):
        try:
            with Image.open(logo_path) as logo_raw:
                logo = make_white_transparent(logo_raw)
                logo_width = int(W * 0.16)
                ratio = logo_width / logo.width
                logo_height = int(logo.height * ratio)
                logo = logo.resize((logo_width, logo_height), resample)
                canvas.paste(logo, (W - logo.width - 24, 20), logo)
        except Exception as e:
            print("ERROR LOGO:", e)

    font_main = load_font(int(W * 0.04))
    box = draw.textbbox((0, 0), texto, font=font_main)
    tw = box[2] - box[0]
    th = box[3] - box[1]

    tx = (W - tw) // 2
    ty = area_height + ((footer_height - th) // 2) - 4

    draw.text((tx + 2, ty + 2), texto, fill=(0, 0, 0, 180), font=font_main)
    draw.text((tx, ty), texto, fill=(255, 255, 255, 255), font=font_main)

    canvas.save(output_path, "PNG", optimize=True)

    thumb = canvas.copy()
    thumb.thumbnail((700, 520), resample)
    thumb.save(thumb_path, "PNG", optimize=True)

    prod.close()
    canvas.close()
    thumb.close()
    shadow.close()
    cleanup_memory()

    return motor


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

    conn = get_conn()

    try:
        for f in files[:1]:
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

            motor = process_catalog_image(upload_path, processed_path, thumb_path)

            codigo, descripcion = split_name(original_name)

            conn.execute("""
                INSERT INTO productos (nombre, codigo, descripcion, precio, imagen, thumb, motor)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                processed_filename,
                codigo,
                descripcion,
                "",
                processed_filename,
                thumb_filename,
                motor,
            ))
            conn.commit()

            if os.path.exists(upload_path):
                os.remove(upload_path)

        conn.close()
        return redirect(url_for("index"))

    except Exception as e:
        print("ERROR EN UPLOAD:", e)

        try:
            if "upload_path" in locals() and os.path.exists(upload_path):
                os.remove(upload_path)
            if "processed_path" in locals() and os.path.exists(processed_path):
                os.remove(processed_path)
            if "thumb_path" in locals() and os.path.exists(thumb_path):
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
            error=f"No se pudo procesar la imagen: {e}",
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
    ws.append(["CODIGO", "DESCRIPCION", "PRECIO", "IMAGEN", "MINIATURA", "MOTOR"])

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
            p["motor"],
        ])

    excel_path = os.path.join(BASE_DIR, "catalogo.xlsx")
    wb.save(excel_path)
    return send_file(excel_path, as_attachment=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
