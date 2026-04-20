import os
import requests
from flask import Flask, render_template, request, jsonify
from datetime import datetime

app = Flask(__name__)

# --- CONFIGURACIÓN ---
API_KEY = os.environ.get("REMOVE_BG_API_KEY", "").strip()

# Usamos rutas absolutas para evitar errores en servidores como Render
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
PROCESSED_FOLDER = os.path.join(BASE_DIR, "static", "processed")

# Asegurar que las carpetas existan al arrancar
for folder in [UPLOAD_FOLDER, PROCESSED_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)

@app.route('/')
def index():
    imagenes = []
    if os.path.exists(PROCESSED_FOLDER):
        # Listar archivos y filtrar solo imágenes
        archivos = [f for f in os.listdir(PROCESSED_FOLDER) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        # Ordenar por fecha de creación (los más nuevos primero)
        archivos.sort(key=lambda x: os.path.getmtime(os.path.join(PROCESSED_FOLDER, x)), reverse=True)
        imagenes = archivos
    
    return render_template('index.html', imagenes=imagenes)

@app.route('/remove-bg', methods=['POST'])
def remove_bg():
    if not API_KEY:
        return jsonify({"error": "Configuración de API ausente"}), 500

    file = request.files.get('file')
    if not file or file.filename == '':
        return jsonify({"error": "No se recibió archivo"}), 400

    try:
        # Llamada directa a la API de Remove.bg
        response = requests.post(
            'https://api.remove.bg/v1.0/removebg',
            files={'image_file': file},
            data={'size': 'auto'},
            headers={'X-Api-Key': API_KEY},
        )

        if response.status_code == requests.codes.ok:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # Limpiamos el nombre original para evitar problemas de ruta
            original_name = "".join(x for x in file.filename if x.isalnum() or x in "._- ")
            output_name = f"proevo_{timestamp}_{original_name}.png"
            output_path = os.path.join(PROCESSED_FOLDER, output_name)
            
            with open(output_path, 'wb') as out:
                out.write(response.content)
            
            return jsonify({"success": True, "url": f"/static/processed/{output_name}"}), 200
        else:
            return jsonify({"error": "Error de API: " + response.text}), response.status_code

    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
