from flask import Flask, render_template, request, send_file, abort
import os, io, re
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from rembg import remove
from werkzeug.utils import secure_filename

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD = os.path.join(BASE_DIR, "static/uploads")
PROCESSED = os.path.join(BASE_DIR, "static/processed")

os.makedirs(UPLOAD, exist_ok=True)
os.makedirs(PROCESSED, exist_ok=True)


# ---------- UTIL ----------
def limpiar_nombre(nombre):
    base = os.path.splitext(nombre)[0]
    base = base.replace("_", " ").replace("-", " ")
    base = re.sub(r"\s+", " ", base).strip().upper()
    return base


def cargar_fuente(size=28):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except:
        return ImageFont.load_default()


# ---------- PROCESAMIENTO PRO ----------
def procesar(imagen_path, output_path):
    try:
        # 1️⃣ REMOVE BG IA
        with open(imagen_path, "rb") as f:
            output = remove(f.read())

        img = Image.open(io.BytesIO(output)).convert("RGBA")

        # 2️⃣ RECORTE AUTOMÁTICO (bounding box real)
        bbox = img.getbbox()
        if bbox:
            img = img.crop(bbox)

        # 3️⃣ CANVAS PROPORCIONAL
        W, H = 1000, 1000
        canvas = Image.new("RGBA", (W, H), (255, 255, 255, 255))

        # 4️⃣ ESCALA INTELIGENTE
        max_size = 700
        img.thumbnail((max_size, max_size), Image.LANCZOS)

        # 5️⃣ CENTRADO PERFECTO
        x = (W - img.width) // 2
        y = (H - img.height) // 2 - 40

        # 6️⃣ SOMBRA PROFESIONAL
        shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw_shadow = ImageDraw.Draw(shadow)

        draw_shadow.ellipse(
            (img.width*0.1, img.height*0.75, img.width*0.9, img.height*0.95),
            fill=(0, 0, 0, 120)
        )

        shadow = shadow.filter(ImageFilter.GaussianBlur(30))
        canvas.paste(shadow, (x, y + 50), shadow)

        # 7️⃣ PEGAR PRODUCTO
        canvas.paste(img, (x, y), img)

        draw = ImageDraw.Draw(canvas)

        # 8️⃣ TEXTO LIMPIO
        texto = limpiar_nombre(os.path.basename(imagen_path))

        if len(texto) > 45:
            texto = texto[:42] + "..."

        font = cargar_fuente(30)

        tw, th = draw.textsize(texto, font=font)

        draw.text(
            ((W - tw) / 2, H - 80),
            texto,
            fill=(50, 50, 50),
            font=font
        )

        # 9️⃣ LOGO
        logo_path = os.path.join(BASE_DIR, "static/logo.png")

        if os.path.exists(logo_path):
            logo = Image.open(logo_path).convert("RGBA")
            logo.thumbnail((200, 60))
            canvas.paste(logo, (W - logo.width - 30, 30), logo)

        # 🔟 EXPORT
        canvas.convert("RGB").save(output_path, "PNG")

    except Exception as e:
        print("ERROR PRO:", e)
        raise e


# ---------- ROUTES ----------
@app.route("/")
def index():
    files = os.listdir(PROCESSED)
    return render_template("index.html", imagenes=files)


@app.route("/remove-bg", methods=["POST"])
def remove_bg():
    try:
        file = request.files.get("file")

        if not file:
            return {"error": "no file"}, 400

        filename = secure_filename(file.filename)

        upload_path = os.path.join(UPLOAD, filename)
        file.save(upload_path)

        output_path = os.path.join(PROCESSED, filename)

        procesar(upload_path, output_path)

        return {"ok": True}

    except Exception as e:
        print("ERROR ENDPOINT:", e)
        return {"error": str(e)}, 500


@app.route("/download/<filename>")
def download(filename):
    path = os.path.join(PROCESSED, filename)

    if not os.path.exists(path):
        return abort(404)

    return send_file(path, as_attachment=True)


# ---------- RUN ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
