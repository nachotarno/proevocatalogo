import os
from flask import Flask, render_template, request, jsonify
from removebg import RemoveBg
from datetime import datetime

app = Flask(__name__)

# --- CONFIGURACIÓN ---
API_KEY = os.environ.get("REMOVE_BG_API_KEY", "").strip()
UPLOAD_FOLDER = "static/uploads"
PROCESSED_FOLDER = "static/processed"

# Asegurar carpetas con rutas absolutas para Render
for folder in [UPLOAD_FOLDER, PROCESSED_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)

@app.route('/')
def index():
    imagenes = []
    if os.path.exists(PROCESSED_FOLDER):
        imagenes = [f for f in os.listdir(PROCESSED_FOLDER) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        imagenes.sort(key=lambda x: os.path.getmtime(os.path.join(PROCESSED_FOLDER, x)), reverse=True)
    return render_template('index.html', imagenes=imagenes)

@app.route('/remove-bg', methods=['POST'])
def remove_bg():
    # Log para ver qué llega (ver en Logs de Render)
    print("DEBUG: Petición recibida en /remove-bg")
    
    # 1. Intentar obtener el archivo de cualquier forma posible
    file = None
    if 'file' in request.files:
        file = request.files['file']
    elif len(request.files) > 0:
        file = list(request.files.values())[0]

    if not file or file.filename == '':
        return jsonify({"error": "No se recibió archivo"}), 400

    if not API_KEY:
        return jsonify({"error": "Falta API Key en Render"}), 500

    try:
        # 2. Guardar y Procesar
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        input_path = os.path.join(UPLOAD_FOLDER, f"temp_{timestamp}_{file.filename}")
        file.save(input_path)

        output_name = f"proevo_{timestamp}.png"
        output_path = os.path.join(PROCESSED_FOLDER, output_name)

        rmbg = RemoveBg(API_KEY, "error.log")
        rmbg.remove_background_from_img_file(input_path, out_path=output_path)

        # 3. Respuesta exitosa
        if os.path.exists(output_path):
            return jsonify({"success": True, "url": f"/{output_path}"}), 200
        else:
            return jsonify({"error": "La IA no generó el archivo"}), 500

    except Exception as e:
        print(f"ERROR: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
