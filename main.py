import io
import os
import time

import requests
from flask import Flask, jsonify, render_template, request
from PIL import Image, ImageDraw, ImageFont
from werkzeug.utils import secure_filename

app = Flask(__name__)

API_KEY = os.environ.get("REMOVE_BG_API_KEY", "").strip()
PROCESSED_FOLDER = os.path.join("static", "processed")
os.makedirs(PROCESSED_FOLDER, exist_ok=True)


def make_white_transparent(image):
    image = image.convert("RGBA")
    pixels = []

    for red, green, blue, alpha in image.getdata():
        if red > 235 and green > 235 and blue > 235:
            pixels.append((255, 255, 255, 0))
        else:
            pixels.append((red, green, blue, alpha))

    image.putdata(pixels)
    return image


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/processed-images")
def processed_images():
    images = []

    for filename in os.listdir(PROCESSED_FOLDER):
        if filename.lower().endswith(".png"):
            file_path = os.path.join(PROCESSED_FOLDER, filename)
            images.append(
                {
                    "filename": filename,
                    "url": f"/static/processed/{filename}",
                    "created": os.path.getmtime(file_path),
                }
            )

    images.sort(key=lambda image: image["created"], reverse=True)
    return jsonify({"images": images})


@app.route("/remove-bg", methods=["POST"])
def remove_bg():
    if not API_KEY:
        return jsonify({"error": "Falta configurar la clave REMOVE_BG_API_KEY de remove.bg."}), 500

    if "image" not in request.files:
        return jsonify({"error": "No se recibió ninguna imagen."}), 400

    image = request.files["image"]
    filename = image.filename

    name_without_ext = os.path.splitext(filename)[0]

    try:
        response = requests.post(
            "https://api.remove.bg/v1.0/removebg",
            files={"image_file": image},
            data={"size": "auto"},
            headers={"X-Api-Key": API_KEY},
            timeout=60,
        )
    except requests.RequestException:
        return jsonify({"error": "No se pudo conectar con remove.bg. Intentá de nuevo."}), 502

    if response.status_code == 200:
        img = Image.open(io.BytesIO(response.content)).convert("RGBA")
        footer_height = max(90, int(img.height * 0.16))
        canvas = Image.new("RGBA", (img.width, img.height + footer_height), (0, 0, 0, 0))
        canvas.paste(img, ((canvas.width - img.width) // 2, 0), img)
        img = canvas

        try:
            logo = make_white_transparent(Image.open("static/logo.png"))

            logo_width = int(img.width * 0.15)
            ratio = logo_width / logo.width
            logo_height = int(logo.height * ratio)
            logo = logo.resize((logo_width, logo_height))

            position_logo = (img.width - logo.width - 20, 20)

            img.paste(logo, position_logo, logo)

        except Exception:
            print("⚠️ Logo no encontrado o error cargando logo")

        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype("arial.ttf", int(img.width * 0.04))
        except Exception:
            font = ImageFont.load_default()

        text = name_without_ext.upper()

        text_box = draw.textbbox((0, 0), text, font=font)
        text_width = text_box[2] - text_box[0]
        text_height = text_box[3] - text_box[1]

        text_position = ((img.width - text_width) // 2, img.height - footer_height + ((footer_height - text_height) // 2))

        shadow_position = (text_position[0] + 2, text_position[1] + 2)
        draw.text(
            shadow_position,
            text,
            fill=(0, 0, 0, 180),
            font=font,
        )

        draw.text(
            text_position,
            text,
            fill=(255, 255, 255, 255),
            font=font,
        )

        safe_name = secure_filename(name_without_ext) or "imagen"
        processed_filename = f"proevo_{safe_name}_{int(time.time())}.png"
        output_path = os.path.join(PROCESSED_FOLDER, processed_filename)
        img.save(output_path)

        return jsonify(
            {
                "filename": processed_filename,
                "url": f"/static/processed/{processed_filename}",
            }
        )

    try:
        error_data = response.json()
        message = error_data.get("errors", [{}])[0].get("title", "Error procesando imagen")
    except ValueError:
        message = response.text or "Error procesando imagen"

    return jsonify({"error": message}), response.status_code


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
