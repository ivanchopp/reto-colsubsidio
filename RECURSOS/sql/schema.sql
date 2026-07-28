-- Esquema para Supabase (Postgres). Ejecutar una sola vez en el SQL Editor
-- del proyecto de Supabase (Project > SQL Editor > New query > Run).
-- Reemplaza los Excel/JSON locales de RECURSOS/ como fuente de datos de la app.

create table if not exists usuarios (
    documento bigint primary key,
    nombre text,
    edad integer,
    correo text,
    telefono text,
    direccion text,
    ciudad text,
    afiliado_colsubsidio text,
    estado_vivienda_propia text,
    suscripciones_actuales text,
    estado_laboral text,
    fecha_inicio_labores text,
    tipo_contrato text,
    rango_salarial text,
    ha_pedido_subsidios text,
    reportado_data_credito text,
    ahorros bigint
);

-- columna agregada despues de la creacion original de la tabla (liquidez
-- verificada para la cuota inicial, ver app/scoring.py); "add column if not
-- exists" para que este script se pueda re-correr sobre un proyecto de
-- Supabase que ya existe sin perder los datos que ya tiene.
alter table usuarios add column if not exists ahorros bigint;

create index if not exists idx_usuarios_telefono on usuarios (telefono);

create table if not exists subsidios (
    id serial primary key,
    subsidio text,
    requisitos_salariales_smmlv text,
    permite_subsidios_anteriores text,
    permite_vivienda_propia text,
    situacion_laboral_riesgo text
);

create table if not exists proyectos (
    slug text primary key,
    data jsonb not null
);

-- Leads (sesiones de chat) para el panel del asesor comercial. A diferencia
-- de usuarios/subsidios/proyectos (catalogo estatico que se recarga con
-- migrar_a_supabase.py), esta tabla la escribe la app en vivo: una fila por
-- sesion de chat, actualizada varias veces durante la conversacion. Ver
-- scripts/crear_tabla_leads.py para aplicar esta migracion (puramente
-- aditiva, nunca hace truncate/delete).
create table if not exists leads (
    session_id uuid primary key,
    telefono text not null,
    nombre text,
    ciudad text,
    usuario_registrado boolean not null default false,
    documento bigint,
    score numeric(5,1),
    segmento_lead text,            -- CALIENTE / TIBIO / FRIO
    project_segment text,          -- VIS / No VIS / "Sin dato (no registrado)"
    scoring_version text,          -- config.SCORING_VERSION vigente al calcular el score (auditoria)
    razones jsonb,
    peer_stats jsonb,
    subsidios_elegibles jsonb,
    contribuciones jsonb,          -- desglose {etiqueta, valor, peso, categoria} para el grafico de torta
    fase text not null,
    finalizada boolean not null default false,
    interaccion_cerrada boolean not null default false,
    enviado_al_asesor boolean not null default false,
    origen text not null default 'organico',  -- meta / google / whatsapp / organico / contact_center
    afiliado boolean,              -- necesario para el cupo agregado de la regla 90/10
    bloqueantes jsonb,             -- que le falta al lead para poder comprar (app/nutricion.py)
    datos_declarados jsonb,        -- variables extraidas de la conversacion (app/extraccion.py)
    creado_en timestamptz not null default now(),
    actualizado_en timestamptz not null default now()
);

create index if not exists idx_leads_creado_en on leads (creado_en desc);
create index if not exists idx_leads_telefono on leads (telefono);
create index if not exists idx_leads_origen on leads (origen);
