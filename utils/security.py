import hashlib
import os
import hmac
import time
from datetime import datetime, timedelta
import pandas as pd
from database.db import get_connection

def hash_password(password: str) -> str:
    """Hash password securely using PBKDF2-HMAC-SHA256 with a unique random salt."""
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return f"{salt.hex()}${key.hex()}"

def verify_password(password: str, hashed_str: str) -> bool:
    """Verify password against stored salt$hash with constant-time comparison."""
    try:
        salt_hex, key_hex = hashed_str.split('$')
        salt = bytes.fromhex(salt_hex)
        expected_key = bytes.fromhex(key_hex)
        actual_key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        return hmac.compare_digest(actual_key, expected_key)
    except Exception:
        return False

def authenticate_user(username_or_email: str, password: str, allow_student_autoreg: bool = True) -> dict:
    """
    Authenticate user by username, email, or full name.
    If the input is an unregistered student name and not a staff/admin credential,
    it can automatically register and sign them in as a student.
    """
    raw_query = username_or_email.strip()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.id, u.username, u.email, u.password_hash, u.full_name, u.role, 
               u.department_id, u.phone, u.is_active,
               d.name as department_name, d.code as department_code, d.default_email as department_email
        FROM users u
        LEFT JOIN departments d ON u.department_id = d.id
        WHERE (LOWER(u.username) = LOWER(?) OR LOWER(u.email) = LOWER(?) OR LOWER(u.full_name) = LOWER(?))
    """, (raw_query, raw_query, raw_query))
    row = cursor.fetchone()
    conn.close()

    if not row:
        # If user is not found, check if it's a student sign-in attempt
        # (Exclude staff_ or admin prefix)
        if allow_student_autoreg and not raw_query.lower().startswith(('staff_', 'admin')):
            return login_or_register_student(raw_query, password=password)
        return {"error": "Invalid username or password."}
    
    if not row['is_active']:
        return {"error": "Your account has been deactivated. Please contact the administrator."}

    if verify_password(password, row['password_hash']):
        log_audit_event("LOGIN", username=row['username'], user_id=row['id'], details=f"User signed in successfully as {row['role']}")
        return {
            "success": True,
            "id": row['id'],
            "username": row['username'],
            "email": row['email'],
            "full_name": row['full_name'],
            "role": row['role'],
            "department_id": row['department_id'],
            "department_name": row['department_name'],
            "department_code": row['department_code'],
            "department_email": row['department_email'],
            "phone": row['phone']
        }
    return {"error": "Invalid username or password."}

def login_or_register_student(student_name_or_id: str, email: str = None, password: str = None) -> dict:
    """
    Log in or automatically register ANY student by name or student ID.
    Enables testing and daily operation with arbitrary student identities (not just seeded accounts).
    """
    import re
    raw_name = (student_name_or_id or "").strip()
    if not raw_name:
        return {"error": "Student name cannot be empty."}

    conn = get_connection()
    cursor = conn.cursor()

    # 1. Check if user already exists by username, email, or full name
    cursor.execute("""
        SELECT u.id, u.username, u.email, u.password_hash, u.full_name, u.role, 
               u.department_id, u.phone, u.is_active
        FROM users u
        WHERE (LOWER(u.username) = LOWER(?) OR LOWER(u.email) = LOWER(?) OR LOWER(u.full_name) = LOWER(?))
    """, (raw_name, raw_name, raw_name))
    row = cursor.fetchone()

    if row:
        if not row['is_active']:
            conn.close()
            return {"error": "This student account has been deactivated."}

        # If password was provided and not matching
        if password and password.strip() and not verify_password(password, row['password_hash']):
            conn.close()
            return {"error": "Incorrect password for this student account."}

        conn.close()
        log_audit_event("STUDENT_LOGIN", username=row['username'], user_id=row['id'], 
                        details=f"Student {row['full_name']} signed in")
        return {
            "success": True,
            "id": row['id'],
            "username": row['username'],
            "email": row['email'],
            "full_name": row['full_name'],
            "role": "student",
            "department_id": None,
            "department_name": None,
            "department_code": None,
            "department_email": None,
            "phone": row['phone']
        }

    # 2. Student does not exist yet -> Register automatically
    clean_base = re.sub(r'[^a-zA-Z0-9]', '_', raw_name.lower()).strip('_')
    if not clean_base:
        clean_base = "student"
    
    username = clean_base if clean_base.startswith("student_") else f"student_{clean_base}"
    
    # Check for username uniqueness
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    if cursor.fetchone():
        username = f"{username}_{int(time.time()) % 10000}"

    full_name = raw_name.title() if not raw_name.startswith("student_") else raw_name.replace("student_", "").replace("_", " ").title()
    
    if not email or "@" not in email:
        email = f"{clean_base.replace('student_', '')}@campus.edu"

    pwd_to_hash = password if (password and len(password) >= 4) else "student123"
    pwd_hash = hash_password(pwd_to_hash)

    cursor.execute("""
        INSERT INTO users (username, email, password_hash, full_name, role, department_id, phone, is_active)
        VALUES (?, ?, ?, ?, 'student', NULL, NULL, 1)
    """, (username, email, pwd_hash, full_name))
    conn.commit()
    new_uid = cursor.lastrowid
    conn.close()

    log_audit_event("STUDENT_REGISTER", username=username, user_id=new_uid, 
                    details=f"New student '{full_name}' registered and signed in")

    return {
        "success": True,
        "id": new_uid,
        "username": username,
        "email": email,
        "full_name": full_name,
        "role": "student",
        "department_id": None,
        "department_name": None,
        "department_code": None,
        "department_email": None,
        "phone": None
    }


def change_user_password(user_id: int, old_password: str, new_password: str) -> tuple:
    """Change user password after verifying old password."""
    if len(new_password) < 6:
        return False, "New password must be at least 6 characters long."
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash, username FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False, "User not found."
    
    if not verify_password(old_password, row['password_hash']):
        conn.close()
        return False, "Current password does not match."
    
    new_hash = hash_password(new_password)
    cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
    conn.commit()
    conn.close()

    log_audit_event("PASSWORD_CHANGE", username=row['username'], user_id=user_id, details="User changed their password")
    return True, "Password updated successfully!"

def log_audit_event(action: str, username: str = None, user_id: int = None, resource_id: str = None, details: str = ""):
    """Record security & operational actions in audit_log."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO audit_log (user_id, username, action, resource_id, details)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, username, action, resource_id, details))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Audit log error: {e}")

# ----------------- Backend-Enforced Access Controls -----------------
def get_complaints_for_department(department_id: int):
    """
    BACKEND-ENFORCED ACCESS RESTRICTION:
    Staff can access ONLY complaints assigned to their own department.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.*, d.name as department_name, d.code as department_code
        FROM complaints c
        LEFT JOIN departments d ON c.assigned_department_id = d.id
        WHERE c.assigned_department_id = ?
        ORDER BY c.id DESC
    """, (department_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_all_complaints_admin():
    """Administrator access: view all campus complaints across all departments."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.*, d.name as department_name, d.code as department_code
        FROM complaints c
        LEFT JOIN departments d ON c.assigned_department_id = d.id
        ORDER BY c.id DESC
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_complaints_for_student(student_id: int, student_name: str = None, student_email: str = None):
    """Student access: view only their own complaints by student ID or matching name/email."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.*, d.name as department_name, d.code as department_code
        FROM complaints c
        LEFT JOIN departments d ON c.assigned_department_id = d.id
        WHERE c.student_id = ? 
           OR (c.student_id IS NULL AND (LOWER(c.student_name) = LOWER(?) OR LOWER(c.student_email) = LOWER(?)))
        ORDER BY c.id DESC
    """, (student_id, student_name or "", student_email or ""))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

# ----------------- Status Workflow & Tracking -----------------
def log_status_transition(complaint_id: int, old_status: str, new_status: str, 
                          user_id: int, user_name: str, remarks: str = "", 
                          rejection_reason: str = None, resolution_notes: str = None,
                          resolution_image_path: str = None):
    """
    Update complaint status:
    Received -> Accepted -> In Progress -> Resolved / Rejected
    Records timestamped activity in status_history and triggers student notification.
    """
    conn = get_connection()
    cursor = conn.cursor()

    resolved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if new_status == "Resolved" else None
    
    update_sql = "UPDATE complaints SET status = ?, updated_at = CURRENT_TIMESTAMP"
    params = [new_status]

    if rejection_reason:
        update_sql += ", rejection_reason = ?"
        params.append(rejection_reason)
    if resolution_notes:
        update_sql += ", resolution_notes = ?"
        params.append(resolution_notes)
    if resolution_image_path:
        update_sql += ", resolution_image_path = ?"
        params.append(resolution_image_path)
    if resolved_at:
        update_sql += ", resolved_at = ?"
        params.append(resolved_at)

    update_sql += " WHERE id = ?"
    params.append(complaint_id)

    cursor.execute(update_sql, tuple(params))

    # 2. Insert into status_history
    cursor.execute("""
        INSERT INTO status_history (complaint_id, old_status, new_status, changed_by_user_id, changed_by_name, remarks)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (complaint_id, old_status, new_status, user_id, user_name, remarks))

    # 3. Notify student
    cursor.execute("SELECT ticket_number, student_id, assigned_department FROM complaints WHERE id = ?", (complaint_id,))
    c_row = cursor.fetchone()
    
    if c_row and c_row['student_id']:
        notif_msg = f"Your complaint {c_row['ticket_number']} status was updated to '{new_status}' by {user_name} ({c_row['assigned_department']})."
        if remarks:
            notif_msg += f" Remarks: {remarks}"
        if rejection_reason:
            notif_msg += f" Rejection Reason: {rejection_reason}"

        cursor.execute("""
            INSERT INTO notifications (recipient_role, recipient_user_id, complaint_id, title, message, notification_type)
            VALUES ('student', ?, ?, ?, ?, 'STATUS_CHANGE')
        """, (c_row['student_id'], complaint_id, f"Ticket {c_row['ticket_number']}: {new_status}", notif_msg))

    conn.commit()
    conn.close()

    log_audit_event("STATUS_UPDATE", username=user_name, user_id=user_id, resource_id=str(complaint_id), 
                    details=f"Status transitioned from {old_status} to {new_status}")

def student_reopen_complaint(complaint_id: int, student_id: int, student_name: str, reopen_reason: str):
    """Allows students to reopen complaints if the issue is not fixed."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT ticket_number, assigned_department_id, assigned_department FROM complaints WHERE id = ?", (complaint_id,))
    c_row = cursor.fetchone()
    if not c_row:
        conn.close()
        return False

    ticket_number = c_row['ticket_number']
    dept_id = c_row['assigned_department_id']
    dept_name = c_row['assigned_department']

    # Update complaint
    cursor.execute("""
        UPDATE complaints
        SET status = 'Reopened', student_confirmed = -1, reopen_reason = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (reopen_reason, complaint_id))

    # Log in status_history
    cursor.execute("""
        INSERT INTO status_history (complaint_id, old_status, new_status, changed_by_user_id, changed_by_name, remarks)
        VALUES (?, 'Resolved', 'Reopened', ?, ?, ?)
    """, (complaint_id, student_id, f"{student_name} (Student)", f"Issue not resolved: {reopen_reason}"))

    # Alert Department Staff (Requirement 6)
    if dept_id:
        cursor.execute("""
            INSERT INTO notifications (recipient_role, recipient_department_id, complaint_id, title, message, notification_type)
            VALUES ('staff', ?, ?, ?, ?, 'REOPENED')
        """, (
            dept_id, 
            complaint_id, 
            f"🔄 Reopened Complaint: {ticket_number}", 
            f"Student {student_name} indicated the issue still persists: '{reopen_reason}'"
        ))

    conn.commit()
    conn.close()

    log_audit_event("COMPLAINT_REOPENED", username=student_name, user_id=student_id, resource_id=ticket_number, details=reopen_reason)
    return True

def student_confirm_fixed(complaint_id: int, student_id: int, student_name: str):
    """Student confirms issue is fixed -> closes ticket."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE complaints 
        SET status = 'Closed', student_confirmed = 1, updated_at = CURRENT_TIMESTAMP 
        WHERE id = ?
    """, (complaint_id,))

    cursor.execute("""
        INSERT INTO status_history (complaint_id, old_status, new_status, changed_by_user_id, changed_by_name, remarks)
        VALUES (?, 'Resolved', 'Closed', ?, ?, 'Student verified issue fixed successfully.')
    """, (complaint_id, student_id, f"{student_name} (Student)"))

    conn.commit()
    conn.close()
    log_audit_event("COMPLAINT_CLOSED", username=student_name, user_id=student_id, resource_id=str(complaint_id), details="Student confirmed issue fixed")

def fetch_status_history_for_complaint(complaint_id: int):
    """Retrieve complete timestamped activity timeline for a complaint."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT old_status, new_status, changed_by_name, remarks, timestamp
        FROM status_history
        WHERE complaint_id = ?
        ORDER BY id ASC
    """, (complaint_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

# ----------------- Notifications System -----------------
def fetch_notifications_for_staff(department_id: int):
    """Fetch notifications for department staff (new assignments, high priority, reopened)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, complaint_id, title, message, notification_type, is_read, created_at
        FROM notifications
        WHERE recipient_role = 'staff' AND (recipient_department_id = ? OR recipient_department_id IS NULL)
        ORDER BY id DESC
    """, (department_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def fetch_notifications_for_student(student_id: int):
    """Fetch notifications for student."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, complaint_id, title, message, notification_type, is_read, created_at
        FROM notifications
        WHERE recipient_role = 'student' AND recipient_user_id = ?
        ORDER BY id DESC
    """, (student_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def mark_notification_read(notif_id: int):
    """Mark a notification as read."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notif_id,))
    conn.commit()
    conn.close()

# ----------------- Department Analytics -----------------
def fetch_department_analytics(department_id: int) -> dict:
    """
    Computes:
    - Total assigned
    - Resolved complaints
    - Pending complaints (Received, Accepted, In Progress, Reopened)
    - High-priority complaints
    - Average resolution time (in hours)
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM complaints WHERE assigned_department_id = ?", (department_id,))
    total_assigned = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM complaints 
        WHERE assigned_department_id = ? AND status IN ('Resolved', 'Closed')
    """, (department_id,))
    resolved_count = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM complaints 
        WHERE assigned_department_id = ? AND status IN ('Received', 'Accepted', 'In Progress', 'Reopened')
    """, (department_id,))
    pending_count = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM complaints 
        WHERE assigned_department_id = ? AND priority = 'High'
    """, (department_id,))
    high_priority_count = cursor.fetchone()[0]

    # Calculate average resolution time for resolved complaints
    cursor.execute("""
        SELECT created_at, resolved_at FROM complaints
        WHERE assigned_department_id = ? AND resolved_at IS NOT NULL
    """, (department_id,))
    resolved_rows = cursor.fetchall()
    conn.close()

    avg_resolution_hours = 0.0
    if resolved_rows:
        durations = []
        for row in resolved_rows:
            try:
                t_start = datetime.strptime(row['created_at'], "%Y-%m-%d %H:%M:%S")
                t_end = datetime.strptime(row['resolved_at'], "%Y-%m-%d %H:%M:%S")
                hours = (t_end - t_start).total_seconds() / 3600.0
                if hours >= 0:
                    durations.append(hours)
            except Exception:
                pass
        if durations:
            avg_resolution_hours = round(sum(durations) / len(durations), 1)

    return {
        "total_assigned": total_assigned,
        "resolved_count": resolved_count,
        "pending_count": pending_count,
        "high_priority_count": high_priority_count,
        "avg_resolution_hours": avg_resolution_hours
    }

# ----------------- Administrator Account Management -----------------
def admin_create_staff_account(admin_user: dict, username: str, email: str, password: str, full_name: str, department_id: int, phone: str = ""):
    """Only administrators can create staff accounts."""
    if not admin_user or admin_user.get('role') != 'admin':
        raise PermissionError("Access Denied: Only administrators can create staff accounts.")

    pwd_hash = hash_password(password)
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO users (username, email, password_hash, full_name, role, department_id, phone, is_active)
            VALUES (?, ?, ?, ?, 'staff', ?, ?, 1)
        """, (username.strip().lower(), email.strip().lower(), pwd_hash, full_name.strip(), department_id, phone.strip()))
        conn.commit()
        uid = cursor.lastrowid
        conn.close()
        log_audit_event("STAFF_CREATED", username=admin_user.get('username'), user_id=admin_user.get('id'), 
                        resource_id=username, details=f"Admin created staff account {full_name} for dept {department_id}")
        return uid, None
    except Exception as e:
        conn.close()
        return None, str(e)

def admin_set_staff_active_status(admin_user: dict, staff_id: int, is_active: bool):
    """Only administrators can activate/deactivate staff accounts."""
    if not admin_user or admin_user.get('role') != 'admin':
        raise PermissionError("Access Denied: Only administrators can modify staff status.")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_active = ? WHERE id = ?", (1 if is_active else 0, staff_id))
    conn.commit()
    conn.close()

    status_str = "ACTIVATED" if is_active else "DEACTIVATED"
    log_audit_event(f"STAFF_{status_str}", username=admin_user.get('username'), user_id=admin_user.get('id'), resource_id=str(staff_id))

def get_all_departments():
    """Retrieve all active college departments."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, code, name, default_email, description FROM departments WHERE is_active = 1 ORDER BY name ASC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_all_users_admin():
    """Admin only: list all users with their departments."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.id, u.username, u.email, u.full_name, u.role, u.department_id, u.phone, u.is_active, u.created_at,
               d.name as department_name, d.code as department_code
        FROM users u
        LEFT JOIN departments d ON u.department_id = d.id
        ORDER BY u.role ASC, u.id ASC
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_audit_logs(limit: int = 150):
    """Admin only: retrieve recent audit log events."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, timestamp, user_id, username, action, resource_id, details
        FROM audit_log
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_complaint_by_id(complaint_id: int):
    """Retrieve detailed record for a specific complaint."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.*, d.name as department_name, d.code as department_code, d.default_email as dept_default_email
        FROM complaints c
        LEFT JOIN departments d ON c.assigned_department_id = d.id
        WHERE c.id = ?
    """, (complaint_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_related_asset(equipment_id: str = None, location: str = None, sub_location: str = None):
    """Cross-reference equipment asset records for complaint details."""
    conn = get_connection()
    cursor = conn.cursor()
    if equipment_id:
        cursor.execute("SELECT * FROM equipment_records WHERE equipment_id = ?", (equipment_id,))
        row = cursor.fetchone()
        if row:
            conn.close()
            return dict(row)
    
    # Try finding asset by location & sub_location
    if location:
        cursor.execute("""
            SELECT * FROM equipment_records 
            WHERE location = ? AND (sub_location = ? OR sub_location IS NULL)
            LIMIT 1
        """, (location, sub_location or ""))
        row = cursor.fetchone()
        if row:
            conn.close()
            return dict(row)

    conn.close()
    return None

