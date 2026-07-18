# Airport Departures for FiestaBoard

An installable FiestaBoard plugin for scheduled airline departure and arrival boards. Unlike nearby-aircraft plugins, it uses an airport schedule feed and exposes flight number, origin or destination, time, delay, terminal, gate, baggage carousel, and operational status. Rows without published airline and flight IATA identifiers are excluded, and codeshare listings for the same physical flight are combined.

![Airport Departures on a Vestaboard Note](./docs/board-display.png)

## Data Provider

The plugin uses the [AirLabs Schedules API](https://airlabs.co/docs/schedules). AirLabs currently returns live schedule data up to roughly ten hours ahead and offers a free key for development and low-volume personal use.

The provider adapter is isolated in `provider.py`, so another vendor can be added without changing the FiestaBoard variables or templates.

## Install

Install the repository's HTTPS URL from FiestaBoard's **Integrations** page:

```text
https://github.com/breedloj/fiestaboard-plugin--airport-departures
```

An AirLabs API key is required.

## Template Variables

### Next Flight

| Variable | Description | Example |
|---|---|---|
| `{{airport_departures.board_type}}` | Selected board type | `arrivals` |
| `{{airport_departures.airport}}` | Configured airport | `PAE` |
| `{{airport_departures.flight}}` | Preferred flight number after codeshare grouping | `AS2248` |
| `{{airport_departures.origin}}` | Origin IATA code for an arrival | `SFO` |
| `{{airport_departures.destination}}` | Destination IATA code | `SFO` |
| `{{airport_departures.display_time}}` | Best known local flight time | `9:44 PM` |
| `{{airport_departures.status_label}}` | Human-readable operational status | `ON TIME` |
| `{{airport_departures.minutes_until_departure}}` | Minutes until the next departure, or `-1` | `90` |
| `{{airport_departures.minutes_until_arrival}}` | Minutes until the next arrival, or `-1` | `90` |
| `{{airport_departures.departures}}` | Ordered, deduplicated departures | array |
| `{{airport_departures.arrivals}}` | Ordered, deduplicated arrivals | array |

### Ready-to-Display

| Variable | Description | Maximum |
|---|---|---|
| `{{airport_departures.line1}}` | Note-ready airport header | 15 tiles |
| `{{airport_departures.line2}}` | First Note-ready flight | 15 tiles |
| `{{airport_departures.line3}}` | Second Note-ready flight | 15 tiles |
| `{{airport_departures.formatted}}` | Compact primary flight | 22 tiles |

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

Note rows use four-digit 24-hour times so a full flight number, counterpart airport, and time fit exactly on 15 tiles. Delays use the latest estimated time. The structured `display_time`, `status_code`, and `status_label` fields remain available for custom templates.

With **Board Type** set to **Arrivals**, the same template becomes:

```text
PAE ARRIVALS
AS2248 SFO 2144
AS2055 LAX 2230
```

Arrival rows show the origin airport and use the best known arrival time. Structured arrivals also expose `terminal`, `gate`, and `baggage` when AirLabs supplies them.

Variable-mode collections can use `airport_departures.minutes_until_departure` or `airport_departures.minutes_until_arrival` to surface the page only when the next flight is close, rather than when AirLabs happens to add a flight to its look-ahead window.

The one-hour default refresh uses no more than 744 scheduled requests during a 31-day month. Lower it only after checking the allowance associated with your API key.

## Configuration

| Setting | Default | Description |
|---|---:|---|
| AirLabs API Key | Required | API credential entered in the UI or `AIRLABS_API_KEY` |
| Board Type | Departures | Select departures or arrivals |
| Airport | SEA | Three-letter IATA airport code |
| Airport Timezone | America/Los_Angeles | Timezone used to classify upcoming and recent flights |
| Maximum Flights | 2 | Maximum deduplicated flights returned |
| Keep Recent Flights | 45 minutes | Grace period for recently departed or arrived flights |
| Refresh Interval | 3,600 seconds | AirLabs polling interval |

Existing installations remain in departure mode automatically. The underlying `max_departures` and `recent_departure_minutes` setting names are retained so saved configurations continue to work unchanged.

## Features

- Selectable scheduled commercial departure or arrival boards
- Codeshare deduplication with primary-flight preference
- Direction-aware status, time, terminal, gate, and baggage data
- Estimated and actual flight time handling
- Optional recent-flight grace period
- Note and Flagship demo layouts
- One schedule request per refresh in either mode
- API errors that avoid exposing credentials

See [docs/SETUP.md](docs/SETUP.md) for setup details.

## Author

Jonathan Breedlove
