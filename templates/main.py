from flask import Flask, render_template, request, send_file
import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

app = Flask(__name__)

UPLOAD = "static/uploads"
PROCESSED = "static/processed"

os.makedirs(UPLOAD, exist_ok=True)
os.makedirs(PROCESSED, exist_ok=True)


# 🔥 PROCESAMIENTO PRO
def procesar_imagen(imagen_path, output_path, nombre_archivo):
    img = Image.open(imagen_path).convert("RGBA")

    # --- LIENZO BLANCO ---
    canvas_size = (800, 800)
    fondo = Image.new("RGBA", canvas_size, (255, 255, 255, 255))

    # --- AJUSTE TAMAÑO ---
    img.thumbnail((600, 600), Image.LANCZOS)

    # --- CENTRADO ---
    x = (canvas_size[0] - img.width) // 2
    y = (canvas_size[1] - img.height) // 2 - 20

    # --- SOMBRA ---
    sombra = Image.new("RGBA", img.size, (0, 0, 0, 180))
    sombra = sombra.filter(ImageFilter.GaussianBlur(25))

    fondo.paste(sombra, (x + 10, y + 30), sombra)
    fondo.paste(img, (x, y), img)

    draw = ImageDraw.Draw(fondo)

    # --- TEXTO AUTOMÁTICO ---
    texto = nombre_archivo.split(".")[0].replace("_", " ").upper()

    try:
        font = ImageFont.truetype("arial.ttf", 24)
    except:
        font = ImageFont.load_default()

    text_w, text_h = draw.textsize(texto, font=font)

    draw.text(
        ((canvas_size[0] - text_w) / 2, canvas_size[1] - 60),
        texto,
        fill=(40, 40, 40),
        font=font
    )

    # --- LOGO ---
    try:
        logo = Image.open("static/logo.png").convert("RGBA")
        logo = logo.resize((140, 50))
        fondo.paste(logo, (canvas_size[0] - 160, 20), logo)
    except:
        pass

    # --- GUARDAR FINAL ---
    fondo.convert("RGB").save(output_path, "PNG")


# 🏠 HOME
@app.route("/")
def index():
    imagenes = os.listdir(PROCESSED)
    return render_template("index.html", imagenes=imagenes)


# 📤 SUBIDA
@app.route("/remove-bg", methods=["POST"])
def remove_bg():
    file = request.files["file"]

    if not file:
        return {"error": "No file"}, 400

    filename = file.filename

    path = os.path.join(UPLOAD, filename)
    file.save(path)

    output_path = os.path.join(PROCESSED, filename)

    # 🔥 PROCESAMIENTO
    procesar_imagen(path, output_path, filename)

    return {"ok": True}


# 📥 DESCARGA
@app.route("/download/<filename>")
def download(filename):
    return send_file(os.path.join(PROCESSED, filename), as_attachment=True)


# 🚀 RUN (solo local, Render usa gunicorn)
if __name__ == "__main__":
    app.run(debug=True)
