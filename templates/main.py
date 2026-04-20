from flask import Flask, render_template, request, send_file
import os
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)

UPLOAD = "static/uploads"
PROCESSED = "static/processed"

os.makedirs(UPLOAD, exist_ok=True)
os.makedirs(PROCESSED, exist_ok=True)


def agregar_marca(imagen_path, output_path, nombre_archivo):
    img = Image.open(imagen_path).convert("RGBA")

    draw = ImageDraw.Draw(img)

    texto = nombre_archivo.split(".")[0].replace("_", " ")

    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except:
        font = ImageFont.load_default()

    w, h = img.size
    text_w, text_h = draw.textsize(texto, font=font)

    draw.text(((w - text_w) / 2, h - text_h - 20),
              texto,
              fill=(255,255,255),
              font=font)

    # LOGO
    logo = Image.open("static/logo.png").convert("RGBA")
    logo = logo.resize((120, 40))

    img.paste(logo, (w - 140, 20), logo)

    img.save(output_path)


@app.route("/")
def index():
    imagenes = os.listdir(PROCESSED)
    return render_template("index.html", imagenes=imagenes)


@app.route("/remove-bg", methods=["POST"])
def remove_bg():
    file = request.files["file"]

    path = os.path.join(UPLOAD, file.filename)
    file.save(path)

    output = os.path.join(PROCESSED, file.filename)

    # acá podés meter tu IA de fondo si querés
    agregar_marca(path, output, file.filename)

    return {"ok": True}


@app.route("/download/<filename>")
def download(filename):
    return send_file(os.path.join(PROCESSED, filename), as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True)
