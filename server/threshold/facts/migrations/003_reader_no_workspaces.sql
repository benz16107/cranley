-- The read-only SQL tool (threshold_reader) must not see workspace ids: an id gives write access to its workspace, and
-- anyone with a phone link can brief the agent. op_log holds every workspace id and op body. TimescaleDB carries the
-- revoke to op_log's chunks. ops_hourly stays readable: it holds counts only (its view runs with the owner's rights).
REVOKE ALL ON op_log FROM threshold_reader;
