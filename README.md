# Airport Departures for FiestaBoard

An installable FiestaBoard plugin for scheduled airline departure boards. Unlike nearby-aircraft plugins, it uses an airport schedule feed and exposes flight number, destination, time, delay, terminal, gate, and operational status. Rows without published airline and flight IATA identifiers are excluded.

## Data Provider

Version 1 uses the [AirLabs Schedules API](https://airlabs.co/docs/schedules). AirLabs currently returns live schedule data up to roughly ten hours ahead and offers a free key for development and low-volume personal use.

The provider adapter is isolated in `provider.py`, so another vendor can be added without changing the FiestaBoard variables or templates.

## Install

After this directory is pushed to a public GitHub repository, install its HTTPS URL from FiestaBoard's Integrations page. Keep the repository name `fiestaboard-plugin--airport-departures` if it may later be submitted to the official registry.

## Note Template

```text
{{airport_departures.line1}}
{{airport_departures.line2}}
{{airport_departures.line3}}
```

Example:

```text
SEA DEPARTURES
AS123 LAX 1930
DL456 SFO 2015
```

Note rows use four-digit 24-hour times so a full flight number, destination, and time fit exactly on 15 tiles. Delays use the latest estimated time. The structured `display_time`, `status_code`, and `status_label` fields remain available for custom templates.

The one-hour default refresh uses no more than 744 scheduled requests during a 31-day month. Lower it only after checking the allowance associated with your API key.

See [docs/SETUP.md](docs/SETUP.md) for setup details.
