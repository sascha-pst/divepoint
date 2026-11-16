CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE places (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), query_text text NOT NULL,
 mrgid bigint, name text NOT NULL, geometry geometry(MultiPolygon,4326) NOT NULL,
 source text NOT NULL, resolved_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX places_geometry_idx ON places USING gist(geometry);
CREATE TABLE species (
 aphia_id bigint PRIMARY KEY CHECK (aphia_id > 0), scientific_name text NOT NULL,
 common_names text[] NOT NULL DEFAULT '{}', fishbase_spec_code bigint, gbif_key bigint,
 inat_taxon_id bigint, depth_min real, depth_max real, max_length_cm real,
 iucn_status text, body_shape text, cross_section text, tail_shape text,
 source_urls jsonb NOT NULL DEFAULT '{}'
);
CREATE TABLE checklists (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 place_id uuid NOT NULL REFERENCES places(id), depth_min real NOT NULL,
 depth_max real NOT NULL CHECK (depth_max >= depth_min), months integer[] NOT NULL DEFAULT '{}',
 aphia_id bigint NOT NULL REFERENCES species(aphia_id),
 obis_count integer NOT NULL DEFAULT 0 CHECK (obis_count >= 0),
 gbif_count integer NOT NULL DEFAULT 0 CHECK (gbif_count >= 0), latest_year integer,
 fetched_at timestamptz NOT NULL DEFAULT now(), CHECK (obis_count + gbif_count > 0),
 UNIQUE(place_id, depth_min, depth_max, months, aphia_id)
);
CREATE TABLE species_docs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), aphia_id bigint REFERENCES species(aphia_id),
 source text NOT NULL, field text NOT NULL, text text NOT NULL, url text NOT NULL,
 embedding vector, release_version text NOT NULL
);
CREATE TABLE photos (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 aphia_id bigint NOT NULL REFERENCES species(aphia_id), url text NOT NULL,
 license_code text NOT NULL CHECK (license_code IN ('cc0', 'cc-by', 'cc-by-sa')),
 attribution text NOT NULL CHECK (length(attribution) > 0), photo_page_url text NOT NULL
);
-- Anonymous local player IDs initially; authentication/ownership enforcement is required before launch.
CREATE TABLE dives (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), player_id uuid NOT NULL,
 place_id uuid NOT NULL REFERENCES places(id), filters jsonb NOT NULL,
 manifest_json jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE encounters (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), dive_id uuid NOT NULL REFERENCES dives(id),
 player_id uuid NOT NULL, aphia_id bigint NOT NULL REFERENCES species(aphia_id),
 logged_at timestamptz NOT NULL DEFAULT now(), UNIQUE(dive_id, player_id, aphia_id)
);
CREATE TABLE sprites (
 aphia_id bigint PRIMARY KEY REFERENCES species(aphia_id),
 tier text NOT NULL CHECK (tier IN ('hero','template','group','fallback')),
 template_id text, palette jsonb, asset_url text, animation_url text
);
