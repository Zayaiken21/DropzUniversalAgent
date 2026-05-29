# TradeSmart Safe Connector

This package creates a safe per-user MT5 connection:

```txt
Streamlit Cloud
→ Relay Server
→ User's ngrok tunnel
→ User's Windows Connector
→ User's MT5 terminal
```

## Safety rules

- MetaTrader5 is imported only on the user's Windows PC.
- XAUUSD only.
- Bearer token required for every bridge request.
- No shell command endpoints.
- No filesystem endpoints.
- No remote desktop.
- Rate limits enabled.
- Audit log saved locally in `local_windows_connector/logs/`.

## User setup

1. Install MetaTrader 5.
2. Install Python.
3. Install ngrok and log in with ngrok.
4. Copy `local_windows_connector/.env.example` to `.env`.
5. Fill:
   - `RELAY_URL`
   - `RELAY_TOKEN` or `PAIRING_CODE`
   - `TRADESMART_USER_KEY`
6. Double-click `start_connector.bat`.

The connector starts:
- local bridge on `127.0.0.1:8000`
- ngrok tunnel
- automatic registration to relay

## Relay setup

Run `relay_server/tradesmart_relay_server.py` somewhere reachable by Streamlit.

Environment:

```env
RELAY_TOKEN=use_a_long_secret
TRADESMART_RELAY_FERNET_KEY=generate_with_cryptography_fernet
RELAY_HOST=0.0.0.0
RELAY_PORT=8010
```

Streamlit env/secrets:

```env
TRADESMART_RELAY_URL=https://your-relay-url
TRADESMART_RELAY_TOKEN=use_a_long_secret
```

## Generate Fernet key

```python
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
```
