from flask import Flask, render_template, request, send_file, abort
import os, sqlite3
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from werkzeug.utils import secure_filename

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD = os.path.join(BASE_DIR, "static", "uploads")
PROCESSED = os.path.join(BASE_DIR, "static", "processed")
DB = os.path.join(BASE_DIR, "db.sqlite3")

os.makedirs(UPLOAD, exist_ok=True)
os.makedirs(PROCESSED, exist_ok=True)

# ---------- DB ----------
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT
    )
    """)
    conn.commit()
    conn.close()

init_db()

# ---------- PROCESAR IMAGEN ----------
def procesar(imagen_path, output_path):
    try:
        img = Image.open(imagen_path).convert("RGBA")

        canvas = Image.new("RGBA", (800, 800), (255,255,255,255))

        img.thumbnail((600,600))
        x = (800 - img.width)//2
        y = (800 - img.height)//2

        # sombra
        shadow = Image.new("RGBA", img.size, (0,0,0,150))
        shadow = shadow.filter(ImageFilter.GaussianBlur(20))

        canvas.paste(shadow, (x+10,y+20), shadow)
        canvas.paste(img, (x,y), img)

        draw = ImageDraw.Draw(canvas)

        # texto
        text = os.path.basename(imagen_path).split(".")[0]

        try:
            font = ImageFont.truetype("arial.ttf", 24)
        except:
            font = ImageFont.load_default()

        draw.text((50,750), text, fill=(50,50,50), font=font)

        # logo
        try:
            logo_path = os.path.join(BASE_DIR, "static", "logo.png")
            if os.path.exists(logo_path):
                logo = Image.open(logo_path).convert("RGBA")
                logo.thumbnail((120,40))
                canvas.paste(logo, (650,20), logo)
        except Exception as e:
            print("ERROR LOGO:", e)

        canvas.convert("RGB").save(output_path, "PNG")

    except Exception as e:
        print("ERROR PROCESANDO:", e)
        raise e


# ---------- RUTAS ----------
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
