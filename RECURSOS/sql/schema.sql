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
    reportado_data_credito text
);

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
