-- The building facts database: scans and buildings with PostGIS geometry, measures as typed columns, rooms and
-- doors, the fact history, flood runs and the workspace op log as hypertables, and room embeddings for search.
-- Everything lives in schema `threshold` so `drop_all` is one statement.

CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS timescaledb_toolkit;
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE;   -- also installs pgvector
CREATE EXTENSION IF NOT EXISTS pg_textsearch;

CREATE SCHEMA IF NOT EXISTS threshold;
SET search_path = threshold, public;

-- A building: a CoStar property, else a street address. Footprint where a scan was fitted to the aerial outline.
CREATE TABLE building (
    id              text PRIMARY KEY,
    property_id     bigint,
    address         text,
    city            text,
    zip             text,
    property_type   text,              -- CoStar's type when the kit has the property, else the scan kind
    listed_area_ft2 double precision,  -- CoStar or listing area for the building or home
    geom            geography(Point, 4326),
    footprint       geography(Polygon, 4326)
);
CREATE INDEX building_geom ON building USING gist (geom);

CREATE TABLE scan (
    sid           text PRIMARY KEY,
    building_id   text REFERENCES building (id),
    name          text,
    kind          text,                -- house | apartment_unit | office | ... (index guess)
    segment       text,
    city          text,
    zip           text,
    address       text,
    geom          geography(Point, 4326),
    walls         boolean,
    polygons      boolean,
    labels        boolean,
    panos         integer,
    floors        integer,
    created       timestamptz
);
CREATE INDEX scan_geom ON scan USING gist (geom);
CREATE INDEX scan_kind_city ON scan (kind, city);
CREATE INDEX scan_building ON scan (building_id);

-- The measures table (tool/access), one typed column per measure. Columns match measure_search.table.FIELDS.
CREATE TABLE measures (
    sid                     text PRIMARY KEY REFERENCES scan (sid) ON DELETE CASCADE,
    error                   text,
    floor_area              real, largest_room_area real, largest_room_label text,
    rooms                   smallint, bedrooms smallint, bathrooms smallint, kitchens smallint,
    living_rooms            smallint, dining_rooms smallint, closets smallint, hallways smallint,
    laundry                 smallint, garages smallint, offices smallint, staircases smallint,
    floors                  smallint, entrances smallint, entrance_width real, doors smallint,
    narrowest_door          real, median_door real, implausible_doors smallint,
    bath_route_door         real, bath_route_m real, bath_route_corridor real,
    bed_route_door_min      real, bed_route_door_max real, kitchen_route_door real,
    bath_turn               real, kitchen_turn real, bed_turn real, largest_turn real,
    longest_wall            real, bed_wall real, living_wall real,
    ceiling_median          real, ceiling_min real, ceiling_max real,
    windows                 smallint, glazed_area real, glazing_ratio real,
    level_changes           smallint, max_sill_step real,
    bed_bath_entry_floor    smallint, wheelchair_rooms_share real, step_free_bath smallint, wheelchair_bath smallint
);
CREATE INDEX measures_bath_route_door ON measures (bath_route_door);
CREATE INDEX measures_bath_turn ON measures (bath_turn);

-- One row per room: what a room-level question needs without opening the plan.
CREATE TABLE room (
    sid             text REFERENCES scan (sid) ON DELETE CASCADE,
    room            text,
    floor           text,
    label           text,
    label_source    text,
    area            real,
    width           real,
    depth           real,
    height          real,
    doors           smallint,
    widest_door     real,              -- clear width (opening less 5 cm), data errors left out
    narrowest_door  real,
    turn_diameter   real,              -- largest circle in the empty room
    windows         smallint,
    glazed_area     real,
    PRIMARY KEY (sid, room)
);
CREATE INDEX room_label ON room (label);

CREATE TABLE door (
    sid         text REFERENCES scan (sid) ON DELETE CASCADE,
    opening     text,
    kind        text,
    width       real,
    implausible boolean,
    step        real,
    floor       text
);
CREATE INDEX door_sid ON door (sid);

-- Derived fields with history: every fact a tool computes about a building, room or scan. Re-computing adds a row;
-- the latest row per (sid, room, field) is the current value. Place columns are filled from `scan` on insert so
-- rollups group without a join; a fact about a scan the database does not hold (a test plan) is skipped.
CREATE TABLE fact (
    at            timestamptz NOT NULL DEFAULT now(),
    sid           text,
    building_id   text,
    room          text,
    field         text NOT NULL,
    value_num     double precision,
    value_text    text,
    unit          text,
    layer         text,               -- matterport | vexcel | costar | drone | model
    method        text,               -- geometry | vision | lookup | simulation
    confidence    text,               -- high | medium | low
    tool          text,
    run           text,
    evidence      jsonb,
    record_value  text,               -- what the CoStar record or listing says for the same field, if anything
    record_path   text,
    city          text,
    zip           text,
    kind          text,
    property_type text
) WITH (
    tsdb.hypertable,
    tsdb.partition_column = 'at',
    tsdb.chunk_interval = '7 days',
    tsdb.segmentby = 'field',
    tsdb.orderby = 'sid, room, at DESC'
);
CREATE INDEX fact_sid_field ON fact (sid, field, at DESC);

CREATE FUNCTION fact_place() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.sid IS NOT NULL AND NEW.kind IS NULL THEN
        SELECT s.building_id, s.city, s.zip, s.kind, b.property_type
          INTO NEW.building_id, NEW.city, NEW.zip, NEW.kind, NEW.property_type
          FROM scan s LEFT JOIN building b ON b.id = s.building_id WHERE s.sid = NEW.sid;
        IF NOT FOUND THEN
            RETURN NULL;
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER fact_place BEFORE INSERT ON fact FOR EACH ROW EXECUTE FUNCTION fact_place();

-- Flood rehearsal runs: water depth per room as the water rises, one row per (run, time, room).
CREATE TABLE flood_run (
    run        text PRIMARY KEY,
    sid        text REFERENCES scan (sid) ON DELETE CASCADE,
    scenario   text,
    datum      text,          -- what level 0 means, e.g. "lowest scanned floor"
    step_m     real,
    step_s     integer,
    started    timestamptz,
    note       text
);
CREATE TABLE flood_depth (
    ts          timestamptz NOT NULL,
    run         text NOT NULL,
    sid         text NOT NULL,
    room        text NOT NULL,
    label       text,
    level_m     real,          -- water level above the run's datum
    depth_m     real,          -- water depth on this room's floor
    wet_area_m2 real
) WITH (
    tsdb.hypertable,
    tsdb.partition_column = 'ts',
    tsdb.chunk_interval = '1 day',
    tsdb.segmentby = 'run',
    tsdb.orderby = 'room, ts'
);
CREATE INDEX flood_depth_level ON flood_depth (level_m, depth_m);

-- The agent's workspace operations, for usage analytics and replay.
CREATE TABLE op_log (
    at          timestamptz NOT NULL,
    workspace   text NOT NULL,
    seq         integer NOT NULL,
    op          text,          -- operation name, e.g. run.finish; "undo" for an undo entry
    by_whom     text,
    tool        text,
    undo        integer,
    cause       integer,
    body        jsonb
) WITH (
    tsdb.hypertable,
    tsdb.partition_column = 'at',
    tsdb.chunk_interval = '7 days',
    tsdb.segmentby = 'workspace',
    tsdb.orderby = 'seq'
);

-- Rooms described by the vision model and embedded for search by meaning.
CREATE TABLE room_text (
    sid          text,
    room         text,
    pano         text,
    description  text NOT NULL,
    features     text[],
    model        text,
    embed_model  text,
    embedding    vector(384),
    labels       smallint[],    -- room type ids for filtered DiskANN (room_type)
    at           timestamptz DEFAULT now(),
    PRIMARY KEY (sid, room),
    FOREIGN KEY (sid, room) REFERENCES room (sid, room) ON DELETE CASCADE
);
CREATE TABLE room_type (id smallint PRIMARY KEY, label text UNIQUE NOT NULL);

CREATE TABLE meta (key text PRIMARY KEY, value jsonb);
