from flask import Flask, render_template, request, send_file, redirect, url_for
import os
import time
import sqlite3

from werkzeug.utils import secure_filename

app = Flask(__name__)

# =========================
# PATHS
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join("static", "uploads")
PROCESSED_DIR = os.path.join("static", "processed")
DB_PATH = os.path.join(BASE_DIR, "catalogo.db")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)

# =========================
# DB
# =========================
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

# =========================
# PROCESO (REMOV BG GRATIS)
# =========================
def procesar(input_path, output_path):
    from rembg import remove  # 🔥 IMPORTANTE: se importa acá, no arriba

    with open(input_path, "rb") as i:
        input_bytes = i.read()

    output_bytes = remove(input_bytes)

    with open(output_path, "wb") as o:
        o.write(output_bytes)

# =========================
# ROUTES
# =========================
@app.route("/")
def index():
    conn = get_conn()
    productos = conn.execute("SELECT * FROM productos ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("index.html", productos=productos)

@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return redirect("/")

    file = request.files["file"]

    if file.filename == "":
        return redirect("/")

    filename = secure_filename(file.filename)
    path = os.path.join(UPLOAD_DIR, filename)

    file.save(path)

    output_name = f"proevo_{int(time.time())}.png"
    output_path = os.path.join(PROCESSED_DIR, output_name)

    try:
        procesar(path, output_path)

        conn = get_conn()
        conn.execute(
            "INSERT INTO productos (nombre, imagen) VALUES (?, ?)",
            (filename, output_name)
        )
        conn.commit()
        conn.close()

        # borrar original
        try:
            os.remove(path)
        except:
            pass

    except Exception as e:
        print("ERROR PROCESAR:", e)

    return redirect("/")

@app.route("/download/<filename>")
def download(filename):
    path = os.path.join(PROCESSED_DIR, filename)

    if not os.path.exists(path):
        return redirect("/")

    return send_file(path, as_attachment=True)

@app.route("/delete/<int:item_id>")
def delete(item_id):
    conn = get_conn()
    row = conn.execute("SELECT imagen FROM productos WHERE id=?", (item_id,)).fetchone()

    if row:
        path = os.path.join(PROCESSED_DIR, row["imagen"])
        if os.path.exists(path):
            try:
                os.remove(path)
            except:
                pass

    conn.execute("DELETE FROM productos WHERE id=?", (item_id,))
    conn.commit()
    conn.close()

    return redirect("/")

# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
