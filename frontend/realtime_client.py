class RealtimeClient:
    """Compatibility stub. Chat is now Streamlit-only; no websocket server is required."""
    def __init__(self, ws_url=None):
        self.ws_url = ws_url

    def safe_send(self, payload):
        return True

    def send_chat(self, *args, **kwargs):
        return True

    def send_presence(self, *args, **kwargs):
        return True
