async function procesarImagen() {
    const fileInput = document.getElementById('fileInput');
    const btn = document.querySelector('button[onclick="procesarImagen()"]');
    const statusText = document.getElementById('fileNameDisplay');

    if (!fileInput.files[0]) {
        alert("Por favor, selecciona una imagen primero.");
        return;
    }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    // Cambiamos el estado del botón
    btn.disabled = true;
    btn.innerText = "PROCESANDO...";
    statusText.innerText = "La IA está trabajando...";

    try {
        const response = await fetch('/remove-bg', {
            method: 'POST',
            body: formData
        });

        if (response.ok) {
            const data = await response.json();
            alert("¡Imagen procesada con éxito!");
            location.reload(); // Recarga para ver la nueva imagen en el catálogo
        } else {
            alert("Error en el servidor. Revisa los logs de Render.");
        }
    } catch (error) {
        console.error("Error:", error);
        alert("No se pudo conectar con el servidor.");
    } finally {
        btn.disabled = false;
        btn.innerText = "PROCESAR IMAGEN";
    }
}

// Función para actualizar el nombre del archivo al seleccionar
function updateFileName() {
    const input = document.getElementById('fileInput');
    const display = document.getElementById('fileNameDisplay');
    if (input.files.length > 0) {
        display.innerText = input.files[0].name;
    }
}
