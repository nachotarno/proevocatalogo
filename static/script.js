let imagenesProcesadas = [];
let vistaCatalogo = "grid";

function scrollToScanner() {
  document.getElementById("scanner").scrollIntoView({ behavior: "smooth" });
}

function scrollToImages() {
  document.getElementById("imagenes").scrollIntoView({ behavior: "smooth" });
  cargarImagenes();
}

function nombreVisible(filename) {
  return filename
    .replace(/^proevo_/, "")
    .replace(/_\d+\.png$/i, "")
    .replace(/_/g, " ")
    .trim()
    .toUpperCase();
}

function codigoVisible(filename) {
  const limpio = nombreVisible(filename);
  return limpio.split(" - ")[0] || "ITEM";
}

function categoriaVisible(filename) {
  const nombre = filename.toLowerCase();
  if (nombre.includes("sensor") || nombre.includes("contact") || nombre.includes("elect")) return "Eléctrico";
  if (nombre.includes("buje") || nombre.includes("rodamiento") || nombre.includes("arandela")) return "Transmisión";
  if (nombre.includes("bloque") || nombre.includes("motor")) return "Motor";
  return "Catálogo";
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    '"': "&quot;"
  }[char]));
}

function setStatus(message, isError = false) {
  const status = document.getElementById("processingStatus");
  status.innerText = message;
  status.classList.toggle("hidden", !message);
  status.classList.toggle("text-red-400", isError);
  status.classList.toggle("text-zinc-400", !isError);
}

function setSelectedFileName() {
  const input = document.getElementById("fileInput");
  const label = document.getElementById("fileNameDisplay");
  label.innerText = input.files[0] ? input.files[0].name : "Arrastrá una imagen o hacé clic";
}

async function procesarImagen() {
  const input = document.getElementById("fileInput");
  const file = input.files[0];
  const btn = document.getElementById("btnProcesar");
  const resultado = document.getElementById("resultado");
  const resultadoPanel = document.getElementById("resultadoPanel");

  if (!file) {
    setStatus("Seleccioná una imagen primero.", true);
    return;
  }

  const formData = new FormData();
  formData.append("image", file);

  btn.innerText = "Procesando...";
  btn.disabled = true;
  setStatus("Quitando fondo, agregando marca PROEVO y guardando en catálogo...");
  document.getElementById("estadoIa").innerText = "Procesando";

  try {
    const response = await fetch("/remove-bg", {
      method: "POST",
      body: formData
    });

    if (!response.ok) {
      let message = "Error procesando imagen";
      try {
        const data = await response.json();
        message = data.error || message;
      } catch {
        message = await response.text();
      }
      setStatus(message, true);
      return;
    }

    const data = await response.json();
    const url = data.url;

    resultado.src = url;
    resultadoPanel.classList.remove("hidden");

    const descargar = document.getElementById("descargar");
    descargar.href = url;
    descargar.download = data.filename || "imagen.png";

    setStatus("Imagen procesada y agregada al archivo visual.");
    await cargarImagenes();
    scrollToImages();
  } catch {
    setStatus("No se pudo procesar la imagen. Revisá tu conexión e intentá de nuevo.", true);
  } finally {
    btn.innerText = "Procesar";
    btn.disabled = false;
    document.getElementById("estadoIa").innerText = "Estable";
  }
}

async function cargarImagenes() {
  const vacio = document.getElementById("catalogoVacio");

  try {
    const response = await fetch("/processed-images");
    const data = await response.json();
    imagenesProcesadas = data.images || [];

    document.getElementById("statTotal").innerText = imagenesProcesadas.length;
    filtrarCatalogo();
    vacio.classList.toggle("hidden", imagenesProcesadas.length > 0);
  } catch {
    setStatus("No se pudieron cargar las imágenes procesadas.", true);
  }
}

function filtrarCatalogo() {
  const termino = document.getElementById("buscarCatalogo").value.toLowerCase();
  const categoria = document.getElementById("filtroCategoria").value;
  const filtradas = imagenesProcesadas.filter((image) => {
    const nombre = image.filename.toLowerCase();
    const categoriaImagen = categoriaVisible(image.filename);
    return nombre.includes(termino) && (!categoria || categoriaImagen === categoria);
  });

  renderCatalogo(filtradas);
  document.getElementById("catalogoVacio").classList.toggle("hidden", filtradas.length > 0);
}

function setViewMode(mode) {
  vistaCatalogo = mode;
  const gridBtn = document.getElementById("btnGrid");
  const listBtn = document.getElementById("btnList");
  gridBtn.className = mode === "grid" ? "p-2 rounded-md bg-zinc-800 text-white transition-colors" : "p-2 rounded-md text-zinc-500 hover:text-zinc-300 transition-colors";
  listBtn.className = mode === "list" ? "p-2 rounded-md bg-zinc-800 text-white transition-colors" : "p-2 rounded-md text-zinc-500 hover:text-zinc-300 transition-colors";
  renderCatalogo(getFilteredImages());
}

function getFilteredImages() {
  const termino = document.getElementById("buscarCatalogo").value.toLowerCase();
  const categoria = document.getElementById("filtroCategoria").value;
  return imagenesProcesadas.filter((image) => {
    const nombre = image.filename.toLowerCase();
    const categoriaImagen = categoriaVisible(image.filename);
    return nombre.includes(termino) && (!categoria || categoriaImagen === categoria);
  });
}

function renderCatalogo(images) {
  const catalogo = document.getElementById("catalogoImagenes");
  catalogo.innerHTML = "";
  catalogo.className = vistaCatalogo === "grid"
    ? "grid gap-6 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4"
    : "catalog-list grid gap-5 grid-cols-1";
  document.getElementById("statVisibles").innerText = images.length;
  document.getElementById("catalogoResumen").innerText = `Mostrando ${images.length} de ${imagenesProcesadas.length} imágenes procesadas con fondo transparente`;

  images.forEach((image) => {
    const nombre = escapeHtml(nombreVisible(image.filename));
    const categoria = escapeHtml(categoriaVisible(image.filename));
    const codigo = escapeHtml(codigoVisible(image.filename));
    const filename = escapeHtml(image.filename);
    const url = escapeHtml(image.url);

    const card = document.createElement("article");
    card.className = "group relative bg-[#161616] border border-zinc-800 hover:border-zinc-600 rounded-2xl overflow-hidden transition-all duration-500 hover:-translate-y-1 hover:shadow-2xl hover:shadow-orange-900/10";
    card.innerHTML = `
      <div class="aspect-square p-8 flex items-center justify-center relative overflow-hidden bg-gradient-to-b from-zinc-800/20 to-transparent">
        <div class="absolute inset-0 opacity-[0.15] grid-texture"></div>
        <img src="${url}" alt="${filename}" class="w-full h-full object-contain relative z-10 transition-transform duration-700 group-hover:scale-110 drop-shadow-2xl">
        <div class="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity duration-300 z-20 flex items-center justify-center backdrop-blur-[2px]">
          <a href="${url}" download="${filename}" class="bg-orange-600 hover:bg-orange-500 text-white flex items-center gap-2 px-6 py-3 rounded-full font-bold text-sm tracking-wide transform translate-y-4 group-hover:translate-y-0 transition-all duration-300 shadow-xl">Descargar PNG</a>
        </div>
      </div>
      <div class="p-5 border-t border-zinc-800 bg-[#111111]">
        <div class="flex justify-between items-start gap-4 mb-3">
          <h3 class="font-bold text-zinc-100 text-sm leading-snug">${nombre}</h3>
          <span class="px-2 py-1 bg-zinc-800 text-zinc-300 text-[10px] font-black uppercase tracking-wider rounded border border-zinc-700 whitespace-nowrap">${codigo.slice(0, 8)}</span>
        </div>
        <div class="flex items-center justify-between gap-4">
          <span class="text-xs font-medium text-zinc-500">${categoria}</span>
          <span class="flex items-center gap-1.5 text-[10px] font-bold text-emerald-500 uppercase tracking-widest"><span class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>Procesado</span>
        </div>
      </div>
    `;
    catalogo.appendChild(card);
  });
}

function configureDropzone() {
  const zone = document.getElementById("uploadZone");
  const input = document.getElementById("fileInput");
  input.addEventListener("change", setSelectedFileName);

  ["dragenter", "dragover"].forEach((eventName) => {
    zone.addEventListener(eventName, (event) => {
      event.preventDefault();
      zone.classList.add("ring-2", "ring-orange-500", "rounded-lg");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    zone.addEventListener(eventName, (event) => {
      event.preventDefault();
      zone.classList.remove("ring-2", "ring-orange-500", "rounded-lg");
    });
  });

  zone.addEventListener("drop", (event) => {
    const files = event.dataTransfer.files;
    if (files.length) {
      input.files = files;
      setSelectedFileName();
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  configureDropzone();
  cargarImagenes();
});
