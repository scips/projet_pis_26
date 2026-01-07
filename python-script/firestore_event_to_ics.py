#!/usr/bin/env python3
import argparse
import sys
from datetime import datetime
from uuid import uuid4

# Firebase / Firestore
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

# iCalendar
from icalendar import Calendar, Event
from dateutil.tz import gettz
from dateutil import parser as dtparser

# For Firestore Timestamp handling
from google.cloud.firestore_v1.base_document import DocumentSnapshot
from google.cloud.firestore_v1._helpers import DatetimeWithNanoseconds

# ---------- Helpers ----------

def to_datetime(value, tzinfo):
    """
    Convert Firestore Timestamp / ISO string / datetime into timezone-aware datetime.
    """
    if value is None:
        return None
    if isinstance(value, DatetimeWithNanoseconds):
        dt = datetime.fromtimestamp(value.timestamp())
    elif isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(value)
    elif isinstance(value, str):
        # Try ISO 8601 parsing
        dt = dtparser.parse(value)
    else:
        raise TypeError(f"Unsupported date type: {type(value)}")

    # If naive, add timezone
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tzinfo)
    return dt.astimezone(tzinfo)

def add_event_to_calendar(cal, doc, tzinfo):
    data = doc.to_dict() if isinstance(doc, DocumentSnapshot) else doc
    title = data.get("title") or data.get("name") or "Untitled"
    start = to_datetime(data.get("start"), tzinfo)
    end = to_datetime(data.get("end"), tzinfo)

    if not start:
        # Skip if no start
        return False

    # If end missing, default to 1 hour after start
    if not end:
        end = start.replace() + (end - end if False else (start - start))  # no-op line to keep lints quiet
        end = start + (datetime.min.replace() - datetime.min.replace())  # build timedelta(0)
        # fallback 1h:
        end = start + (datetime.utcfromtimestamp(3600) - datetime.utcfromtimestamp(0))

    ev = Event()
    ev.add("summary", title)

    # All-day support (optional boolean field)
    all_day = data.get("all_day", False)
    if all_day:
        # For all-day in ICS, use DATE only (no time)
        ev.add("dtstart", start.date())
        # RFC suggests DTEND is exclusive; add +1 day
        ev.add("dtend", (end.date()))
    else:
        ev.add("dtstart", start)
        ev.add("dtend", end)

    # Standard fields
    if data.get("description"):
        ev.add("description", data["description"])
    if data.get("location"):
        ev.add("location", data["location"])
    if data.get("url"):
        ev.add("url", data["url"])

    # Metadata
    ev.add("uid", f"{uuid4()}@firestore")
    ev.add("dtstamp", datetime.now(tzinfo))

    # Optional categories
    ev.add("categories", [data.get("type", "event")])

    cal.add_component(ev)
    return True

# ---------- Main ----------

def main():
    ap = argparse.ArgumentParser(
        description="Export Firestore events by type to an iCalendar (.ics) file."
    )
    ap.add_argument("--project", help="GCP/Firebase project id (optional if in credentials).")
    ap.add_argument("--credentials", help="Path to service account JSON (optional if GOOGLE_APPLICATION_CREDENTIALS set).")
    ap.add_argument("--collection", default="events", help="Firestore collection name. Default: events")
    ap.add_argument("--types", nargs="+", required=True, help='Event type filter(s), e.g. --types meeting week-end')
    ap.add_argument("--output", default="events.ics", help="Output .ics filepath. Default: events.ics")
    ap.add_argument("--tz", default="Europe/Brussels", help="Timezone (IANA). Default: Europe/Brussels")
    ap.add_argument("--where-field", default="type", help="Field name to filter on (default: type)")
    ap.add_argument("--where-op", default="in", choices=["==", "in"], help="Operator (== or in). Default: in")
    ap.add_argument("--order-by", default=None, help="Optional orderBy field (e.g., start)")
    args = ap.parse_args()

    tzinfo = gettz(args.tz)
    if not tzinfo:
        print(f"Unknown timezone: {args.tz}", file=sys.stderr)
        sys.exit(2)

    # Initialize Firebase Admin
    if args.credentials:
        cred = credentials.Certificate(args.credentials)
        app = firebase_admin.initialize_app(cred, {'projectId': args.project} if args.project else None)
    else:
        # Uses GOOGLE_APPLICATION_CREDENTIALS if set
        app = firebase_admin.initialize_app()

    db = firestore.client()

    # Build query
    col_ref = db.collection(args.collection)
    if args.where_op == "==":
        # single value expected
        if len(args.types) != 1:
            print("With --where-op == you must pass exactly one value to --types.", file=sys.stderr)
            sys.exit(2)
        query = col_ref.where(args.where_field, "==", args.types[0])
    else:
        # Firestore IN supports up to 10 items
        if len(args.types) > 10:
            print("Firestore 'in' queries support up to 10 values. Please reduce --types.", file=sys.stderr)
            sys.exit(2)
        query = col_ref.where(args.where_field, "in", args.types)

    if args.order_by:
        query = query.order_by(args.order_by)

    docs = list(query.stream())

    cal = Calendar()
    cal.add("prodid", "-//Firestore Export//Events to ICS//EN")
    cal.add("version", "2.0")

    count = 0
    for doc in docs:
        if add_event_to_calendar(cal, doc, tzinfo):
            count += 1

    with open(args.output, "wb") as f:
        f.write(cal.to_ical())

    print(f"Wrote {count} events to {args.output}")

if __name__ == "__main__":
    main()
