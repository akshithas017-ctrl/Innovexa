import streamlit as st
import pandas as pd
import sqlite3
import os
import json
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go

# Database initialization & utilities
from database.db import get_connection, init_db
from database.seed_data import seed_sample_data
from utils.complaint_engine import (
    check_duplicate_complaint, 
    classify_priority_explainable, 
    suggest_department_and_email
)
from utils.security import (
    hash_password,
    verify_password,
    authenticate_user,
    login_or_register_student,
    change_user_password,
    log_audit_event,
    get_complaints_for_department,
    get_all_complaints_admin,
    get_complaints_for_student,
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
    get_all_departments,
    get_all_users_admin,
    get_audit_logs,
    get_complaint_by_id,
    get_related_asset
)

# ----------------- Data Access Helpers (Exported for Testing) -----------------
def fetch_complaints_df():
    """Retrieve all complaints as a pandas DataFrame."""
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT id, ticket_number, student_id, student_name, student_email, location, sub_location, 
               category, priority, priority_reason, assigned_department, assigned_department_id,
               department_email, status, rejection_reason, resolution_notes, resolution_image_path,
               image_path, is_duplicate, created_at, updated_at, resolved_at, description,
               related_equipment_id, related_equipment_name
        FROM complaints ORDER BY id DESC
    """, conn)
    conn.close()
    return df

def fetch_work_orders_df():
    """Retrieve all engineering work orders."""
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT wo.wo_number, c.ticket_number, c.location, c.sub_location,
               wo.assigned_department, c.department_email, wo.priority, c.priority_reason,
               wo.instructions, wo.status, wo.created_at
        FROM work_orders wo
        LEFT JOIN complaints c ON wo.complaint_id = c.id
        ORDER BY wo.id DESC
    """, conn)
    conn.close()
    return df

def fetch_agent_logs_df():
    """Retrieve all multi-agent execution logs."""
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT al.id, c.ticket_number, al.agent_name, al.action_summary, 
               al.structured_output, al.timestamp
        FROM agent_logs al
        LEFT JOIN complaints c ON al.complaint_id = c.id
        ORDER BY al.id DESC
    """, conn)
    conn.close()
    return df

def save_uploaded_file(uploaded_file, folder="complaints"):
    """Persist uploaded user or technician photograph to disk."""
    if uploaded_file is None:
        return None
    try:
        target_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads", folder)
        os.makedirs(target_dir, exist_ok=True)
        safe_name = f"{int(datetime.now().timestamp())}_{uploaded_file.name.replace(' ', '_')}"
        file_path = os.path.join(target_dir, safe_name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return file_path
    except Exception as e:
        st.error(f"Error saving photo: {e}")
        return None

# ----------------- Main Streamlit App -----------------
def main():
    st.set_page_config(
        page_title="CampusFix | Smart Campus Complaint Management",
        page_icon="🏫",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # Initialize DB and sample data cleanly
    init_db()
    seed_sample_data()

    # Session State Initialization
    if "user" not in st.session_state:
        st.session_state.user = None
    if "selected_complaint_id" not in st.session_state:
        st.session_state.selected_complaint_id = None
    if "reopen_target_id" not in st.session_state:
        st.session_state.reopen_target_id = None

    # Custom UI Styling
    st.markdown("""
    <style>
        .main {
            background-color: #f8fafc;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }
        .brand-title {
            font-size: 2.1rem;
            font-weight: 800;
            background: linear-gradient(120deg, #1e3a8a, #2563eb);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 2px;
            letter-spacing: -0.5px;
        }
        .brand-sub {
            font-size: 0.98rem;
            color: #64748b;
            font-weight: 500;
            margin-top: -2px;
            margin-bottom: 18px;
        }
        .metric-card {
            background: white;
            padding: 18px;
            border-radius: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.06);
            border: 1px solid #e2e8f0;
            text-align: center;
        }
        .metric-num {
            font-size: 2.1rem;
            font-weight: 700;
            color: #0f172a;
        }
        .metric-label {
            font-size: 0.85rem;
            font-weight: 600;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .badge-status-received { background-color: #e0f2fe; color: #0369a1; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.82rem; }
        .badge-status-accepted { background-color: #ede9fe; color: #6d28d9; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.82rem; }
        .badge-status-in-progress { background-color: #fef3c7; color: #b45309; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.82rem; }
        .badge-status-resolved { background-color: #dcfce7; color: #15803d; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.82rem; }
        .badge-status-closed { background-color: #f1f5f9; color: #475569; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.82rem; }
        .badge-status-reopened { background-color: #ffe4e6; color: #e11d48; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.82rem; }
        .badge-status-rejected { background-color: #fee2e2; color: #991b1b; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.82rem; }
        
        .badge-high { background-color: #fee2e2; color: #991b1b; padding: 3px 8px; border-radius: 5px; font-weight: 700; font-size: 0.8rem; }
        .badge-med { background-color: #fef3c7; color: #92400e; padding: 3px 8px; border-radius: 5px; font-weight: 700; font-size: 0.8rem; }
        .badge-low { background-color: #dbeafe; color: #1e40af; padding: 3px 8px; border-radius: 5px; font-weight: 700; font-size: 0.8rem; }
        
        .timeline-box {
            border-left: 3px solid #3b82f6;
            padding-left: 14px;
            margin-bottom: 14px;
        }
        .user-chip {
            background: #f1f5f9;
            padding: 10px 14px;
            border-radius: 10px;
            border: 1px solid #cbd5e1;
            margin-bottom: 12px;
        }
    </style>
    """, unsafe_allow_html=True)

    # =========================================================================
    # LOGIN SCREEN (When Not Authenticated)
    # =========================================================================
    if not st.session_state.user:
        st.markdown('<h1 class="brand-title">🏫 CampusFix Portal Sign-In</h1>', unsafe_allow_html=True)
        st.markdown('<p class="brand-sub">AI-Powered Smart Campus Complaint Management System with Role-Based Access Control</p>', unsafe_allow_html=True)
        
        _, center_col, _ = st.columns([1, 2.4, 1])

        with center_col:
            tab_student, tab_staff_admin = st.tabs([
                "🎓 Student Sign-In (Any Student Name)",
                "🏢 Department Staff & Admin Sign-In"
            ])

            with tab_student:
                st.markdown("##### 🎓 Student Portal Access")
                st.caption("Enter **ANY student name** or student ID below. New student profiles are initialized automatically!")
                with st.form("student_login_form"):
                    student_name_input = st.text_input(
                        "Student Full Name or Student ID *",
                        placeholder="e.g. Rohan Sharma, Sneha Rao, Aditya, Kavya, STU-1024..."
                    )
                    student_email_input = st.text_input(
                        "Campus Email (Optional)",
                        placeholder="e.g. rohan.s@campus.edu (auto-generated if empty)"
                    )
                    student_pwd_input = st.text_input(
                        "Password (Optional)",
                        type="password",
                        placeholder="Default: student123"
                    )
                    student_login_submit = st.form_submit_button("🚀 Sign In as Student", type="primary", use_container_width=True)

                    if student_login_submit:
                        if not student_name_input.strip():
                            st.error("Please enter a student name or ID.")
                        else:
                            res = login_or_register_student(
                                student_name_input, 
                                email=student_email_input, 
                                password=student_pwd_input
                            )
                            if res.get("success"):
                                st.session_state.user = res
                                st.success(f"Welcome, {res['full_name']}!")
                                st.rerun()
                            else:
                                st.error(res.get("error", "Student sign-in failed."))

            with tab_staff_admin:
                st.markdown("##### 🔐 Department Staff & Admin Credentials")
                st.caption("Enter your staff username or official email with secure password.")
                with st.form("login_form"):
                    username_input = st.text_input("Username or Campus Email", placeholder="e.g. staff_cse, staff_hvac, admin...")
                    password_input = st.text_input("Password", type="password", placeholder="••••••••")
                    login_submitted = st.form_submit_button("Sign In to Portal", type="primary", use_container_width=True)

                    if login_submitted:
                        if not username_input or not password_input:
                            st.error("Please enter both username and password.")
                        else:
                            auth_res = authenticate_user(username_input, password_input)
                            if auth_res.get("success"):
                                st.session_state.user = auth_res
                                st.success(f"Welcome back, {auth_res['full_name']}!")
                                st.rerun()
                            else:
                                st.error(auth_res.get("error", "Authentication failed."))
        return

    # =========================================================================
    # AUTHENTICATED USER SESSION & SIDEBAR
    # =========================================================================
    user = st.session_state.user
    role = user.get("role", "student")
    user_id = user.get("id")
    dept_id = user.get("department_id")
    dept_name = user.get("department_name") or "Campus Administration"

    with st.sidebar:
        st.image("https://img.icons8.com/fluency/96/school-building.png", width=56)
        st.markdown("### **CampusFix**")
        st.caption("AI-Powered Smart Campus Complaints")
        st.divider()

        # User Profile Chip
        role_badge = {
            "staff": f"🛠️ Staff ({user.get('department_code', 'DEPT')})",
            "admin": "👑 Administrator",
            "student": "🎓 Student"
        }.get(role, role.title())

        st.markdown(f"""
            <div class="user-chip">
                <div style="font-weight: 700; color: #0f172a; font-size: 0.95rem;">{user.get('full_name')}</div>
                <div style="font-size: 0.8rem; color: #2563eb; font-weight: 600;">{role_badge}</div>
                <div style="font-size: 0.75rem; color: #64748b; margin-top: 3px;">📧 {user.get('email')}</div>
            </div>
        """, unsafe_allow_html=True)

        # Unread Notifications Count
        if role == "staff" and dept_id:
            notifs = fetch_notifications_for_staff(dept_id)
        elif role == "student":
            notifs = fetch_notifications_for_student(user_id)
        else:
            notifs = []
        
        unread_count = sum(1 for n in notifs if not n.get("is_read"))
        notif_label = f"🔔 Notifications ({unread_count} new)" if unread_count > 0 else "🔔 Notifications"

        # Build Navigation Menu based on Role
        # STRICT CONSTRAINT: Campus Equipment Directory is REMOVED from navigation!
        if role == "staff":
            nav_options = [
                "🏢 Department Dashboard",
                "📋 Assigned Complaints & Actions",
                "📈 Department Analytics",
                notif_label,
                "🤖 AI Multi-Agent Pipeline",
                "👤 Staff Profile & Security"
            ]
        elif role == "student":
            nav_options = [
                "📝 Submit Complaint",
                "🔍 My Complaints & Tracking",
                notif_label,
                "🤖 AI Multi-Agent Pipeline",
                "👤 My Profile & Security"
            ]
        else: # admin
            nav_options = [
                "📊 Campus Overview",
                "📋 All Complaints & Dispatch",
                "👥 Staff Account Management",
                "🛡️ Security Audit Log",
                "🤖 AI Multi-Agent Pipeline",
                "👤 Admin Profile & Security"
            ]

        menu_choice = st.radio("Portal Navigation", nav_options, index=0)

        st.divider()
        if st.button("🚪 Sign Out", use_container_width=True):
            log_audit_event("LOGOUT", username=user.get("username"), user_id=user_id, details="User logged out")
            st.session_state.user = None
            st.session_state.selected_complaint_id = None
            st.rerun()

        st.markdown("#### **System Integrity**")
        st.success("● SQLite Isolation: Backend Enforced")
        st.success("● PBKDF2 Hashes: Active")
        st.success("● 4 AI Agents: Operational")
        st.caption("CampusFix v2.1.0 • Department Dashboard")


    # =========================================================================
    # ROLE: DEPARTMENT STAFF DASHBOARD
    # =========================================================================
    if role == "staff":

        # -------------------------------------------------------------
        # View 1: Department Dashboard Overview
        # -------------------------------------------------------------
        if menu_choice == "🏢 Department Dashboard":
            st.markdown(f'<h1 class="brand-title">{dept_name} Dashboard</h1>', unsafe_allow_html=True)
            st.markdown(f'<p class="brand-sub">Real-time complaint triage, service requests, and analytics for <b>{dept_name}</b></p>', unsafe_allow_html=True)

            analytics = fetch_department_analytics(dept_id)
            dept_complaints = get_complaints_for_department(dept_id)

            # Requirement 1: Dashboard Overview KPIs
            # Total assigned, pending, in-progress and resolved complaints
            in_prog_count = sum(1 for c in dept_complaints if c['status'] == 'In Progress')
            
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-num" style="color: #2563eb;">{analytics['total_assigned']}</div>
                        <div class="metric-label">Total Assigned</div>
                    </div>
                """, unsafe_allow_html=True)
            with c2:
                st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-num" style="color: #ea580c;">{analytics['pending_count']}</div>
                        <div class="metric-label">Pending / New</div>
                    </div>
                """, unsafe_allow_html=True)
            with c3:
                st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-num" style="color: #d97706;">{in_prog_count}</div>
                        <div class="metric-label">In Progress</div>
                    </div>
                """, unsafe_allow_html=True)
            with c4:
                st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-num" style="color: #16a34a;">{analytics['resolved_count']}</div>
                        <div class="metric-label">Resolved / Closed</div>
                    </div>
                """, unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            # High priority & Reopened alert banners
            urgent_reopened = [c for c in dept_complaints if c['status'] == 'Reopened']
            urgent_high = [c for c in dept_complaints if c['priority'] == 'High' and c['status'] not in ('Resolved', 'Closed', 'Rejected')]

            if urgent_reopened:
                st.error(f"⚠️ **Attention Required:** {len(urgent_reopened)} complaint(s) were REOPENED by students because the problem was not fixed!")
            if urgent_high:
                st.warning(f"⚡ **High Priority Alert:** {len(urgent_high)} open high-priority safety or infrastructure issue(s) assigned to your department.")

            # Quick Table Preview
            st.markdown("### 📌 Active Department Complaints")
            if dept_complaints:
                df_view = pd.DataFrame(dept_complaints)[[
                    'ticket_number', 'location', 'sub_location', 'priority', 'status', 'created_at'
                ]]
                st.dataframe(
                    df_view,
                    column_config={
                        "ticket_number": st.column_config.TextColumn("Ticket ID", width="small"),
                        "location": st.column_config.TextColumn("Building / Block"),
                        "sub_location": st.column_config.TextColumn("Area / Room"),
                        "priority": st.column_config.TextColumn("Priority"),
                        "status": st.column_config.TextColumn("Current Status"),
                        "created_at": st.column_config.DatetimeColumn("Reported Date")
                    },
                    hide_index=True,
                    use_container_width=True
                )
                st.info("💡 To manage status, inspect uploaded photos, or accept/reject complaints, go to **📋 Assigned Complaints & Actions** in the sidebar.")
            else:
                st.success("🎉 No active complaints assigned to your department at this moment.")


        # -------------------------------------------------------------
        # View 2: Assigned Complaints & Comprehensive Actions
        # -------------------------------------------------------------
        elif menu_choice == "📋 Assigned Complaints & Actions":
            st.markdown(f'<h1 class="brand-title">Manage Assigned Complaints</h1>', unsafe_allow_html=True)
            st.markdown(f'<p class="brand-sub">Department: <b>{dept_name}</b> • Backend-isolated department access</p>', unsafe_allow_html=True)

            # Fetch complaints strictly for this department
            raw_complaints = get_complaints_for_department(dept_id)

            if not raw_complaints:
                st.info("No complaints found for your department.")
            else:
                # Requirement 2: Search and Filters
                col_search, col_f_status, col_f_priority = st.columns([2, 1, 1])
                with col_search:
                    search_query = st.text_input("🔍 Search by Ticket ID, Location, or Keyword", placeholder="e.g. AC-LIB, Library, water, CFX-2026-1001...")
                with col_f_status:
                    status_filter = st.selectbox(
                        "Filter by Status",
                        ["All", "Received", "Accepted", "In Progress", "Resolved", "Closed", "Reopened", "Rejected"]
                    )
                with col_f_priority:
                    priority_filter = st.selectbox(
                        "Filter by Priority",
                        ["All", "High", "Medium", "Low"]
                    )

                # Apply Filters
                filtered = raw_complaints
                if status_filter != "All":
                    filtered = [c for c in filtered if c['status'] == status_filter]
                if priority_filter != "All":
                    filtered = [c for c in filtered if c['priority'] == priority_filter]
                if search_query:
                    q = search_query.lower()
                    filtered = [c for c in filtered if (
                        q in c['ticket_number'].lower() or
                        q in (c['location'] or '').lower() or
                        q in (c['sub_location'] or '').lower() or
                        q in (c['description'] or '').lower() or
                        q in (c['student_name'] or '').lower()
                    )]

                st.markdown(f"**Showing {len(filtered)} complaint(s)**")

                # Requirement 2: Display Table
                df_assigned = pd.DataFrame(filtered)[[
                    'id', 'ticket_number', 'description', 'location', 'sub_location', 'priority', 'status', 'created_at'
                ]]
                
                st.dataframe(
                    df_assigned,
                    column_config={
                        "id": st.column_config.NumberColumn("ID", width="small"),
                        "ticket_number": st.column_config.TextColumn("Ticket ID", width="small"),
                        "description": st.column_config.TextColumn("Description Preview", width="large"),
                        "location": st.column_config.TextColumn("Location"),
                        "sub_location": st.column_config.TextColumn("Area"),
                        "priority": st.column_config.TextColumn("Priority"),
                        "status": st.column_config.TextColumn("Status"),
                        "created_at": st.column_config.DatetimeColumn("Submitted Date")
                    },
                    hide_index=True,
                    use_container_width=True
                )

                st.divider()

                # Selector for Complaint Details & Actions
                ticket_options = {c['id']: f"{c['ticket_number']} — {c['location']} ({c['sub_location']}) [{c['status']}]" for c in filtered}
                if not ticket_options:
                    st.info("No complaints match the filter criteria.")
                else:
                    selected_cid = st.selectbox(
                        "🎯 Select a Complaint to View Details, Timeline, & Perform Actions:",
                        options=list(ticket_options.keys()),
                        format_func=lambda x: ticket_options[x]
                    )

                    complaint = get_complaint_by_id(selected_cid)

                    if complaint:
                        st.markdown("<br>", unsafe_allow_html=True)
                        
                        # Requirement 3: Complaint Details View
                        st.markdown(f"### 📋 Complaint Details: `{complaint['ticket_number']}`")
                        
                        det_col1, det_col2 = st.columns([1.5, 1])
                        
                        with det_col1:
                            # Status & Priority Badges
                            status_cls = f"badge-status-{complaint['status'].lower().replace(' ', '-')}"
                            prio_cls = f"badge-{complaint['priority'].lower()[:3]}"
                            
                            st.markdown(f"""
                                <div style="display: flex; gap: 10px; align-items: center; margin-bottom: 12px;">
                                    <span class="{status_cls}">{complaint['status']}</span>
                                    <span class="{prio_cls}">{complaint['priority']} Priority</span>
                                    <span style="color: #64748b; font-size: 0.85rem;">Reported: {complaint['created_at']}</span>
                                </div>
                            """, unsafe_allow_html=True)

                            st.markdown(f"**📍 Location:** {complaint['location']} • `{complaint['sub_location']}`")
                            st.markdown(f"**📝 Description:**")
                            st.info(complaint['description'])

                            # Student Details (Authorized Info Only: Name & Email)
                            st.markdown(f"""
                                <div style="background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px; margin-bottom: 12px;">
                                    <b>👤 Reported By (Authorized Student Details):</b><br>
                                    • Name: <b>{complaint['student_name']}</b><br>
                                    • Campus Email: <code>{complaint['student_email']}</code>
                                </div>
                            """, unsafe_allow_html=True)

                            # AI Category & Explainable Priority Reason
                            st.markdown(f"**🤖 AI Category:** `{complaint['category']}`")
                            st.markdown(f"**⚡ Explainable Priority Reason:**")
                            st.caption(complaint['priority_reason'] or "Assessed via multi-agent safety and campus impact scoring.")

                            # Duplicate Detection Result
                            if complaint['is_duplicate']:
                                st.warning(f"⚠️ Flagged as duplicate of Ticket #{complaint['duplicate_of_id']}")
                            else:
                                st.success("✅ **Investigation Agent Result:** Unique issue. No prior duplicate active within 24h.")

                            # Reopen reason or rejection reason if applicable
                            if complaint['status'] == 'Reopened' and complaint['reopen_reason']:
                                st.error(f"🔄 **Student Reopen Feedback:** {complaint['reopen_reason']}")
                            if complaint['status'] == 'Rejected' and complaint['rejection_reason']:
                                st.error(f"❌ **Rejection Reason:** {complaint['rejection_reason']}")

                        with det_col2:
                            # Related Asset Details (from SQLite equipment_records)
                            asset = get_related_asset(
                                complaint['related_equipment_id'],
                                complaint['location'],
                                complaint['sub_location']
                            )
                            st.markdown("#### ⚙️ Related Equipment Asset")
                            if asset:
                                st.markdown(f"""
                                    <div style="background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 8px; padding: 12px; font-size: 0.88rem;">
                                        <b>Asset ID:</b> <code>{asset['equipment_id']}</code><br>
                                        <b>Name:</b> {asset['name']}<br>
                                        <b>Category:</b> {asset['category']}<br>
                                        <b>Last Serviced:</b> {asset['last_serviced']}<br>
                                        <b>Operational Status:</b> <span style="font-weight: bold; color: {'green' if asset['status']=='Operational' else 'red'};">{asset['status']}</span>
                                    </div>
                                """, unsafe_allow_html=True)
                            else:
                                st.caption("No specific tagged asset record mapped to this physical location.")

                            # Uploaded Problem Image (if student attached one)
                            st.markdown("#### 📷 Student Uploaded Photograph")
                            if complaint['image_path']:
                                try:
                                    st.image(complaint['image_path'], caption=f"Issue Photo: {complaint['ticket_number']}", use_container_width=True)
                                except Exception:
                                    st.caption(f"Photo path: {complaint['image_path']}")
                            else:
                                st.caption("No initial photo uploaded by student.")

                            # Uploaded Resolution Image (if resolved)
                            if complaint['resolution_image_path']:
                                st.markdown("#### ✅ Resolution Proof Photograph")
                                try:
                                    st.image(complaint['resolution_image_path'], caption="Resolution Photograph Uploaded by Staff", use_container_width=True)
                                except Exception:
                                    st.caption(f"Resolution Photo: {complaint['resolution_image_path']}")


                        # -------------------------------------------------------------
                        # Requirement 4: Complaint Actions (Accept, Reject, Status Update, Remarks, Resolution Photo)
                        # -------------------------------------------------------------
                        st.markdown("<hr style='margin: 20px 0;'>", unsafe_allow_html=True)
                        st.markdown("### 🛠️ Department Staff Actions")

                        action_col1, action_col2 = st.columns(2)

                        with action_col1:
                            st.markdown("##### ⚡ Quick Status Update")
                            
                            valid_next_statuses = ["Received", "Accepted", "In Progress", "Resolved"]
                            curr_status = complaint['status']
                            
                            new_status = st.selectbox(
                                "Advance Status (Requirement 5: Tracking)",
                                options=valid_next_statuses,
                                index=valid_next_statuses.index(curr_status) if curr_status in valid_next_statuses else 0
                            )

                            staff_remarks = st.text_input(
                                "Staff Remarks / Technician Activity Notes",
                                placeholder="e.g. Cleared condensate line, replaced faulty capacitor..."
                            )

                            resolution_notes = ""
                            resolution_photo = None
                            if new_status == "Resolved":
                                resolution_notes = st.text_area(
                                    "Resolution Summary (Required for closure)",
                                    placeholder="Describe specific fix applied, parts replaced, and verification test..."
                                )
                                resolution_photo = st.file_uploader(
                                    "📸 Upload Resolution Proof Photograph (Optional)",
                                    type=["jpg", "jpeg", "png"]
                                )

                            if st.button("💾 Apply Status & Update Complaint", type="primary", use_container_width=True):
                                res_img_path = None
                                if resolution_photo:
                                    res_img_path = save_uploaded_file(resolution_photo, folder="resolutions")

                                log_status_transition(
                                    complaint_id=complaint['id'],
                                    old_status=curr_status,
                                    new_status=new_status,
                                    user_id=user['id'],
                                    user_name=user['full_name'],
                                    remarks=staff_remarks,
                                    resolution_notes=resolution_notes,
                                    resolution_image_path=res_img_path
                                )
                                st.success(f"Status successfully updated to '{new_status}'!")
                                st.rerun()

                        with action_col2:
                            st.markdown("##### ❌ Reject Complaint (With Mandatory Reason)")
                            with st.expander("Click to Reject Complaint", expanded=False):
                                rejection_reason = st.text_area(
                                    "Reason for Rejection * (Mandatory)",
                                    placeholder="Explain clearly why this complaint cannot be handled by the department (e.g. Outside campus maintenance boundary, duplicate physical request, invalid location)..."
                                )
                                if st.button("Confirm Rejection", type="secondary", use_container_width=True):
                                    if not rejection_reason.strip():
                                        st.error("A detailed rejection reason is required.")
                                    else:
                                        log_status_transition(
                                            complaint_id=complaint['id'],
                                            old_status=complaint['status'],
                                            new_status="Rejected",
                                            user_id=user['id'],
                                            user_name=user['full_name'],
                                            remarks=f"Rejected: {rejection_reason}",
                                            rejection_reason=rejection_reason
                                        )
                                        st.warning("Complaint marked as Rejected.")
                                        st.rerun()


                        # -------------------------------------------------------------
                        # Requirement 7: Complaint History Activity Timeline
                        # -------------------------------------------------------------
                        st.markdown("<hr style='margin: 20px 0;'>", unsafe_allow_html=True)
                        st.markdown("### ⏱️ Complaint History & Audit Timeline")
                        
                        history = fetch_status_history_for_complaint(complaint['id'])
                        if history:
                            for h in history:
                                st.markdown(f"""
                                    <div class="timeline-box">
                                        <div style="font-size: 0.82rem; color: #64748b;">📅 {h['timestamp']}</div>
                                        <div style="font-weight: 700; color: #1e293b; font-size: 0.95rem;">
                                            {h['old_status'] or 'Submitted'} ➔ <span style="color: #2563eb;">{h['new_status']}</span>
                                        </div>
                                        <div style="font-size: 0.88rem; color: #334155;">
                                            <b>Action By:</b> {h['changed_by_name']}<br>
                                            <b>Remarks:</b> {h['remarks'] or 'No additional notes'}
                                        </div>
                                    </div>
                                """, unsafe_allow_html=True)
                        else:
                            st.caption("No transitions recorded yet.")


        # -------------------------------------------------------------
        # View 3: Department Analytics (Requirement 8)
        # -------------------------------------------------------------
        elif menu_choice == "📈 Department Analytics":
            st.markdown(f'<h1 class="brand-title">{dept_name} Analytics</h1>', unsafe_allow_html=True)
            st.markdown(f'<p class="brand-sub">Performance metrics, resolution velocity, and priority breakdowns</p>', unsafe_allow_html=True)

            analytics = fetch_department_analytics(dept_id)
            dept_complaints = get_complaints_for_department(dept_id)

            # Analytics Metric Cards (Resolved, pending, high-priority, avg resolution time)
            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-num" style="color: #16a34a;">{analytics['resolved_count']}</div>
                        <div class="metric-label">Resolved Issues</div>
                    </div>
                """, unsafe_allow_html=True)
            with m2:
                st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-num" style="color: #ea580c;">{analytics['pending_count']}</div>
                        <div class="metric-label">Pending Issues</div>
                    </div>
                """, unsafe_allow_html=True)
            with m3:
                st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-num" style="color: #dc2626;">{analytics['high_priority_count']}</div>
                        <div class="metric-label">High Priority</div>
                    </div>
                """, unsafe_allow_html=True)
            with m4:
                st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-num" style="color: #7c3aed;">{analytics['avg_resolution_hours']} hrs</div>
                        <div class="metric-label">Avg Resolution Time</div>
                    </div>
                """, unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            if dept_complaints:
                df_dept = pd.DataFrame(dept_complaints)
                c_ch1, c_ch2 = st.columns(2)
                
                with c_ch1:
                    st.markdown("##### ⚡ Priority Distribution")
                    prio_counts = df_dept['priority'].value_counts().reset_index()
                    prio_counts.columns = ['Priority', 'Count']
                    color_map = {'High': '#ef4444', 'Medium': '#f59e0b', 'Low': '#3b82f6'}
                    fig_prio = px.pie(
                        prio_counts,
                        names='Priority',
                        values='Count',
                        color='Priority',
                        color_discrete_map=color_map,
                        hole=0.4
                    )
                    fig_prio.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=10))
                    st.plotly_chart(fig_prio, use_container_width=True)

                with c_ch2:
                    st.markdown("##### 📌 Lifecycle Status Breakdown")
                    stat_counts = df_dept['status'].value_counts().reset_index()
                    stat_counts.columns = ['Status', 'Count']
                    fig_stat = px.bar(
                        stat_counts,
                        x='Status',
                        y='Count',
                        color='Status',
                        text='Count',
                        color_discrete_sequence=px.colors.qualitative.Safe
                    )
                    fig_stat.update_layout(showlegend=False, height=280, margin=dict(l=10, r=10, t=10, b=10))
                    st.plotly_chart(fig_stat, use_container_width=True)
            else:
                st.info("No complaint data to plot for this department.")


        # -------------------------------------------------------------
        # View 4: Notifications (Requirement 6)
        # -------------------------------------------------------------
        elif "Notifications" in menu_choice:
            st.markdown(f'<h1 class="brand-title">{dept_name} Notifications</h1>', unsafe_allow_html=True)
            st.markdown('<p class="brand-sub">Alerts for new assignments, high-priority issues, and student-reopened complaints</p>', unsafe_allow_html=True)

            notifs = fetch_notifications_for_staff(dept_id)
            if not notifs:
                st.info("No new notifications for your department.")
            else:
                for n in notifs:
                    box_color = "#fef2f2" if n['notification_type'] == 'HIGH_PRIORITY' else "#fffbeb" if n['notification_type'] == 'REOPENED' else "#f0fdf4"
                    border_color = "#f87171" if n['notification_type'] == 'HIGH_PRIORITY' else "#f59e0b" if n['notification_type'] == 'REOPENED' else "#86efac"
                    read_badge = "✅ Read" if n['is_read'] else "🆕 Unread"

                    st.markdown(f"""
                        <div style="background: {box_color}; border: 1.5px solid {border_color}; border-radius: 8px; padding: 14px; margin-bottom: 10px;">
                            <div style="display: flex; justify-content: space-between; font-weight: 700; font-size: 0.95rem; color: #1e293b;">
                                <span>{n['title']}</span>
                                <span style="font-size: 0.8rem; color: #64748b;">{read_badge} • {n['created_at']}</span>
                            </div>
                            <div style="font-size: 0.9rem; color: #334155; margin-top: 4px;">{n['message']}</div>
                        </div>
                    """, unsafe_allow_html=True)

                    if not n['is_read']:
                        if st.button("Mark as Read", key=f"read_notif_{n['id']}"):
                            mark_notification_read(n['id'])
                            st.rerun()


        # -------------------------------------------------------------
        # View 5: Multi-Agent Pipeline
        # -------------------------------------------------------------
        elif menu_choice == "🤖 AI Multi-Agent Pipeline":
            render_agent_pipeline_view()


        # -------------------------------------------------------------
        # View 6: Staff Profile & Security (Requirement 9)
        # -------------------------------------------------------------
        elif menu_choice == "👤 Staff Profile & Security":
            st.markdown('<h1 class="brand-title">Staff Profile & Account Security</h1>', unsafe_allow_html=True)
            st.markdown('<p class="brand-sub">View credentials, access permissions, and update password</p>', unsafe_allow_html=True)

            p_col1, p_col2 = st.columns(2)
            with p_col1:
                st.markdown("### 👤 Staff Credentials")
                st.markdown(f"""
                    <div style="background: white; border: 1px solid #cbd5e1; border-radius: 10px; padding: 18px; font-size: 0.92rem; line-height: 1.8;">
                        <b>Full Name:</b> {user.get('full_name')}<br>
                        <b>Staff Username:</b> <code>{user.get('username')}</code><br>
                        <b>Campus Email:</b> <code>{user.get('email')}</code><br>
                        <b>Assigned Department:</b> {dept_name} (Code: <code>{user.get('department_code')}</code>)<br>
                        <b>Official Dept Email:</b> <code>{user.get('department_email')}</code><br>
                        <b>Contact Phone:</b> {user.get('phone') or 'Not specified'}<br>
                        <b>Role Level:</b> <code>DEPARTMENT_STAFF</code> (Backend Isolated)
                    </div>
                """, unsafe_allow_html=True)

            with p_col2:
                st.markdown("### 🔑 Change Password")
                with st.form("staff_pwd_form"):
                    old_pwd = st.text_input("Current Password", type="password")
                    new_pwd = st.text_input("New Password (min 6 characters)", type="password")
                    confirm_pwd = st.text_input("Confirm New Password", type="password")
                    update_pwd_btn = st.form_submit_button("Update Password", type="primary", use_container_width=True)

                    if update_pwd_btn:
                        if new_pwd != confirm_pwd:
                            st.error("New passwords do not match.")
                        else:
                            success, msg = change_user_password(user['id'], old_pwd, new_pwd)
                            if success:
                                st.success(msg)
                            else:
                                st.error(msg)


    # =========================================================================
    # ROLE: STUDENT WORKFLOW
    # =========================================================================
    elif role == "student":

        # -------------------------------------------------------------
        # View 1: Submit Complaint (with Image, Duplicate Detection, Priority)
        # -------------------------------------------------------------
        if menu_choice == "📝 Submit Complaint":
            st.markdown('<h1 class="brand-title">Submit a Campus Complaint</h1>', unsafe_allow_html=True)
            st.markdown('<p class="brand-sub">Report facility, equipment or infrastructure issues. Our multi-agent system screens duplicates and routes to the receiving department.</p>', unsafe_allow_html=True)

            c_n, c_e = st.columns(2)
            with c_n:
                student_name = st.text_input("Student Name *", value=user.get('full_name', 'Student'))
            with c_e:
                student_email = st.text_input("Campus Email *", value=user.get('email', 'student@campus.edu'))

            c_l, c_s = st.columns(2)
            with c_l:
                location = st.selectbox(
                    "Primary Location *",
                    [
                        "Central Library",
                        "Computer Science Block",
                        "Engineering Academic Block",
                        "Science & Research Wing",
                        "Management Block",
                        "Main Auditorium",
                        "Boys Hostel Block B",
                        "Girls Hostel Block A",
                        "Student Cafeteria",
                        "Sports Complex & Gymnasium",
                        "Utility Substation"
                    ]
                )
            with c_s:
                sub_location = st.text_input("Specific Room / Area *", placeholder="e.g. 2nd Floor Reading Hall, Lab 4, Room 201...")

            description = st.text_area(
                "Problem Description *",
                placeholder="Describe the problem clearly (e.g. AC unit is leaking water onto study desks, or projector not working, or exposed electrical wires)...",
                height=110
            )

            # Upload Image (Requirement 3: Uploaded image)
            uploaded_image = st.file_uploader(
                "📷 Upload Photograph of Problem (Optional)",
                type=["png", "jpg", "jpeg"]
            )

            # Suggest receiving department and email
            suggested_dept, suggested_email = suggest_department_and_email(location, description or "")

            st.markdown("#### 🏢 Receiving Department & Notification Routing")
            st.caption("The suggested department and email address below are **fully editable** by the student before submission.")

            d_c, e_c = st.columns(2)
            with d_c:
                assigned_dept = st.text_input("Receiving Department (Editable) *", value=suggested_dept)
            with e_c:
                dept_email = st.text_input("Department Email Address (Editable) *", value=suggested_email)

            st.markdown(f"""
                <div style="background: #f1f5f9; border: 1px solid #cbd5e1; padding: 6px 12px; border-radius: 8px; font-size: 0.88rem; color: #334155; margin-bottom: 12px;">
                    📧 <b>Target Recipient:</b> <code>{dept_email}</code> | <b>Department:</b> <code>{assigned_dept}</code>
                </div>
            """, unsafe_allow_html=True)

            if st.button("🚀 Submit Complaint to Maintenance", type="primary", use_container_width=True):
                if not student_name or not student_email or not description or not sub_location:
                    st.error("Please fill in all required fields (Name, Email, Location, Area, and Description).")
                elif not dept_email or "@" not in dept_email:
                    st.error("Please provide a valid receiving department email address.")
                else:
                    # Feature 1: Duplicate Complaint Detection
                    with st.spinner("🔍 Investigation Agent checking for duplicate complaints..."):
                        dup_check = check_duplicate_complaint(location, sub_location, description)

                    if dup_check["is_duplicate"]:
                        # BLOCK SUBMISSION
                        st.error("🚫 **Submission Blocked: A Similar Active Complaint Already Exists!**")
                        st.markdown(f"""
                            <div style="background: #fffbeb; border: 1.5px solid #f59e0b; border-radius: 10px; padding: 16px; margin: 12px 0;">
                                <h4 style="color: #92400e; margin-top: 0px;">⚠️ Existing Active Ticket: {dup_check['existing_ticket']}</h4>
                                <p style="color: #78350f; font-size: 0.95rem;">
                                    A similar issue has already been reported for <b>{dup_check['location']} ({dup_check['sub_location']})</b> and is currently: <b>{dup_check['status']}</b>.
                                </p>
                                <p style="font-size: 0.88rem; color: #1e293b;">
                                    <b>Assigned Department:</b> {dup_check['assigned_department']}<br>
                                    <b>Original Description:</b> <i>"{dup_check['original_description']}"</i>
                                </p>
                                <div style="font-size: 0.85rem; color: #92400e; margin-top: 6px;">
                                    ℹ️ <i>To prevent technician duplicate efforts, your report was linked to this existing ticket. You can track progress in 'My Complaints'.</i>
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                    else:
                        # Feature 3: Explainable Priority Classification
                        with st.spinner("⚡ Priority Agent analyzing severity, safety risks, and impact..."):
                            prio_res = classify_priority_explainable(description, location, sub_location)

                        assigned_priority = prio_res.get("priority", "Medium")
                        prio_reason = prio_res.get("reason", "Standard campus maintenance issue.")
                        urgency_score = prio_res.get("urgency_score", 5)

                        # Determine Category & Equipment Match
                        cat_detect = "General Maintenance"
                        text_l = (description + " " + location).lower()
                        if any(k in text_l for k in ["ac", "cooling", "chiller"]): cat_detect = "HVAC"
                        elif any(k in text_l for k in ["wire", "spark", "electric", "switch"]): cat_detect = "Electrical"
                        elif any(k in text_l for k in ["water", "leak", "tap", "pipe"]): cat_detect = "Plumbing"
                        elif any(k in text_l for k in ["projector", "mic", "wifi", "network"]): cat_detect = "IT & AV"
                        elif any(k in text_l for k in ["chair", "desk", "table"]): cat_detect = "Furniture"

                        # Save uploaded image if provided
                        saved_img_path = save_uploaded_file(uploaded_image, folder="complaints")

                        # Map department name to ID
                        conn = get_connection()
                        cur = conn.cursor()
                        cur.execute("SELECT id FROM departments WHERE name = ? OR code = ?", (assigned_dept, assigned_dept))
                        row_d = cur.fetchone()
                        dept_fk_id = row_d[0] if row_d else 1

                        cur.execute("SELECT COUNT(*) FROM complaints")
                        ticket_num = f"CFX-2026-{1001 + cur.fetchone()[0]}"

                        # Insert into complaints
                        cur.execute("""
                            INSERT INTO complaints (
                                ticket_number, student_id, student_name, student_email, location, sub_location,
                                description, image_path, category, priority, priority_reason,
                                assigned_department, assigned_department_id, department_email, status, is_duplicate
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Received', 0)
                        """, (
                            ticket_num, user['id'], student_name, student_email, location, sub_location,
                            description, saved_img_path, cat_detect, assigned_priority, prio_reason,
                            assigned_dept, dept_fk_id, dept_email
                        ))
                        cid = cur.lastrowid

                        # Log in status history
                        cur.execute("""
                            INSERT INTO status_history (complaint_id, old_status, new_status, changed_by_user_id, changed_by_name, remarks)
                            VALUES (?, NULL, 'Received', ?, ?, 'Initial complaint submitted by student')
                        """, (cid, user['id'], student_name))

                        # Notify Department Staff (Requirement 6)
                        cur.execute("""
                            INSERT INTO notifications (recipient_role, recipient_department_id, complaint_id, title, message, notification_type)
                            VALUES ('staff', ?, ?, ?, ?, ?)
                        """, (
                            dept_fk_id,
                            cid,
                            f"📌 New Assignment: {ticket_num}",
                            f"New {assigned_priority}-priority issue at {location} ({sub_location}): {description[:80]}...",
                            "HIGH_PRIORITY" if assigned_priority == "High" else "NEW_ASSIGNMENT"
                        ))

                        # Generate Work Order
                        cur.execute("SELECT COUNT(*) FROM work_orders")
                        wo_num = f"WO-2026-{cur.fetchone()[0] + 1:03d}"
                        cur.execute("""
                            INSERT INTO work_orders (wo_number, complaint_id, assigned_department, priority, instructions, status)
                            VALUES (?, ?, ?, ?, ?, 'Pending')
                        """, (wo_num, cid, assigned_dept, assigned_priority, f"Assigned to {assigned_dept} ({dept_email}): {description}"))

                        # Agent Activity Logs
                        cur.execute("""
                            INSERT INTO agent_logs (complaint_id, agent_name, action_summary, structured_output)
                            VALUES (?, 'Detection Agent', ?, ?)
                        """, (cid, f"Identified category {cat_detect} and problem scope.", json.dumps({"category": cat_detect})))

                        cur.execute("""
                            INSERT INTO agent_logs (complaint_id, agent_name, action_summary, structured_output)
                            VALUES (?, 'Priority Agent', ?, ?)
                        """, (cid, f"Assigned {assigned_priority} Priority: {prio_reason}", json.dumps({"priority": assigned_priority, "score": urgency_score, "reason": prio_reason})))

                        cur.execute("""
                            INSERT INTO agent_logs (complaint_id, agent_name, action_summary, structured_output)
                            VALUES (?, 'Action Agent', ?, ?)
                        """, (cid, f"Dispatched Work Order {wo_num} to {assigned_dept}.", json.dumps({"work_order": wo_num, "email": dept_email})))

                        conn.commit()
                        conn.close()

                        log_audit_event("COMPLAINT_SUBMITTED", username=user.get('username'), user_id=user['id'], resource_id=ticket_num)

                        st.success(f"✅ Complaint successfully submitted! Your Ticket ID is **{ticket_num}**.")
                        st.info("You can track this complaint under 'My Complaints & Tracking'.")


        # -------------------------------------------------------------
        # View 2: My Complaints & Tracking (Requirement 5: Reopen & Confirm)
        # -------------------------------------------------------------
        elif menu_choice == "🔍 My Complaints & Tracking":
            st.markdown('<h1 class="brand-title">My Registered Complaints</h1>', unsafe_allow_html=True)
            st.markdown('<p class="brand-sub">Live tracking of your service requests, status timeline, and issue confirmation</p>', unsafe_allow_html=True)

            my_complaints = get_complaints_for_student(user['id'], user.get('full_name'), user.get('email'))
            if not my_complaints:
                st.info("You haven't submitted any complaints yet.")
            else:
                for comp in my_complaints:
                    with st.expander(f"📌 Ticket {comp['ticket_number']} — {comp['location']} ({comp['sub_location']}) [{comp['status']}]", expanded=(comp['status'] == 'Resolved')):
                        s_col1, s_col2 = st.columns([1.5, 1])
                        
                        with s_col1:
                            st.markdown(f"**Current Status:** `{comp['status']}`")
                            st.markdown(f"**Assigned Department:** {comp['assigned_department']}")
                            st.markdown(f"**Priority:** `{comp['priority']}` — {comp['priority_reason']}")
                            st.markdown(f"**Description:**")
                            st.info(comp['description'])

                            if comp['status'] == 'Rejected':
                                st.error(f"❌ **Rejection Reason:** {comp['rejection_reason']}")

                            if comp['status'] == 'Resolved':
                                st.success("✅ **Department Marked Resolved:** " + (comp['resolution_notes'] or "Work completed."))

                                # Requirement 5: Student Confirm Fixed or Reopen
                                st.markdown("#### ❓ Is the problem fixed?")
                                rc1, rc2 = st.columns(2)
                                with rc1:
                                    if st.button("✅ Yes, Confirm Fixed", key=f"fix_{comp['id']}", type="primary"):
                                        student_confirm_fixed(comp['id'], user['id'], user['full_name'])
                                        st.success("Ticket closed. Thank you for confirming!")
                                        st.rerun()
                                with rc2:
                                    if st.button("🔄 No, Issue Not Fixed (Reopen)", key=f"reopen_btn_{comp['id']}"):
                                        st.session_state.reopen_target_id = comp['id']

                                # If student clicked reopen, show reason box
                                if st.session_state.reopen_target_id == comp['id']:
                                    reopen_text = st.text_area(
                                        "Please explain what issue still persists:",
                                        key=f"reopen_reason_{comp['id']}"
                                    )
                                    if st.button("Submit Reopen Request", key=f"submit_reopen_{comp['id']}"):
                                        if not reopen_text.strip():
                                            st.error("Please enter a brief explanation.")
                                        else:
                                            student_reopen_complaint(comp['id'], user['id'], user['full_name'], reopen_text)
                                            st.session_state.reopen_target_id = None
                                            st.warning("Complaint reopened and department staff notified!")
                                            st.rerun()

                        with s_col2:
                            if comp['image_path']:
                                try:
                                    st.image(comp['image_path'], caption="Your Uploaded Photo", use_container_width=True)
                                except Exception:
                                    pass
                            if comp['resolution_image_path']:
                                try:
                                    st.image(comp['resolution_image_path'], caption="Resolution Photograph", use_container_width=True)
                                except Exception:
                                    pass

                        # Status Activity Timeline
                        st.markdown("##### ⏱️ Status Timeline")
                        hist = fetch_status_history_for_complaint(comp['id'])
                        if hist:
                            for h in hist:
                                st.markdown(f"""
                                    <div class="timeline-box">
                                        <div style="font-size: 0.8rem; color: #64748b;">{h['timestamp']}</div>
                                        <div style="font-weight: 700; color: #1e293b;">{h['old_status'] or 'Submitted'} ➔ <span style="color: #2563eb;">{h['new_status']}</span></div>
                                        <div style="font-size: 0.85rem; color: #475569;">By {h['changed_by_name']}: {h['remarks']}</div>
                                    </div>
                                """, unsafe_allow_html=True)


        # -------------------------------------------------------------
        # View 3: Student Notifications (Requirement 6)
        # -------------------------------------------------------------
        elif "Notifications" in menu_choice:
            st.markdown('<h1 class="brand-title">My Notifications</h1>', unsafe_allow_html=True)
            st.markdown('<p class="brand-sub">Real-time status updates and communications regarding your tickets</p>', unsafe_allow_html=True)

            notifs = fetch_notifications_for_student(user['id'])
            if not notifs:
                st.info("No notifications at this time.")
            else:
                for n in notifs:
                    st.markdown(f"""
                        <div style="background: white; border: 1px solid #cbd5e1; border-radius: 8px; padding: 14px; margin-bottom: 8px;">
                            <div style="display: flex; justify-content: space-between; font-weight: 700;">
                                <span>{n['title']}</span>
                                <span style="font-size: 0.8rem; color: #64748b;">{n['created_at']}</span>
                            </div>
                            <p style="font-size: 0.9rem; color: #334155; margin: 4px 0 0 0;">{n['message']}</p>
                        </div>
                    """, unsafe_allow_html=True)
                    if not n['is_read']:
                        if st.button("Mark as Read", key=f"s_notif_{n['id']}"):
                            mark_notification_read(n['id'])
                            st.rerun()


        # -------------------------------------------------------------
        # View 4: Multi-Agent Pipeline
        # -------------------------------------------------------------
        elif menu_choice == "🤖 AI Multi-Agent Pipeline":
            render_agent_pipeline_view()


        # -------------------------------------------------------------
        # View 5: Student Profile & Password
        # -------------------------------------------------------------
        elif "Profile" in menu_choice:
            st.markdown('<h1 class="brand-title">Student Profile & Security</h1>', unsafe_allow_html=True)
            sp1, sp2 = st.columns(2)
            with sp1:
                st.markdown(f"""
                    <div style="background: white; border: 1px solid #cbd5e1; border-radius: 10px; padding: 18px; font-size: 0.92rem; line-height: 1.8;">
                        <b>Full Name:</b> {user.get('full_name')}<br>
                        <b>Student ID / Username:</b> <code>{user.get('username')}</code><br>
                        <b>Campus Email:</b> <code>{user.get('email')}</code><br>
                        <b>Phone:</b> {user.get('phone') or 'Not specified'}<br>
                        <b>Role:</b> <code>STUDENT</code>
                    </div>
                """, unsafe_allow_html=True)
            with sp2:
                st.markdown("### 🔑 Change Password")
                with st.form("stud_pwd_form"):
                    old_p = st.text_input("Current Password", type="password")
                    new_p = st.text_input("New Password", type="password")
                    c_p = st.text_input("Confirm New Password", type="password")
                    if st.form_submit_button("Update Password", type="primary", use_container_width=True):
                        if new_p != c_p:
                            st.error("Passwords do not match.")
                        else:
                            ok, msg = change_user_password(user['id'], old_p, new_p)
                            if ok: st.success(msg)
                            else: st.error(msg)


    # =========================================================================
    # ROLE: ADMINISTRATOR WORKFLOW
    # =========================================================================
    else: # admin

        # -------------------------------------------------------------
        # View 1: Campus-Wide Overview
        # -------------------------------------------------------------
        if menu_choice == "📊 Campus Overview":
            st.markdown('<h1 class="brand-title">CampusFix Executive Center</h1>', unsafe_allow_html=True)
            st.markdown('<p class="brand-sub">Campus-wide overview of all complaint streams, departmental response rates, and dispatches</p>', unsafe_allow_html=True)

            all_complaints = get_all_complaints_admin()
            df_comp = pd.DataFrame(all_complaints) if all_complaints else pd.DataFrame()

            total_c = len(df_comp)
            resolved_c = sum(1 for c in all_complaints if c['status'] in ('Resolved', 'Closed'))
            pending_c = sum(1 for c in all_complaints if c['status'] in ('Received', 'Accepted', 'In Progress', 'Reopened'))
            high_prio_c = sum(1 for c in all_complaints if c['priority'] == 'High')

            k1, k2, k3, k4 = st.columns(4)
            with k1:
                st.markdown(f"""<div class="metric-card"><div class="metric-num" style="color: #2563eb;">{total_c}</div><div class="metric-label">Campus Complaints</div></div>""", unsafe_allow_html=True)
            with k2:
                st.markdown(f"""<div class="metric-card"><div class="metric-num" style="color: #ea580c;">{pending_c}</div><div class="metric-label">Pending Triage</div></div>""", unsafe_allow_html=True)
            with k3:
                st.markdown(f"""<div class="metric-card"><div class="metric-num" style="color: #16a34a;">{resolved_c}</div><div class="metric-label">Resolved Issues</div></div>""", unsafe_allow_html=True)
            with k4:
                st.markdown(f"""<div class="metric-card"><div class="metric-num" style="color: #dc2626;">{high_prio_c}</div><div class="metric-label">High Priority</div></div>""", unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            if not df_comp.empty:
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("##### 🏢 Complaints by Assigned Department")
                    dept_counts = df_comp['assigned_department'].value_counts().reset_index()
                    dept_counts.columns = ['Department', 'Count']
                    fig_dept = px.bar(dept_counts, x='Department', y='Count', color='Department', text='Count')
                    fig_dept.update_layout(showlegend=False, height=280, margin=dict(l=10, r=10, t=10, b=10))
                    st.plotly_chart(fig_dept, use_container_width=True)

                with c2:
                    st.markdown("##### ⚡ Priority Distribution (Explainable AI)")
                    prio_counts = df_comp['priority'].value_counts().reset_index()
                    prio_counts.columns = ['Priority', 'Count']
                    fig_prio = px.pie(prio_counts, names='Priority', values='Count', color='Priority',
                                      color_discrete_map={'High': '#ef4444', 'Medium': '#f59e0b', 'Low': '#3b82f6'}, hole=0.4)
                    fig_prio.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=10))
                    st.plotly_chart(fig_prio, use_container_width=True)


        # -------------------------------------------------------------
        # View 2: All Complaints Across All Departments
        # -------------------------------------------------------------
        elif menu_choice == "📋 All Complaints & Dispatch":
            st.markdown('<h1 class="brand-title">All Campus Complaints & Dispatch</h1>', unsafe_allow_html=True)
            st.markdown('<p class="brand-sub">Comprehensive overview of tickets across all academic blocks and facilities</p>', unsafe_allow_html=True)

            df_all = fetch_complaints_df()
            if not df_all.empty:
                st.dataframe(
                    df_all[[
                        'ticket_number', 'student_name', 'location', 'sub_location', 'category',
                        'priority', 'priority_reason', 'assigned_department', 'department_email', 'status', 'created_at'
                    ]],
                    column_config={
                        "ticket_number": st.column_config.TextColumn("Ticket ID", width="small"),
                        "student_name": st.column_config.TextColumn("Reported By"),
                        "location": st.column_config.TextColumn("Location"),
                        "sub_location": st.column_config.TextColumn("Room / Area"),
                        "category": st.column_config.TextColumn("Category"),
                        "priority": st.column_config.TextColumn("Priority"),
                        "priority_reason": st.column_config.TextColumn("Explainable Reason", width="large"),
                        "assigned_department": st.column_config.TextColumn("Assigned Department"),
                        "department_email": st.column_config.TextColumn("Dept Email"),
                        "status": st.column_config.TextColumn("Status"),
                        "created_at": st.column_config.DatetimeColumn("Reported At")
                    },
                    hide_index=True,
                    use_container_width=True
                )
            else:
                st.info("No complaints found.")


        # -------------------------------------------------------------
        # View 3: Staff Account Management (Admin Only)
        # -------------------------------------------------------------
        elif menu_choice == "👥 Staff Account Management":
            st.markdown('<h1 class="brand-title">Department Staff Account Management</h1>', unsafe_allow_html=True)
            st.markdown('<p class="brand-sub">Security Control: Only Administrators can create, assign, and deactivate staff accounts</p>', unsafe_allow_html=True)

            departments = get_all_departments()
            dept_dict = {d['id']: f"{d['name']} ({d['code']})" for d in departments}

            t1, t2 = st.tabs(["📋 Current Staff Directory", "➕ Create New Staff Account"])

            with t1:
                users_list = get_all_users_admin()
                staff_users = [u for u in users_list if u['role'] == 'staff']
                
                if staff_users:
                    df_staff = pd.DataFrame(staff_users)[[
                        'id', 'full_name', 'username', 'email', 'department_name', 'phone', 'is_active', 'created_at'
                    ]]
                    st.dataframe(
                        df_staff,
                        column_config={
                            "id": st.column_config.NumberColumn("User ID", width="small"),
                            "full_name": st.column_config.TextColumn("Staff Member"),
                            "username": st.column_config.TextColumn("Username"),
                            "email": st.column_config.TextColumn("Campus Email"),
                            "department_name": st.column_config.TextColumn("Assigned Department"),
                            "phone": st.column_config.TextColumn("Contact Phone"),
                            "is_active": st.column_config.CheckboxColumn("Active Status"),
                            "created_at": st.column_config.DatetimeColumn("Created Date")
                        },
                        hide_index=True,
                        use_container_width=True
                    )

                    st.markdown("##### ⚙️ Toggle Staff Account Activation")
                    act_col1, act_col2 = st.columns(2)
                    with act_col1:
                        target_staff_id = st.selectbox(
                            "Select Staff Member",
                            options=[s['id'] for s in staff_users],
                            format_func=lambda sid: next((f"{s['full_name']} (@{s['username']}) - {s['department_name']}" for s in staff_users if s['id'] == sid), "")
                        )
                    with act_col2:
                        current_active = next((bool(s['is_active']) for s in staff_users if s['id'] == target_staff_id), True)
                        new_state = st.radio("Account Status", ["Active", "Deactivated"], index=0 if current_active else 1, horizontal=True)
                        if st.button("Apply Status Change"):
                            admin_set_staff_active_status(user, target_staff_id, (new_state == "Active"))
                            st.success(f"Staff account status changed to {new_state}!")
                            st.rerun()

            with t2:
                with st.form("create_staff_form"):
                    st.markdown("##### Add New Department Staff Member")
                    cf1, cf2 = st.columns(2)
                    with cf1:
                        new_full_name = st.text_input("Full Name *", placeholder="e.g. Dr. Ramesh Gupta")
                        new_username = st.text_input("Staff Username *", placeholder="e.g. staff_mech")
                        new_password = st.text_input("Initial Password *", type="password", value="staff123")
                    with cf2:
                        new_email = st.text_input("Campus Email *", placeholder="e.g. ramesh.mech@campus.edu")
                        new_phone = st.text_input("Contact Phone", placeholder="+91 98765 00000")
                        new_dept_id = st.selectbox(
                            "Assign Department *",
                            options=list(dept_dict.keys()),
                            format_func=lambda x: dept_dict[x]
                        )

                    create_submitted = st.form_submit_button("Create Staff Account", type="primary", use_container_width=True)
                    if create_submitted:
                        if not new_full_name or not new_username or not new_email or not new_password:
                            st.error("Please fill in all required fields.")
                        else:
                            uid, err = admin_create_staff_account(
                                user, new_username, new_email, new_password, new_full_name, new_dept_id, new_phone
                            )
                            if err:
                                st.error(f"Error creating account: {err}")
                            else:
                                st.success(f"Staff account for {new_full_name} created successfully with ID #{uid}!")
                                st.rerun()


        # -------------------------------------------------------------
        # View 4: Security Audit Log (Admin Only)
        # -------------------------------------------------------------
        elif menu_choice == "🛡️ Security Audit Log":
            st.markdown('<h1 class="brand-title">Security & Operational Audit Log</h1>', unsafe_allow_html=True)
            st.markdown('<p class="brand-sub">Cryptographic log of user logins, role privilege exercises, status changes, and administrative actions</p>', unsafe_allow_html=True)

            logs = get_audit_logs(limit=200)
            if logs:
                df_logs = pd.DataFrame(logs)
                st.dataframe(
                    df_logs,
                    column_config={
                        "id": st.column_config.NumberColumn("Log ID", width="small"),
                        "timestamp": st.column_config.DatetimeColumn("Timestamp"),
                        "username": st.column_config.TextColumn("User"),
                        "action": st.column_config.TextColumn("Action"),
                        "resource_id": st.column_config.TextColumn("Target Resource"),
                        "details": st.column_config.TextColumn("Details / Remarks", width="large")
                    },
                    hide_index=True,
                    use_container_width=True
                )
            else:
                st.info("No audit logs recorded.")


        # -------------------------------------------------------------
        # View 5: Multi-Agent Pipeline
        # -------------------------------------------------------------
        elif menu_choice == "🤖 AI Multi-Agent Pipeline":
            render_agent_pipeline_view()


        # -------------------------------------------------------------
        # View 6: Admin Profile & Security
        # -------------------------------------------------------------
        elif "Profile" in menu_choice:
            st.markdown('<h1 class="brand-title">Administrator Profile & Security</h1>', unsafe_allow_html=True)
            ap1, ap2 = st.columns(2)
            with ap1:
                st.markdown(f"""
                    <div style="background: white; border: 1px solid #cbd5e1; border-radius: 10px; padding: 18px; font-size: 0.92rem; line-height: 1.8;">
                        <b>Full Name:</b> {user.get('full_name')}<br>
                        <b>Admin Username:</b> <code>{user.get('username')}</code><br>
                        <b>Campus Email:</b> <code>{user.get('email')}</code><br>
                        <b>Role Level:</b> <code>SYSTEM_ADMINISTRATOR</code> (Full Campus Access)
                    </div>
                """, unsafe_allow_html=True)
            with ap2:
                st.markdown("### 🔑 Change Administrator Password")
                with st.form("admin_pwd_form"):
                    old_p = st.text_input("Current Password", type="password")
                    new_p = st.text_input("New Password", type="password")
                    c_p = st.text_input("Confirm New Password", type="password")
                    if st.form_submit_button("Update Password", type="primary", use_container_width=True):
                        if new_p != c_p:
                            st.error("Passwords do not match.")
                        else:
                            ok, msg = change_user_password(user['id'], old_p, new_p)
                            if ok: st.success(msg)
                            else: st.error(msg)


# ----------------- Shared AI Multi-Agent Pipeline View -----------------
def render_agent_pipeline_view():
    st.markdown('<h1 class="brand-title">AI Multi-Agent Coordination Pipeline</h1>', unsafe_allow_html=True)
    st.markdown('<p class="brand-sub">Real-time visibility into the four specialized agents collaborating on tickets</p>', unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown("""
        <div style="background: white; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">
            <span style="background-color: #e0f2fe; color: #0369a1; padding: 3px 8px; border-radius: 9999px; font-size: 0.72rem; font-weight: 700;">AGENT 1</span>
            <h4 style="margin: 8px 0 4px 0;">🔍 Detection</h4>
            <p style="font-size: 0.83rem; color: #475569;">Extracts category, affected subsystem, and technical scope from complaint text.</p>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown("""
        <div style="background: white; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">
            <span style="background-color: #fef3c7; color: #b45309; padding: 3px 8px; border-radius: 9999px; font-size: 0.72rem; font-weight: 700;">AGENT 2</span>
            <h4 style="margin: 8px 0 4px 0;">🔎 Investigation</h4>
            <p style="font-size: 0.83rem; color: #475569;">Performs duplicate detection, verifies equipment asset, and flags repeated issues.</p>
        </div>
        """, unsafe_allow_html=True)
    with c3:
        st.markdown("""
        <div style="background: white; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">
            <span style="background-color: #fee2e2; color: #b91c1c; padding: 3px 8px; border-radius: 9999px; font-size: 0.72rem; font-weight: 700;">AGENT 3</span>
            <h4 style="margin: 8px 0 4px 0;">⚡ Priority</h4>
            <p style="font-size: 0.83rem; color: #475569;">Assigns explainable priority based on severity, safety risks, and disruption.</p>
        </div>
        """, unsafe_allow_html=True)
    with c4:
        st.markdown("""
        <div style="background: white; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">
            <span style="background-color: #dcfce7; color: #15803d; padding: 3px 8px; border-radius: 9999px; font-size: 0.72rem; font-weight: 700;">AGENT 4</span>
            <h4 style="margin: 8px 0 4px 0;">🛠️ Action</h4>
            <p style="font-size: 0.83rem; color: #475569;">Creates work order, assigns to department dashboard, and notifies technicians.</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### 📜 Live Agent Activity Logs")
    logs_df = fetch_agent_logs_df()

    if not logs_df.empty:
        for _, row in logs_df.iterrows():
            with st.expander(f"📌 Ticket {row['ticket_number']} — {row['agent_name']} ({row['timestamp']})"):
                st.markdown(f"**Action Summary:** {row['action_summary']}")
                if row['structured_output']:
                    try:
                        structured = json.loads(row['structured_output'])
                        st.json(structured)
                    except:
                        st.code(row['structured_output'], language="json")
    else:
        st.info("No agent activities logged yet.")


# Execute when launched by Streamlit
if __name__ == "__main__":
    main()
