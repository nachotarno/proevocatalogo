async function procesarImagen() {
    const fileInput = document.getElementById('fileInput');
    const btn = document.querySelector('button[onclick="procesarImagen()"]');
    const statusText = document.getElementById('fileNameDisplay');

    if (!fileInput.files || fileInput.files.length === 0) {
        alert("Primero seleccioná una foto de un repuesto.");
        return;
    }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    // UI Feedback
    btn.disabled = true;
    btn.style.opacity = "0.5";
    btn.innerText = "QUITANDO FONDO...";
    statusText.innerText = "Procesando para Proevo...";

    try {
        const response = await fetch('/remove-bg', {
            method: 'POST',
            body: formData
            // IMPORTANTE: No pongas 'Content-Type' manual, deja que el navegador lo haga
        });

        const result = await response.json();

        if (response.ok && result.success) {
            alert("¡Repuesto listo!");
            window.location.reload(); 
        } else {
            console.error("Error del servidor:", result);
            alert("Error: " + (result.error || "Algo falló en el servidor."));
        }
    } catch (error) {
        console.error("Error de conexión:", error);
        alert("No se pudo conectar con el servidor de Render.");
    } finally {
        btn.disabled = false;
        btn.style.opacity = "1";
        btn.innerText = "PROCESAR IMAGEN";
    }
}

function updateFileName() {
    const input = document.getElementById('fileInput');
    const display = document.getElementById('fileNameDisplay');
    if (input.files.length > 0) {
        display.innerText = input.files[0].name;
    }
}
