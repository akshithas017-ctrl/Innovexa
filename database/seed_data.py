import sqlite3
import os
from datetime import datetime, timedelta
from database.db import get_connection, init_db
from utils.security import hash_password

def seed_sample_data(force_reseed=False):
    """Seed departments, user accounts, equipment records, complaints, history, and notifications."""
    conn = get_connection()
    cursor = conn.cursor()

    if force_reseed:
        cursor.execute("DROP TABLE IF EXISTS notifications")
        cursor.execute("DROP TABLE IF EXISTS status_history")
        cursor.execute("DROP TABLE IF EXISTS audit_log")
        cursor.execute("DROP TABLE IF EXISTS agent_logs")
        cursor.execute("DROP TABLE IF EXISTS work_orders")
        cursor.execute("DROP TABLE IF EXISTS complaints")
        cursor.execute("DROP TABLE IF EXISTS equipment_records")
        cursor.execute("DROP TABLE IF EXISTS users")
        cursor.execute("DROP TABLE IF EXISTS departments")
        conn.commit()
    conn.close()

    init_db()
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Seed College Departments
    cursor.execute("SELECT COUNT(*) FROM departments")
    if cursor.fetchone()[0] == 0:
        departments = [
            ("CSE", "Computer Science & Engineering", "cse.facilities@campus.edu", "Computing labs, software servers, and academic department facilities"),
            ("ISE", "Information Science & Engineering", "ise.facilities@campus.edu", "Information technology and network laboratory infrastructure"),
            ("AIML", "Artificial Intelligence & Machine Learning", "aiml.facilities@campus.edu", "AI computing clusters, GPU workstations, and departmental labs"),
            ("AIDS", "Artificial Intelligence & Data Science", "aids.facilities@campus.edu", "Data analytics labs, presentation studios, and seminar halls"),
            ("ECE", "Electronics & Communication Engineering", "ece.facilities@campus.edu", "Circuits, communication labs, VLSI design facilities"),
            ("EEE", "Electrical & Electronics Engineering", "electrical.maintenance@campus.edu", "High voltage labs, power electronics, electrical machinery"),
            ("MECH", "Mechanical Engineering", "mech.workshop@campus.edu", "Workshops, thermodynamics labs, CAD/CAM design center"),
            ("CIVIL", "Civil Engineering & Infrastructure", "civil.infra@campus.edu", "Structures, environmental testing, civil works, building infrastructure"),
            ("MBA", "Management Studies", "mba.dept@campus.edu", "Auditoriums, case-study rooms, executive conference suites"),
            ("MCA", "Computer Applications", "mca.dept@campus.edu", "Software development centers, server rooms, project labs"),
            ("LIBRARY", "Central Library Facilities", "library.facilities@campus.edu", "Digital reading halls, study cubicles, book circulation sections"),
            ("HOSTEL", "Hostel Management & Residential Services", "hostel.office@campus.edu", "Hostel rooms, residential dining, student recreation centers"),
            ("ESTATE_HVAC", "Estate & Facilities (HVAC)", "facilities.hvac@campus.edu", "Central air conditioning, ventilation, and chiller plants"),
            ("PLUMBING", "Campus Water & Plumbing Services", "plumbing.services@campus.edu", "Water filtration RO plants, piping, restrooms, sanitization taps"),
            ("IT_NETWORKS", "Campus IT & Network Infrastructure", "it.networks@campus.edu", "Campus-wide Wi-Fi access points, fiber backbones, firewalls"),
            ("SANITATION", "Sanitation & Hygiene Services", "sanitation@campus.edu", "Campus cleanliness, waste segregation, washroom hygiene")
        ]
        cursor.executemany("""
            INSERT INTO departments (code, name, default_email, description, is_active)
            VALUES (?, ?, ?, ?, 1)
        """, departments)
        conn.commit()

    # Map department code -> dict
    cursor.execute("SELECT code, id, name, default_email FROM departments")
    dep_map = {row['code']: row for row in cursor.fetchall()}

    # 2. Seed Users
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        users_data = [
            # Administrator
            ("admin", "admin@campusfix.edu", hash_password("admin123"), "Dr. Rajesh Kumar", "admin", None, "+91 98765 00001"),
            
            # Department Staff
            ("staff_cse", "staff.cse@campusfix.edu", hash_password("staff123"), "Prof. Sunita Rao", "staff", dep_map["CSE"]['id'], "+91 98765 11001"),
            ("staff_hvac", "hvac.staff@campusfix.edu", hash_password("staff123"), "Vikram Joshi", "staff", dep_map["ESTATE_HVAC"]['id'], "+91 98765 22002"),
            ("staff_plumbing", "plumbing.staff@campusfix.edu", hash_password("staff123"), "Ramesh Kumar", "staff", dep_map["PLUMBING"]['id'], "+91 98765 33003"),
            ("staff_it", "it.staff@campusfix.edu", hash_password("staff123"), "Ananya Deshmukh", "staff", dep_map["IT_NETWORKS"]['id'], "+91 98765 44004"),
            ("staff_hostel", "hostel.warden@campusfix.edu", hash_password("staff123"), "Col. S. N. Murthy", "staff", dep_map["HOSTEL"]['id'], "+91 98765 55005"),
            ("staff_library", "library.head@campusfix.edu", hash_password("staff123"), "Meenakshi Sundaram", "staff", dep_map["LIBRARY"]['id'], "+91 98765 66006"),
            
            # Students
            ("student_aarav", "aarav.sharma@campus.edu", hash_password("student123"), "Aarav Sharma", "student", None, "+91 98765 99001"),
            ("student_priya", "priya.p@campus.edu", hash_password("student123"), "Priya Patel", "student", None, "+91 98765 99002")
        ]

        cursor.executemany("""
            INSERT INTO users (username, email, password_hash, full_name, role, department_id, phone, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """, users_data)
        conn.commit()

    cursor.execute("SELECT username, id FROM users")
    user_map = {row['username']: row['id'] for row in cursor.fetchall()}

    # 3. Seed Equipment Records (Retained in database for AI cross-referencing)
    cursor.execute("SELECT COUNT(*) FROM equipment_records")
    if cursor.fetchone()[0] == 0:
        sample_equipment = [
            ("AC-LIB-201", "Daikin 2-Ton Inverter AC", "HVAC", "Central Library", "2nd Floor Reading Hall", "2026-09-15", "Operational"),
            ("AC-LIB-202", "Daikin 2-Ton Inverter AC", "HVAC", "Central Library", "2nd Floor Reading Hall", "2026-09-15", "Faulty"),
            ("PRJ-AUD-01", "Epson PowerLite Laser Projector", "IT & AV", "Main Auditorium", "Stage A", "2026-10-01", "Operational"),
            ("WIFI-CS-301", "Cisco Catalyst Access Point", "IT & Network", "Computer Science Block", "3rd Floor Lab 4", "2026-10-10", "Operational"),
            ("WC-HST-101", "Kent Commercial Water Cooler & RO", "Plumbing", "Boys Hostel Block B", "Ground Floor Lobby", "2026-08-20", "Operational"),
            ("WC-HST-102", "Kent Commercial Water Cooler & RO", "Plumbing", "Girls Hostel Block A", "1st Floor Pantry", "2026-08-25", "Faulty"),
            ("GEN-PWR-01", "Cummins 250kVA Campus Generator", "Electrical", "Utility Substation", "Substation Yard", "2026-11-01", "Operational"),
            ("LIFT-ENG-01", "Otis 8-Passenger Elevator", "Mechanical", "Engineering Academic Block", "South Wing Elevator Bay", "2026-10-15", "Operational"),
            ("FURN-SEM-12", "Executive Ergonomic Chair Set (x30)", "Furniture", "Management Block", "Seminar Hall 2", "2026-07-12", "Operational")
        ]

        cursor.executemany("""
            INSERT INTO equipment_records (equipment_id, name, category, location, sub_location, last_serviced, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, sample_equipment)
        conn.commit()

    # 4. Seed Complaints with Image URLs, Asset Details, Statuses
    cursor.execute("SELECT COUNT(*) FROM complaints")
    if cursor.fetchone()[0] == 0:
        sample_complaints = [
            # Complaint 1: HVAC (In Progress)
            (
                "CFX-2026-1001",
                user_map["student_aarav"],
                "Aarav Sharma",
                "aarav.sharma@campus.edu",
                "Central Library",
                "2nd Floor Reading Hall",
                "The air conditioning unit AC-LIB-202 in the quiet study corner has been leaking water onto the study desks and making a loud buzzing rattle.",
                "https://images.unsplash.com/photo-1581092160607-ee22621dd758?w=500",
                None,
                "HVAC",
                "High",
                "High safety and water damage risk: Active condensate water leakage onto student study desks with risk to electrical sockets and library books.",
                "Estate & Facilities (HVAC)",
                dep_map["ESTATE_HVAC"]['id'],
                "facilities.hvac@campus.edu",
                "In Progress",
                None,
                None,
                0,
                None,
                0,
                None,
                "AC-LIB-202",
                "Daikin 2-Ton Inverter AC",
                (datetime.now() - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S"),
                None
            ),
            # Complaint 2: Plumbing (Accepted)
            (
                "CFX-2026-1002",
                user_map["student_priya"],
                "Priya Patel",
                "priya.p@campus.edu",
                "Girls Hostel Block A",
                "1st Floor Pantry",
                "Water purifier WC-HST-102 tap is broken and clean drinking water is continuously overflowing onto the corridor floor.",
                "https://images.unsplash.com/photo-1585704032915-c3400ca199e7?w=500",
                None,
                "Plumbing",
                "High",
                "High urgency and health hazard: Continuous overflow of drinking water creates slip risk on corridor floor and cuts off clean drinking water supply for hostel residents.",
                "Campus Water & Plumbing Services",
                dep_map["PLUMBING"]['id'],
                "plumbing.services@campus.edu",
                "Accepted",
                None,
                None,
                0,
                None,
                0,
                None,
                "WC-HST-102",
                "Kent Commercial Water Cooler & RO",
                (datetime.now() - timedelta(hours=4)).strftime("%Y-%m-%d %H:%M:%S"),
                None
            ),
            # Complaint 3: CSE (Received)
            (
                "CFX-2026-1003",
                user_map["student_aarav"],
                "Aarav Sharma",
                "aarav.sharma@campus.edu",
                "Computer Science Block",
                "3rd Floor Lab 4",
                "Wi-Fi connection drops intermittently every 5 minutes during our distributed systems practicals.",
                None,
                None,
                "IT & Network",
                "Medium",
                "Medium priority: Network disruption impacting computer science practical lab session; no direct safety hazard.",
                "Computer Science & Engineering",
                dep_map["CSE"]['id'],
                "cse.facilities@campus.edu",
                "Received",
                None,
                None,
                0,
                None,
                0,
                None,
                "WIFI-CS-301",
                "Cisco Catalyst Access Point",
                (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
                None
            ),
            # Complaint 4: HVAC (Resolved)
            (
                "CFX-2026-1004",
                user_map["student_aarav"],
                "Aarav Sharma",
                "aarav.sharma@campus.edu",
                "Central Library",
                "Ground Floor Circulation",
                "Thermostat in circulation foyer stuck at 16 degrees causing severe draft.",
                None,
                "https://images.unsplash.com/photo-1581092160607-ee22621dd758?w=500",
                "HVAC",
                "Low",
                "Low priority: Temperature regulation issue in foyer; no active damage or safety hazard.",
                "Estate & Facilities (HVAC)",
                dep_map["ESTATE_HVAC"]['id'],
                "facilities.hvac@campus.edu",
                "Resolved",
                None,
                "Recalibrated digital thermostat and replaced sensor battery. Temperature stabilized at 24C.",
                0,
                None,
                0,
                None,
                "AC-LIB-201",
                "Daikin 2-Ton Inverter AC",
                (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
                (datetime.now() - timedelta(hours=14)).strftime("%Y-%m-%d %H:%M:%S")
            ),
            # Complaint 5: CSE (Reopened)
            (
                "CFX-2026-1005",
                user_map["student_aarav"],
                "Aarav Sharma",
                "aarav.sharma@campus.edu",
                "Computer Science Block",
                "1st Floor Seminar Hall",
                "HDMI audio cable crackling during technical seminars.",
                None,
                None,
                "IT & AV",
                "Medium",
                "Medium priority: Lecture AV issue.",
                "Computer Science & Engineering",
                dep_map["CSE"]['id'],
                "cse.facilities@campus.edu",
                "Reopened",
                None,
                None,
                -1,
                "The audio cable was replaced but the projector speaker hum still persists on full volume.",
                0,
                None,
                "PRJ-AUD-01",
                "Epson PowerLite Laser Projector",
                (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S"),
                None
            )
        ]

        cursor.executemany("""
            INSERT INTO complaints (
                ticket_number, student_id, student_name, student_email, location, sub_location,
                description, image_path, resolution_image_path, category, priority, priority_reason,
                assigned_department, assigned_department_id, department_email, status,
                rejection_reason, resolution_notes, student_confirmed, reopen_reason,
                is_duplicate, duplicate_of_id, related_equipment_id, related_equipment_name,
                created_at, resolved_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, sample_complaints)
        conn.commit()

        # 5. Status History Timeline
        history_records = [
            (1, "Received", "Accepted", user_map["staff_hvac"], "Vikram Joshi", "Assigned senior HVAC technician to inspect condensate line.", (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")),
            (1, "Accepted", "In Progress", user_map["staff_hvac"], "Vikram Joshi", "Technician on-site clearing drain obstruction.", (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")),
            (2, "Received", "Accepted", user_map["staff_plumbing"], "Ramesh Kumar", "Emergency plumber dispatched with replacement Kent tap cartridge.", (datetime.now() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")),
            (4, "Received", "Accepted", user_map["staff_hvac"], "Vikram Joshi", "Work scheduled.", (datetime.now() - timedelta(hours=20)).strftime("%Y-%m-%d %H:%M:%S")),
            (4, "Accepted", "In Progress", user_map["staff_hvac"], "Vikram Joshi", "Recalibrating sensor.", (datetime.now() - timedelta(hours=16)).strftime("%Y-%m-%d %H:%M:%S")),
            (4, "In Progress", "Resolved", user_map["staff_hvac"], "Vikram Joshi", "Recalibrated digital thermostat and replaced sensor battery. Temperature stabilized at 24C.", (datetime.now() - timedelta(hours=14)).strftime("%Y-%m-%d %H:%M:%S")),
            (5, "Resolved", "Reopened", user_map["student_aarav"], "Aarav Sharma (Student)", "The audio cable was replaced but the projector speaker hum still persists on full volume.", (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S"))
        ]
        cursor.executemany("""
            INSERT INTO status_history (complaint_id, old_status, new_status, changed_by_user_id, changed_by_name, remarks, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, history_records)

        # 6. Notifications for Staff & Students
        notifications_data = [
            # Staff alerts
            ("staff", None, dep_map["ESTATE_HVAC"]['id'], 1, "⚡ High Priority Alert: CFX-2026-1001", "High priority water leakage reported at Central Library 2nd Floor Reading Hall.", "HIGH_PRIORITY", 0, (datetime.now() - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S")),
            ("staff", None, dep_map["CSE"]['id'], 3, "📌 New Assignment: CFX-2026-1003", "New complaint assigned to Computer Science & Engineering for 3rd Floor Lab 4 Wi-Fi.", "NEW_ASSIGNMENT", 0, (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")),
            ("staff", None, dep_map["CSE"]['id'], 5, "🔄 Complaint Reopened: CFX-2026-1005", "Student Aarav Sharma reopened CFX-2026-1005: Projector speaker hum persists.", "REOPENED", 0, (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")),
            
            # Student alerts
            ("student", user_map["student_aarav"], None, 1, "Status Update: CFX-2026-1001", "Vikram Joshi updated your ticket status to 'In Progress'.", "STATUS_CHANGE", 0, (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")),
            ("student", user_map["student_aarav"], None, 4, "Complaint Resolved: CFX-2026-1004", "Your thermostat issue is marked Resolved. Please verify and confirm.", "STATUS_CHANGE", 0, (datetime.now() - timedelta(hours=14)).strftime("%Y-%m-%d %H:%M:%S"))
        ]
        cursor.executemany("""
            INSERT INTO notifications (recipient_role, recipient_user_id, recipient_department_id, complaint_id, title, message, notification_type, is_read, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, notifications_data)

        # 7. Audit Log Initial Records
        audit_records = [
            (user_map["staff_hvac"], "staff_hvac", "STATUS_UPDATE", "CFX-2026-1001", "Staff updated status to In Progress", (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")),
            (user_map["staff_hvac"], "staff_hvac", "STATUS_UPDATE", "CFX-2026-1004", "Staff resolved complaint and uploaded resolution details", (datetime.now() - timedelta(hours=14)).strftime("%Y-%m-%d %H:%M:%S"))
        ]
        cursor.executemany("""
            INSERT INTO audit_log (user_id, username, action, resource_id, details, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, audit_records)

        # 8. Work Orders
        sample_wos = [
            ("WO-2026-001", 1, "Estate & Facilities (HVAC)", "High", "Inspect Daikin AC unit AC-LIB-202. Fix condensate leak.", "In Progress", (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")),
            ("WO-2026-002", 2, "Campus Water & Plumbing Services", "High", "Emergency repair of water dispenser tap WC-HST-102.", "Accepted", (datetime.now() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")),
            ("WO-2026-003", 3, "Computer Science & Engineering", "Medium", "Inspect Cisco AP WIFI-CS-301 in Lab 4.", "Received", (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")),
            ("WO-2026-004", 4, "Estate & Facilities (HVAC)", "Low", "Recalibrate thermostat at circulation desk.", "Completed", (datetime.now() - timedelta(hours=14)).strftime("%Y-%m-%d %H:%M:%S"))
        ]
        cursor.executemany("""
            INSERT INTO work_orders (wo_number, complaint_id, assigned_department, priority, instructions, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, sample_wos)

        # 9. Agent Activity Logs
        sample_logs = [
            (1, "Detection Agent", "Identified category as HVAC and detected location Central Library 2nd Floor.", '{"category": "HVAC", "confidence": 0.98}', (datetime.now() - timedelta(hours=5, minutes=58)).strftime("%Y-%m-%d %H:%M:%S")),
            (1, "Investigation Agent", "Cross-referenced equipment AC-LIB-202. Verified this is a primary issue (no open duplicate within 24h).", '{"duplicate": false, "equipment_match": "AC-LIB-202"}', (datetime.now() - timedelta(hours=5, minutes=55)).strftime("%Y-%m-%d %H:%M:%S")),
            (1, "Priority Agent", "Assigned priority HIGH: Water leakage hazard over student study desks.", '{"priority": "High", "urgency_score": 9}', (datetime.now() - timedelta(hours=5, minutes=52)).strftime("%Y-%m-%d %H:%M:%S")),
            (1, "Action Agent", "Generated Work Order WO-2026-001 dispatched to Estate & Facilities (HVAC).", '{"work_order": "WO-2026-001"}', (datetime.now() - timedelta(hours=5, minutes=50)).strftime("%Y-%m-%d %H:%M:%S"))
        ]
        cursor.executemany("""
            INSERT INTO agent_logs (complaint_id, agent_name, action_summary, structured_output, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, sample_logs)

        conn.commit()

    conn.close()

if __name__ == "__main__":
    seed_sample_data(force_reseed=True)
    print("Database seeded with full Department Staff and Operations workflow.")
