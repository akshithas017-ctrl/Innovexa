import sqlite3
import os
from datetime import datetime

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "campusfix.db")

def get_connection():
    """Establish and return SQLite database connection."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database tables for CampusFix with full Department Staff & Security support."""
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Departments Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS departments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        default_email TEXT NOT NULL,
        description TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 2. Users Table (Role-based access: student, staff, admin)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL, -- 'student', 'staff', 'admin'
        department_id INTEGER,
        phone TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (department_id) REFERENCES departments(id)
    )
    """)

    # 3. Complaints Table with Images, Explainable Priority, and Status Workflow
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS complaints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_number TEXT UNIQUE NOT NULL,
        student_id INTEGER,
        student_name TEXT NOT NULL,
        student_email TEXT NOT NULL,
        location TEXT NOT NULL,
        sub_location TEXT,
        description TEXT NOT NULL,
        image_path TEXT,
        resolution_image_path TEXT,
        category TEXT DEFAULT 'Uncategorized',
        priority TEXT DEFAULT 'Medium',
        priority_reason TEXT,
        assigned_department TEXT DEFAULT 'General Administration',
        assigned_department_id INTEGER,
        department_email TEXT,
        status TEXT DEFAULT 'Received', -- 'Received', 'Accepted', 'In Progress', 'Resolved', 'Closed', 'Reopened', 'Rejected'
        rejection_reason TEXT,
        resolution_notes TEXT,
        student_confirmed INTEGER DEFAULT 0, -- 1 = confirmed fixed, -1 = reopened
        reopen_reason TEXT,
        is_duplicate INTEGER DEFAULT 0,
        duplicate_of_id INTEGER,
        related_equipment_id TEXT,
        related_equipment_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        resolved_at TIMESTAMP,
        FOREIGN KEY (student_id) REFERENCES users(id),
        FOREIGN KEY (assigned_department_id) REFERENCES departments(id),
        FOREIGN KEY (duplicate_of_id) REFERENCES complaints(id)
    )
    """)

    # 4. Status History Table (Audit Timeline)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS status_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        complaint_id INTEGER NOT NULL,
        old_status TEXT,
        new_status TEXT NOT NULL,
        changed_by_user_id INTEGER,
        changed_by_name TEXT NOT NULL,
        remarks TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (complaint_id) REFERENCES complaints(id),
        FOREIGN KEY (changed_by_user_id) REFERENCES users(id)
    )
    """)

    # 5. Notifications Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipient_role TEXT, -- 'staff', 'student', 'all'
        recipient_user_id INTEGER,
        recipient_department_id INTEGER,
        complaint_id INTEGER,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        notification_type TEXT NOT NULL, -- 'NEW_ASSIGNMENT', 'HIGH_PRIORITY', 'REOPENED', 'STATUS_CHANGE'
        is_read INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (recipient_user_id) REFERENCES users(id),
        FOREIGN KEY (recipient_department_id) REFERENCES departments(id),
        FOREIGN KEY (complaint_id) REFERENCES complaints(id)
    )
    """)

    # 6. Audit Log Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        action TEXT NOT NULL, -- 'LOGIN', 'LOGOUT', 'PASSWORD_CHANGE', 'STATUS_UPDATE', 'STAFF_CREATED', 'STAFF_DEACTIVATED'
        resource_id TEXT,
        details TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 7. Equipment Records Table (Retained for AI duplicate & asset matching)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS equipment_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        equipment_id TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        location TEXT NOT NULL,
        sub_location TEXT,
        last_serviced TEXT,
        status TEXT DEFAULT 'Operational'
    )
    """)

    # 8. Work Orders Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS work_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        wo_number TEXT UNIQUE NOT NULL,
        complaint_id INTEGER NOT NULL,
        assigned_department TEXT NOT NULL,
        priority TEXT NOT NULL,
        instructions TEXT,
        status TEXT DEFAULT 'Pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (complaint_id) REFERENCES complaints(id)
    )
    """)

    # 9. Agent Activity Logs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS agent_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        complaint_id INTEGER,
        agent_name TEXT NOT NULL,
        action_summary TEXT NOT NULL,
        structured_output TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (complaint_id) REFERENCES complaints(id)
    )
    """)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database schema successfully initialized at", DB_PATH)
