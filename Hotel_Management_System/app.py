"""
Web-Based Hotel Management System
Built with Python + Flask. All data is stored in hotel_records.csv.

Run:   python app.py
Open:  http://127.0.0.1:5000
"""
import csv
import os
from datetime import date, datetime

from flask import Flask, flash, redirect, render_template, request, url_for

app = Flask(__name__)
app.secret_key = "hotel-management-secret-key"

# ------------------------------------------------------------------
# SETTINGS  (change names here to match your own files and hotel)
# ------------------------------------------------------------------
HOTEL_NAME = "Grand Oasis Hotel"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RECORDS_FILE = os.path.join(BASE_DIR, "hotel_records.csv")

FIELDS = ["booking_id", "name", "phone", "id_proof", "room_no", "room_type",
          "check_in", "check_out", "nights", "room_charge", "food_charge",
          "orders", "status"]

# File names of the pictures inside the static folder
IMAGES = {
    "logo": "logo.png",
    "banner": "banner.jpg",
    "hotel": "hotel.jpg",
    "restaurant": "restaurant.jpg",
}

# Room types: price per night and the picture shown for that type
ROOM_TYPES = {
    "Single": {"price": 5000, "image": "room_single.jpg"},
    "Double": {"price": 8000, "image": "room_double.jpg"},
    "Suite": {"price": 15000, "image": "room_suite.jpg"},
}

# Room number -> room type
ROOMS = {
    "101": "Single", "102": "Double", "103": "Single", "104": "Double",
    "201": "Suite", "202": "Suite", "203": "Double", "204": "Single",
}

# Restaurant menu: item -> price
MENU = {
    "Chicken Biryani": 350,
    "Grilled Fish": 450,
    "Club Sandwich": 250,
    "Pasta Alfredo": 300,
    "Fresh Salad": 150,
    "Tea": 50,
    "Coffee": 80,
    "Fresh Juice": 120,
}


# ------------------------------------------------------------------
# FILE HANDLING FUNCTIONS (CSV)
# ------------------------------------------------------------------
def read_records():
    """Return every row of hotel_records.csv as a list of dictionaries."""
    try:
        with open(RECORDS_FILE, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return []


def write_records(rows):
    """Rewrite the whole CSV file with the given list of dictionaries."""
    with open(RECORDS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, restval="",
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def append_record(row):
    """Add one new row at the end of the CSV file."""
    records = read_records()
    records.append(row)
    write_records(records)


# ------------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------------
def parse_date(text):
    """Convert 'YYYY-MM-DD' text into a date. Raises ValueError if wrong."""
    return datetime.strptime(text, "%Y-%m-%d").date()


def to_int(value):
    """Convert text to int, returning 0 when it is empty or invalid."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def next_booking_id(records):
    numbers = [int(r["booking_id"][1:]) for r in records
               if r.get("booking_id", "")[1:].isdigit()]
    return "B{:03d}".format(max(numbers, default=0) + 1)


def room_is_free(room_no, check_in, check_out, records):
    """False if an active booking for this room overlaps the new dates."""
    for r in records:
        if r.get("room_no") == room_no and r.get("status") == "Checked-in":
            try:
                old_in = parse_date(r["check_in"])
                old_out = parse_date(r["check_out"])
            except (ValueError, KeyError):
                continue
            if check_in < old_out and old_in < check_out:
                return False
    return True


def is_in_house(record):
    """True if the guest has arrived (check-in date reached) and not left."""
    if record.get("status") != "Checked-in":
        return False
    try:
        return parse_date(record["check_in"]) <= date.today()
    except (ValueError, KeyError):
        return False


def find_in_house(room_no, records):
    """Return the in-house booking dictionary for a room, or None."""
    for r in records:
        if r.get("room_no") == room_no and is_in_house(r):
            return r
    return None


def room_status_map(records):
    """Room number -> 'Available', 'Reserved' or 'Occupied' (as of today)."""
    status = {no: "Available" for no in ROOMS}
    today = date.today()
    for r in records:
        no = r.get("room_no")
        if r.get("status") != "Checked-in" or no not in status:
            continue
        try:
            arrival = parse_date(r["check_in"])
        except (ValueError, KeyError):
            continue
        if arrival <= today:
            status[no] = "Occupied"
        elif status[no] != "Occupied":
            status[no] = "Reserved"
    return status


def room_options(records):
    """List of rooms with price and today's status, used by forms."""
    status = room_status_map(records)
    options = []
    for no, rtype in ROOMS.items():
        options.append({"no": no, "type": rtype,
                        "price": ROOM_TYPES[rtype]["price"],
                        "status": status[no]})
    return options


def make_bill(booking):
    """Build a bill dictionary from one booking row."""
    room_charge = to_int(booking.get("room_charge"))
    food_charge = to_int(booking.get("food_charge"))
    orders = [o.strip() for o in booking.get("orders", "").split(";")
              if o.strip()]
    return {"booking": booking, "room_charge": room_charge,
            "food_charge": food_charge, "orders": orders,
            "total": room_charge + food_charge}


@app.context_processor
def inject_globals():
    """Variables available in every template."""
    return {"hotel_name": HOTEL_NAME, "images": IMAGES,
            "today": date.today().isoformat()}


# ------------------------------------------------------------------
# ROUTES
# ------------------------------------------------------------------
@app.route("/")
def home():
    records = read_records()
    status = room_status_map(records)
    rooms = []
    for no, rtype in ROOMS.items():
        rooms.append({"no": no, "type": rtype,
                      "price": ROOM_TYPES[rtype]["price"],
                      "image": ROOM_TYPES[rtype]["image"],
                      "status": status[no]})
    stats = {
        "total": len(rooms),
        "available": sum(1 for r in rooms if r["status"] == "Available"),
        "occupied": sum(1 for r in rooms if r["status"] == "Occupied"),
        "guests": sum(1 for r in records if is_in_house(r)),
    }
    return render_template("home.html", rooms=rooms, stats=stats)


@app.route("/book", methods=["GET", "POST"])
def book_room():
    records = read_records()
    form = {"name": "", "phone": "", "id_proof": "", "check_in": "",
            "check_out": "", "room_no": request.args.get("room", "")}

    if request.method == "POST":
        for key in ("name", "phone", "id_proof", "room_no",
                    "check_in", "check_out"):
            form[key] = request.form.get(key, "").strip()
        phone = form["phone"].replace(" ", "").lstrip("+")
        errors = []

        if not form["name"]:
            errors.append("Enter the guest's name.")
        if not (phone.isdigit() and 7 <= len(phone) <= 15):
            errors.append("Enter a phone number with 7 to 15 digits.")
        if not form["id_proof"]:
            errors.append("Enter the guest's ID proof number.")
        if form["room_no"] not in ROOMS:
            errors.append("Choose a room from the list.")

        check_in = check_out = None
        try:
            check_in = parse_date(form["check_in"])
            check_out = parse_date(form["check_out"])
            if check_in < date.today():
                errors.append("Check-in date cannot be in the past.")
            if check_out <= check_in:
                errors.append("Check-out must be after the check-in date.")
        except ValueError:
            errors.append("Enter valid check-in and check-out dates.")

        if not errors and not room_is_free(form["room_no"], check_in,
                                           check_out, records):
            errors.append("Room {} is already booked for those dates. "
                          "Choose another room or different dates."
                          .format(form["room_no"]))

        if errors:
            for message in errors:
                flash(message, "error")
        else:
            rtype = ROOMS[form["room_no"]]
            nights = (check_out - check_in).days
            booking_id = next_booking_id(records)
            append_record({
                "booking_id": booking_id,
                "name": form["name"],
                "phone": phone,
                "id_proof": form["id_proof"],
                "room_no": form["room_no"],
                "room_type": rtype,
                "check_in": check_in.isoformat(),
                "check_out": check_out.isoformat(),
                "nights": nights,
                "room_charge": nights * ROOM_TYPES[rtype]["price"],
                "food_charge": 0,
                "orders": "",
                "status": "Checked-in",
            })
            flash("Booking {} saved. Room {} is reserved for {} night(s)."
                  .format(booking_id, form["room_no"], nights), "success")
            return redirect(url_for("guests", q=booking_id))

    options = room_options(records)
    prices = {o["no"]: o["price"] for o in options}
    return render_template("book.html", form=form, options=options,
                           prices=prices)


@app.route("/guests")
def guests():
    query = request.args.get("q", "").strip().lower()
    rows = read_records()
    if query:
        rows = [r for r in rows if query in " ".join(
            r.get(k, "") for k in ("booking_id", "name", "phone", "room_no")
        ).lower()]
    rows.reverse()  # newest first
    return render_template("guests.html", rows=rows, q=query)


@app.route("/restaurant", methods=["GET", "POST"])
def restaurant():
    records = read_records()

    if request.method == "POST":
        room_no = request.form.get("room_no", "")
        item = request.form.get("item", "")
        qty = to_int(request.form.get("qty", "1"))
        booking = find_in_house(room_no, records)

        if booking is None:
            flash("Room {} has no guest staying right now.".format(room_no),
                  "error")
        elif item not in MENU:
            flash("Choose an item from the menu.", "error")
        elif not 1 <= qty <= 50:
            flash("Quantity must be between 1 and 50.", "error")
        else:
            cost = MENU[item] * qty
            booking["food_charge"] = str(to_int(booking.get("food_charge"))
                                         + cost)
            entry = "{} x{}".format(item, qty)
            old = booking.get("orders", "")
            booking["orders"] = old + "; " + entry if old else entry
            write_records(records)
            flash("Added {} to room {}. Amount: {}."
                  .format(entry, room_no, cost), "success")
        return redirect(url_for("restaurant"))

    in_house = [r for r in records if is_in_house(r)]
    return render_template("restaurant.html", menu=MENU, in_house=in_house)


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    records = read_records()

    if request.method == "POST":
        room_no = request.form.get("room_no", "")
        booking = find_in_house(room_no, records)
        if booking is None:
            flash("Room {} has no guest staying right now."
                  .format(room_no), "error")
            return redirect(url_for("checkout"))
        return render_template("bill.html", bill=make_bill(booking),
                               final=False)

    in_house = [r for r in records if is_in_house(r)]
    return render_template("checkout.html", in_house=in_house)


@app.route("/checkout/confirm", methods=["POST"])
def confirm_checkout():
    records = read_records()
    booking_id = request.form.get("booking_id", "")
    for r in records:
        if r.get("booking_id") == booking_id and r.get("status") == "Checked-in":
            r["status"] = "Checked-out"
            write_records(records)
            flash("Room {} is now available.".format(r["room_no"]),
                  "success")
            return render_template("bill.html", bill=make_bill(r),
                                   final=True)
    flash("That booking was not found or is already checked out.", "error")
    return redirect(url_for("checkout"))


if __name__ == "__main__":
    app.run(debug=True)
