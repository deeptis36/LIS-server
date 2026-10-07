ERBA EM-200 / MultiXL ASTM Listener

Files:
- erba_listener.py : TCP listener, ASTM handshake, raw/JSON save, API POST
- erba_parser.py   : ASTM -> JSON parser only
- .env.example     : configuration template
- requirements.txt : Python dependencies

Important:
This version does NOT require appointment_id.
It follows the working MAGLUMI pattern: parse the analyzer/system data,
set source_device=ERBA_EM_200, save raw + parsed JSON, then POST the parsed
JSON to the analyzer-webhook endpoint.

Do not overwrite your existing .env automatically. Update its API_PATH_TEMPLATE
to /api/v1/hospital/rims/analyzer-webhook if you want API posting enabled.
