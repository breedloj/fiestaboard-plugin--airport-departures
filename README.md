# Airport Departures for FiestaBoard

An installable FiestaBoard plugin for scheduled airline departure boards. Unlike nearby-aircraft plugins, it uses an airport schedule feed and exposes flight number, destination, time, delay, terminal, gate, and operational status. Rows without published airline and flight IATA identifiers are excluded, and codeshare listings for the same physical departure are combined.

![Airport Departures on a Vestaboard Note](./docs/board-display.png)

## Data Provider

Version 1 uses the [AirLabs Schedules API](https://airlabs.co/docs/schedules). AirLabs currently returns live schedule data up to roughly ten hours ahead and offers a free key for development and low-volume personal use.

The provider adapter is isolated in `provider.py`, so another vendor can be added without changing the FiestaBoard variables or templates.

## Install

Install the repository's HTTPS URL from FiestaBoard's **Integrations** page:

```text
https://github.com/breedloj/fiestaboard-plugin--airport-departures
```

An AirLabs API key is required.

## Template Variables

### Next Departure

| Variable | Description | Example |
|---|---|---|
| `{{airport_departures.airport}}` | Configured departure airport | `PAE` |
| `{{airport_departures.flight}}` | Preferred flight number after codeshare grouping | `AS2248` |
| `{{airport_departures.destination}}` | Destination IATA code | `SFO` |
| `{{airport_departures.display_time}}` | Best known local departure time | `9:44 PM` |
| `{{airport_departures.status_label}}` | Human-readable operational status | `ON TIME` |
| `{{airport_departures.minutes_until_departure}}` | Minutes until the next departure, or `-1` | `90` |
| `{{airport_departures.departures}}` | Ordered, deduplicated departures | array |

### Ready-to-Display

| Variable | Description | Maximum |
|---|---|---|
| `{{airport_departures.line1}}` | Note-ready airport header | 15 tiles |
| `{{airport_departures.line2}}` | First Note-ready departure | 15 tiles |
| `{{airport_departures.line3}}` | Second Note-ready departure | 15 tiles |
| `{{airport_departures.formatted}}` | Compact primary departure | 22 tiles |

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

Variable-mode collections can use `airport_departures.minutes_until_departure` to surface the page only when the next flight is close, rather than when AirLabs happens to add a flight to its look-ahead window.

The one-hour default refresh uses no more than 744 scheduled requests during a 31-day month. Lower it only after checking the allowance associated with your API key.

## Configuration

| Setting | Default | Description |
|---|---:|---|
| AirLabs API Key | Required | API credential entered in the UI or `AIRLABS_API_KEY` |
| Departure Airport | SEA | Three-letter IATA airport code |
| Airport Timezone | America/Los_Angeles | Timezone used to classify upcoming and recent departures |
| Maximum Departures | 2 | Maximum deduplicated departures returned |
| Keep Recent Departures | 45 minutes | Grace period for recently delayed or departed flights |
| Refresh Interval | 3,600 seconds | AirLabs polling interval |

## Features

- Scheduled commercial departures rather than nearby airborne traffic
- Codeshare deduplication with primary-flight preference
- Estimated and actual departure time handling
- Optional recent-departure grace period
- Note and Flagship demo layouts
- API errors that avoid exposing credentials

See [docs/SETUP.md](docs/SETUP.md) for setup details.

## Author

Jonathan Breedlove
