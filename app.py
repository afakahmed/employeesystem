import os
from datetime import date, datetime
from collections import defaultdict, OrderedDict

from flask import Flask, render_template, jsonify, request
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip("\"'")
SUPABASE_KEY = (os.environ.get("SUPABASE_SERVICE_KEY", "") or os.environ.get("SUPABASE_KEY", "")).strip("\"'")

supabase: Client | None = None

if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"WARNING - Supabase initialization error: {e}")
        supabase = None

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def db():
    if supabase is None:
        raise RuntimeError(
            "Supabase is not configured or the API key is invalid. Set SUPABASE_URL and SUPABASE_KEY "
            "environment variables correctly in the Render Dashboard."
        )
    return supabase

def ok(data=None, message="success", status=200):
    return jsonify({"success": True, "message": message, "data": data}), status

def err(message, status=400):
    return jsonify({"success": False, "message": str(message), "data": None}), status

def full_name_select():
    return (
        "*, department:departments(id,name), "
        "position:positions(id,title), "
        "manager:employees!manager_id(id,first_name,last_name)"
    )

# ---------------------------------------------------------------------------
# SPA Routing
# ---------------------------------------------------------------------------
SPA_ROUTES = [
    "/", "/login", "/dashboard", "/employees", "/departments", 
    "/positions", "/attendance", "/leaves", "/payroll"
]

def _spa_page():
    return render_template("index.html")

for _route in SPA_ROUTES:
    app.add_url_rule(_route, endpoint=f"spa_page{_route.replace('/', '_') or '_root'}", view_func=_spa_page)

@app.route("/healthz")
def healthz():
    return ok({"status": "ok", "supabase_configured": supabase is not None})

# ---------------------------------------------------------------------------
# Auth (Mock)
# ---------------------------------------------------------------------------
@app.route("/api/login", methods=["POST"])
def login():
    payload = request.get_json(force=True)
    email = payload.get("email")
    password = payload.get("password")
    
    if email == "admin@javagoat.hr" and password == "password123":
        return ok({"token": "mock-jwt-token-xyz", "user": {"name": "HR Admin", "role": "Administrator"}}, "Login successful")
    return err("Invalid email or password", 401)

# ===========================================================================
# API: DEPARTMENTS
# ===========================================================================
@app.route("/api/departments", methods=["GET"])
def get_departments():
    try:
        query = db().table("departments").select("*")
        search = request.args.get("search")
        if search:
            query = query.or_(f"name.ilike.%{search}%,location.ilike.%{search}%")
        res = query.order("name").execute()
        return ok(res.data)
    except Exception as e:
        return err(e, 500)

@app.route("/api/departments/<int:dep_id>", methods=["GET"])
def get_department(dep_id):
    try:
        res = db().table("departments").select("*").eq("id", dep_id).single().execute()
        return ok(res.data)
    except Exception as e:
        return err(e, 404)

@app.route("/api/departments", methods=["POST"])
def create_department():
    payload = request.get_json(force=True)
    try:
        res = db().table("departments").insert({
            "name": payload.get("name"),
            "description": payload.get("description"),
            "location": payload.get("location"),
        }).execute()
        return ok(res.data, "Department created", 201)
    except Exception as e:
        return err(e, 400)

@app.route("/api/departments/<int:dep_id>", methods=["PUT"])
def update_department(dep_id):
    payload = request.get_json(force=True)
    allowed = ["name", "description", "location"]
    row = {k: payload[k] for k in allowed if k in payload}
    try:
        res = db().table("departments").update(row).eq("id", dep_id).execute()
        return ok(res.data, "Department updated")
    except Exception as e:
        return err(e, 400)

@app.route("/api/departments/<int:dep_id>", methods=["DELETE"])
def delete_department(dep_id):
    try:
        db().table("departments").delete().eq("id", dep_id).execute()
        return ok(None, "Department deleted")
    except Exception as e:
        return err(e, 400)

# ===========================================================================
# API: POSITIONS
# ===========================================================================
@app.route("/api/positions", methods=["GET"])
def get_positions():
    try:
        # Fetch position info AND employees assigned to it
        query = db().table("positions").select("*, department:departments(id,name), employees:employees(id,first_name,last_name,employee_code)").order("title")
        search = request.args.get("search")
        if search:
            query = query.ilike("title", f"%{search}%")
        res = query.execute()
        return ok(res.data)
    except Exception as e:
        return err(e, 500)

@app.route("/api/positions/<int:pos_id>", methods=["GET"])
def get_position(pos_id):
    try:
        res = db().table("positions").select("*, department:departments(id,name)").eq("id", pos_id).single().execute()
        return ok(res.data)
    except Exception as e:
        return err(e, 404)

@app.route("/api/positions", methods=["POST"])
def create_position():
    payload = request.get_json(force=True)
    try:
        res = db().table("positions").insert({
            "title": payload.get("title"),
            "department_id": payload.get("department_id") or None,
            "min_salary": payload.get("min_salary") or 0,
            "max_salary": payload.get("max_salary") or 0,
        }).execute()
        return ok(res.data, "Position created", 201)
    except Exception as e:
        return err(e, 400)

@app.route("/api/positions/<int:pos_id>", methods=["PUT"])
def update_position(pos_id):
    payload = request.get_json(force=True)
    allowed = ["title", "department_id", "min_salary", "max_salary"]
    row = {k: payload[k] for k in allowed if k in payload}
    try:
        res = db().table("positions").update(row).eq("id", pos_id).execute()
        return ok(res.data, "Position updated")
    except Exception as e:
        return err(e, 400)

@app.route("/api/positions/<int:pos_id>", methods=["DELETE"])
def delete_position(pos_id):
    try:
        db().table("positions").delete().eq("id", pos_id).execute()
        return ok(None, "Position deleted")
    except Exception as e:
        return err(e, 400)

# ===========================================================================
# API: EMPLOYEES
# ===========================================================================
@app.route("/api/employees", methods=["GET"])
def get_employees():
    try:
        query = db().table("employees").select(full_name_select())
        department_id = request.args.get("department_id")
        status = request.args.get("status")
        search = request.args.get("search")
        if department_id: query = query.eq("department_id", department_id)
        if status: query = query.eq("status", status)
        if search:
            query = query.or_(f"first_name.ilike.%{search}%,last_name.ilike.%{search}%,email.ilike.%{search}%,employee_code.ilike.%{search}%")
        res = query.order("id", desc=True).execute()
        return ok(res.data)
    except Exception as e:
        return err(e, 500)

@app.route("/api/employees/<int:emp_id>", methods=["GET"])
def get_employee(emp_id):
    try:
        res = db().table("employees").select(full_name_select()).eq("id", emp_id).single().execute()
        return ok(res.data)
    except Exception as e:
        return err(e, 404)

@app.route("/api/employees", methods=["POST"])
def create_employee():
    payload = request.get_json(force=True)
    try:
        row = {
            "employee_code": payload.get("employee_code"),
            "first_name": payload.get("first_name"),
            "last_name": payload.get("last_name"),
            "email": payload.get("email"),
            "phone": payload.get("phone"),
            "gender": payload.get("gender") or None,
            "date_of_birth": payload.get("date_of_birth") or None,
            "address": payload.get("address"),
            "department_id": payload.get("department_id") or None,
            "position_id": payload.get("position_id") or None,
            "manager_id": payload.get("manager_id") or None,
            "hire_date": payload.get("hire_date") or str(date.today()),
            "salary": payload.get("salary") or 0,
            "status": payload.get("status") or "active"
        }
        res = db().table("employees").insert(row).execute()
        return ok(res.data, "Employee created", 201)
    except Exception as e:
        return err(e, 400)

@app.route("/api/employees/<int:emp_id>", methods=["PUT"])
def update_employee(emp_id):
    payload = request.get_json(force=True)
    # Partial update to allow assigning position_id without wiping other fields
    allowed = ["employee_code", "first_name", "last_name", "email", "phone", "gender", "date_of_birth", "address", "department_id", "position_id", "manager_id", "hire_date", "salary", "status"]
    row = {k: payload[k] for k in allowed if k in payload}
    try:
        res = db().table("employees").update(row).eq("id", emp_id).execute()
        return ok(res.data, "Employee updated")
    except Exception as e:
        return err(e, 400)

@app.route("/api/employees/<int:emp_id>", methods=["DELETE"])
def delete_employee(emp_id):
    try:
        db().table("employees").delete().eq("id", emp_id).execute()
        return ok(None, "Employee deleted")
    except Exception as e:
        return err(e, 400)

# ===========================================================================
# API: ATTENDANCE
# ===========================================================================
@app.route("/api/attendance", methods=["GET"])
def get_attendance():
    try:
        query = db().table("attendance").select("*, employee:employees(id,first_name,last_name,employee_code)")
        emp_id = request.args.get("employee_id")
        d_from = request.args.get("from")
        d_to = request.args.get("to")
        status = request.args.get("status")
        if emp_id: query = query.eq("employee_id", emp_id)
        if d_from: query = query.gte("date", d_from)
        if d_to: query = query.lte("date", d_to)
        if status: query = query.eq("status", status)
        res = query.order("date", desc=True).execute()
        return ok(res.data)
    except Exception as e:
        return err(e, 500)

@app.route("/api/attendance", methods=["POST"])
def create_attendance():
    payload = request.get_json(force=True)
    try:
        row = {
            "employee_id": payload.get("employee_id"),
            "date": payload.get("date") or str(date.today()),
            "check_in": payload.get("check_in") or None,
            "check_out": payload.get("check_out") or None,
            "status": payload.get("status") or "present",
            "notes": payload.get("notes"),
        }
        res = db().table("attendance").insert(row).execute()
        return ok(res.data, "Attendance recorded", 201)
    except Exception as e:
        return err(e, 400)

@app.route("/api/attendance/<int:att_id>", methods=["PUT"])
def update_attendance(att_id):
    payload = request.get_json(force=True)
    allowed = ["employee_id", "date", "check_in", "check_out", "status", "notes"]
    row = {k: payload[k] for k in allowed if k in payload}
    try:
        res = db().table("attendance").update(row).eq("id", att_id).execute()
        return ok(res.data, "Attendance updated")
    except Exception as e:
        return err(e, 400)

@app.route("/api/attendance/<int:att_id>", methods=["DELETE"])
def delete_attendance(att_id):
    try:
        db().table("attendance").delete().eq("id", att_id).execute()
        return ok(None, "Attendance record deleted")
    except Exception as e:
        return err(e, 400)

# ===========================================================================
# API: LEAVES
# ===========================================================================
@app.route("/api/leaves", methods=["GET"])
def get_leaves():
    try:
        query = db().table("leaves").select(
            "*, employee:employees!employee_id(id,first_name,last_name,employee_code), "
            "approver:employees!approved_by(id,first_name,last_name)"
        )
        status = request.args.get("status")
        emp_id = request.args.get("employee_id")
        if status: query = query.eq("status", status)
        if emp_id: query = query.eq("employee_id", emp_id)
        res = query.order("id", desc=True).execute()
        return ok(res.data)
    except Exception as e:
        return err(e, 500)

@app.route("/api/leaves", methods=["POST"])
def create_leave():
    payload = request.get_json(force=True)
    try:
        row = {
            "employee_id": payload.get("employee_id"),
            "leave_type": payload.get("leave_type"),
            "start_date": payload.get("start_date"),
            "end_date": payload.get("end_date"),
            "reason": payload.get("reason"),
            "status": payload.get("status") or "pending",
            "approved_by": payload.get("approved_by") or None,
        }
        res = db().table("leaves").insert(row).execute()
        return ok(res.data, "Leave request created", 201)
    except Exception as e:
        return err(e, 400)

@app.route("/api/leaves/<int:leave_id>", methods=["PUT"])
def update_leave(leave_id):
    payload = request.get_json(force=True)
    allowed = ["employee_id", "leave_type", "start_date", "end_date", "reason", "status", "approved_by"]
    row = {k: payload[k] for k in allowed if k in payload}
    try:
        res = db().table("leaves").update(row).eq("id", leave_id).execute()
        return ok(res.data, "Leave request updated")
    except Exception as e:
        return err(e, 400)

@app.route("/api/leaves/<int:leave_id>", methods=["DELETE"])
def delete_leave(leave_id):
    try:
        db().table("leaves").delete().eq("id", leave_id).execute()
        return ok(None, "Leave request deleted")
    except Exception as e:
        return err(e, 400)

# ===========================================================================
# API: PAYROLL
# ===========================================================================
@app.route("/api/payroll", methods=["GET"])
def get_payroll():
    try:
        query = db().table("payroll").select("*, employee:employees(id,first_name,last_name,employee_code)")
        emp_id = request.args.get("employee_id")
        month = request.args.get("month")
        year = request.args.get("year")
        status = request.args.get("status")
        if emp_id: query = query.eq("employee_id", emp_id)
        if month: query = query.eq("month", month)
        if year: query = query.eq("year", year)
        if status: query = query.eq("status", status)
        res = query.order("year", desc=True).order("month", desc=True).execute()
        return ok(res.data)
    except Exception as e:
        return err(e, 500)

@app.route("/api/payroll", methods=["POST"])
def create_payroll():
    payload = request.get_json(force=True)
    basic = payload.get("basic_salary") or 0
    allowances = payload.get("allowances") or 0
    deductions = payload.get("deductions") or 0
    try:
        row = {
            "employee_id": payload.get("employee_id"),
            "month": payload.get("month"),
            "year": payload.get("year"),
            "basic_salary": basic,
            "allowances": allowances,
            "deductions": deductions,
            "net_salary": (basic + allowances) - deductions,
            "payment_date": payload.get("payment_date") or None,
            "status": payload.get("status") or "pending",
        }
        res = db().table("payroll").insert(row).execute()
        return ok(res.data, "Payroll entry created", 201)
    except Exception as e:
        return err(e, 400)

@app.route("/api/payroll/<int:pay_id>", methods=["PUT"])
def update_payroll(pay_id):
    payload = request.get_json(force=True)
    allowed = ["employee_id", "month", "year", "basic_salary", "allowances", "deductions", "payment_date", "status"]
    row = {k: payload[k] for k in allowed if k in payload}
    if "basic_salary" in row or "allowances" in row or "deductions" in row:
        basic = row.get("basic_salary", 0)
        allowances = row.get("allowances", 0)
        deductions = row.get("deductions", 0)
        row["net_salary"] = (basic + allowances) - deductions
    try:
        res = db().table("payroll").update(row).eq("id", pay_id).execute()
        return ok(res.data, "Payroll entry updated")
    except Exception as e:
        return err(e, 400)

@app.route("/api/payroll/<int:pay_id>", methods=["DELETE"])
def delete_payroll(pay_id):
    try:
        db().table("payroll").delete().eq("id", pay_id).execute()
        return ok(None, "Payroll entry deleted")
    except Exception as e:
        return err(e, 400)

# ===========================================================================
# API: DASHBOARD AGGREGATES
# ===========================================================================
@app.route("/api/dashboard/stats", methods=["GET"])
def dashboard_stats():
    try:
        client = db()
        employees = client.table("employees").select("id,status,department_id,position_id,salary,hire_date").execute().data
        departments = client.table("departments").select("id,name").execute().data
        positions = client.table("positions").select("id,title").execute().data
        leaves = client.table("leaves").select("id,status").execute().data
        attendance_today = client.table("attendance").select("id,status").eq("date", str(date.today())).execute().data

        total_employees = len(employees)
        active_employees = len([e for e in employees if e["status"] == "active"])
        total_monthly_salary = sum(float(e["salary"] or 0) for e in employees if e["status"] == "active")

        dep_name_by_id = {d["id"]: d["name"] for d in departments}
        pos_name_by_id = {p["id"]: p["title"] for p in positions}
        
        dep_counts = defaultdict(int)
        status_counts = defaultdict(int)
        pos_counts = defaultdict(int)
        
        for e in employees:
            status_counts[e["status"]] += 1
            if e["status"] not in ("terminated",):
                dep_counts[dep_name_by_id.get(e["department_id"], "Unassigned")] += 1
            if e.get("position_id"):
                pos_counts[pos_name_by_id.get(e["position_id"], "Unknown")] += 1

        department_distribution = [{"label": k, "value": v} for k, v in sorted(dep_counts.items(), key=lambda x: -x[1])]
        status_distribution = [{"label": k, "value": v} for k, v in status_counts.items()]
        position_distribution = [{"label": k, "value": v} for k, v in sorted(pos_counts.items(), key=lambda x: -x[1])]

        month_buckets = OrderedDict()
        now = datetime.today()
        for i in range(11, -1, -1):
            y = now.year + ((now.month - i - 1) // 12)
            m = ((now.month - i - 1) % 12) + 1
            month_buckets[f"{y}-{m:02d}"] = 0
            
        for e in employees:
            hd = e.get("hire_date")
            if hd:
                key = hd[:7]
                if key in month_buckets:
                    month_buckets[key] += 1
                    
        hiring_trend = [{"label": k, "value": v} for k, v in month_buckets.items()]

        all_recent_attendance = client.table("attendance").select("date,status").order("date").execute().data
        day_buckets = defaultdict(lambda: {"present": 0, "absent": 0, "late": 0})
        for a in all_recent_attendance:
            day_buckets[a["date"]][a["status"] if a["status"] in ("present", "absent", "late") else "present"] += 1
            
        attendance_trend = [
            {"label": k, "present": v["present"], "absent": v["absent"], "late": v["late"]}
            for k, v in sorted(day_buckets.items())[-14:]
        ]

        return ok({
            "cards": {
                "total_employees": total_employees,
                "active_employees": active_employees,
                "total_departments": len(departments),
                "pending_leaves": len([l for l in leaves if l["status"] == "pending"]),
                "present_today": len([a for a in attendance_today if a["status"] in ("present", "late", "half_day")]),
                "absent_today": len([a for a in attendance_today if a["status"] == "absent"]),
                "total_monthly_salary": total_monthly_salary,
            },
            "department_distribution": department_distribution,
            "status_distribution": status_distribution,
            "position_distribution": position_distribution,
            "hiring_trend": hiring_trend,
            "attendance_trend": attendance_trend,
        })
    except Exception as e:
        return err(e, 500)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
