-- Optional. Run against a database you administer. No existing table is dropped.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE TABLE IF NOT EXISTS idle_sites (
    site_id text PRIMARY KEY,
    name text NOT NULL,
    site_type text NOT NULL,
    address text,
    source text NOT NULL,
    is_demo boolean NOT NULL DEFAULT false,
    is_green boolean NOT NULL DEFAULT false,
    impervious_ratio double precision CHECK (impervious_ratio BETWEEN 0 AND 1),
    feasibility_score double precision CHECK (feasibility_score BETWEEN 0 AND 1),
    geom geometry(MultiPolygon, 4326) NOT NULL,
    CHECK (ST_IsValid(geom) AND NOT ST_IsEmpty(geom))
);
CREATE INDEX IF NOT EXISTS idle_sites_geom_idx ON idle_sites USING gist(geom);
