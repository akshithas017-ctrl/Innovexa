import sys
import os

# Add workspace to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db import get_connection, init_db
from utils.complaint_engine import (
    check_duplicate_complaint, 
    classify_priority_explainable, 
    suggest_department_and_email
)
from app import fetch_complaints_df, fetch_work_orders_df

def test_duplicate_detection():
    print("--- TEST 1: DUPLICATE COMPLAINT DETECTION ---")
    dup = check_duplicate_complaint(
        "Central Library", 
        "2nd Floor Reading Hall", 
        "The AC unit is leaking water onto study desks and rattling"
    )
    assert dup["is_duplicate"] is True, "Should detect duplicate of CFX-2026-1001"
    assert dup["existing_ticket"] == "CFX-2026-1001", f"Expected CFX-2026-1001, got {dup.get('existing_ticket')}"
    assert dup["status"] in ["In Progress", "Work Order Created", "Received", "Accepted"], f"Expected active status, got {dup.get('status')}"
    assert dup["assigned_department"] == "Estate & Facilities (HVAC)", "Department mismatch"
    assert dup["department_email"] == "facilities.hvac@campus.edu", "Email mismatch"
    print(f"✅ Duplicate detected: Ticket={dup['existing_ticket']}, Status={dup['status']}, Dept={dup['assigned_department']}, Email={dup['department_email']}")

    non_dup = check_duplicate_complaint(
        "Main Auditorium", 
        "Stage A", 
        "Microphone battery level indicator is low"
    )
    assert non_dup["is_duplicate"] is False, "Should not detect duplicate for new auditorium issue"
    print("✅ Non-duplicate check passed cleanly!")

def test_explainable_priority():
    print("\n--- TEST 2: EXPLAINABLE PRIORITY CLASSIFICATION ---")
    # High Example: Exposed wires
    p_high = classify_priority_explainable("Exposed electrical wires near the switchboard sparking", "Engineering Block", "Room 201")
    assert p_high["priority"] == "High", f"Expected High, got {p_high['priority']}"
    assert any(w in p_high["reason"].lower() for w in ["spark", "electrocution", "safety", "fire", "shock"]), "Reason must explain safety hazard"
    print(f"✅ High Priority: {p_high['priority']} | Reason: {p_high['reason']}")

    # Medium Example: Projector not working in classroom
    p_med = classify_priority_explainable("Projector not working in one classroom during lecture", "Science Wing", "Hall B")
    assert p_med["priority"] == "Medium", f"Expected Medium, got {p_med['priority']}"
    assert any(w in p_med["reason"].lower() for w in ["academic", "classroom", "lecture", "projector"]), "Reason must explain classroom disruption"
    print(f"✅ Medium Priority: {p_med['priority']} | Reason: {p_med['reason']}")

    # Low Example: Minor furniture damage
    p_low = classify_priority_explainable("Minor furniture damage with scratched wood on desk", "Management Block", "Room 105")
    assert p_low["priority"] == "Low", f"Expected Low, got {p_low['priority']}"
    assert any(w in p_low["reason"].lower() for w in ["minor", "furniture", "routine", "cosmetic"]), "Reason must explain minor impact"
    print(f"✅ Low Priority: {p_low['priority']} | Reason: {p_low['reason']}")

def test_department_email():
    print("\n--- TEST 3: USER-EDITABLE DEPARTMENT EMAIL PERSISTENCE ---")
    conn = get_connection()
    cur = conn.cursor()
    custom_email = "custom.technician.leads@campus.edu"
    cur.execute("""
        INSERT INTO complaints (
            ticket_number, student_name, student_email, location, sub_location,
            description, category, priority, priority_reason, assigned_department,
            department_email, status
        ) VALUES ('CFX-TEST-200', 'Test Student', 'test@campus.edu', 'Science Wing', 'Lab 3',
                  'Microscope lens is loose', 'Lab Equipment', 'Low', 'Minor lens adjustment',
                  'Science Lab Maintenance', ?, 'Submitted')
    """, (custom_email,))
    conn.commit()
    cid = cur.lastrowid
    conn.close()

    # Verify retrieval
    df = fetch_complaints_df()
    saved = df[df["id"] == cid].iloc[0]
    assert saved["department_email"] == custom_email, f"Expected {custom_email}, got {saved['department_email']}"
    assert saved["priority_reason"] == "Minor lens adjustment"
    print(f"✅ Saved custom email verified in DB: {saved['department_email']} for Ticket: {saved['ticket_number']}")

    # Cleanup
    conn = get_connection()
    conn.cursor().execute("DELETE FROM complaints WHERE id = ?", (cid,))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    test_duplicate_detection()
    test_explainable_priority()
    test_department_email()
    print("\n🎉 ALL TESTS PASSED WITH 100% SUCCESS!")
