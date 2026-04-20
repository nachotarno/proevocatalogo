from flask import Flask, render_template, request, send_file, abort
import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

app = Flask(__name__)

UPLOAD = "static/uploads"
PROCESSED = "static/processed"

os.makedirs(UPLOAD, exist_ok=True)
os.makedirs(PROCESSED, exist_ok=True)


# 🧹 LIMPIAR IMÁGENES VIEJAS (opcional pero útil)
def limpiar_procesados():
    for file in os.listdir(PROCESSED):
        path = os.path.join(PROCESSED, file)
        try:
            os.remove(path)
        except:
            pass


# 🔥 PROCESAMIENTO PRO
def procesar_imagen(imagen_path, output_path, nombre_archivo):
    print("PROCESANDO:", nombre_archivo)

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

    # --- LOGO (RUTA SEGURA PARA RENDER) ---
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        logo_path = os.path.join(base_dir, "static", "logo.png")

        if os.path.exists(logo_path):
            logo = Image.open(logo_path).convert("RGBA")
            logo = logo.resize((140, 50))
            fondo.paste(logo, (canvas_size[0] - 160, 20), logo)
        else:
            print("⚠️ Logo no encontrado")
    except Exception as e:
        print("Error cargando logo:", e)

    # --- GUARDAR FINAL ---
    fondo.convert("RGB").save(output_path, "PNG")


# 🏠 HOME
@app.route("/")
def index():
    imagenes = os.listdir(PROCESSED)
    return render_template("index.html", imagenes=imagenes)


# 📤 SUBIR Y PROCESAR
@app.route("/remove-bg", methods=["POST"])
def remove_bg():
    file = request.files.get("file")

    if not file:
        return {"error": "No file"}, 400

    filename = file.filename

    # 🧹 limpiar anteriores (opcional)
    limpiar_procesados()

    upload_path = os.path.join(UPLOAD, filename)
    file.save(upload_path)

    output_path = os.path.join(PROCESSED, filename)

    procesar_imagen(upload_path, output_path, filename)

    return {"ok": True}


# 📥 DESCARGAR
@app.route("/download/<filename>")
def download(filename):
    path = os.path.join(PROCESSED, filename)

    if not os.path.exists(path):
        return abort(404)

    return send_file(path, as_attachment=True)


# 🚀 LOCAL (Render usa gunicorn)
import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
