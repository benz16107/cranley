-- Garage columns for garage_fit's city search (tools/garage_fit/measures.py); measure_search.table.FIELDS carries them.
SET search_path = threshold, public;
ALTER TABLE measures ADD COLUMN IF NOT EXISTS garage_width real,
                     ADD COLUMN IF NOT EXISTS garage_depth real,
                     ADD COLUMN IF NOT EXISTS garage_door_width real,
                     ADD COLUMN IF NOT EXISTS garage_door_height real,
                     ADD COLUMN IF NOT EXISTS garage_ceiling real;
