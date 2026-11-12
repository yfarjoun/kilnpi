# Staging instance on the Pi

A parallel `kilnpi-staging` systemd unit runs a second copy of the backend on
the Pi, isolated from the production service. Used to validate DB migrations
and API/UI changes against a copy of the live database before touching prod.

## What staging gives up

- **No real Modbus.** The single RS485 serial port can only have one owner; it
  stays with the prod service. Staging runs `MOCK_CONTROLLER=1`, so the poller
  returns mock values. That is enough to exercise the DB, API, WebSocket, and
  frontend end-to-end, but not the SP interpolation logic against real segment
  reads.
- **No OLED or buttons.** `KILN_HEADLESS=1` skips the SPI display and GPIO
  button init, so staging doesn't fight prod over `/dev/spi*` or the HAT GPIOs.
- **No splash hand-off.** The ready sentinel `/tmp/kilnpi-ready` is not
  touched, so prod's splash-service handshake is unaffected.

## One-time setup (on the Pi)

```
ssh farjoun@kiln.local

# Separate checkout at ~/kilnpi-staging, matching the service WorkingDirectory.
git clone <repo-url> ~/kilnpi-staging
cd ~/kilnpi-staging
uv sync --extra dev
mkdir -p data

# Install the staging unit.
cp kilnpi-staging.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable kilnpi-staging.service
```

The unit listens on port 8001; browse it at `http://kiln.local:8001/`.
Production remains on port 8000.

## Using staging to rehearse a change

1. On the Pi, update the staging checkout to the branch you want to test:
   ```
   cd ~/kilnpi-staging
   git fetch && git checkout <branch>
   uv sync   # only if deps changed
   ```

2. Seed the staging DB from a copy of the live DB (so the migration runs
   against real data layout, and the History/Monitor views have content):
   ```
   sudo systemctl --user stop kilnpi-staging   # release the DB file
   cp ~/kilnpi/data/kiln.db ~/kilnpi-staging/data/kiln-staging.db
   sudo systemctl --user start kilnpi-staging
   journalctl --user -u kilnpi-staging -n 100 -f
   ```
   Confirm the migration log line, then:
   ```
   sqlite3 ~/kilnpi-staging/data/kiln-staging.db '.indexes readings'
   # expect: idx_readings_firing_ts
   ```

3. Browse `http://kiln.local:8001/` and exercise History (old firings load,
   `(manual)` ones render), Monitor (range selector preload works), CSV
   export, notes patch, etc.

## Promoting to production

Once staging is green, deploy to prod with a backup-and-swap under a stopped
service (do NOT do this while firing):

```
sudo systemctl --user stop kilnpi
cp ~/kilnpi/data/kiln.db ~/kilnpi/data/kiln.db.$(date +%F).bak
cd ~/kilnpi
git fetch && git checkout <sha>
uv sync   # if deps changed
sudo systemctl --user start kilnpi
journalctl --user -u kilnpi -n 100 -f
```

If anything throws on startup, stop the service, `mv` the backup DB back,
`git checkout -` and restart.

## Validating the Modbus-dependent changes

The SP interpolation and segment-read locking cannot be validated against
mock data. Options, in order of safety:

- **Dry-read during idle:** pause prod briefly (stop `kilnpi`, run staging
  with `MOCK_CONTROLLER=0` for a few polls, stop staging, restart prod). The
  poller will read the controller's current state without starting a firing.
- **Full firing on staging:** stop prod, run staging with real controller for
  a short test firing, then swap back. Higher risk — the staging DB captures
  the firing, and recovering it to prod means merging DB files.

In practice: for a change like this one (new reads are additive, lock
discipline is tightened not loosened), the dry-read is usually enough.
