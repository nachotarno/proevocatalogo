import os
import requests
from flask import Flask, render_template, request, jsonify
from datetime import datetime

app = Flask(__name__)

API_KEY = os.environ.get("REMOVE_BG_API_KEY", "").strip()
UPLOAD_FOLDER = "static/uploads"
PROCESSED_FOLDER = "static/processed"

for folder in [UPLOAD_FOLDER, PROCESSED_FOLDER]:
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
    file = request.files.get('file')
    if not file or not API_KEY:
        return jsonify({"error": "Falta archivo o API Key"}), 400

    try:
        # Llamada directa a la API
        response = requests.post(
            'https://api.remove.bg/v1.0/removebg',
            files={'image_file': file},
            data={'size': 'auto'},
            headers={'X-Api-Key': API_KEY},
        )

        if response.status_code == requests.codes.ok:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_name = f"proevo_{timestamp}.png"
            output_path = os.path.join(PROCESSED_FOLDER, output_name)
            
            with open(output_path, 'wb') as out:
                out.write(response.content)
            
            return jsonify({"success": True, "url": f"/{output_path}"}), 200
        else:
            return jsonify({"error": response.text}), response.status_code

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
