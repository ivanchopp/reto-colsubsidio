let sessionId = null;
let sesionFinalizada = false;
let usuarioEncontrado = true;
let esperandoRespuesta = false;
let timerAvisoInactividad = null;
let timerCierreInactividad = null;
let estadoSesion = { fase: "saludo", tema_actual: null, respuestas_aspiracionales: 0, finalizada: false, interaccion_cerrada: false, recomendacion: null };

const pantallaInicio = document.getElementById("pantalla-inicio");
const pantallaChat = document.getElementById("pantalla-chat");
const mensajesDiv = document.getElementById("mensajes");
const inputTelefono = document.getElementById("input-telefono");
const inputMensaje = document.getElementById("input-mensaje");
const btnEnviarMensaje = document.getElementById("btn-enviar");
const btnMicrofono = document.getElementById("btn-microfono");
const resumenVacio = document.getElementById("resumen-vacio");
const resumenContenido = document.getElementById("resumen-contenido");
const btnEnviarAsesor = document.getElementById("btn-enviar-asesor");
const estadoEnvio = document.getElementById("estado-envio");
const btnFinalizarChat = document.getElementById("btn-finalizar-chat");
const barraChatInput = document.getElementById("barra-chat-input");
const barraChatFinalizado = document.getElementById("barra-chat-finalizado");
const btnNuevaConversacion = document.getElementById("btn-nueva-conversacion");
const companera = document.getElementById("companera");
const estadoAvatar = document.getElementById("estado-avatar");
const tituloAvatar = document.getElementById("titulo-avatar");
const progresoTexto = document.getElementById("progreso-texto");
const progresoNumero = document.getElementById("progreso-numero");
const progresoBarra = document.getElementById("progreso-barra");
const respuestasRapidas = document.getElementById("respuestas-rapidas");
const proyectoRecomendado = document.getElementById("proyecto-recomendado");
const recomendadoNombre = document.getElementById("recomendado-nombre");
const recomendadoUbicacion = document.getElementById("recomendado-ubicacion");
const recomendadoAmenities = document.getElementById("recomendado-amenities");
const recomendadoBrochure = document.getElementById("recomendado-brochure");

const RETARDO_MINIMO_MS = 700;
const AVISO_INACTIVIDAD_MS = 2 * 60 * 1000;
const CIERRE_INACTIVIDAD_MS = 3 * 60 * 1000;
const MENSAJE_AVISO_INACTIVIDAD = "¿Sigues ahí? Si no recibo respuesta en un minuto voy a cerrar esta conversación por inactividad.";
const URL_REGEX = /https?:\/\/[^\s<>"']+/g;

function escaparHtml(texto) {
  const div = document.createElement("div");
  div.textContent = texto;
  return div.innerHTML;
}

function conLinksClicables(textoEscapado) {
  return textoEscapado.replace(URL_REGEX, (url) => {
    const cierre = url.match(/[.,;:!?)\]'”"]+$/);
    const puntuacion = cierre ? cierre[0] : "";
    const urlLimpia = puntuacion ? url.slice(0, -puntuacion.length) : url;
    return `<a href="${urlLimpia}" target="_blank" rel="noopener noreferrer">${urlLimpia}</a>${puntuacion}`;
  });
}

function agregarBurbuja(texto, quien) {
  const div = document.createElement("div");
  div.className = `burbuja ${quien}`;
  div.innerHTML = conLinksClicables(escaparHtml(texto));
  mensajesDiv.appendChild(div);
  mensajesDiv.scrollTop = mensajesDiv.scrollHeight;
}

function sugerenciasParaTema(tema) {
  const temaNormalizado = (tema || "").toLowerCase();
  if (temaNormalizado.includes("suenos") || temaNormalizado.includes("sueños")) {
    return ["Tener vivienda propia", "Más espacio para mi familia", "Invertir para el futuro"];
  }
  if (temaNormalizado.includes("vivir ahi") || temaNormalizado.includes("vivir ahí") || temaNormalizado.includes("inversion") || temaNormalizado.includes("inversión")) {
    return ["Para vivir", "Como inversión", "Aún lo estoy decidiendo"];
  }
  if (temaNormalizado.includes("proximos 5") || temaNormalizado.includes("próximos 5")) {
    return ["Cerca del trabajo", "En una zona tranquila", "Con mi familia creciendo"];
  }
  if (temaNormalizado.includes("indispensable") || temaNormalizado.includes("proxima casa") || temaNormalizado.includes("próxima casa")) {
    return ["Más espacio", "Buena ubicación", "Zonas comunes"];
  }
  if (temaNormalizado.includes("estilo de vida")) {
    return ["Trabajo desde casa", "Vida familiar", "Activo y social"];
  }
  return [];
}

function mostrarRespuestasRapidas(estado, estadoAvatarActual) {
  respuestasRapidas.innerHTML = "";
  const sugerencias = sugerenciasParaTema(estado.tema_actual);
  const disponibles = estado.fase === "aspiracional" && !estado.finalizada && estadoAvatarActual !== "pensando" && sugerencias.length;
  if (!disponibles) {
    respuestasRapidas.classList.add("oculto");
    return;
  }
  sugerencias.forEach((sugerencia) => {
    const boton = document.createElement("button");
    boton.type = "button";
    boton.className = "respuesta-rapida";
    boton.textContent = sugerencia;
    boton.addEventListener("click", () => enviarMensaje(sugerencia));
    respuestasRapidas.appendChild(boton);
  });
  respuestasRapidas.classList.remove("oculto");
}

function mostrarProyectoRecomendado(recomendacion, mostrar) {
  if (!mostrar || !recomendacion) {
    proyectoRecomendado.classList.add("oculto");
    return;
  }
  recomendadoNombre.textContent = recomendacion.nombre;
  recomendadoUbicacion.textContent = [recomendacion.ciudad, recomendacion.categoria].filter(Boolean).join(" · ");
  recomendadoAmenities.innerHTML = "";
  (recomendacion.amenities || []).forEach((amenity) => {
    const item = document.createElement("li");
    item.textContent = amenity;
    recomendadoAmenities.appendChild(item);
  });
  try {
    const url = new URL(recomendacion.brochure_url);
    if (url.protocol !== "http:" && url.protocol !== "https:") throw new Error("Protocolo no permitido");
    recomendadoBrochure.href = url.href;
    recomendadoBrochure.classList.remove("oculto");
  } catch (_) {
    recomendadoBrochure.removeAttribute("href");
    recomendadoBrochure.classList.add("oculto");
  }
  proyectoRecomendado.classList.remove("oculto");
}

function actualizarExperiencia(estado = estadoSesion, forzarEstado = null) {
  const respuestas = Math.min(estado.respuestas_aspiracionales || 0, 3);
  const completa = estado.finalizada || estado.fase === "recomendacion" || estado.fase === "cierre";
  const porcentaje = completa ? 100 : Math.round((respuestas / 3) * 100);
  progresoBarra.style.width = `${porcentaje}%`;

  if (completa) {
    progresoTexto.textContent = "Tu ruta está lista";
    progresoNumero.textContent = "3 de 3";
  } else if (estado.fase === "aspiracional") {
    progresoTexto.textContent = respuestas ? "Conociendo tus sueños" : "Empecemos a conocerte";
    progresoNumero.textContent = `${respuestas} de 3`;
  } else {
    progresoTexto.textContent = "Conociéndote";
    progresoNumero.textContent = "0 de 3";
  }

  let estadoAvatarActual = forzarEstado;
  if (!estadoAvatarActual) {
    if (estado.interaccion_cerrada) estadoAvatarActual = "despedida";
    else if (completa) estadoAvatarActual = "celebrando";
    else if (estado.fase === "aspiracional") estadoAvatarActual = "curiosa";
    else estadoAvatarActual = "saludo";
  }
  companera.dataset.estado = estadoAvatarActual;

  const copy = {
    saludo: ["¡Hola! Soy Lina", "Vamos a encontrar un lugar para ti"],
    pensando: ["Lina está pensando", "Un momento, estoy uniendo las piezas"],
    curiosa: ["Quiero conocerte mejor", "Cada respuesta nos acerca a tu hogar"],
    celebrando: ["¡Tenemos una buena ruta!", "Mira la recomendación que preparé para ti"],
    despedida: ["Hasta pronto", "Aquí estaré cuando quieras seguir soñando"],
  };
  const [estadoTexto, titulo] = copy[estadoAvatarActual] || copy.saludo;
  estadoAvatar.textContent = estadoTexto;
  tituloAvatar.textContent = titulo;
  mostrarRespuestasRapidas(estado, estadoAvatarActual);
  mostrarProyectoRecomendado(estado.recomendacion, completa);
}

async function leerJson(url, opciones) {
  const respuesta = await fetch(url, opciones);
  if (!respuesta.ok) throw new Error(`Error HTTP ${respuesta.status}`);
  return respuesta.json();
}

async function sincronizarExperiencia() {
  if (!sessionId) return;
  try {
    estadoSesion = await leerJson(`/api/sesion/${sessionId}`);
    actualizarExperiencia();
  } catch (error) {
    console.warn("No se pudo sincronizar el estado visual de la sesión:", error);
  }
}

function mostrarEscribiendo() {
  const div = document.createElement("div");
  div.className = "burbuja bot escribiendo";
  div.id = "burbuja-escribiendo";
  div.setAttribute("aria-label", "Lina está escribiendo");
  div.innerHTML = "<span></span><span></span><span></span>";
  mensajesDiv.appendChild(div);
  mensajesDiv.scrollTop = mensajesDiv.scrollHeight;
}

function ocultarEscribiendo() { document.getElementById("burbuja-escribiendo")?.remove(); }
function esperar(ms) { return new Promise((resolve) => setTimeout(resolve, ms)); }

async function pedirConIndicadorEscribiendo(peticion) {
  esperandoRespuesta = true;
  inputMensaje.disabled = true;
  btnEnviarMensaje.disabled = true;
  btnMicrofono.disabled = true;
  actualizarExperiencia(estadoSesion, "pensando");
  mostrarEscribiendo();
  const inicio = Date.now();
  let data = null;
  try { data = await peticion(); }
  catch (error) { console.error("Falló la conexión con el asesor digital:", error); }
  const transcurrido = Date.now() - inicio;
  if (transcurrido < RETARDO_MINIMO_MS) await esperar(RETARDO_MINIMO_MS - transcurrido);
  ocultarEscribiendo();
  esperandoRespuesta = false;
  if (!sesionFinalizada) {
    inputMensaje.disabled = false;
    btnEnviarMensaje.disabled = false;
    btnMicrofono.disabled = !reconocimientoDisponible;
  }
  return data;
}

async function iniciar() {
  const telefono = inputTelefono.value.trim();
  if (!telefono) {
    inputTelefono.focus();
    return;
  }
  pantallaInicio.classList.add("oculto");
  pantallaChat.classList.remove("oculto");
  btnFinalizarChat.classList.remove("oculto");
  const data = await pedirConIndicadorEscribiendo(() => leerJson("/api/iniciar", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ telefono }),
  }));
  if (!data) {
    pantallaChat.classList.add("oculto");
    btnFinalizarChat.classList.add("oculto");
    pantallaInicio.classList.remove("oculto");
    document.querySelector(".ayuda").textContent = "No pudimos conectarnos. Revisa tu conexión e intenta de nuevo.";
    actualizarExperiencia({ fase: "saludo", respuestas_aspiracionales: 0 });
    return;
  }
  sessionId = data.session_id;
  sesionFinalizada = false;
  usuarioEncontrado = data.usuario_encontrado;
  agregarBurbuja(data.mensaje, "bot");
  await sincronizarExperiencia();
  reiniciarTemporizadorInactividad();
}

async function enviarMensaje(respuestaRapida = null) {
  const texto = (respuestaRapida || inputMensaje.value).trim();
  if (!texto || !sessionId || sesionFinalizada || esperandoRespuesta) return;
  inputMensaje.value = "";
  respuestasRapidas.classList.add("oculto");
  agregarBurbuja(texto, "user");
  limpiarTemporizadoresInactividad();
  const data = await pedirConIndicadorEscribiendo(() => leerJson("/api/mensaje", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ session_id: sessionId, texto }),
  }));
  if (!data) {
    agregarBurbuja("No pude enviar tu mensaje por un problema de conexión. Por favor intenta de nuevo.", "bot");
    inputMensaje.value = texto;
    await sincronizarExperiencia();
    reiniciarTemporizadorInactividad();
    return;
  }
  agregarBurbuja(data.mensaje, "bot");
  await sincronizarExperiencia();
  reiniciarTemporizadorInactividad();
  if (data.finalizada) {
    if (!usuarioEncontrado) {
      sesionFinalizada = true;
      limpiarTemporizadoresInactividad();
      bloquearChat();
    }
    await cargarResumen();
    if (data.envio_asesor) mostrarEstadoEnvio(data.envio_asesor);
  }
}

function limpiarTemporizadoresInactividad() {
  clearTimeout(timerAvisoInactividad);
  clearTimeout(timerCierreInactividad);
}

function reiniciarTemporizadorInactividad() {
  limpiarTemporizadoresInactividad();
  if (sesionFinalizada || !sessionId) return;
  timerAvisoInactividad = setTimeout(() => agregarBurbuja(MENSAJE_AVISO_INACTIVIDAD, "bot"), AVISO_INACTIVIDAD_MS);
  timerCierreInactividad = setTimeout(() => finalizarConversacion("inactividad"), CIERRE_INACTIVIDAD_MS);
}

async function finalizarConversacion(motivo) {
  if (sesionFinalizada || !sessionId) return;
  sesionFinalizada = true;
  limpiarTemporizadoresInactividad();
  const data = await pedirConIndicadorEscribiendo(() => leerJson(`/api/finalizar/${sessionId}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ motivo }),
  }));
  if (!data) {
    agregarBurbuja("No pudimos cerrar la conversación por un problema de conexión. Intenta de nuevo con el botón Finalizar.", "bot");
    sesionFinalizada = false;
    await sincronizarExperiencia();
    reiniciarTemporizadorInactividad();
    return;
  }
  agregarBurbuja(data.mensaje, "bot");
  await sincronizarExperiencia();
  bloquearChat();
  await cargarResumen();
  if (data.envio_asesor) mostrarEstadoEnvio(data.envio_asesor);
}

function bloquearChat() {
  inputMensaje.disabled = true;
  btnEnviarMensaje.disabled = true;
  btnMicrofono.disabled = true;
  btnFinalizarChat.classList.add("oculto");
  barraChatInput.classList.add("oculto");
  barraChatFinalizado.classList.remove("oculto");
}

function reiniciarChatCompleto() {
  limpiarTemporizadoresInactividad();
  sesionFinalizada = false;
  usuarioEncontrado = true;
  sessionId = null;
  estadoSesion = { fase: "saludo", tema_actual: null, respuestas_aspiracionales: 0, finalizada: false, interaccion_cerrada: false, recomendacion: null };
  mensajesDiv.innerHTML = "";
  inputTelefono.value = "";
  inputMensaje.disabled = false;
  btnEnviarMensaje.disabled = false;
  btnMicrofono.disabled = !reconocimientoDisponible;
  barraChatInput.classList.remove("oculto");
  barraChatFinalizado.classList.add("oculto");
  btnFinalizarChat.classList.add("oculto");
  pantallaChat.classList.add("oculto");
  pantallaInicio.classList.remove("oculto");
  actualizarExperiencia();
  inputTelefono.focus();
}

function mostrarEstadoEnvio({ enviado, detalle }) {
  estadoEnvio.textContent = enviado ? `✓ Correo enviado automáticamente al asesor — ${detalle}` : `⚠ ${detalle}`;
  btnEnviarAsesor.textContent = enviado ? "Reenviar correo al asesor" : "Reintentar envío al asesor";
}

async function cargarResumen() {
  try {
    const { asunto, cuerpo, enviado_al_asesor } = await leerJson(`/api/resumen/${sessionId}`);
    resumenVacio.classList.add("oculto");
    resumenContenido.classList.remove("oculto");
    btnEnviarAsesor.classList.remove("oculto");
    resumenContenido.textContent = `Asunto: ${asunto}\n\n${cuerpo}`;
    btnEnviarAsesor.textContent = enviado_al_asesor ? "Reenviar correo al asesor" : "Enviar correo al asesor";
  } catch (error) { console.warn("No se pudo cargar el resumen:", error); }
}

async function enviarAAsesor() {
  btnEnviarAsesor.disabled = true;
  estadoEnvio.textContent = "Enviando…";
  try { mostrarEstadoEnvio(await leerJson(`/api/enviar-asesor/${sessionId}`, { method: "POST" })); }
  catch (error) { estadoEnvio.textContent = "⚠ No se pudo enviar el correo. Intenta nuevamente."; }
  btnEnviarAsesor.disabled = false;
}

// Dictado opcional: el navegador convierte la voz a texto antes de enviarla,
// así el backend y sus reglas conversacionales no requieren cambios.
const ReconocimientoVoz = window.SpeechRecognition || window.webkitSpeechRecognition;
const reconocimientoDisponible = Boolean(ReconocimientoVoz);
let reconocimiento = null;
let dictando = false;
let textoAntesDeDictado = "";
if (reconocimientoDisponible) {
  reconocimiento = new ReconocimientoVoz();
  reconocimiento.lang = "es-CO";
  reconocimiento.continuous = false;
  reconocimiento.interimResults = false;
  reconocimiento.maxAlternatives = 1;
  reconocimiento.addEventListener("start", () => {
    dictando = true;
    btnMicrofono.classList.add("escuchando");
  });
  reconocimiento.addEventListener("end", () => {
    dictando = false;
    btnMicrofono.classList.remove("escuchando");
  });
  reconocimiento.addEventListener("result", (evento) => {
    // Un evento puede contener resultados anteriores además del nuevo. Se
    // parte de resultIndex y se reconstruye el fragmento dictado para no
    // anexar la misma sílaba o frase varias veces al campo de texto.
    const transcripcion = Array.from(evento.results)
      .slice(evento.resultIndex)
      .filter((resultado) => resultado.isFinal)
      .map((resultado) => resultado[0].transcript.trim())
      .filter(Boolean)
      .join(" ");
    if (transcripcion) {
      inputMensaje.value = [textoAntesDeDictado, transcripcion].filter(Boolean).join(" ");
    }
    inputMensaje.focus();
  });
  reconocimiento.addEventListener("error", () => {
    btnMicrofono.classList.remove("escuchando");
    agregarBurbuja("No pude activar el dictado. Puedes escribir tu mensaje cuando quieras.", "bot");
  });
} else {
  btnMicrofono.disabled = true;
  btnMicrofono.title = "El dictado no está disponible en este navegador";
}

btnMicrofono.addEventListener("click", () => {
  if (!reconocimiento || esperandoRespuesta || sesionFinalizada) return;
  if (dictando) {
    reconocimiento.stop();
    return;
  }
  textoAntesDeDictado = inputMensaje.value.trim();
  try { reconocimiento.start(); } catch (_) { dictando = false; }
});
document.getElementById("btn-iniciar").addEventListener("click", iniciar);
document.getElementById("btn-enviar").addEventListener("click", enviarMensaje);
inputMensaje.addEventListener("keydown", (e) => { if (e.key === "Enter") enviarMensaje(); });
inputTelefono.addEventListener("keydown", (e) => { if (e.key === "Enter") iniciar(); });
btnEnviarAsesor.addEventListener("click", enviarAAsesor);
btnFinalizarChat.addEventListener("click", () => finalizarConversacion("manual"));
btnNuevaConversacion.addEventListener("click", reiniciarChatCompleto);

const ventanaChat = document.getElementById("ventana-chat");
const btnChatFlotante = document.getElementById("btn-chat-flotante");
function abrirChat() {
  ventanaChat.classList.remove("oculto");
  btnChatFlotante.classList.add("oculto");
  (pantallaChat.classList.contains("oculto") ? inputTelefono : inputMensaje).focus();
}
function cerrarChat() { ventanaChat.classList.add("oculto"); btnChatFlotante.classList.remove("oculto"); }
btnChatFlotante.addEventListener("click", abrirChat);
document.getElementById("btn-cerrar-chat").addEventListener("click", cerrarChat);
document.getElementById("btn-abrir-chat-nav").addEventListener("click", abrirChat);
document.getElementById("btn-abrir-chat-hero").addEventListener("click", abrirChat);

async function cargarProyectos() {
  const grid = document.getElementById("proyectos-grid");
  const sub = document.querySelector(".proyectos-sub");
  try {
    const proyectos = await leerJson("/api/proyectos");
    sub.textContent = `${proyectos.length} proyectos disponibles en la red Colsubsidio.`;
    grid.innerHTML = proyectos.map((p) => `
      <article class="proyecto-card"><span class="segmento">${escaparHtml(p.segmento)}</span>
      <h3>${escaparHtml(p.nombre)}</h3><div class="ciudad">${escaparHtml(p.ciudad)} · ${escaparHtml(p.categoria)}</div>
      <ul class="amenities">${p.amenities.map((a) => `<li>${escaparHtml(a)}</li>`).join("")}</ul>
      ${p.brochure_url ? `<a class="brochure-link" href="${escaparHtml(p.brochure_url)}" target="_blank" rel="noopener noreferrer">Ver brochure digital →</a>` : ""}</article>`).join("");
  } catch (error) { sub.textContent = "No se pudo cargar el catálogo de proyectos."; }
}

actualizarExperiencia();
cargarProyectos();
