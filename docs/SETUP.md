# Airport Departures Setup

1. Create an AirLabs account and API key at <https://airlabs.co>.
2. Install this plugin from its public GitHub HTTPS URL.
3. Open **Integrations** and enable **Airport Departures**.
4. Enter the API key and a three-letter departure airport such as `PAE`.
5. Set the airport's IANA timezone, such as `America/Los_Angeles`.
6. Set **Maximum Departures** to `2` and **Keep Recent Departures** to `0`.
7. Start with the one-hour refresh interval so a free allowance is not consumed accidentally.

## Recommended Note Page

```text
{{airport_departures.line1}}
{{airport_departures.line2}}
{{airport_departures.line3}}
```

The first row identifies the airport. The next two rows show the earliest upcoming scheduled airline departures and their best known times. Cancelled flights and rows without published airline and flight IATA identifiers are excluded.

## Advanced Templates

Structured departures are available by fixed index:

```text
{{airport_departures.departures.0.flight}}
{{airport_departures.departures.0.destination}}
{{airport_departures.departures.0.status_label}}
```

Additional fields include `display_time`, `compact_time`, `scheduled_time`, `estimated_time`, `terminal`, `gate`, `delay_minutes`, and `status_color`.

## API Limits

AirLabs controls request allowances. FiestaBoard caches this plugin according to the configured refresh interval. At the default 3,600 seconds, the theoretical maximum is 24 requests per day.
