let sessionId = null;
let sesionFinalizada = false;
let usuarioEncontrado = true;
let esperandoRespuesta = false;
let timerAvisoInactividad = null;
let timerCierreInactividad = null;

const pantallaInicio = document.getElementById("pantalla-inicio");
const pantallaChat = document.getElementById("pantalla-chat");
const mensajesDiv = document.getElementById("mensajes");
const inputTelefono = document.getElementById("input-telefono");
const inputMensaje = document.getElementById("input-mensaje");
const btnEnviarMensaje = document.getElementById("btn-enviar");
const resumenVacio = document.getElementById("resumen-vacio");
const resumenContenido = document.getElementById("resumen-contenido");
const btnEnviarAsesor = document.getElementById("btn-enviar-asesor");
const estadoEnvio = document.getElementById("estado-envio");
const btnFinalizarChat = document.getElementById("btn-finalizar-chat");
const barraChatInput = document.getElementById("barra-chat-input");
const barraChatFinalizado = document.getElementById("barra-chat-finalizado");
const btnNuevaConversacion = document.getElementById("btn-nueva-conversacion");

const RETARDO_MINIMO_MS = 700;
const AVISO_INACTIVIDAD_MS = 2 * 60 * 1000;
const CIERRE_INACTIVIDAD_MS = 3 * 60 * 1000;
const MENSAJE_AVISO_INACTIVIDAD =
  "¿Sigues ahí? Si no recibo respuesta en un minuto voy a cerrar esta conversación por inactividad.";

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

// Muestra la burbuja de "escribiendo" DESDE que arranca la peticion (no
// despues de que ya llego la respuesta), para que la espera real del LLM
// tenga retroalimentacion visible. Si la respuesta llega muy rapido, se
// completa un minimo de RETARDO_MINIMO_MS para que la animacion no parpadee;
// si tarda mas (ej. el turno de recomendacion, que arma un prompt mas largo),
// el usuario ve "escribiendo..." durante toda la espera real, sin sumarle
// un retardo artificial encima. Mientras tanto, el input queda bloqueado
// para que no se puedan mandar mensajes mientras el agente "esta pensando".
async function pedirConIndicadorEscribiendo(peticion) {
  esperandoRespuesta = true;
  inputMensaje.disabled = true;
  btnEnviarMensaje.disabled = true;
  mostrarEscribiendo();
  const inicio = Date.now();
  const data = await peticion();
  const transcurrido = Date.now() - inicio;
  if (transcurrido < RETARDO_MINIMO_MS) {
    await esperar(RETARDO_MINIMO_MS - transcurrido);
  }
  ocultarEscribiendo();
  esperandoRespuesta = false;
  if (!sesionFinalizada) {
    inputMensaje.disabled = false;
    btnEnviarMensaje.disabled = false;
  }
  return data;
}

async function iniciar() {
  const telefono = inputTelefono.value.trim();
  if (!telefono) return;

  pantallaInicio.classList.add("oculto");
  pantallaChat.classList.remove("oculto");
  btnFinalizarChat.classList.remove("oculto");

  const data = await pedirConIndicadorEscribiendo(() =>
    fetch("/api/iniciar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ telefono }),
    }).then((r) => r.json())
  );
  sessionId = data.session_id;
  sesionFinalizada = false;
  usuarioEncontrado = data.usuario_encontrado;
  agregarBurbuja(data.mensaje, "bot");
  reiniciarTemporizadorInactividad();
}

async function enviarMensaje() {
  const texto = inputMensaje.value.trim();
  if (!texto || !sessionId || sesionFinalizada || esperandoRespuesta) return;
  inputMensaje.value = "";
  agregarBurbuja(texto, "user");
  reiniciarTemporizadorInactividad();

  const data = await pedirConIndicadorEscribiendo(() =>
    fetch("/api/mensaje", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, texto }),
    }).then((r) => r.json())
  );
  agregarBurbuja(data.mensaje, "bot");

  if (data.finalizada) {
    if (!usuarioEncontrado) {
      // no se encontraron datos del usuario: el mensaje que se acaba de
      // mostrar ya es la despedida (no hay recomendacion ni fue el usuario
      // quien pidio cerrar), asi que se cierra de inmediato en vez de
      // esperar los 5 min de inactividad -- esa espera solo aplica a los
      // mensajes previos a la despedida.
      sesionFinalizada = true;
      limpiarTemporizadoresInactividad();
      bloquearChat();
    }
    await cargarResumen();
    if (data.envio_asesor) {
      mostrarEstadoEnvio(data.envio_asesor);
    }
  }
}

// ---------- Finalizar conversacion (boton manual o inactividad) ----------
function limpiarTemporizadoresInactividad() {
  clearTimeout(timerAvisoInactividad);
  clearTimeout(timerCierreInactividad);
}

function reiniciarTemporizadorInactividad() {
  limpiarTemporizadoresInactividad();
  if (sesionFinalizada || !sessionId) return;
  timerAvisoInactividad = setTimeout(() => {
    agregarBurbuja(MENSAJE_AVISO_INACTIVIDAD, "bot");
  }, AVISO_INACTIVIDAD_MS);
  timerCierreInactividad = setTimeout(() => {
    finalizarConversacion("inactividad");
  }, CIERRE_INACTIVIDAD_MS);
}

async function finalizarConversacion(motivo) {
  if (sesionFinalizada || !sessionId) return;
  sesionFinalizada = true;
  limpiarTemporizadoresInactividad();

  const data = await pedirConIndicadorEscribiendo(() =>
    fetch(`/api/finalizar/${sessionId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ motivo }),
    }).then((r) => r.json())
  );
  agregarBurbuja(data.mensaje, "bot");
  bloquearChat();
  await cargarResumen();
  if (data.envio_asesor) {
    mostrarEstadoEnvio(data.envio_asesor);
  }
}

function bloquearChat() {
  inputMensaje.disabled = true;
  btnEnviarMensaje.disabled = true;
  btnFinalizarChat.classList.add("oculto");
  barraChatInput.classList.add("oculto");
  barraChatFinalizado.classList.remove("oculto");
}

function reiniciarChatCompleto() {
  limpiarTemporizadoresInactividad();
  sesionFinalizada = false;
  usuarioEncontrado = true;
  sessionId = null;
  mensajesDiv.innerHTML = "";
  inputTelefono.value = "";
  inputMensaje.disabled = false;
  btnEnviarMensaje.disabled = false;
  barraChatInput.classList.remove("oculto");
  barraChatFinalizado.classList.add("oculto");
  btnFinalizarChat.classList.add("oculto");
  pantallaChat.classList.add("oculto");
  pantallaInicio.classList.remove("oculto");
  inputTelefono.focus();
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
btnFinalizarChat.addEventListener("click", () => finalizarConversacion("manual"));
btnNuevaConversacion.addEventListener("click", reiniciarChatCompleto);

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
          ${
            p.brochure_url
              ? `<a class="brochure-link" href="${p.brochure_url}" target="_blank" rel="noopener noreferrer">Ver brochure digital →</a>`
              : ""
          }
        </article>`
      )
      .join("");
  } catch (e) {
    sub.textContent = "No se pudo cargar el catálogo de proyectos.";
  }
}

cargarProyectos();
