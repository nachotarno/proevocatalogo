def procesar(path, output):
    try:
        from PIL import ImageOps

        img_bytes = remove_bg(path)

        # 🔥 corregir rotación (EXIF)
        prod = Image.open(io.BytesIO(img_bytes))
        prod = ImageOps.exif_transpose(prod).convert("RGBA")

        # 🔥 recorte inteligente
        bbox = prod.getbbox()
        if bbox:
            prod = prod.crop(bbox)

        # 🔥 canvas transparente
        W, H = 1000, 1000
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))

        # 🔥 escalado inteligente
        max_size = 700
        prod.thumbnail((max_size, max_size), Image.LANCZOS)

        # 🔥 centrado REAL (no fijo)
        x = (W - prod.width) // 2
        y = (H - prod.height) // 2

        # 🔥 sombra pro (tipo e-commerce)
        shadow = Image.new("RGBA", (prod.width, prod.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(shadow)

        draw.ellipse(
            (
                prod.width * 0.15,
                prod.height * 0.75,
                prod.width * 0.85,
                prod.height * 0.95
            ),
            fill=(0, 0, 0, 120)
        )

        shadow = shadow.filter(ImageFilter.GaussianBlur(30))

        # posición sombra
        canvas.paste(shadow, (x, y + int(prod.height * 0.1)), shadow)

        # 🔥 pegar producto
        canvas.paste(prod, (x, y), prod)

        # 🔥 LOGO ARRIBA DERECHA
        logo_path = os.path.join(BASE_DIR, "static/logo.png")

        if os.path.exists(logo_path):
            logo = Image.open(logo_path).convert("RGBA")

            # tamaño proporcional
            logo.thumbnail((200, 80), Image.LANCZOS)

            lx = W - logo.width - 20
            ly = 20

            canvas.paste(logo, (lx, ly), logo)

        # guardar PNG transparente
        canvas.save(output, "PNG")

    except Exception as e:
        print("ERROR PROCESAR:", e)
