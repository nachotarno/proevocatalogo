from flask import Flask, render_template, request, send_file, redirect, url_for
import os, io, time, sqlite3

from PIL import Image
from werkzeug.utils import secure_filename
from rembg import remove

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join("static", "uploads")
PROCESSED_DIR = os.path.join("static", "processed")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)

DB_PATH = "catalogo.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT,
            imagen TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def procesar(input_path, output_path):
    with open(input_path, "rb") as i:
        input_bytes = i.read()

    output_bytes = remove(input_bytes)

    with open(output_path, "wb") as o:
        o.write(output_bytes)

@app.route("/")
def index():
    conn = get_conn()
    productos = conn.execute("SELECT * FROM productos ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("index.html", productos=productos)

@app.route("/upload", methods=["POST"])
def upload():
    file = request.files["file"]

    filename = secure_filename(file.filename)
    path = os.path.join(UPLOAD_DIR, filename)

    file.save(path)

    output_name = f"proevo_{int(time.time())}.png"
    output_path = os.path.join(PROCESSED_DIR, output_name)

    try:
        procesar(path, output_path)

        conn = get_conn()
        conn.execute("INSERT INTO productos (nombre, imagen) VALUES (?, ?)", (filename, output_name))
        conn.commit()
        conn.close()

    except Exception as e:
        print("ERROR:", e)

    return redirect("/")

@app.route("/download/<filename>")
def download(filename):
    return send_file(os.path.join(PROCESSED_DIR, filename), as_attachment=True)

if __name__ == "__main__":
    app.run()
