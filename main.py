from flask import Flask, render_template, request, send_file, abort
import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from rembg import remove
from werkzeug.utils import secure_filename

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD = os.path.join(BASE_DIR, "static/uploads")
PROCESSED = os.path.join(BASE_DIR, "static/processed")

os.makedirs(UPLOAD, exist_ok=True)
os.makedirs(PROCESSED, exist_ok=True)


def procesar(imagen_path, output_path):
    try:
        # ---------- QUITAR FONDO REAL ----------
        with open(imagen_path, "rb") as f:
            input_data = f.read()

        output_data = remove(input_data)

        producto = Image.open(
            io.BytesIO(output_data)
        ).convert("RGBA")

        # ---------- FONDO BLANCO ----------
        canvas = Image.new("RGBA", (900, 900), (255,255,255,255))

        producto.thumbnail((650,650))

        x = (900 - producto.width)//2
        y = (900 - producto.height)//2 - 30

        # ---------- SOMBRA ----------
        shadow = Image.new("RGBA", producto.size, (0,0,0,150))
        shadow = shadow.filter(ImageFilter.GaussianBlur(25))

        canvas.paste(shadow, (x+10, y+30), shadow)
        canvas.paste(producto, (x,y), producto)

        draw = ImageDraw.Draw(canvas)

        # ---------- TEXTO ----------
        texto = os.path.basename(imagen_path).split(".")[0]

        try:
            font = ImageFont.truetype("arial.ttf", 24)
        except:
            font = ImageFont.load_default()

        draw.text((50, 840), texto, fill=(50,50,50), font=font)

        # ---------- LOGO ----------
        logo_path = os.path.join(BASE_DIR, "static/logo.png")
        if os.path.exists(logo_path):
            logo = Image.open(logo_path).convert("RGBA")
            logo.thumbnail((140,50))
            canvas.paste(logo, (740,20), logo)

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
