CREATE TABLE IF NOT EXISTS bank_institutions (
  codigo_institucion  text PRIMARY KEY,
  nombre_institucion  text NOT NULL,
  rut                 text,
  codigo_swift        text,
  is_aggregate        boolean NOT NULL DEFAULT false,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now()
);

-- Plan de cuentas (dimensión). Un código puede tener descripción distinta por época.
CREATE TABLE IF NOT EXISTS bank_accounts (
  id                  bigserial PRIMARY KEY,
  statement           text NOT NULL,          -- 'balance' | 'resultado'
  codigo_cuenta       text NOT NULL,
  descripcion_cuenta  text NOT NULL,
  taxonomy_epoch      text NOT NULL,          -- 'pre_2022' | 'compendio_2022'
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  UNIQUE (statement, codigo_cuenta, taxonomy_epoch)
);

-- Hecho mensual, multi-moneda.
CREATE TABLE IF NOT EXISTS bank_financial_data (
  id                       bigserial PRIMARY KEY,
  codigo_institucion       text NOT NULL REFERENCES bank_institutions(codigo_institucion),
  account_id               bigint NOT NULL REFERENCES bank_accounts(id),
  period_year              int NOT NULL,
  period_month             int NOT NULL,
  moneda_no_reajustable    numeric,
  moneda_reajustable_ipc   numeric,
  moneda_reajustable_tc    numeric,
  moneda_extranjera        numeric,
  moneda_total             numeric,
  taxonomy_epoch           text NOT NULL,
  unit                     text NOT NULL DEFAULT 'CLP',   -- 'CLP' | 'MMCLP'
  created_at               timestamptz NOT NULL DEFAULT now(),
  updated_at               timestamptz NOT NULL DEFAULT now(),
  UNIQUE (codigo_institucion, account_id, period_year, period_month)
);
CREATE INDEX IF NOT EXISTS ix_bank_fd_inst_period
  ON bank_financial_data (codigo_institucion, period_year, period_month);

-- Adecuación de capital: componentes (aplanados) + indicadores (IRS/IRE/capital básico)
-- fusionados en una fila por institución/período. raw preserva lo no modelado.
CREATE TABLE IF NOT EXISTS bank_capital_adequacy (
  id                        bigserial PRIMARY KEY,
  codigo_institucion        text NOT NULL REFERENCES bank_institutions(codigo_institucion),
  period_year               int NOT NULL,
  period_month              int NOT NULL,
  activos_ponderados_riesgo numeric,
  activos_totales           numeric,
  capital_basico            numeric,
  patrimonio_efectivo       numeric,
  provisiones_voluntarias   numeric,
  bonos_subordinados        numeric,
  interes_minoritario       numeric,
  indice_irs                numeric,   -- índice de solvencia
  indice_ire                numeric,
  raw                       jsonb,
  created_at                timestamptz NOT NULL DEFAULT now(),
  updated_at                timestamptz NOT NULL DEFAULT now(),
  UNIQUE (codigo_institucion, period_year, period_month)
);

-- Ficha / perfil: snapshot mensual.
CREATE TABLE IF NOT EXISTS bank_profiles (
  id                  bigserial PRIMARY KEY,
  codigo_institucion  text NOT NULL REFERENCES bank_institutions(codigo_institucion),
  period_year         int NOT NULL,
  period_month        int NOT NULL,
  codigo_swift        text,
  rut                 text,
  direccion           text,
  telefono            text,
  sitio_web           text,
  sucursales          int,
  oficinas            int,
  cajeros             int,
  empleados           int,
  emp_hombres_perm    int,
  emp_mujeres_perm    int,
  emp_hombres_ext     int,
  emp_mujeres_ext     int,
  fecha_publicacion   date,
  raw                 jsonb,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  UNIQUE (codigo_institucion, period_year, period_month)
);

CREATE TABLE IF NOT EXISTS bank_shareholders (
  id                  bigserial PRIMARY KEY,
  codigo_institucion  text NOT NULL REFERENCES bank_institutions(codigo_institucion),
  period_year         int NOT NULL,
  period_month        int NOT NULL,
  serie               text,
  rut                 text,
  nombre              text,
  participacion       numeric,
  numero_acciones     numeric,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  UNIQUE (codigo_institucion, period_year, period_month, rut, serie)
);

CREATE TABLE IF NOT EXISTS bank_executives (
  id                  bigserial PRIMARY KEY,
  codigo_institucion  text NOT NULL REFERENCES bank_institutions(codigo_institucion),
  period_year         int NOT NULL,
  period_month        int NOT NULL,
  nombre              text NOT NULL,
  cargo               text,
  fecha_asuncion      date,
  tipo                text,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  UNIQUE (codigo_institucion, period_year, period_month, nombre, cargo)
);

-- Log de corridas. Un renglón por (institución, recurso, período) intentado.
CREATE TABLE IF NOT EXISTS bank_data_imports (
  id                  bigserial PRIMARY KEY,
  codigo_institucion  text,
  report              text NOT NULL,   -- balance|resultado|adecuacion|perfil|accionistas|integrantes
  period_year         int,
  period_month        int,
  status              text NOT NULL,   -- running|completed|no_data|failed
  rows_total          int DEFAULT 0,
  rows_ok             int DEFAULT 0,
  rows_failed         int DEFAULT 0,
  message             text,
  started_at          timestamptz NOT NULL DEFAULT now(),
  finished_at         timestamptz
);
