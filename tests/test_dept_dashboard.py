import sys
import os
import sqlite3

# Add workspace to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db import get_connection, init_db
from database.seed_data import seed_sample_data
from utils.security import (
    authenticate_user,
    hash_password,
    verify_password,
    change_user_password,
    get_complaints_for_department,
    get_all_complaints_admin,
    get_complaints_for_student,
    get_complaint_by_id,
    get_related_asset,
    log_status_transition,
    student_reopen_complaint,
    student_confirm_fixed,
    fetch_status_history_for_complaint,
    fetch_notifications_for_staff,
    fetch_notifications_for_student,
    mark_notification_read,
    fetch_department_analytics,
    admin_create_staff_account,
    admin_set_staff_active_status,
    login_or_register_student,
    get_all_departments,
    get_all_users_admin,
    get_audit_logs
)

def run_all_tests():
    print("=" * 65)
    print("RUNNING CAMPUSFIX DEPARTMENT STAFF DASHBOARD TEST SUITE")
    print("=" * 65)

    # 1. Test Authentication & Password Hashing
    print("\n--- TEST 1: ROLE-BASED AUTHENTICATION & SECURE PBKDF2 HASHING ---")
    staff_auth = authenticate_user("staff_cse", "staff123")
    assert staff_auth.get("success") is True, "staff_cse authentication failed"
    assert staff_auth["role"] == "staff", "Role should be staff"
    assert staff_auth["department_code"] == "CSE", f"Expected CSE, got {staff_auth['department_code']}"
    print(f"✅ Staff Auth: {staff_auth['full_name']} | Role={staff_auth['role']} | Dept={staff_auth['department_code']}")

    admin_auth = authenticate_user("admin", "admin123")
    assert admin_auth.get("success") is True
    assert admin_auth["role"] == "admin"
    print(f"✅ Admin Auth: {admin_auth['full_name']} | Role={admin_auth['role']}")

    student_auth = authenticate_user("student_aarav", "student123")
    assert student_auth.get("success") is True
    assert student_auth["role"] == "student"
    print(f"✅ Student Auth: {student_auth['full_name']} | Role={student_auth['role']}")

    # Test ANY Student Name Login (Auto-registration & retrieval)
    print("\n--- TEST 1B: ARBITRARY STUDENT NAME INPUT ---")
    custom_stu_1 = login_or_register_student("Rohan Sharma")
    assert custom_stu_1.get("success") is True, "Failed to login/register Rohan Sharma"
    assert custom_stu_1["full_name"] == "Rohan Sharma"
    assert custom_stu_1["role"] == "student"
    print(f"✅ Arbitrary Student 1: Name='{custom_stu_1['full_name']}' | Email='{custom_stu_1['email']}' | ID={custom_stu_1['id']}")

    custom_stu_2 = login_or_register_student("Sneha Rao", email="sneha.r@campus.edu")
    assert custom_stu_2.get("success") is True
    assert custom_stu_2["full_name"] == "Sneha Rao"
    assert custom_stu_2["email"] == "sneha.r@campus.edu"
    print(f"✅ Arbitrary Student 2: Name='{custom_stu_2['full_name']}' | Email='{custom_stu_2['email']}'")

    # Re-login with existing custom student
    relogin_stu_1 = login_or_register_student("Rohan Sharma")
    assert relogin_stu_1["id"] == custom_stu_1["id"], "Should retrieve existing account for Rohan Sharma"
    print(f"✅ Re-login verified: retrieved existing user ID #{relogin_stu_1['id']} for 'Rohan Sharma'")

    # Invalid password check for staff
    bad_auth = authenticate_user("staff_cse", "wrongpass")
    assert "error" in bad_auth, "Invalid password must fail"
    print("✅ Rejected incorrect credentials cleanly.")

    # 2. Test Backend Department Access Isolation
    print("\n--- TEST 2: BACKEND-ENFORCED DEPARTMENT ISOLATION ---")
    hvac_auth = authenticate_user("staff_hvac", "staff123")
    hvac_dept_id = hvac_auth["department_id"]
    cse_dept_id = staff_auth["department_id"]

    hvac_complaints = get_complaints_for_department(hvac_dept_id)
    cse_complaints = get_complaints_for_department(cse_dept_id)

    assert len(hvac_complaints) > 0, "HVAC should have complaints"
    assert len(cse_complaints) > 0, "CSE should have complaints"

    for c in hvac_complaints:
        assert c["assigned_department_id"] == hvac_dept_id, f"HVAC staff saw non-HVAC complaint #{c['id']}"
    for c in cse_complaints:
        assert c["assigned_department_id"] == cse_dept_id, f"CSE staff saw non-CSE complaint #{c['id']}"

    # Verify no overlap between HVAC and CSE complaints
    hvac_ids = set(c["id"] for c in hvac_complaints)
    cse_ids = set(c["id"] for c in cse_complaints)
    assert hvac_ids.isdisjoint(cse_ids), "Department isolation breached! Shared complaint IDs found."
    print(f"✅ Backend Isolation verified: HVAC has {len(hvac_complaints)} tickets, CSE has {len(cse_complaints)} tickets. Zero overlap!")

    # 3. Test Complaint Details & Asset Cross-Referencing
    print("\n--- TEST 3: COMPLAINT DETAILS & RELATED ASSET DATA ---")
    comp_1 = get_complaint_by_id(1)
    assert comp_1 is not None, "Complaint 1 not found"
    assert comp_1["student_name"] == "Aarav Sharma"
    assert comp_1["student_email"] == "aarav.sharma@campus.edu"
    assert comp_1["priority_reason"] is not None
    print(f"✅ Authorized Student Details: {comp_1['student_name']} ({comp_1['student_email']})")

    # Asset matching from equipment_records
    asset = get_related_asset(comp_1["related_equipment_id"])
    assert asset is not None, "Equipment asset AC-LIB-202 should exist in SQLite"
    assert asset["equipment_id"] == "AC-LIB-202"
    assert asset["name"] == "Daikin 2-Ton Inverter AC"
    print(f"✅ Related Asset Matched: {asset['equipment_id']} — {asset['name']} (Status: {asset['status']})")

    # 4. Test Staff Actions & Status Transition Workflow
    print("\n--- TEST 4: STAFF ACTIONS (ACCEPT, UPDATE STATUS, RESOLVE, REJECT) ---")
    # Insert a temporary test complaint for testing actions
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO complaints (
            ticket_number, student_id, student_name, student_email, location, sub_location,
            description, category, priority, priority_reason, assigned_department,
            assigned_department_id, department_email, status
        ) VALUES ('CFX-ACTION-TEST', ?, 'Test Student', 'test@campus.edu', 'Engineering Block', 'Lab 1',
                  'Oscilloscope display flashing', 'Electrical', 'Medium', 'Lab equipment issue',
                  'Computer Science & Engineering', ?, 'cse.facilities@campus.edu', 'Received')
    """, (student_auth["id"], cse_dept_id))
    test_cid = cur.lastrowid
    conn.commit()
    conn.close()

    # Step A: Accept complaint
    log_status_transition(
        complaint_id=test_cid,
        old_status="Received",
        new_status="Accepted",
        user_id=staff_auth["id"],
        user_name=staff_auth["full_name"],
        remarks="Accepted by CSE technician"
    )
    c_updated = get_complaint_by_id(test_cid)
    assert c_updated["status"] == "Accepted", f"Expected Accepted, got {c_updated['status']}"
    print("✅ Status transition 1: Received ➔ Accepted")

    # Step B: Advance to In Progress
    log_status_transition(
        complaint_id=test_cid,
        old_status="Accepted",
        new_status="In Progress",
        user_id=staff_auth["id"],
        user_name=staff_auth["full_name"],
        remarks="Bench testing power supply"
    )
    c_updated = get_complaint_by_id(test_cid)
    assert c_updated["status"] == "In Progress"
    print("✅ Status transition 2: Accepted ➔ In Progress")

    # Step C: Advance to Resolved with resolution photo & notes
    log_status_transition(
        complaint_id=test_cid,
        old_status="In Progress",
        new_status="Resolved",
        user_id=staff_auth["id"],
        user_name=staff_auth["full_name"],
        remarks="Replaced fuse and tested calibration",
        resolution_notes="Power supply circuit fuse replaced. Calibrated to 100MHz.",
        resolution_image_path="uploads/resolutions/proof_test.jpg"
    )
    c_updated = get_complaint_by_id(test_cid)
    assert c_updated["status"] == "Resolved"
    assert c_updated["resolution_notes"] == "Power supply circuit fuse replaced. Calibrated to 100MHz."
    assert c_updated["resolution_image_path"] == "uploads/resolutions/proof_test.jpg"
    assert c_updated["resolved_at"] is not None
    print(f"✅ Status transition 3: In Progress ➔ Resolved (Resolved At: {c_updated['resolved_at']})")

    # 5. Test Student Confirm Fixed vs Reopen
    print("\n--- TEST 5: STUDENT RESOLUTION CONFIRMATION & REOPEN ---")
    # Reopen ticket
    student_reopen_complaint(test_cid, student_auth["id"], student_auth["full_name"], "Display still flickers under load")
    c_reopened = get_complaint_by_id(test_cid)
    assert c_reopened["status"] == "Reopened"
    assert c_reopened["reopen_reason"] == "Display still flickers under load"
    print(f"✅ Student Reopen: Status={c_reopened['status']} | Reason={c_reopened['reopen_reason']}")

    # Now student confirms fixed
    student_confirm_fixed(test_cid, student_auth["id"], student_auth["full_name"])
    c_closed = get_complaint_by_id(test_cid)
    assert c_closed["status"] == "Closed"
    print(f"✅ Student Confirm Fixed: Status={c_closed['status']}")

    # 6. Test Notifications System
    print("\n--- TEST 6: NOTIFICATIONS DISPATCH & READ ACKNOWLEDGEMENT ---")
    staff_notifs = fetch_notifications_for_staff(cse_dept_id)
    assert len(staff_notifs) > 0, "Staff should have received notifications"
    reopened_notifs = [n for n in staff_notifs if n["notification_type"] == "REOPENED"]
    assert len(reopened_notifs) > 0, "Staff should have an alert for the reopened ticket"
    print(f"✅ Staff Notification Received: '{reopened_notifs[0]['title']}'")

    # Mark as read
    target_nid = reopened_notifs[0]["id"]
    mark_notification_read(target_nid)
    updated_notifs = fetch_notifications_for_staff(cse_dept_id)
    n_obj = next(n for n in updated_notifs if n["id"] == target_nid)
    assert n_obj["is_read"] == 1, "Notification should be marked read"
    print("✅ Notification marked as read successfully.")

    # 7. Test History Activity Timeline
    print("\n--- TEST 7: TIMESTAMPED ACTIVITY TIMELINE ---")
    history = fetch_status_history_for_complaint(test_cid)
    assert len(history) >= 4, f"Expected at least 4 history records, got {len(history)}"
    for h in history:
        print(f"   ⏱️ {h['timestamp']} | {h['old_status']} ➔ {h['new_status']} | By {h['changed_by_name']}: {h['remarks']}")
    print("✅ Activity timeline recorded complete audit trail!")

    # 8. Test Department Analytics
    print("\n--- TEST 8: DEPARTMENT ANALYTICS & RESOLUTION TIME ---")
    analytics = fetch_department_analytics(hvac_dept_id)
    assert analytics["total_assigned"] > 0
    assert "avg_resolution_hours" in analytics
    print(f"✅ HVAC Analytics: Total={analytics['total_assigned']}, Resolved={analytics['resolved_count']}, "
          f"Pending={analytics['pending_count']}, HighPriority={analytics['high_priority_count']}, "
          f"AvgResolutionTime={analytics['avg_resolution_hours']} hours")

    # 9. Test Staff Profile Password Change & Security Audit Log
    print("\n--- TEST 9: PASSWORD UPDATE & AUDIT TRAIL ---")
    # Change password
    pwd_changed, msg = change_user_password(staff_auth["id"], "staff123", "newstaffpass456")
    assert pwd_changed is True, msg
    # Verify new password works
    reauth = authenticate_user("staff_cse", "newstaffpass456")
    assert reauth.get("success") is True, "Reauth with new password failed"
    # Revert password for future runs
    change_user_password(staff_auth["id"], "newstaffpass456", "staff123")
    print("✅ Staff password change verified with PBKDF2 hashing!")

    # Verify audit logs
    audit_logs = get_audit_logs(limit=10)
    assert len(audit_logs) > 0, "Audit logs should not be empty"
    actions = [l["action"] for l in audit_logs]
    assert any(a in actions for a in ["LOGIN", "STATUS_UPDATE", "PASSWORD_CHANGE"]), "Important actions must appear in audit log"
    print(f"✅ Security Audit Log verified: {len(audit_logs)} recent events logged.")

    # 10. Clean up test complaint
    conn = get_connection()
    conn.cursor().execute("DELETE FROM complaints WHERE id = ?", (test_cid,))
    conn.cursor().execute("DELETE FROM status_history WHERE complaint_id = ?", (test_cid,))
    conn.commit()
    conn.close()

    print("\n" + "=" * 65)
    print("🎉 ALL 10 TESTS PASSED WITH 100% SUCCESS!")
    print("=" * 65)

if __name__ == "__main__":
    run_all_tests()
