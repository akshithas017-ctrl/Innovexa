# CampusFix – AI-Powered Smart Campus Complaint Management System

CampusFix automates campus complaint handling using four collaborating AI agents powered by the Google Gemini API, Pandas, and SQLite, with professional role-based dashboards for **Department Staff**, **Students**, and **Administrators**.

---

## 🏛️ Department Staff Dashboard

The **Campus Equipment Directory** page has been removed from the navigation and replaced with a dedicated, role-isolated **Department Staff Dashboard** equipped with the following 9 core capabilities:

1. **Dashboard Overview**:
   - Real-time KPI summary: Total assigned, pending, in-progress, and resolved complaints.
   - Alert banners for high-priority hazards and student-reopened complaints.
2. **Assigned Complaints Queue**:
   - Displays complaint ID, description preview, location, priority badge, submission date, and status.
   - Instant search across tickets, locations, and keywords.
   - Dual-axis filtering by complaint status and priority level.
   - **Backend Enforced**: Staff only see complaints assigned strictly to their own department.
3. **Comprehensive Complaint Details**:
   - **Authorized Student Information Only**: Shows student name and campus email while protecting sensitive personal details.
   - Problem description and student-uploaded photographs.
   - AI category, explainable priority rationale, and duplicate detection status.
   - **Related Asset Details**: Cross-referenced equipment asset details (Asset ID, Name, Category, Last Serviced, Operational Status) from the campus asset database.
4. **Staff Complaint Actions**:
   - **Accept Complaint**: Acknowledge ticket and advance status.
   - **Reject Complaint**: Mandatory rejection reason input required; records reason and notifies student.
   - **Update Status**: Advance through lifecycle (`Received` ➔ `Accepted` ➔ `In Progress` ➔ `Resolved`).
   - **Technician Remarks**: Add operational log notes at each step.
   - **Resolution Photograph Upload**: Staff can upload resolution proof photos when marking an issue resolved.
5. **Sequential Status Tracking & Student Verification**:
   - `Received` ➔ `Accepted` ➔ `In Progress` ➔ `Resolved` ➔ `Closed`.
   - When marked **Resolved**, the student is prompted:
     - **Confirm Fixed**: Confirms resolution and officially closes ticket (`Closed`).
     - **Reopen Complaint**: If the problem persists, student enters an explanation and marks ticket as `Reopened`, immediately alerting department staff.
6. **Smart Notifications System**:
   - Alerts staff upon new complaint assignments, high-priority emergencies, and student reopen events.
   - Automatically notifies students whenever their ticket status changes or when remarks/rejection reasons are submitted.
   - Unread notification badges and one-click "Mark as Read" action.
7. **Timestamped Activity Timeline (History)**:
   - Full chronological audit history (`status_history`) tracking date, time, staff member name, previous status ➔ new status, and remarks.
8. **Department Analytics**:
   - Track resolved, pending, high-priority volume, and **average resolution time (in hours)**.
   - Interactive Plotly charts for priority and status distribution.
9. **Staff Profile & Account Security**:
   - Staff credentials viewer and PBKDF2-HMAC-SHA256 password change interface.
   - Session logout.

---

## 🔐 Security & Access Control

- **Backend-Enforced Isolation**: Staff queries parameterize `assigned_department_id = ?`, preventing unauthorized cross-department data access.
- **Cryptographic Password Hashing**: Passwords stored as salted PBKDF2-HMAC-SHA256 hashes (100,000 iterations); no plain text.
- **Administrative Privileges**: Only administrators can create staff accounts and activate/deactivate accounts.
- **Comprehensive Audit Logging**: All logins, logouts, status transitions, reopens, and user administrative changes are logged to `audit_log`.

---

## 🔑 Demo Hackathon Login Credentials

For demonstration and testing, enter any student name in the Student Sign-In tab or use the accounts below:

| Role | Username | Password | Full Name | Department |
| :--- | :--- | :--- | :--- | :--- |
| **👑 Admin** | `admin` | `admin123` | Dr. Rajesh Kumar | Central Administration |
| **🛠️ Staff (CSE)** | `staff_cse` | `staff123` | Prof. Sunita Rao | Computer Science & Engineering |
| **❄️ Staff (HVAC)** | `staff_hvac` | `staff123` | Vikram Joshi | Estate & Facilities (HVAC) |
| **🚰 Staff (Plumbing)** | `staff_plumbing` | `staff123` | Ramesh Kumar | Water & Plumbing Services |
| **🌐 Staff (IT)** | `staff_it` | `staff123` | Ananya Deshmukh | IT & Network Infrastructure |
| **🏢 Staff (Hostel)** | `staff_hostel` | `staff123` | Col. S. N. Murthy | Hostel Management |
| **📚 Staff (Library)** | `staff_library` | `staff123` | Meenakshi Sundaram | Central Library Facilities |
| **🎓 Student** | `student_aarav` | `student123` | Aarav Sharma | Computer Science (Student) |
| **🎓 Student** | `student_priya` | `student123` | Priya Patel | Engineering (Student) |
| **🎓 Any Student Name** | *Any Name Input* | `student123` | e.g. Rohan Sharma, Sneha Rao, etc. | Auto-Registered Student |

> [!TIP]
> **Dynamic Student Sign-In**: You can enter **ANY student name or ID** in the Student Login tab or the Instant Student Access box. New student accounts are created dynamically on the fly with automatic profile initialization and complaint tracking.


---

## 🤖 The 4 Collaborating AI Agents

1. **Detection Agent**: Understands student complaints, extracts issue intent, and identifies the problem category.
2. **Investigation Agent**: Cross-references equipment records and executes the Duplicate Detection algorithm.
3. **Priority Agent**: Assesses urgency, performs explainable priority classification (Severity, Safety, People Affected, Disruption), and routes to the appropriate department.
4. **Action Agent**: Dispatches work orders, updates SQLite database, and routes notifications to the user-editable department email.

---

## 🛠️ Tech Stack
- **Frontend / UI**: Streamlit
- **Data Analytics & Charts**: Pandas, Plotly Express
- **Database**: SQLite3 with foreign-key referential integrity
- **Security**: PBKDF2-HMAC-SHA256 password hashing & parameter-bound SQL
- **AI Engine**: Google Gemini API with fallback Campus NLP Reasoning Engine

---

## 🚀 Running the Application & Tests

### 1. Run Automated Test Suites
```powershell
# Department Staff Dashboard & Security Tests
.\venv\Scripts\python.exe tests/test_dept_dashboard.py

# Core Feature Tests (Duplicate Detection, Explainable Priority, Editable Dept Email)
.\venv\Scripts\python.exe tests/test_features.py
```

### 2. Launch Streamlit Application
```powershell
.\venv\Scripts\streamlit.exe run app.py
```
Open `http://localhost:8501` in your browser..
