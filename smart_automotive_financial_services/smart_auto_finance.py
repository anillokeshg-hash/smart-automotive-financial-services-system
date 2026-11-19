"""
Smart Automotive Financial Services System - simple base project
----------------------------------------------------------------
Features:
  1. Vehicle catalog and customer records
  2. EMI calculator with credit-score based interest rates
  3. Automated loan approval / rejection with reasons
  4. Full repayment (amortization) schedule
  5. Installment payments with outstanding-balance tracking
  6. Vehicle insurance premium quotes
  7. Portfolio report (disbursed, collected, outstanding, approval rate)

Run:   python smart_auto_finance.py          (interactive menu)
Demo:  python smart_auto_finance.py --demo   (sample data and full walkthrough)
Needs only the Python 3.8+ standard library.
"""

import sqlite3
import sys
from datetime import date

DB_FILE = "auto_finance.db"

# ---------------- business rules (easy to tune) ----------------
MIN_CREDIT_SCORE = 600          # below this, loan is rejected
MIN_DOWN_PAYMENT_PCT = 10       # of vehicle price
MIN_TENURE, MAX_TENURE = 12, 84  # months
MAX_DEBT_TO_INCOME = 0.50       # (existing EMIs + new EMI) / monthly income
GST_RATE = 0.18                 # applied on insurance premium


# ----------------------------------------------------------------------
# Database
# ----------------------------------------------------------------------
def get_conn(db_file=DB_FILE):
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS vehicles (
            id     INTEGER PRIMARY KEY AUTOINCREMENT,
            make   TEXT NOT NULL,
            model  TEXT NOT NULL,
            year   INTEGER NOT NULL,
            kind   TEXT NOT NULL CHECK (kind IN ('car','suv','bike')),
            price  REAL NOT NULL CHECK (price > 0)
        );

        CREATE TABLE IF NOT EXISTS customers (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            name           TEXT NOT NULL,
            phone          TEXT,
            monthly_income REAL NOT NULL CHECK (monthly_income > 0),
            credit_score   INTEGER NOT NULL CHECK (credit_score BETWEEN 300 AND 900),
            existing_emi   REAL NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS loans (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            vehicle_id  INTEGER NOT NULL REFERENCES vehicles(id),
            applied_on  TEXT NOT NULL,
            down_payment REAL NOT NULL,
            principal   REAL NOT NULL,
            rate        REAL,
            months      INTEGER NOT NULL,
            emi         REAL,
            status      TEXT NOT NULL CHECK (status IN ('ACTIVE','CLOSED','REJECTED')),
            reason      TEXT
        );

        CREATE TABLE IF NOT EXISTS payments (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            loan_id        INTEGER NOT NULL REFERENCES loans(id),
            installment_no INTEGER NOT NULL,
            amount         REAL NOT NULL,
            paid_on        TEXT NOT NULL,
            UNIQUE (loan_id, installment_no)
        );
        """
    )
    conn.commit()


# ----------------------------------------------------------------------
# Finance maths
# ----------------------------------------------------------------------
def calc_emi(principal, annual_rate, months):
    r = annual_rate / 12 / 100
    if r == 0:
        return principal / months
    f = (1 + r) ** months
    return principal * r * f / (f - 1)


def rate_for_score(score):
    """Annual interest rate (%) by credit score; None means not eligible."""
    if score >= 750:
        return 8.5
    if score >= 700:
        return 9.5
    if score >= 650:
        return 11.0
    if score >= MIN_CREDIT_SCORE:
        return 13.5
    return None


def build_schedule(principal, annual_rate, months):
    """Amortization schedule; final installment clears any rounding difference."""
    r = annual_rate / 12 / 100
    emi = round(calc_emi(principal, annual_rate, months), 2)
    balance = round(principal, 2)
    rows = []
    for i in range(1, months + 1):
        interest = round(balance * r, 2)
        if i == months:
            principal_part = balance
            payment = round(balance + interest, 2)
        else:
            payment = emi
            principal_part = round(payment - interest, 2)
        balance = round(balance - principal_part, 2)
        rows.append({"no": i, "payment": payment, "interest": interest,
                     "principal": principal_part, "balance": max(balance, 0.0)})
    return rows


# ----------------------------------------------------------------------
# Vehicles and customers
# ----------------------------------------------------------------------
def add_vehicle(conn, make, model, year, kind, price):
    cur = conn.execute(
        "INSERT INTO vehicles (make, model, year, kind, price) VALUES (?,?,?,?,?)",
        (make, model, int(year), kind.lower(), float(price)),
    )
    conn.commit()
    return cur.lastrowid


def add_customer(conn, name, phone, income, score, existing_emi=0):
    cur = conn.execute(
        "INSERT INTO customers (name, phone, monthly_income, credit_score, existing_emi) VALUES (?,?,?,?,?)",
        (name, phone, float(income), int(score), float(existing_emi)),
    )
    conn.commit()
    return cur.lastrowid


def print_vehicles(conn):
    rows = conn.execute("SELECT * FROM vehicles ORDER BY id").fetchall()
    print(f"\n{'ID':<4}{'Vehicle':<28}{'Type':<6}{'Year':<6}{'Price (Rs.)':>14}")
    print("-" * 58)
    for v in rows:
        print(f"{v['id']:<4}{v['make'] + ' ' + v['model']:<28}{v['kind']:<6}{v['year']:<6}{v['price']:>14,.0f}")


def print_customers(conn):
    rows = conn.execute("SELECT * FROM customers ORDER BY id").fetchall()
    print(f"\n{'ID':<4}{'Name':<18}{'Income':>12}{'Score':>7}{'Existing EMI':>14}")
    print("-" * 55)
    for c in rows:
        print(f"{c['id']:<4}{c['name']:<18}{c['monthly_income']:>12,.0f}{c['credit_score']:>7}{c['existing_emi']:>14,.0f}")


# ----------------------------------------------------------------------
# Loan application and decision
# ----------------------------------------------------------------------
def apply_for_loan(conn, customer_id, vehicle_id, down_payment, months):
    cust = conn.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
    veh = conn.execute("SELECT * FROM vehicles WHERE id=?", (vehicle_id,)).fetchone()
    if cust is None:
        raise ValueError("Customer not found.")
    if veh is None:
        raise ValueError("Vehicle not found.")
    if not (0 <= down_payment < veh["price"]):
        raise ValueError("Down payment must be between 0 and the vehicle price.")
    if not (MIN_TENURE <= months <= MAX_TENURE):
        raise ValueError(f"Tenure must be {MIN_TENURE}-{MAX_TENURE} months.")

    principal = veh["price"] - down_payment
    rate = rate_for_score(cust["credit_score"])
    emi, reason = None, None

    if rate is None:
        reason = f"Credit score {cust['credit_score']} is below the minimum of {MIN_CREDIT_SCORE}"
    elif down_payment < veh["price"] * MIN_DOWN_PAYMENT_PCT / 100:
        reason = f"Down payment is below {MIN_DOWN_PAYMENT_PCT}% of the vehicle price"
    else:
        emi = round(calc_emi(principal, rate, months), 2)
        dti = (cust["existing_emi"] + emi) / cust["monthly_income"]
        if dti > MAX_DEBT_TO_INCOME:
            reason = (f"Debt-to-income ratio {dti:.0%} exceeds the limit of "
                      f"{MAX_DEBT_TO_INCOME:.0%}")

    status = "REJECTED" if reason else "ACTIVE"
    cur = conn.execute(
        """INSERT INTO loans (customer_id, vehicle_id, applied_on, down_payment, principal,
                              rate, months, emi, status, reason)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (customer_id, vehicle_id, date.today().isoformat(), down_payment, principal,
         rate, months, emi, status, reason),
    )
    if status == "ACTIVE":
        # the new EMI becomes part of the customer's existing obligations
        conn.execute("UPDATE customers SET existing_emi = existing_emi + ? WHERE id=?",
                     (emi, customer_id))
    conn.commit()
    return {"loan_id": cur.lastrowid, "status": status, "reason": reason,
            "rate": rate, "emi": emi, "principal": principal}


def print_decision(res):
    print("\n--- Loan decision ---")
    print(f"Application #{res['loan_id']}: {res['status']}")
    if res["status"] == "REJECTED":
        print(f"Reason: {res['reason']}")
    else:
        print(f"Loan amount : Rs. {res['principal']:,.2f}")
        print(f"Interest    : {res['rate']}% p.a.")
        print(f"Monthly EMI : Rs. {res['emi']:,.2f}")


# ----------------------------------------------------------------------
# Repayments
# ----------------------------------------------------------------------
def get_loan(conn, loan_id):
    loan = conn.execute("SELECT * FROM loans WHERE id=?", (loan_id,)).fetchone()
    if loan is None:
        raise ValueError("Loan not found.")
    return loan


def print_schedule(conn, loan_id, limit=None):
    loan = get_loan(conn, loan_id)
    if loan["status"] == "REJECTED":
        raise ValueError("This application was rejected; there is no schedule.")
    paid = {r["installment_no"] for r in
            conn.execute("SELECT installment_no FROM payments WHERE loan_id=?", (loan_id,))}
    rows = build_schedule(loan["principal"], loan["rate"], loan["months"])
    print(f"\nSchedule for loan #{loan_id}")
    print(f"{'No':>3}{'Payment':>12}{'Interest':>11}{'Principal':>12}{'Balance':>13}  Status")
    print("-" * 62)
    for r in rows[:limit] if limit else rows:
        mark = "PAID" if r["no"] in paid else "due"
        print(f"{r['no']:>3}{r['payment']:>12,.2f}{r['interest']:>11,.2f}"
              f"{r['principal']:>12,.2f}{r['balance']:>13,.2f}  {mark}")
    if limit and loan["months"] > limit:
        print(f"... ({loan['months'] - limit} more installments)")


def outstanding(conn, loan):
    """Principal still owed on a loan, based on installments paid so far."""
    if loan["status"] != "ACTIVE":
        return 0.0
    n = conn.execute("SELECT COUNT(*) FROM payments WHERE loan_id=?", (loan["id"],)).fetchone()[0]
    if n == 0:
        return loan["principal"]
    sched = build_schedule(loan["principal"], loan["rate"], loan["months"])
    return sched[n - 1]["balance"]


def pay_installment(conn, loan_id):
    loan = get_loan(conn, loan_id)
    if loan["status"] != "ACTIVE":
        raise ValueError(f"Loan is {loan['status']}; nothing to pay.")
    n = conn.execute("SELECT COUNT(*) FROM payments WHERE loan_id=?", (loan_id,)).fetchone()[0]
    sched = build_schedule(loan["principal"], loan["rate"], loan["months"])
    row = sched[n]
    conn.execute(
        "INSERT INTO payments (loan_id, installment_no, amount, paid_on) VALUES (?,?,?,?)",
        (loan_id, row["no"], row["payment"], date.today().isoformat()),
    )
    closed = row["no"] == loan["months"]
    if closed:
        conn.execute("UPDATE loans SET status='CLOSED' WHERE id=?", (loan_id,))
        conn.execute("UPDATE customers SET existing_emi = MAX(existing_emi - ?, 0) WHERE id=?",
                     (loan["emi"], loan["customer_id"]))
    conn.commit()
    msg = f"Installment {row['no']}/{loan['months']} paid: Rs. {row['payment']:,.2f}. "
    msg += "Loan fully repaid and closed!" if closed else f"Balance left: Rs. {row['balance']:,.2f}"
    return msg


# ----------------------------------------------------------------------
# Insurance
# ----------------------------------------------------------------------
BASE_RATE = {"car": 0.030, "suv": 0.035, "bike": 0.025}


def insurance_quote(conn, vehicle_id, ncb_pct=0):
    """Premium = insured value x base rate, less no-claim bonus, plus GST."""
    v = conn.execute("SELECT * FROM vehicles WHERE id=?", (vehicle_id,)).fetchone()
    if v is None:
        raise ValueError("Vehicle not found.")
    if not (0 <= ncb_pct <= 50):
        raise ValueError("No-claim bonus must be between 0 and 50.")
    age = max(date.today().year - v["year"], 0)
    idv = v["price"] * max(1 - 0.10 * age, 0.40)         # depreciated insured value
    base = idv * BASE_RATE[v["kind"]]
    discount = base * ncb_pct / 100
    net = base - discount
    gst = net * GST_RATE
    return {"vehicle": f"{v['make']} {v['model']}", "age": age, "idv": idv,
            "base": base, "discount": discount, "gst": gst, "total": net + gst}


def print_quote(q):
    print(f"\n--- Insurance quote: {q['vehicle']} ---")
    print(f"Vehicle age            : {q['age']} year(s)")
    print(f"Insured value (IDV)    : Rs. {q['idv']:>12,.2f}")
    print(f"Base premium           : Rs. {q['base']:>12,.2f}")
    print(f"No-claim discount      : Rs. {-q['discount']:>12,.2f}")
    print(f"GST ({GST_RATE:.0%})            : Rs. {q['gst']:>12,.2f}")
    print(f"Total yearly premium   : Rs. {q['total']:>12,.2f}")


# ----------------------------------------------------------------------
# Portfolio report
# ----------------------------------------------------------------------
def portfolio_report(conn):
    loans = conn.execute("SELECT * FROM loans").fetchall()
    total = len(loans)
    approved = [l for l in loans if l["status"] != "REJECTED"]
    rejected = [l for l in loans if l["status"] == "REJECTED"]
    disbursed = sum(l["principal"] for l in approved)
    collected = conn.execute("SELECT COALESCE(SUM(amount),0) FROM payments").fetchone()[0]
    owed = sum(outstanding(conn, l) for l in approved)
    print("\n" + "=" * 50)
    print("  PORTFOLIO REPORT")
    print("=" * 50)
    print(f"  Applications received : {total}")
    print(f"  Approved / Rejected   : {len(approved)} / {len(rejected)}")
    if total:
        print(f"  Approval rate         : {len(approved) / total:.0%}")
    print(f"  Total disbursed       : Rs. {disbursed:,.2f}")
    print(f"  Collected so far      : Rs. {collected:,.2f}")
    print(f"  Principal outstanding : Rs. {owed:,.2f}")
    print(f"  Active / Closed loans : "
          f"{sum(l['status'] == 'ACTIVE' for l in loans)} / {sum(l['status'] == 'CLOSED' for l in loans)}")
    if rejected:
        print("\n  Rejection reasons:")
        for l in rejected:
            print(f"   - Loan #{l['id']}: {l['reason']}")
    print("=" * 50)


# ----------------------------------------------------------------------
# Demo
# ----------------------------------------------------------------------
def run_demo(conn):
    add_vehicle(conn, "Maruti", "Swift", 2025, "car", 800000)
    add_vehicle(conn, "Hyundai", "Creta", 2024, "suv", 1500000)
    add_vehicle(conn, "Honda", "Activa", 2023, "bike", 90000)
    add_vehicle(conn, "Tata", "Nexon", 2022, "suv", 1200000)
    add_customer(conn, "Anita Rao", "9876500001", 90000, 780)
    add_customer(conn, "Ravi Kumar", "9876500002", 45000, 560)
    add_customer(conn, "Meera Shah", "9876500003", 50000, 720, existing_emi=15000)
    print_vehicles(conn)
    print_customers(conn)

    print("\n>>> Anita applies for a Creta (strong profile)")
    res = apply_for_loan(conn, 1, 2, 300000, 60)
    print_decision(res)

    print("\n>>> Ravi applies for a Swift (low credit score)")
    print_decision(apply_for_loan(conn, 2, 1, 100000, 48))

    print("\n>>> Meera applies for a Nexon (too much existing debt)")
    print_decision(apply_for_loan(conn, 3, 4, 120000, 36))

    print("\n>>> Anita pays three installments")
    for _ in range(3):
        print(pay_installment(conn, 1))
    print_schedule(conn, 1, limit=6)

    print_quote(insurance_quote(conn, 2, ncb_pct=20))
    portfolio_report(conn)


# ----------------------------------------------------------------------
# Interactive menu
# ----------------------------------------------------------------------
def ask_int(prompt):
    while True:
        try:
            return int(input(prompt))
        except ValueError:
            print("Please enter a whole number.")


def ask_float(prompt):
    while True:
        try:
            return float(input(prompt))
        except ValueError:
            print("Please enter a number.")


def menu(conn):
    text = """
===== SMART AUTOMOTIVE FINANCIAL SERVICES =====
1. View vehicles           6. Pay next installment
2. Add vehicle             7. View repayment schedule
3. Add customer            8. Insurance quote
4. EMI calculator          9. Portfolio report
5. Apply for loan         10. View customers
0. Exit
"""
    while True:
        print(text)
        c = input("Choose: ").strip()
        try:
            if c == "1":
                print_vehicles(conn)
            elif c == "2":
                add_vehicle(conn, input("Make: "), input("Model: "), ask_int("Year: "),
                            input("Type (car/suv/bike): "), ask_float("Price: "))
                print("Vehicle added.")
            elif c == "3":
                add_customer(conn, input("Name: "), input("Phone: "), ask_float("Monthly income: "),
                             ask_int("Credit score (300-900): "), ask_float("Existing monthly EMIs: "))
                print("Customer added.")
            elif c == "4":
                p, r, m = ask_float("Loan amount: "), ask_float("Annual rate %: "), ask_int("Months: ")
                print(f"EMI = Rs. {calc_emi(p, r, m):,.2f}  |  total interest = "
                      f"Rs. {calc_emi(p, r, m) * m - p:,.2f}")
            elif c == "5":
                print_vehicles(conn)
                print_customers(conn)
                res = apply_for_loan(conn, ask_int("Customer ID: "), ask_int("Vehicle ID: "),
                                     ask_float("Down payment: "), ask_int("Tenure (months): "))
                print_decision(res)
            elif c == "6":
                print(pay_installment(conn, ask_int("Loan ID: ")))
            elif c == "7":
                print_schedule(conn, ask_int("Loan ID: "))
            elif c == "8":
                print_vehicles(conn)
                print_quote(insurance_quote(conn, ask_int("Vehicle ID: "), ask_float("No-claim bonus %: ")))
            elif c == "9":
                portfolio_report(conn)
            elif c == "10":
                print_customers(conn)
            elif c == "0":
                print("Goodbye!")
                break
            else:
                print("Invalid choice.")
        except (ValueError, sqlite3.Error) as e:
            print(f"Error: {e}")


def main():
    demo = "--demo" in sys.argv
    conn = get_conn(":memory:" if demo else DB_FILE)
    init_db(conn)
    if demo:
        run_demo(conn)
    else:
        menu(conn)
    conn.close()


if __name__ == "__main__":
    main()
