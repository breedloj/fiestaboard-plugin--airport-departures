# Airport Departures and Arrivals Setup

![Airport Departures on a Vestaboard Note](./board-display.png)

1. Create an AirLabs account and API key at <https://airlabs.co>.
2. Install this plugin from its public GitHub HTTPS URL.
3. Open **Integrations** and enable **Airport Departures**.
4. Enter the API key and a three-letter airport such as `PAE`.
5. Choose **Departures** or **Arrivals** under **Board Type**.
6. Set the airport's IANA timezone, such as `America/Los_Angeles`.
7. Set **Maximum Flights** to `2` and **Keep Recent Flights** to `0` for upcoming flights only.
8. Start with the one-hour refresh interval so a free allowance is not consumed accidentally.

## Recommended Note Page

```text
{{airport_departures.line1}}
{{airport_departures.line2}}
{{airport_departures.line3}}
```

The first row identifies the airport and direction. The next two rows show the earliest relevant scheduled airline flights and their best known times. Departure rows show destinations; arrival rows show origins. Cancelled flights and rows without published airline and flight IATA identifiers are excluded.

Departure example:

```text
PAE DEPARTURES
AS2248 SFO 1910
AS2055 LAX 2040
```

Arrival example:

```text
PAE ARRIVALS
AS2248 SFO 2144
AS2055 LAX 2230
```

## Advanced Templates

Structured departures are available by fixed index:

```text
{{airport_departures.departures.0.flight}}
{{airport_departures.departures.0.destination}}
{{airport_departures.departures.0.status_label}}
```

Additional fields include `display_time`, `compact_time`, `scheduled_time`, `estimated_time`, `terminal`, `gate`, `delay_minutes`, and `status_color`.

Structured arrivals use the parallel `arrivals` array:

```text
{{airport_departures.arrivals.0.flight}}
{{airport_departures.arrivals.0.origin}}
{{airport_departures.arrivals.0.display_time}}
```

Arrivals may also expose `baggage` when the provider includes a carousel.

To select this page only when a departure is within two hours, use this variable-collection rule:

```text
AND(airport_departures.departure_count > 0, airport_departures.minutes_until_departure >= 0, airport_departures.minutes_until_departure <= 120)
```

For an arrival board, use:

```text
AND(airport_departures.arrival_count > 0, airport_departures.minutes_until_arrival >= 0, airport_departures.minutes_until_arrival <= 120)
```

## API Limits

AirLabs controls request allowances. FiestaBoard caches this plugin according to the configured refresh interval. At the default 3,600 seconds, the theoretical maximum is 24 requests per day.

The plugin fetches only the selected board type, so choosing arrivals uses the same one-request-per-refresh pattern as departures.

## Upgrading from 1.2

No configuration changes are required. Installations without a saved **Board Type** continue to use departures, and all existing departure variables and templates retain their previous behavior. Arrivals are opt-in.

## Troubleshooting

### No departures appear

- Confirm the airport uses scheduled airline service and the IATA code is correct.
- Set **Keep Recent Flights** to `0` when you only want future departures.
- AirLabs generally exposes a limited look-ahead window, so a quiet airport may legitimately have no returned flights yet.
- Private, positioning, and other rows without published airline identifiers are intentionally excluded.

### No arrivals appear

- Confirm **Board Type** is set to **Arrivals**.
- Confirm the airport and timezone are correct.
- AirLabs may not expose the next arrival yet at airports with sparse airline service.
- Set **Keep Recent Flights** to `0` when you only want flights that have not arrived.

### The same physical flight has multiple numbers

AirLabs may return marketing, operating, and partner codeshares separately. The plugin groups records sharing the same operating service, counterpart airport, and scheduled time, then prefers the primary marketing listing.

### AirLabs returns an error

- Re-enter the API key in **Integrations**.
- Confirm the key's request allowance has not been exhausted.
- Increase the refresh interval before retrying if the provider reports a rate limit.
