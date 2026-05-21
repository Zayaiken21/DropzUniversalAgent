from datetime import datetime, timezone
from zoneinfo import ZoneInfo

EST = ZoneInfo("America/New_York")

def utc_now():
    return datetime.now(timezone.utc)

def iso_utc_now():
    return utc_now().isoformat()

def to_est_label(utc_iso):
    dt = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
    return dt.astimezone(EST).strftime("%Y-%m-%d %I:%M %p %Z")

def to_local_label(utc_iso, tz_name=None):
    dt = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
    if tz_name:
        try:
            tz = ZoneInfo(tz_name)
            return dt.astimezone(tz).strftime("%Y-%m-%d %I:%M %p %Z")
        except Exception:
            pass
    return to_est_label(utc_iso)