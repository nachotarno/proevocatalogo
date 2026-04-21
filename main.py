def procesar(path, output):
    try:
        img_bytes = remove_bg(path)

        # ✅ corregir rotación EXIF
        prod = Image.open(io.BytesIO(img_bytes))
        prod = ImageOps.exif_transpose(prod).convert("RGBA")

        # ✅ recorte automático
        bbox = prod.getbbox()
        if bbox:
            prod = prod.crop(bbox)

        # ✅ canvas transparente
        W, H = 1000, 1000
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))

        # ✅ resize compatible (fix Render)
        max_size = 700
        try:
            resample = Image.Resampling.LANCZOS
        except:
            resample = Image.LANCZOS

        prod.thumbnail((max_size, max_size), resample)

        # ✅ centrado real
        x = (W - prod.width) // 2
        y = (H - prod.height) // 2

        # ✅ sombra pro
        shadow = Image.new("RGBA", (prod.width, prod.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(shadow)

        draw.ellipse(
            (
                int(prod.width * 0.15),
                int(prod.height * 0.75),
                int(prod.width * 0.85),
                int(prod.height * 0.95)
            ),
            fill=(0, 0, 0, 120)
        )

        shadow = shadow.filter(ImageFilter.GaussianBlur(30))

        canvas.paste(shadow, (x, y + int(prod.height * 0.1)), shadow)

        # ✅ producto
        canvas.paste(prod, (x, y), prod)

        # ✅ LOGO ARRIBA DERECHA (fix seguro)
        logo_path = os.path.join(BASE_DIR, "static/logo.png")

        if os.path.exists(logo_path):
            try:
                logo = Image.open(logo_path).convert("RGBA")

                logo.thumbnail((200, 80), resample)

                lx = W - logo.width - 20
                ly = 20

                canvas.paste(logo, (lx, ly), logo)
            except Exception as e:
                print("ERROR LOGO:", e)

        # ✅ guardar final
        canvas.save(output, "PNG")

    except Exception as e:
        print("ERROR PROCESAR:", e)
