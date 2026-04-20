import os
import requests
from flask import Flask, render_template, request, jsonify, send_from_directory
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)

API_KEY = os.environ.get("REMOVE_BG_API_KEY", "").strip()
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
PROCESSED_FOLDER = os.path.join(BASE_DIR, "static", "processed")
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

@app.route('/')
def index():
    imagenes = []
    if os.path.exists(PROCESSED_FOLDER):
        archivos = [f for f in os.listdir(PROCESSED_FOLDER) if f.lower().endswith('.png')]
        archivos.sort(key=lambda x: os.path.getmtime(os.path.join(PROCESSED_FOLDER, x)), reverse=True)
        imagenes = archivos
    return render_template('index.html', imagenes=imagenes)

@app.route('/remove-bg', methods=['POST'])
def remove_bg():
    file = request.files.get('file')
    if not file or not API_KEY:
        return jsonify({"error": "Falta archivo o API Key"}), 400

    try:
        # 1. Quitar fondo con la API
        response = requests.post(
            'https://api.remove.bg/v1.0/removebg',
            files={'image_file': file},
            data={'size': 'auto'},
            headers={'X-Api-Key': API_KEY},
        )

        if response.status_code == requests.codes.ok:
            # 2. Procesar la imagen con Pillow para agregar Logo y Texto
            img = Image.open(requests.get(response.url, stream=True).raw if hasattr(response, 'url') else io.BytesIO(response.content)).convert("RGBA")
            
            # Crear un lienzo blanco cuadrado (estilo catálogo)
            size = max(img.size) + 200
            canvas = Image.new("RGBA", (size, size), (255, 255, 255, 255))
            
            # Pegar el repuesto en el centro
            offset = ((size - img.width) // 2, (size - img.height) // 2)
            canvas.paste(img, offset, img)
            
            # Dibujar Texto (Simulación de Logo y Descripción)
            draw = ImageDraw.Draw(canvas)
            # Nota: En Render es difícil cargar fuentes custom, usamos la default
            draw.text((size-150, 40), "PROEVO", fill=(100, 100, 100, 255))
            draw.text((size//2 - 100, size-60), file.filename[:40], fill=(50, 50, 50, 255))

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_name = f"proevo_{timestamp}.png"
            output_path = os.path.join(PROCESSED_FOLDER, output_name)
            
            canvas.save(output_path, "PNG")
            return jsonify({"success": True, "url": f"/static/processed/{output_name}"}), 200
        
        return jsonify({"error": "Error en API"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Ruta para forzar la descarga
@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(PROCESSED_FOLDER, filename, as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
