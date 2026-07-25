let sessionId = null;

const pantallaInicio = document.getElementById("pantalla-inicio");
const pantallaChat = document.getElementById("pantalla-chat");
const mensajesDiv = document.getElementById("mensajes");
const inputTelefono = document.getElementById("input-telefono");
const inputMensaje = document.getElementById("input-mensaje");
const resumenVacio = document.getElementById("resumen-vacio");
const resumenContenido = document.getElementById("resumen-contenido");
const btnEnviarAsesor = document.getElementById("btn-enviar-asesor");
const estadoEnvio = document.getElementById("estado-envio");

const RETARDO_RESPUESTA_MS = 3000;

function agregarBurbuja(texto, quien) {
  const div = document.createElement("div");
  div.className = `burbuja ${quien}`;
  div.textContent = texto;
  mensajesDiv.appendChild(div);
  mensajesDiv.scrollTop = mensajesDiv.scrollHeight;
}

function mostrarEscribiendo() {
  const div = document.createElement("div");
  div.className = "burbuja bot escribiendo";
  div.id = "burbuja-escribiendo";
  div.innerHTML = "<span></span><span></span><span></span>";
  mensajesDiv.appendChild(div);
  mensajesDiv.scrollTop = mensajesDiv.scrollHeight;
}

function ocultarEscribiendo() {
  document.getElementById("burbuja-escribiendo")?.remove();
}

function esperar(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function agregarBurbujaBotConRetardo(texto) {
  mostrarEscribiendo();
  await esperar(RETARDO_RESPUESTA_MS);
  ocultarEscribiendo();
  agregarBurbuja(texto, "bot");
}

async function iniciar() {
  const telefono = inputTelefono.value.trim();
  if (!telefono) return;

  const resp = await fetch("/api/iniciar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ telefono }),
  });
  const data = await resp.json();
  sessionId = data.session_id;

  pantallaInicio.classList.add("oculto");
  pantallaChat.classList.remove("oculto");
  await agregarBurbujaBotConRetardo(data.mensaje);
}

async function enviarMensaje() {
  const texto = inputMensaje.value.trim();
  if (!texto || !sessionId) return;
  inputMensaje.value = "";
  agregarBurbuja(texto, "user");

  const resp = await fetch("/api/mensaje", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, texto }),
  });
  const data = await resp.json();
  await agregarBurbujaBotConRetardo(data.mensaje);

  if (data.finalizada) {
    await cargarResumen();
    if (data.envio_asesor) {
      mostrarEstadoEnvio(data.envio_asesor);
    }
  }
}

function mostrarEstadoEnvio({ enviado, detalle }) {
  estadoEnvio.textContent = enviado ? `✅ Correo enviado automáticamente al asesor — ${detalle}` : `⚠️ ${detalle}`;
  btnEnviarAsesor.textContent = enviado ? "Reenviar correo al asesor" : "Reintentar envío al asesor";
}

async function cargarResumen() {
  const resp = await fetch(`/api/resumen/${sessionId}`);
  const { asunto, cuerpo, enviado_al_asesor } = await resp.json();

  resumenVacio.classList.add("oculto");
  resumenContenido.classList.remove("oculto");
  btnEnviarAsesor.classList.remove("oculto");
  resumenContenido.textContent = `Asunto: ${asunto}\n\n${cuerpo}`;
  btnEnviarAsesor.textContent = enviado_al_asesor ? "Reenviar correo al asesor" : "Enviar correo al asesor";
}

async function enviarAAsesor() {
  btnEnviarAsesor.disabled = true;
  estadoEnvio.textContent = "Enviando...";
  const resp = await fetch(`/api/enviar-asesor/${sessionId}`, { method: "POST" });
  const data = await resp.json();
  mostrarEstadoEnvio(data);
  btnEnviarAsesor.disabled = false;
}

document.getElementById("btn-iniciar").addEventListener("click", iniciar);
document.getElementById("btn-enviar").addEventListener("click", enviarMensaje);
inputMensaje.addEventListener("keydown", (e) => { if (e.key === "Enter") enviarMensaje(); });
inputTelefono.addEventListener("keydown", (e) => { if (e.key === "Enter") iniciar(); });
btnEnviarAsesor.addEventListener("click", enviarAAsesor);

// ---------- Widget de chat flotante ----------
const ventanaChat = document.getElementById("ventana-chat");
const btnChatFlotante = document.getElementById("btn-chat-flotante");

function abrirChat() {
  ventanaChat.classList.remove("oculto");
  btnChatFlotante.classList.add("oculto");
  (pantallaChat.classList.contains("oculto") ? inputTelefono : inputMensaje).focus();
}

function cerrarChat() {
  ventanaChat.classList.add("oculto");
  btnChatFlotante.classList.remove("oculto");
}

btnChatFlotante.addEventListener("click", abrirChat);
document.getElementById("btn-cerrar-chat").addEventListener("click", cerrarChat);
document.getElementById("btn-abrir-chat-nav").addEventListener("click", abrirChat);
document.getElementById("btn-abrir-chat-hero").addEventListener("click", abrirChat);

// ---------- Catalogo de proyectos (vitrina) ----------
async function cargarProyectos() {
  const grid = document.getElementById("proyectos-grid");
  const sub = document.querySelector(".proyectos-sub");
  try {
    const resp = await fetch("/api/proyectos");
    const proyectos = await resp.json();
    sub.textContent = `${proyectos.length} proyectos disponibles en la red Colsubsidio.`;
    grid.innerHTML = proyectos
      .map(
        (p) => `
        <article class="proyecto-card">
          <span class="segmento">${p.segmento}</span>
          <h3>${p.nombre}</h3>
          <div class="ciudad">${p.ciudad} · ${p.categoria}</div>
          <ul class="amenities">${p.amenities.map((a) => `<li>${a}</li>`).join("")}</ul>
        </article>`
      )
      .join("");
  } catch (e) {
    sub.textContent = "No se pudo cargar el catálogo de proyectos.";
  }
}

cargarProyectos();
