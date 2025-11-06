\
import os
import csv
import io
import logging
from datetime import datetime, date
from contextlib import contextmanager

from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint, func, case, text
from sqlalchemy.exc import OperationalError
from dotenv import load_dotenv

# ------------------ Config ------------------
load_dotenv()
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "saree_crm.db")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")
LOG_FILE = os.getenv("LOG_FILE", os.path.join(BASE_DIR, "logs", "crm.log"))
BACKUP_DIR = os.getenv("BACKUP_DIR", os.path.join(BASE_DIR, "backups"))

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")

# --- INR formatter for Indian commas (e.g., 12,21,507) ---
def format_inr(value):
    try:
        n = int(value or 0)
    except (TypeError, ValueError):
        n = 0
    s = str(n)
    if len(s) <= 3:
        return s
    last3 = s[-3:]
    rest = s[:-3]
    parts = []
    while len(rest) > 2:
        parts.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        parts.insert(0, rest)
    return ",".join(parts + [last3])

# make available in Jinja:  {{ amount|inr }}
app.jinja_env.filters['inr'] = format_inr

# --- Badge helpers for status coloring ---
def payment_badge(s: str) -> str:
    m = {"Paid": "text-success fw-semibold",
         "Pending": "text-danger fw-semibold"}
    return m.get(s or "", "text-muted")

def delivery_badge(s: str) -> str:
    m = {"Pending": "text-warning fw-semibold",
         "Shipped": "text-info fw-semibold",
         "Delivered": "text-success fw-semibold",
         "Cancelled": "text-danger fw-semibold",
         "Failed": "text-danger fw-semibold"}
    return m.get(s or "", "text-muted")

app.jinja_env.filters["pay_badge"] = payment_badge
app.jinja_env.filters["delv_badge"] = delivery_badge




# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("vihaa.vastra_sarees")

db = SQLAlchemy(app)

# ------------------ Models ------------------
class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, index=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    instagram = db.Column(db.String(120), default="None")
    phone = db.Column(db.String(20), nullable=True)
    city = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    orders = db.relationship("Order", backref="customer", lazy=True, cascade="all, delete-orphan")

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.String(30), unique=True, index=True, nullable=False)
    date = db.Column(db.Date, default=date.today, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    saree_type = db.Column(db.String(120), nullable=False)  # e.g., Banarasi, Silk
    amount = db.Column(db.Integer, nullable=False, default=0)
    purchase = db.Column(db.String(20), default="Online")  # Online/Offline
    payment_status = db.Column(db.String(20), default="Pending")  # Paid/Pending
    payment_mode = db.Column(db.String(20), default="Pending")  # UPI/Cash/Pending
    delivery_status = db.Column(db.String(20), default="Pending")  # Delivered/Cancelled/Pending
    remarks = db.Column(db.String(255), default="")

    __table_args__ = (
        CheckConstraint("amount >= 0", name="check_amount_nonnegative"),
    )

class FollowUp(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    due_date = db.Column(db.Date, nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    notes = db.Column(db.String(255), default="")
    status = db.Column(db.String(20), default="Open")  # Open/Done
    customer = db.relationship("Customer")


# --- Delivery timeline log ---
class DeliveryLog(db.Model):
    __tablename__ = "delivery_log"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), index=True, nullable=False)
    when = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(32), nullable=False)  # Pending/Packed/Shipped/Out for Delivery/Delivered/Cancelled/Failed
    note = db.Column(db.String(200))

# ------------------ Helpers ------------------
def ensure_columns():
    """SQLite-safe ensure new columns exist without breaking existing DB."""
    # Example no-op; kept for future migrations
    pass

def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

@contextmanager
def app_context():
    with app.app_context():
        yield

# ------------------ Routes ------------------
@app.route("/")
def home():
    return redirect(url_for("dashboard"))

@app.route("/dashboard")
def dashboard():
    # Summary cards
    total_customers = db.session.scalar(db.select(func.count(Customer.id))) or 0
    total_orders = db.session.scalar(db.select(func.count(Order.id))) or 0
    total_sales = db.session.scalar(db.select(func.coalesce(func.sum(
        case(
            (Order.payment_status == "Paid", Order.amount),
            else_=0
        )
    ), 0))) or 0
    avg_order = db.session.scalar(db.select(func.coalesce(func.avg(Order.amount), 0))) or 0
    pending_payments = db.session.scalar(db.select(func.count()).select_from(Order).where(Order.payment_status == "Pending")) or 0
    pending_delivery = db.session.scalar(db.select(func.count()).select_from(Order).where(Order.delivery_status == "Pending")) or 0
    pending_followups = db.session.scalar(db.select(func.count(FollowUp.id)).where(FollowUp.status=="Open")) or 0

    # Monthly sales (last 4 months)
    monthly = db.session.execute(text("""
        SELECT strftime('%Y-%m', date) AS ym, SUM(amount) AS total
        FROM "order"
        WHERE payment_status='Paid'
        GROUP BY ym
        ORDER BY ym DESC
        LIMIT 6
    """)).mappings().all()
    monthly_chart = {
        "labels": [m["ym"] for m in monthly][::-1],
        "data": [int(m["total"]) for m in monthly][::-1]
    }

    # Saree type distribution
    dist = db.session.execute(text("""
        SELECT saree_type, COUNT(*) as cnt
        FROM "order"
        GROUP BY saree_type
        ORDER BY cnt DESC
        LIMIT 12
    """)).mappings().all()
    type_chart = {
        "labels": [d["saree_type"] for d in dist],
        "data": [int(d["cnt"]) for d in dist]
    }

    return render_template("dashboard.html",
                           total_customers=total_customers,
                           total_orders=total_orders,
                           total_sales=total_sales,
                           avg_order=int(avg_order),
                           pending_payments=pending_payments,
                           pending_delivery=pending_delivery,
                           pending_followups=pending_followups,
                           monthly_chart=monthly_chart,
                           type_chart=type_chart,
                           db_path=DATABASE_URL.replace("sqlite:///", ""))

# ---------------- Customers ----------------
@app.route("/customers", methods=["GET", "POST"])
def customers():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Name is required", "danger")
            return redirect(url_for("customers"))
        code = request.form.get("code") or f"CUST{str(int(datetime.utcnow().timestamp()))[-6:]}"
        c = Customer(
            code=code,
            name=name,
            instagram=request.form.get("instagram") or "None",
            phone=request.form.get("phone"),
            city=request.form.get("city"),
            notes=request.form.get("notes") or ""
        )
        db.session.add(c)
        db.session.commit()
        flash("Customer saved", "success")
        return redirect(url_for("customers"))
    q = request.args.get("q", "").strip()
    query = db.select(Customer).order_by(Customer.id.desc())
    if q:
        like = f"%{q}%"
        query = query.where(
            (Customer.name.ilike(like)) | (Customer.city.ilike(like)) | (Customer.phone.ilike(like)) | (Customer.code.ilike(like))
        )
    items = db.session.execute(query).scalars().all()
    return render_template("customers.html", items=items, q=q)

@app.route("/customers/<int:cid>/delete", methods=["POST"])
def delete_customer(cid):
    c = db.session.get(Customer, cid)
    if not c:
        flash("Customer not found", "warning")
    else:
        db.session.delete(c)
        db.session.commit()
        flash("Customer deleted", "info")
    return redirect(url_for("customers"))

# ---------------- Edit Customer ----------------
@app.route("/customers/<int:cid>/edit", methods=["GET", "POST"])
def edit_customer(cid):
    c = db.session.get(Customer, cid)
    if not c:
        flash("Customer not found", "warning")
        return redirect(url_for("customers"))

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        phone = (request.form.get("phone") or "").strip()
        city = (request.form.get("city") or "").strip()
        instagram = (request.form.get("instagram") or "").strip() or "None"
        notes = (request.form.get("notes") or "").strip()

        if not name:
            flash("Name is required", "danger")
            return redirect(url_for("edit_customer", cid=cid))

        # Enforce unique phone if provided (ignore self)
        if phone:
            exists = db.session.execute(
                db.select(Customer).where(Customer.phone == phone, Customer.id != cid)
            ).scalar()
            if exists:
                flash("Another customer already has this phone number.", "danger")
                return redirect(url_for("edit_customer", cid=cid))

        c.name = name
        c.phone = phone or None
        c.city = city
        c.instagram = instagram
        c.notes = notes

        db.session.commit()
        flash("Customer updated", "success")
        return redirect(url_for("customers"))

    return render_template("customer_edit.html", c=c)


# ---------------- Orders ----------------
@app.route("/orders", methods=["GET", "POST"])
def orders():
    if request.method == "POST":
        # Validation & coercion
        customer_id = safe_int(request.form.get("customer_id"))
        amount = safe_int(request.form.get("amount"))
        order_id = request.form.get("order_id") or f"ORD{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        o = Order(
            order_id=order_id,
            date=datetime.strptime(request.form.get("date") or datetime.today().strftime("%Y-%m-%d"), "%Y-%m-%d"),
            customer_id=customer_id,
            saree_type=request.form.get("saree_type") or "Saree",
            amount=amount,
            purchase=request.form.get("purchase") or "Online",
            payment_status=request.form.get("payment_status") or "Pending",
            payment_mode=request.form.get("payment_mode") or ("Pending" if request.form.get("payment_status")!="Paid" else "UPI"),
            delivery_status=request.form.get("delivery_status") or "Pending",
            remarks=request.form.get("remarks") or ""
        )
        db.session.add(o)
        db.session.commit()
        flash("Order added", "success")
        return redirect(url_for("orders"))
    # Filters
    pay = request.args.get("pay")
    month = request.args.get("month")
    q = db.select(Order).order_by(Order.date.desc(), Order.id.desc())
    if pay in {"Paid","Pending"}:
        q = q.where(Order.payment_status==pay)
    if month:
        q = q.where(text("strftime('%Y-%m', date)=:m")).params(m=month)
    items = db.session.execute(q).scalars().all()
    customers = db.session.execute(db.select(Customer).order_by(Customer.id.desc())).scalars().all()

    return render_template("orders.html", items=items, customers=customers)

@app.route("/orders/<int:oid>/delete", methods=["POST"])
def delete_order(oid):
    o = db.session.get(Order, oid)
    if not o:
        flash("Order not found", "warning")
    else:
        db.session.delete(o)
        db.session.commit()
        flash("Order deleted", "info")
    return redirect(url_for("orders"))
# ---------------- Edit Order ----------------
@app.route("/orders/<int:oid>/edit", methods=["GET","POST"])
def edit_order(oid):
    o = db.session.get(Order, oid)
    if not o:
        flash("Order not found", "warning")
        return redirect(url_for("orders"))

    if request.method == "POST":
        # Update with basic validations
        try:
            o.date = datetime.strptime(request.form.get("date"), "%Y-%m-%d").date()
        except Exception:
            pass  # keep old date if parse fails

        o.customer_id = safe_int(request.form.get("customer_id"), o.customer_id)
        o.saree_type = request.form.get("saree_type") or o.saree_type
        o.amount = safe_int(request.form.get("amount"), o.amount)
        o.purchase = request.form.get("purchase") or o.purchase
        o.payment_status = request.form.get("payment_status") or o.payment_status

        # Couple payment mode with status
        mode = request.form.get("payment_mode") or o.payment_mode
        if o.payment_status == "Pending":
            mode = "Pending"
        o.payment_mode = mode

        o.delivery_status = request.form.get("delivery_status") or o.delivery_status
        o.remarks = request.form.get("remarks") or o.remarks

        db.session.commit()
        flash("Order updated", "success")
        return redirect(url_for("orders"))

    customers = db.session.execute(db.select(Customer).order_by(Customer.name)).scalars().all()
    return render_template("order_edit.html", o=o, customers=customers)


# ---------------- Payments ----------------


from flask import request  # ensure this import exists at top of file

@app.route("/payments")
def payments():
    # Totals
    paid_total = db.session.scalar(
        db.select(db.func.sum(Order.amount)).where(Order.payment_status == "Paid")
    ) or 0
    pending_total = db.session.scalar(
        db.select(db.func.sum(Order.amount)).where(Order.payment_status == "Pending")
    ) or 0

    # Donut: separate UPI, Cash, and Pending
    mode_rows = db.session.execute(db.text("""
        SELECT
            CASE
                WHEN payment_status = 'Pending' THEN 'Pending'
                ELSE payment_mode
            END AS mode,
            SUM(amount) AS total
        FROM "order"
        WHERE payment_status IN ('Paid','Pending')
        GROUP BY mode
        ORDER BY total DESC
    """)).mappings().all()

    donut = {
        "labels": [r["mode"] or "Pending" for r in mode_rows],
        "data":   [int(r["total"] or 0) for r in mode_rows],
    }

    # Monthly chart: Paid amounts per month (YYYY-MM)
    monthly = db.session.execute(db.text("""
        SELECT strftime('%Y-%m', date) AS ym, SUM(amount) AS total
        FROM "order"
        WHERE payment_status = 'Paid'
        GROUP BY ym
        ORDER BY ym
    """)).mappings().all()

    monthly_chart = {
        "labels": [m["ym"] for m in monthly],
        "data":   [int(m["total"] or 0) for m in monthly],
    }

    # Optional filter from URL (?status=Paid|Pending)
    status_filter = request.args.get("status")
    query = db.select(Order).order_by(Order.date.desc(), Order.id.desc())
    if status_filter in {"Paid", "Pending"}:
        query = query.where(Order.payment_status == status_filter)

    items = db.session.execute(query).scalars().all()

    return render_template(
        "payments.html",
        paid_total=int(paid_total or 0),
        pending_total=int(pending_total or 0),
        donut=donut,
        monthly_chart=monthly_chart,
        items=items,
        selected_status=status_filter or "All",
    )

# ---------------- Delivery ----------------
@app.route("/delivery")
def delivery():
    q = request.args.get("q","").strip()
    status = request.args.get("status")
    ptype = request.args.get("ptype")
    courier = request.args.get("courier")
    dfrom = request.args.get("from")
    dto = request.args.get("to")

    # Base query: newest first
    query = db.select(Order).order_by(Order.date.desc(), Order.id.desc())

    # Filters
    if status in {"Pending","Packed","Shipped","Out for Delivery","Delivered","Cancelled","Failed"}:
        query = query.where(Order.delivery_status == status)
    if ptype in {"Online","Offline"}:
        query = query.where(Order.purchase == ptype)
    if courier:
        query = query.where(Order.courier == courier)
    if q:
        like = f"%{q}%"
        # search order_id, tracking_id, or customer name
        query = query.join(Customer).where(
            db.or_(Order.order_id.like(like), Order.tracking_id.like(like), Customer.name.like(like))
        )
    if dfrom:
        query = query.where(db.func.date(db.func.coalesce(Order.shipment_date, Order.date)) >= dfrom)
    if dto:
        query = query.where(db.func.date(db.func.coalesce(Order.shipment_date, Order.date)) <= dto)

    # Execute query
    items = db.session.execute(query).scalars().all()

    # KPI counts (by status)
    def count(s):
        return db.session.scalar(db.select(db.func.count(Order.id)).where(Order.delivery_status == s)) or 0
    kpis = {
        "Pending": count("Pending"),
        "Packed": count("Packed"),
        "Shipped": count("Shipped"),
        "OFD": count("Out for Delivery"),
        "Delivered": count("Delivered"),
        "Cancelled": count("Cancelled"),
        "Failed": count("Failed"),
    }

    # ---------- ADD THIS BLOCK (logs_map) ----------
    # Build a map of logs for only the orders shown on this page
    order_ids = [o.id for o in items]
    logs_map = {}
    if order_ids:
        logs = db.session.execute(
            db.select(DeliveryLog)
              .where(DeliveryLog.order_id.in_(order_ids))
              .order_by(DeliveryLog.when.desc())
        ).scalars().all()
        for lg in logs:
            logs_map.setdefault(lg.order_id, []).append(lg)
    # ---------- END ADD BLOCK ----------

    return render_template(
        "delivery.html",
        items=items,
        kpis=kpis,
        status=status, ptype=ptype, q=q, courier=courier, dfrom=dfrom, dto=dto,
        logs_map=logs_map  # <-- pass it to the template
    )



# ---------------- Follow-ups ----------------
@app.route("/followups", methods=["GET","POST"])
def followups():
    if request.method == "POST":
        f = FollowUp(
            due_date=datetime.strptime(request.form.get("due_date"), "%Y-%m-%d").date(),
            customer_id=safe_int(request.form.get("customer_id")),
            notes=request.form.get("notes") or "",
            status="Open"
        )
        db.session.add(f)
        db.session.commit()
        flash("Follow-up added", "success")
        return redirect(url_for("followups"))
    items = db.session.execute(db.select(FollowUp).order_by(FollowUp.due_date.asc())).scalars().all()
    customers = db.session.execute(db.select(Customer).order_by(Customer.name)).scalars().all()
    return render_template("followups.html", items=items, customers=customers)

@app.route("/followups/<int:fid>/toggle", methods=["POST"])
def followup_toggle(fid):
    f = db.session.get(FollowUp, fid)
    if not f:
        flash("Follow-up not found", "warning")
    else:
        f.status = "Done" if f.status=="Open" else "Open"
        db.session.commit()
        flash("Follow-up updated", "info")
    return redirect(url_for("followups"))
# ---------------- Follow-up Status Update ----------------
@app.route("/followups/<int:fid>/status", methods=["POST"])
def followup_status(fid):
    f = db.session.get(FollowUp, fid)
    if not f:
        flash("Follow-up not found", "warning")
        return redirect(url_for("followups"))
    new_status = request.form.get("status") or "Open"
    # Allow: Open / In Progress / Completed / Closed / Dropped
    allowed = {"Open", "In Progress", "Completed", "Closed", "Dropped"}
    if new_status not in allowed:
        flash("Invalid status", "danger")
        return redirect(url_for("followups"))
    f.status = new_status
    db.session.commit()
    flash("Follow-up status updated", "success")
    return redirect(url_for("followups"))


# ---------------- Reports / Export ----------------
@app.route("/reports")
def reports():
    # Simple KPI for now
    kpis = {
        "total_customers": db.session.scalar(db.select(func.count(Customer.id))) or 0,
        "total_orders": db.session.scalar(db.select(func.count(Order.id))) or 0,
        "paid_revenue": int(db.session.scalar(db.select(func.coalesce(func.sum(
            case((Order.payment_status=="Paid", Order.amount), else_=0)
        ),0))) or 0),
        "pending_amount": int(db.session.scalar(db.select(func.coalesce(func.sum(
            case((Order.payment_status=="Pending", Order.amount), else_=0)
        ),0))) or 0),
    }
    return render_template("reports.html", kpis=kpis)

@app.route("/export/csv")
def export_csv():
    table = request.args.get("table","orders")
    output = io.StringIO()
    writer = csv.writer(output)
    if table == "customers":
        writer.writerow(["ID","Code","Name","Instagram","Phone","City","Notes","Created"])
        for c in db.session.execute(db.select(Customer).order_by(Customer.id)).scalars():
            writer.writerow([c.id, c.code, c.name, c.instagram, c.phone, c.city, c.notes, c.created_at])
    else:
        writer.writerow(["ID","OrderID","Date","CustomerCode","CustomerName","SareeType","Amount","Purchase","PaymentStatus","PaymentMode","DeliveryStatus","Remarks"])
        q = db.session.execute(db.select(Order).order_by(Order.id)).scalars().all()
        for o in q:
            writer.writerow([o.id, o.order_id, o.date, o.customer.code, o.customer.name, o.saree_type, o.amount, o.purchase, o.payment_status, o.payment_mode, o.delivery_status, o.remarks])
    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode("utf-8")), as_attachment=True,
                     download_name=f"{table}.csv", mimetype="text/csv")

# ---------------- Settings ----------------
@app.route("/settings")
def settings():
    return render_template("settings.html", db_path=DATABASE_URL.replace("sqlite:///",""), log_file=LOG_FILE, backup_dir=BACKUP_DIR)

# ---------------- CLI init and seed ----------------
def seed_demo():
    if db.session.scalar(db.select(func.count(Customer.id))) > 0:
        return
    cities = ["Hyderabad","Guntur","Warangal","Vijayawada","Nizamabad","Secunderabad"]
    names = ["Farah Jain","Varsha Khanna","Oviya Kapoor","Oviya Reddy","Varsha Patel","Yamini Jain","Nisha Bhat","Rani Agarwal","Sarita Iyer","Jaya Jain","Lakshmi Menon","Priya Reddy","Aravind"]
    customers = []
    for i, n in enumerate(names, start=1):
        c = Customer(code=f"CUST{str(i).zfill(5)}", name=n, instagram="None", phone=str(9000000000+i), city=cities[i % len(cities)])
        db.session.add(c); customers.append(c)
    db.session.commit()
    # Orders
    import random
    types = ["Banarasi","Silk","Chiffon","Georgette","Kanchipuram","Paithani","Organza","Linen","Cotton"]
    for i in range(1, 40):
        cust = random.choice(customers)
        paid = random.choice(["Paid","Pending","Paid"])
        mode = "UPI" if paid=="Paid" else "Pending"
        o = Order(order_id=f"ORD{date.today().strftime('%Y%m%d')}-{10000+i}",
                  date=date.today(),
                  customer_id=cust.id,
                  saree_type=random.choice(types),
                  amount=random.choice([799,999,1499,2499,2999,4999,8250,9000,10000,12250,14990]),
                  purchase=random.choice(["Online","Offline"]),
                  payment_status=paid,
                  payment_mode=mode,
                  delivery_status=random.choice(["Pending","Delivered","Cancelled"]),
                  remarks="")
        db.session.add(o)
    db.session.commit()
    # Follow-ups
    for i in range(1,6):
        f = FollowUp(due_date=date.today(), customer_id=customers[i].id, notes="Call customer", status="Open")
        db.session.add(f)
    db.session.commit()
# ---------------- Main ----------------
def ensure_columns():
    """Ensure delivery-related columns exist on 'order' table (SQLite-safe)."""
    from sqlalchemy import text
    cols = {r["name"] for r in db.session.execute(text('PRAGMA table_info("order")')).mappings()}
    to_add = []
    def want(name, typ): 
        if name not in cols: to_add.append((name, typ))
    want("courier", "TEXT")
    want("tracking_id", "TEXT")
    want("shipment_date", "DATE")
    want("delivery_eta", "DATE")
    want("delivered_date", "DATE")
    want("last_update", "DATETIME")
    for name, typ in to_add:
        db.session.execute(text(f'ALTER TABLE "order" ADD COLUMN {name} {typ}'))
    if to_add:
        db.session.commit()

if __name__ == "__main__":
    with app.app_context():
        try:
            db.create_all()
            ensure_columns()
            seed_demo()
        except OperationalError as e:
            logger.exception("DB init failed")
            raise
    app.run(host="0.0.0.0", port=5000, debug=False)
