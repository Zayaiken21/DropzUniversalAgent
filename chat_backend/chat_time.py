from datetime import datetime, timezone
from zoneinfo import ZoneInfo

EST = ZoneInfo("America/New_York")


def utc_now():
    return datetime.now(timezone.utc)


def iso_utc_now():
    return utc_now().isoformat()


def to_est_label(utc_iso):
    if not utc_iso:
        return ""
    dt = datetime.fromisoformat(str(utc_iso).replace("Z", "+00:00"))
    return dt.astimezone(EST).strftime("%m/%d/%Y %I:%M %p")


def to_local_label(utc_iso, tz_name=None):
    if not utc_iso:
        return ""
    dt = datetime.fromisoformat(str(utc_iso).replace("Z", "+00:00"))
    if tz_name:
        try:
            return dt.astimezone(ZoneInfo(tz_name)).strftime("%m/%d/%Y %I:%M %p")
        except Exception:
            pass
    return to_est_label(utc_iso)
