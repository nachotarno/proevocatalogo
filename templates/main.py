import os
from flask import Flask, render_template, request, jsonify
from removebg import RemoveBg
from datetime import datetime

app = Flask(__name__)

# --- CONFIGURACIÓN ---
# Asegúrate de tener esta variable en Render -> Environment Variables
API_KEY = os.environ.get("REMOVE_BG_API_KEY", "").strip()

# Carpetas de almacenamiento
UPLOAD_FOLDER = os.path.join("static", "uploads")
PROCESSED_FOLDER = os.path.join("static", "processed")

# Crear carpetas si no existen
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

@app.route('/')
def index():
    # Escanea la carpeta processed para mostrar las imágenes en el catálogo
    imagenes = []
    if os.path.exists(PROCESSED_FOLDER):
        imagenes = [f for f in os.listdir(PROCESSED_FOLDER) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        # Ordenar por fecha de creación (más nuevas primero)
        imagenes.sort(key=lambda x: os.path.getmtime(os.path.join(PROCESSED_FOLDER, x)), reverse=True)
    
    return render_template('index.html', imagenes=imagenes)

@app.route('/remove-bg', methods=['POST'])
def remove_bg():
    # 1. Validación de API Key
    if not API_KEY:
        print("DEBUG ERROR: No se encontró REMOVE_BG_API_KEY en las variables de entorno.")
        return jsonify({"error": "Falta la configuración de API en el servidor"}), 500

    # 2. Verificación del archivo recibido
    if 'file' not in request.files:
        print("DEBUG ERROR: El campo 'file' no llegó en la petición.")
        return jsonify({"error": "No se recibió ningún archivo"}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        print("DEBUG ERROR: El usuario no seleccionó ningún archivo.")
        return jsonify({"error": "Archivo sin nombre"}), 400

    try:
        # 3. Guardar archivo original temporalmente
        filename = file.filename
        input_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(input_path)
        print(f"DEBUG: Imagen original guardada en {input_path}")

        # 4. Procesamiento con Remove.bg
        # Generamos un nombre único para evitar conflictos
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_name = f"proevo_{timestamp}_{filename.split('.')[0]}.png"
        output_path = os.path.join(PROCESSED_FOLDER, output_name)

        rmbg = RemoveBg(API_KEY, "error.log")
        rmbg.remove_background_from_img_file(input_path, out_path=output_path)

        # Verificar si se creó el archivo
        if os.path.exists(output_path):
            print(f"DEBUG: Procesamiento exitoso. Imagen guardada en {output_path}")
            # Opcional: Borrar la imagen original para no llenar el disco
            # os.remove(input_path) 
            return jsonify({
                "success": True, 
                "message": "Imagen procesada",
                "url": f"/{output_path}"
            }), 200
        else:
            print("DEBUG ERROR: El proceso terminó pero no se generó el archivo de salida.")
            return jsonify({"error": "Error al generar la imagen transparente"}), 500

    except Exception as e:
        print(f"DEBUG EXCEPTION: {str(e)}")
        return jsonify({"error": f"Error interno: {str(e)}"}), 500

if __name__ == '__main__':
    # Usar puerto de Render si está disponible
    port = int(os.environ.get("PORT", 5000))RT", 5000)))
