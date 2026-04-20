async function procesarImagen() {
    const fileInput = document.getElementById('fileInput');
    const btn = document.querySelector('button[onclick="procesarImagen()"]');
    const statusText = document.getElementById('fileNameDisplay');

    // 1. Validación de archivo
    if (!fileInput.files || fileInput.files.length === 0) {
        alert("Por favor, seleccioná primero la foto del repuesto.");
        return;
    }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    // 2. Feedback Visual (PROEVO Style)
    btn.disabled = true;
    btn.style.opacity = "0.7";
    btn.innerText = "QUITANDO FONDO...";
    statusText.innerText = "La IA de Proevo está trabajando...";

    try {
        // 3. Envío al servidor
        const response = await fetch('/remove-bg', {
            method: 'POST',
            body: formData
            // Nota: No se añade Header de Content-Type, el navegador lo hace solo al usar FormData
        });

        const result = await response.json();

        if (response.ok && result.success) {
            // 4. Éxito: Esperamos un momento para que Render registre el archivo
            statusText.innerText = "¡Imagen lista! Actualizando catálogo...";
            statusText.style.color = "#f59e0b"; // Color naranja Proevo
            
            setTimeout(() => {
                window.location.reload();
            }, 1500); 

        } else {
            // Manejo de errores de la API (ej: falta de créditos)
            console.error("Error del servidor:", result);
            alert("Error: " + (result.error || "No se pudo procesar la imagen."));
            resetBtn(btn, statusText);
        }

    } catch (error) {
        console.error("Error de conexión:", error);
        alert("No se pudo conectar con el servidor de Render. Reintentá en unos segundos.");
        resetBtn(btn, statusText);
    }
}

// Función auxiliar para resetear el botón si algo falla
function resetBtn(btn, statusText) {
    btn.disabled = false;
    btn.style.opacity = "1";
    btn.innerText = "PROCESAR IMAGEN";
    statusText.innerText = "Subir nuevo repuesto";
}

// Función para mostrar el nombre del archivo seleccionado en el diseño
function updateFileName() {
    const input = document.getElementById('fileInput');
    const display = document.getElementById('fileNameDisplay');
    if (input.files.length > 0) {
        display.innerText = input.files[0].name;
    }
}
