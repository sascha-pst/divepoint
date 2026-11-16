-- Run once on existing databases; new databases apply both numbered files via Compose.
CREATE TABLE IF NOT EXISTS fishbase_snapshots (
 release_version text NOT NULL,
 table_name text NOT NULL CHECK (table_name IN ('species','ecology','morphdat')),
 source_url text NOT NULL,
 sha256 text NOT NULL CHECK (length(sha256) = 64),
 row_count integer NOT NULL CHECK (row_count >= 0),
 captured_at timestamptz NOT NULL,
 imported_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (release_version, table_name)
);
CREATE TABLE IF NOT EXISTS fishbase_records (
 release_version text NOT NULL,
 table_name text NOT NULL,
 row_number integer NOT NULL,
 spec_code bigint,
 data jsonb NOT NULL,
 PRIMARY KEY (release_version, table_name, row_number),
 FOREIGN KEY (release_version, table_name)
  REFERENCES fishbase_snapshots(release_version, table_name) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS fishbase_records_species_idx ON fishbase_records(spec_code);
CREATE TABLE IF NOT EXISTS fishbase_taxon_mappings (
 release_version text NOT NULL,
 spec_code bigint NOT NULL,
 aphia_id bigint NOT NULL REFERENCES species(aphia_id),
 fishbase_name text NOT NULL,
 worms_record jsonb NOT NULL,
 PRIMARY KEY (release_version, spec_code),
 UNIQUE (release_version, aphia_id)
);
