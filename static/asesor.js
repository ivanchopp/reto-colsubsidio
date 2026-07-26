const REFRESCO_LISTA_MS = 20000;
const REFRESCO_DETALLE_MS = 5000;

const COLOR_CONTRIBUCION = {
  reglas: "#0067b1",
  peers: "#7c6bab",
  vectorial: "#2f9c8f",
  subsidios: "#c99400",
};

const URL_REGEX = /https?:\/\/[^\s<>"']+/g;

function escaparHtml(texto) {
  const div = document.createElement("div");
  div.textContent = texto;
  return div.innerHTML;
}

// mismo patron que static/app.js: escapa primero, despues convierte URLs
// sueltas en <a> clicables -- nunca reintroduce HTML desde el contenido.
function conLinksClicables(textoEscapado) {
  return textoEscapado.replace(URL_REGEX, (url) => {
    const cierre = url.match(/[.,;:!?)\]'"]+$/);
    const puntuacion = cierre ? cierre[0] : "";
    const urlLimpia = puntuacion ? url.slice(0, -puntuacion.length) : url;
    return `<a href="${urlLimpia}" target="_blank" rel="noopener noreferrer">${urlLimpia}</a>${puntuacion}`;
  });
}

function iniciales(nombre) {
  const partes = (nombre || "?").trim().split(/\s+/);
  return partes.slice(0, 2).map((p) => p[0]?.toUpperCase() || "").join("") || "?";
}

function claseSegmento(segmento) {
  if (segmento === "CALIENTE") return "caliente";
  if (segmento === "TIBIO") return "tibio";
  if (segmento === "FRIO") return "frio";
  return "sindatos";
}

function etiquetaSegmento(segmento) {
  if (segmento === "CALIENTE") return "Caliente";
  if (segmento === "TIBIO") return "Tibio";
  if (segmento === "FRIO") return "Frío";
  return "Sin datos";
}

let leadSeleccionado = null;
let timerDetalle = null;

async function cargarLeadsHoy() {
  let leads;
  try {
    const resp = await fetch("/api/asesor/leads/hoy");
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    leads = await resp.json();
  } catch (e) {
    document.getElementById("resumen-sub").textContent = "No se pudo cargar la lista de leads.";
    return;
  }

  const porSegmento = { CALIENTE: 0, TIBIO: 0, FRIO: 0 };
  leads.forEach((l) => {
    if (l.segmento_lead in porSegmento) porSegmento[l.segmento_lead] += 1;
  });
  document.getElementById("tile-total").textContent = leads.length;
  document.getElementById("tile-caliente").textContent = porSegmento.CALIENTE;
  document.getElementById("tile-tibio").textContent = porSegmento.TIBIO;
  document.getElementById("tile-frio").textContent = porSegmento.FRIO;

  const enCurso = leads.filter((l) => !l.interaccion_cerrada).length;
  document.getElementById("resumen-sub").textContent =
    `${leads.length} conversación(es) iniciada(s) hoy` +
    (enCurso ? ` · ${enCurso} en curso` : "");
  document.getElementById("conteo-leads").textContent = `${leads.length} hoy`;

  renderLista(leads);
  cargarResumenDia();
}

const ETIQUETA_ORIGEN = {
  meta: "Meta Ads",
  google: "Google Ads",
  whatsapp: "WhatsApp",
  organico: "Orgánico",
  contact_center: "Contact center",
  desconocido: "Sin origen",
};

async function cargarResumenDia() {
  let stats;
  try {
    const resp = await fetch("/api/asesor/resumen-dia");
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    stats = await resp.json();
  } catch (e) {
    document.getElementById("cuota-detalle").textContent = "No se pudo cargar el resumen del día.";
    return;
  }
  renderCuota(stats.cuota_90_10);
  renderCanales(stats.calidad_por_origen);
}

function renderCuota(cuota) {
  const estado = document.getElementById("cuota-estado");
  const detalle = document.getElementById("cuota-detalle");
  const barraAfiliados = document.getElementById("cuota-barra-afiliados");
  const barraNoAfiliados = document.getElementById("cuota-barra-no-afiliados");

  if (!cuota || !cuota.derivables) {
    estado.textContent = "Sin leads derivables";
    estado.className = "asesor-cuota-estado neutro";
    detalle.textContent = "Todavía no hay leads calientes para derivar al equipo comercial.";
    barraAfiliados.style.width = "0%";
    barraNoAfiliados.style.width = "0%";
    return;
  }

  const pctNoAfiliados = cuota.pct_no_afiliados;
  barraAfiliados.style.width = `${100 - pctNoAfiliados}%`;
  barraNoAfiliados.style.width = `${pctNoAfiliados}%`;

  if (cuota.excedido) {
    estado.textContent = "Cupo excedido";
    estado.className = "asesor-cuota-estado excedido";
    detalle.textContent =
      `${cuota.no_afiliados} de ${cuota.derivables} leads derivables son no afiliados (${pctNoAfiliados}%), ` +
      `por encima del cupo de ${cuota.cupo_no_afiliados}. Priorizar afiliados en las próximas derivaciones.`;
    return;
  }

  estado.textContent = `${cuota.cupo_disponible} de cupo disponible`;
  estado.className = "asesor-cuota-estado ok";
  detalle.textContent =
    `${cuota.afiliados} afiliado(s) y ${cuota.no_afiliados} no afiliado(s) sobre ${cuota.derivables} leads derivables ` +
    `(${pctNoAfiliados}%). El cupo para no afiliados es de ${cuota.cupo_no_afiliados}.`;
}

function renderCanales(canales) {
  const cont = document.getElementById("tabla-canales");
  if (!canales || !canales.length) {
    cont.innerHTML = `<div class="asesor-vacio">Sin datos todavía.</div>`;
    return;
  }
  cont.innerHTML = canales
    .map((c) => `
      <div class="asesor-canal-fila">
        <span class="asesor-canal-nombre">${escaparHtml(ETIQUETA_ORIGEN[c.origen] || c.origen)}</span>
        <span class="asesor-canal-total">${c.total} lead(s)</span>
        <span class="asesor-canal-barra"><i style="width:${c.pct_calientes}%"></i></span>
        <span class="asesor-canal-pct">${c.pct_calientes}% caliente</span>
      </div>
    `)
    .join("");
}

function renderLista(leads) {
  const cont = document.getElementById("lista-leads");
  if (!leads.length) {
    cont.innerHTML = `<div class="asesor-vacio">Todavía no hay conversaciones hoy.</div>`;
    return;
  }
  cont.innerHTML = leads
    .map((l) => {
      const seg = claseSegmento(l.segmento_lead);
      return `
        <div class="asesor-fila ${l.session_id === leadSeleccionado ? "activa" : ""}" data-id="${l.session_id}">
          <div class="iniciales">${iniciales(l.nombre)}</div>
          <div class="info">
            <div class="nombre">${escaparHtml(l.nombre)} ${!l.interaccion_cerrada ? '<span class="asesor-punto-en-curso" title="Conversación en curso"></span>' : ""}</div>
            <div class="meta">${escaparHtml(l.telefono)}${l.ciudad ? " · " + escaparHtml(l.ciudad) : ""}</div>
          </div>
          <div class="derecha">
            <span class="asesor-pill ${seg}">${etiquetaSegmento(l.segmento_lead)}</span>
            <div class="score" style="color:${l.score !== null ? COLOR_SEGMENTO[seg] : "var(--texto-tenue)"}">${l.score !== null ? l.score.toFixed(1) : "—"}</div>
            <div class="hora">${l.hora}</div>
          </div>
        </div>
      `;
    })
    .join("");

  cont.querySelectorAll(".asesor-fila").forEach((el) => {
    el.addEventListener("click", () => seleccionarLead(el.dataset.id));
  });
}

const COLOR_SEGMENTO = {
  caliente: "#c43d3d",
  tibio: "#b9791a",
  frio: "#3e6e93",
  sindatos: "#6b6b6a",
};

function medidorSVG(score, segmento) {
  const color = COLOR_SEGMENTO[claseSegmento(segmento)];
  const x = Math.max(20, Math.min(300, 20 + (score / 100) * 280));
  return `
    <svg viewBox="0 0 320 100" xmlns="http://www.w3.org/2000/svg">
      <rect x="20" y="44" width="112" height="20" rx="4" fill="var(--frio-bg)" />
      <rect x="132" y="44" width="84" height="20" fill="var(--tibio-bg)" />
      <rect x="216" y="44" width="84" height="20" rx="4" fill="var(--caliente-bg)" />
      <line x1="132" y1="40" x2="132" y2="68" stroke="var(--borde)" stroke-width="2" />
      <text x="132" y="82" font-size="10" fill="var(--texto-tenue)" text-anchor="middle">40</text>
      <line x1="216" y1="40" x2="216" y2="68" stroke="var(--borde)" stroke-width="2" />
      <text x="216" y="82" font-size="10" fill="var(--texto-tenue)" text-anchor="middle">70</text>
      <text x="20" y="82" font-size="10" fill="var(--texto-tenue)" text-anchor="start">0</text>
      <text x="300" y="82" font-size="10" fill="var(--texto-tenue)" text-anchor="end">100</text>
      <polygon points="${x - 7},34 ${x + 7},34 ${x},48" fill="${color}" />
      <text x="${x}" y="26" font-size="15" font-weight="700" fill="${color}" text-anchor="middle" font-variant-numeric="tabular-nums">${score.toFixed(1)}</text>
    </svg>
  `;
}

function tortaSVG(contribuciones) {
  const total = contribuciones.reduce((s, c) => s + c.valor, 0);
  const r = 42, cx = 60, cy = 60;
  const circunferencia = 2 * Math.PI * r;
  let acumulado = 0;
  const anillos = contribuciones
    .map((c) => {
      const fraccion = total > 0 ? c.valor / total : 0;
      const largo = fraccion * circunferencia;
      const offset = -acumulado * circunferencia;
      acumulado += fraccion;
      const color = COLOR_CONTRIBUCION[c.categoria] || "#8a8a89";
      return `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${color}"
        stroke-width="20" stroke-dasharray="${largo} ${circunferencia - largo}"
        stroke-dashoffset="${offset}" transform="rotate(-90 ${cx} ${cy})" />`;
    })
    .join("");
  return `
    <svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
      <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="var(--borde)" stroke-width="20" />
      ${anillos}
      <text x="${cx}" y="${cy - 3}" text-anchor="middle" font-size="19" font-weight="800"
        fill="var(--grafito)" font-variant-numeric="tabular-nums">${total.toFixed(1)}</text>
      <text x="${cx}" y="${cy + 12}" text-anchor="middle" font-size="8.5" fill="var(--texto-tenue)"
        letter-spacing="0.03em">PUNTOS</text>
    </svg>
  `;
}

function tortaLeyenda(contribuciones) {
  const total = contribuciones.reduce((s, c) => s + c.valor, 0);
  return `
    <ul class="asesor-torta-leyenda">
      ${contribuciones
        .map((c) => {
          const color = COLOR_CONTRIBUCION[c.categoria] || "#8a8a89";
          const pesoTxt = c.peso !== null && c.peso !== undefined ? ` <span style="color:var(--texto-tenue)">(peso ${(c.peso * 100).toFixed(0)}%)</span>` : "";
          return `
            <li>
              <span class="swatch" style="background:${color}"></span>
              <span class="etiqueta-item">${escaparHtml(c.etiqueta)}${pesoTxt}</span>
              <span class="valor-item">${c.valor.toFixed(1)}</span>
              <span class="pct-item">${total > 0 ? ((c.valor / total) * 100).toFixed(0) : 0}%</span>
            </li>
          `;
        })
        .join("")}
    </ul>
  `;
}

function bloqueScore(scoring) {
  if (!scoring) {
    return `
      <div class="asesor-seccion-titulo">Cálculo del segmento</div>
      <div class="asesor-sin-score">Todavía no se ha calculado un score para este contacto — la conversación sigue en curso.</div>
    `;
  }

  const gauge = `
    <div class="asesor-seccion-titulo">Cálculo del segmento</div>
    ${medidorSVG(scoring.score, scoring.segmento_lead)}
  `;

  if (scoring.contribuciones && scoring.contribuciones.length) {
    return `
      ${gauge}
      <div class="asesor-torta-wrap" style="margin-top:14px">
        ${tortaSVG(scoring.contribuciones)}
        ${tortaLeyenda(scoring.contribuciones)}
      </div>
    `;
  }

  return `
    ${gauge}
    <div class="asesor-sin-score" style="margin-top:14px">
      Este contacto no está registrado en el sistema, así que no hay datos financieros para
      desglosar: se le asigna un puntaje fijo de baja confianza (${scoring.score.toFixed(0)}/100)
      hasta que se registre o un asesor lo verifique manualmente.
    </div>
  `;
}

function bloqueApoyo(scoring) {
  const peerStats = scoring?.peer_stats;
  const subsidios = scoring?.subsidios_elegibles || [];
  if (!peerStats && !subsidios.length) return "";

  const peersHtml = peerStats
    ? peerStats.total_peers
      ? `
        <div class="asesor-tarjeta-apoyo">
          <div class="titulo-mini">Perfiles similares (${peerStats.total_peers})</div>
          <div class="dato-linea"><span>Con vivienda propia</span><span>${(peerStats.pct_con_vivienda_propia ?? 0).toFixed(0)}%</span></div>
          <div class="dato-linea"><span>Desistió</span><span>${(peerStats.pct_desistido ?? 0).toFixed(0)}%</span></div>
          <div class="dato-linea"><span>Rechazado</span><span>${(peerStats.pct_rechazado ?? 0).toFixed(0)}%</span></div>
          <div class="dato-linea"><span>Sin vivienda</span><span>${(peerStats.pct_sin_vivienda ?? 0).toFixed(0)}%</span></div>
        </div>
      `
      : `<div class="asesor-tarjeta-apoyo"><div class="titulo-mini">Perfiles similares</div><div class="dato-linea"><span>Sin suficientes datos</span></div></div>`
    : "";

  const subsidiosHtml = `
    <div class="asesor-tarjeta-apoyo">
      <div class="titulo-mini">Subsidios aplicables</div>
      ${
        subsidios.length
          ? subsidios
              .map(
                (s) => `
              <div class="asesor-subsidio-item">
                <div class="nombre-sub">${escaparHtml(s.nombre)}</div>
                <div class="req-sub">${escaparHtml(s.requisito_salarial_texto || "")}</div>
              </div>
            `
              )
              .join("")
          : `<div class="dato-linea"><span>Ninguno detectado</span></div>`
      }
    </div>
  `;

  return `
    <div class="asesor-seccion-titulo">Contexto de apoyo</div>
    <div class="asesor-tarjetas-apoyo">${peersHtml}${subsidiosHtml}</div>
  `;
}

function bloqueChat(data) {
  if (!data.chat_disponible) {
    return `
      <div class="asesor-seccion-titulo">Conversación</div>
      <div class="asesor-no-disponible">${escaparHtml(data.chat_mensaje || "Transcript no disponible.")}</div>
    `;
  }
  const mensajes = (data.historial || [])
    .map((m) => `<div class="burbuja ${m.role === "assistant" ? "bot" : "user"}">${conLinksClicables(escaparHtml(m.content))}</div>`)
    .join("");
  return `
    <div class="asesor-seccion-titulo">Conversación ${!data.interaccion_cerrada ? '<span style="color:#2fa84f">· en vivo</span>' : ""}</div>
    <div class="asesor-chat-transcript">${mensajes}</div>
    ${data.interaccion_cerrada ? `<div class="asesor-chat-nota">Conversación finalizada</div>` : ""}
  `;
}

// Que le falta a este lead para poder comprar. Solo se muestra si no es
// CALIENTE: en un lead listo para cerrar, listar pendientes distrae del
// unico objetivo, que es llamarlo.
function bloqueNutricion(scoring) {
  const bloqueantes = scoring?.bloqueantes || [];
  if (!bloqueantes.length || scoring?.segmento_lead === "CALIENTE") return "";
  const items = bloqueantes
    .map((b) => `
      <li>
        <strong>${escaparHtml(b.titulo)}</strong>
        <span>${escaparHtml(b.accion)}</span>
      </li>
    `)
    .join("");
  return `
    <div class="asesor-seccion-titulo">Plan de nutrición</div>
    <ul class="asesor-nutricion">${items}</ul>
  `;
}

function renderDetalle(data) {
  const det = document.getElementById("detalle");
  const seg = claseSegmento(data.scoring?.segmento_lead);
  det.innerHTML = `
    <div class="asesor-detalle-encabezado">
      <div class="quien">
        <div class="asesor-avatar-grande">${iniciales(data.nombre)}</div>
        <div>
          <h3>${escaparHtml(data.nombre)}</h3>
          <div class="telefono">${escaparHtml(data.telefono)}${data.ciudad ? " · " + escaparHtml(data.ciudad) : ""}</div>
        </div>
      </div>
      <div style="text-align:right">
        ${data.scoring ? `<span class="asesor-pill ${seg}">${etiquetaSegmento(data.scoring.segmento_lead)}</span>` : ""}
        <div class="asesor-estado-fase">${!data.interaccion_cerrada ? '<span class="asesor-punto-en-curso"></span>' : ""}${escaparHtml(data.fase)}</div>
      </div>
    </div>
    ${bloqueScore(data.scoring)}
    ${bloqueNutricion(data.scoring)}
    ${bloqueApoyo(data.scoring)}
    ${bloqueChat(data)}
  `;
}

async function cargarDetalle(sessionId) {
  try {
    const resp = await fetch(`/api/asesor/leads/${sessionId}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    renderDetalle(data);
  } catch (e) {
    // si falla un refresco silencioso no reemplazamos el detalle ya
    // visible -- el usuario sigue viendo la ultima version buena
  }
}

function seleccionarLead(sessionId) {
  leadSeleccionado = sessionId;
  document.querySelectorAll(".asesor-fila").forEach((el) => {
    el.classList.toggle("activa", el.dataset.id === sessionId);
  });
  clearInterval(timerDetalle);
  cargarDetalle(sessionId);
  timerDetalle = setInterval(() => cargarDetalle(sessionId), REFRESCO_DETALLE_MS);
}

document.getElementById("fecha-hoy").textContent = new Date().toLocaleDateString("es-CO", {
  weekday: "long",
  day: "numeric",
  month: "long",
});

// HTTP Basic Auth no tiene "logout" real -- el navegador guarda la
// credencial buena por origen hasta que se cierra. El truco estandar es
// pisarla con una invalida: se manda una peticion sincronica con usuario y
// clave inventados a un endpoint protegido; el navegador reemplaza la
// credencial cacheada por esta (que el servidor va a rechazar con 401), asi
// que la proxima vez que alguien entre a /asesor le vuelve a pedir login.
function cerrarSesion() {
  try {
    const xhr = new XMLHttpRequest();
    xhr.open("GET", "/api/asesor/leads/hoy", false, "logout", "logout-" + Date.now());
    xhr.send();
  } catch (e) {
    // se espera que falle (401) -- lo que importa es que quedo sobreescrita
  }
  window.location.href = "/";
}

document.getElementById("btn-cerrar-sesion").addEventListener("click", cerrarSesion);

cargarLeadsHoy();
setInterval(cargarLeadsHoy, REFRESCO_LISTA_MS);
