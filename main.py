from flask import Flask, render_template, request, send_file, abort
import os, io
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from werkzeug.utils import secure_filename

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD = os.path.join(BASE_DIR, "static/uploads")
PROCESSED = os.path.join(BASE_DIR, "static/processed")

os.makedirs(UPLOAD, exist_ok=True)
os.makedirs(PROCESSED, exist_ok=True)

API_KEY = os.environ.get("REMOVE_BG_API_KEY")


def cargar_fuente(size=28):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except:
        return ImageFont.load_default()


def limpiar_nombre(nombre):
    base = os.path.splitext(nombre)[0]
    base = base.replace("_", " ").replace("-", " ")
    return base.upper()


def quitar_fondo_removebg(image_path):
    with open(image_path, "rb") as img_file:
        response = requests.post(
            "https://api.remove.bg/v1.0/removebg",
            files={"image_file": img_file},
            data={"size": "auto"},
            headers={"X-Api-Key": API_KEY},
        )

    if response.status_code != 200:
        raise Exception(f"Remove.bg error: {response.text}")

    return response.content


def procesar(imagen_path, output_path):
    try:
        img_bytes = quitar_fondo_removebg(imagen_path)

        producto = Image.open(io.BytesIO(img_bytes)).convert("RGBA")

        bbox = producto.getbbox()
        if bbox:
            producto = producto.crop(bbox)

        W, H = 1000, 1000
        canvas = Image.new("RGBA", (W, H), (255, 255, 255, 255))

        producto.thumbnail((700, 700))

        x = (W - producto.width) // 2
        y = (H - producto.height) // 2 - 40

        shadow = Image.new("RGBA", producto.size, (0, 0, 0, 0))
        draw_shadow = ImageDraw.Draw(shadow)

        draw_shadow.ellipse(
            (producto.width*0.1, producto.height*0.75, producto.width*0.9, producto.height*0.95),
            fill=(0, 0, 0, 120)
        )

        shadow = shadow.filter(ImageFilter.GaussianBlur(30))
        canvas.paste(shadow, (x, y + 50), shadow)

        canvas.paste(producto, (x, y), producto)

        draw = ImageDraw.Draw(canvas)

        texto = limpiar_nombre(os.path.basename(imagen_path))

        if len(texto) > 45:
            texto = texto[:42] + "..."

        font = cargar_fuente(30)

        # 🔥 FIX NUEVO
        bbox = draw.textbbox((0, 0), texto, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

        draw.text(
            ((W - tw) / 2, H - 80),
            texto,
            fill=(50, 50, 50),
            font=font
        )

        logo_path = os.path.join(BASE_DIR, "static/logo.png")

        if os.path.exists(logo_path):
            logo = Image.open(logo_path).convert("RGBA")
            logo.thumbnail((200, 60))
            canvas.paste(logo, (W - logo.width - 30, 30), logo)

        canvas.convert("RGB").save(output_path, "PNG")

    except Exception as e:
        print("ERROR PROCESANDO:", e)
        raise e


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

        if not API_KEY:
            return {"error": "Falta API KEY remove.bg"}, 500

        filename = secure_filename(file.filename)

        upload_path = os.path.join(UPLOAD, filename)
        file.save(upload_path)

        output_path = os.path.join(PROCESSED, filename)

        procesar(upload_path, output_path)

        return {"ok": True}

    except Exception as e:
        print("ERROR:", e)
        return {"error": str(e)}, 500


@app.route("/download/<filename>")
def download(filename):
    path = os.path.join(PROCESSED, filename)

    if not os.path.exists(path):
        return abort(404)

    return send_file(path, as_attachment=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
