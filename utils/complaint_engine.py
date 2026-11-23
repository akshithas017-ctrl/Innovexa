import os
import re
import json
from dotenv import load_dotenv
from database.db import get_connection

load_dotenv()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# ----------------- 1. Duplicate Complaint Detection -----------------
def check_duplicate_complaint(location: str, sub_location: str, description: str) -> dict:
    """
    Checks existing active complaints before creating a new one.
    Compares complaint description and location.
    If similar complaint exists, returns duplicate details.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Query active/open complaints at this location
    cursor.execute("""
        SELECT id, ticket_number, student_name, student_email, location, sub_location,
               description, category, priority, priority_reason, assigned_department,
               department_email, status, created_at
        FROM complaints
        WHERE status NOT IN ('Resolved', 'Closed', 'Completed')
        ORDER BY id DESC
    """)
    active_complaints = [dict(row) for row in cursor.fetchall()]
    conn.close()

    stopwords = {
        "the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "is", "was",
        "are", "with", "has", "been", "it", "this", "that", "near", "my", "our",
        "there", "from", "by", "not", "have", "be", "or", "as", "room", "floor"
    }

    def tokenize(text):
        tokens = re.findall(r'[a-zA-Z0-9]+', (text or "").lower())
        return set(t for t in tokens if t not in stopwords and len(t) > 2)

    new_desc_tokens = tokenize(description)
    new_loc_tokens = tokenize(location + " " + (sub_location or ""))

    best_match = None
    highest_score = 0
    match_keywords = []

    for comp in active_complaints:
        comp_loc_tokens = tokenize(comp['location'] + " " + (comp['sub_location'] or ""))
        loc_overlap = new_loc_tokens.intersection(comp_loc_tokens)
        
        # Check if locations match or share significant campus zone
        same_location = (
            comp['location'].strip().lower() == location.strip().lower() or 
            len(loc_overlap) >= 2 or
            (sub_location and comp['sub_location'] and sub_location.strip().lower() in comp['sub_location'].strip().lower())
        )

        if not same_location:
            continue

        comp_desc_tokens = tokenize(comp['description'])
        desc_overlap = new_desc_tokens.intersection(comp_desc_tokens)
        
        # Calculate overlap score
        total_unique = len(new_desc_tokens.union(comp_desc_tokens))
        jaccard = (len(desc_overlap) / total_unique) if total_unique > 0 else 0

        # Duplicate condition:
        # At same location: either >= 3 matching description keywords or Jaccard similarity >= 0.25
        if (len(desc_overlap) >= 3 or jaccard >= 0.25) and len(desc_overlap) > highest_score:
            highest_score = len(desc_overlap)
            best_match = comp
            match_keywords = list(desc_overlap)

    if best_match:
        return {
            "is_duplicate": True,
            "existing_ticket": best_match['ticket_number'],
            "existing_id": best_match['id'],
            "status": best_match['status'],
            "assigned_department": best_match.get('assigned_department') or "General Administration",
            "department_email": best_match.get('department_email') or "facilities@campus.edu",
            "location": best_match['location'],
            "sub_location": best_match['sub_location'],
            "original_description": best_match['description'],
            "created_at": best_match['created_at'],
            "matching_keywords": match_keywords,
            "message": f"A similar complaint ({best_match['ticket_number']}) is already active for this location. Do not submit a duplicate."
        }

    return {
        "is_duplicate": False,
        "message": "No matching active complaint found. Complaint is unique."
    }


# ------------- 2. Explainable Priority Classification Engine -------------
def classify_priority_explainable(description: str, location: str, sub_location: str = "", category: str = "") -> dict:
    """
    Classifies complaints as Low, Medium, or High based on:
    1. Severity of the issue
    2. Safety risk
    3. Number of people affected
    4. Urgency and impact on campus activities
    Returns priority and transparent explainable reason.
    """
    # 1. Try Gemini API if key is present
    if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
        try:
            from google import genai
            client = genai.Client(api_key=GEMINI_API_KEY)
            prompt = f"""
            You are the Priority Classification Agent for CampusFix Smart Campus System.
            Classify this student complaint as "Low", "Medium", or "High":
            - Location: {location} ({sub_location})
            - Problem Description: "{description}"
            - Category: {category}

            Base your decision strictly on these 4 criteria:
            1. Severity of the issue
            2. Safety risk (e.g. electrical sparking, fire, gas, water flooding = High)
            3. Number of people affected (e.g. auditorium/library vs single classroom vs single chair)
            4. Urgency and impact on campus activities (e.g. lecture disruption, exam)

            Examples:
            - Exposed electrical wires: High (Electrocution hazard, critical safety threat).
            - Projector not working in one classroom: Medium (Academic disruption during lectures, no safety risk).
            - Minor furniture damage: Low (Minor cosmetic defect on single chair, no safety risk or class halt).

            Respond ONLY with a valid JSON object in this exact schema:
            {{
                "priority": "<Low|Medium|High>",
                "urgency_score": <int between 1 and 10>,
                "reason": "<clear, explainable 1-2 sentence justification covering safety risk, severity, and people affected>"
            }}
            """
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config={"response_mime_type": "application/json"}
            )
            data = json.loads(response.text)
            return data
        except Exception:
            pass

    # 2. Rule-Based Explainable Classification Engine
    text = (description + " " + location + " " + (sub_location or "")).lower()

    # Criteria 1: Safety Risks (High Priority Triggers)
    safety_triggers = [
        ("exposed wire", "Exposed live electrical wiring posing critical electrocution hazard"),
        ("spark", "Electrical sparking detected with immediate short-circuit and fire risk"),
        ("fire", "Active fire or burning smell posing immediate danger to campus occupants"),
        ("burning", "Burning odor or overheating electrical equipment with imminent fire hazard"),
        ("shock", "Electric shock hazard reported on accessible equipment/fixtures"),
        ("gas", "Gas leakage or toxic chemical hazard requiring emergency containment"),
        ("flood", "Major water flooding threatening electrical conduits and structural integrity"),
        ("overflow", "Continuous water overflow causing severe slipping hazard and property damage"),
        ("elevator trapped", "Passenger entrapment in elevator requiring emergency rescue"),
        ("blackout", "Complete power outage disrupting critical campus building infrastructure"),
        ("broken glass", "Shattered glass shards in high-footfall area creating injury risk")
    ]

    for trigger, explanation in safety_triggers:
        if trigger in text:
            return {
                "priority": "High",
                "urgency_score": 9,
                "reason": f"High Priority: {explanation}. Immediate intervention required to ensure student safety."
            }

    # Criteria 2: Academic & Functional Disruption (Medium Priority Triggers)
    medium_triggers = [
        ("projector", "Projector malfunction in lecture venue disrupting classroom teaching activities; no direct safety hazard"),
        ("wifi", "Network/Wi-Fi connectivity failure disrupting lab practicals and coursework access for multiple students"),
        ("internet", "Campus network drop impacting academic computer lab operations"),
        ("ac", "Air conditioning failure in populated academic/lab space affecting indoor temperature and comfort"),
        ("cooling", "Inadequate cooling in academic block during active study hours"),
        ("water cooler", "Drinking water dispenser out of service; inconvenience to students but alternative dispensers available"),
        ("mic", "Audio-visual microphone or speaker failure in lecture hall"),
        ("light", "Classroom ceiling lighting partially non-functional, affecting reading visibility")
    ]

    for trigger, explanation in medium_triggers:
        if trigger in text:
            return {
                "priority": "Medium",
                "urgency_score": 6,
                "reason": f"Medium Priority: {explanation}."
            }

    # Criteria 3: Minor / Localized Maintenance (Low Priority Triggers)
    low_triggers = [
        ("chair", "Minor furniture defect affecting an individual seat; no safety risk or class disruption"),
        ("desk", "Minor surface scratch or loose desk armrest; suitable for routine maintenance"),
        ("door", "Squeaking hinge or non-critical door latch alignment; low urgency"),
        ("paint", "Minor cosmetic paint peeling or wall mark; routine aesthetic maintenance"),
        ("trash", "Routine litter or trash bin clearance request; standard housekeeping dispatch"),
        ("clock", "Wall clock battery discharged; minimal operational impact")
    ]

    for trigger, explanation in low_triggers:
        if trigger in text:
            return {
                "priority": "Low",
                "urgency_score": 3,
                "reason": f"Low Priority: {explanation}."
            }

    # Default fallback assessment based on location crowd density
    if any(k in text for k in ["auditorium", "library", "hostel", "exam"]):
        return {
            "priority": "Medium",
            "urgency_score": 5,
            "reason": "Medium Priority: Issue reported in a high-density student area with moderate operational impact."
        }
    else:
        return {
            "priority": "Low",
            "urgency_score": 3,
            "reason": "Low Priority: Minor localized issue with minimal safety risk and limited impact on campus activities."
        }


# ------------- 3. Department & Email Auto-Suggester Engine -------------
def suggest_department_and_email(location: str, description: str) -> tuple:
    """
    Suggests default receiving department and editable email based on problem context.
    """
    text = (location + " " + description).lower()

    if any(k in text for k in ["ac", "air condition", "cooling", "chiller", "ventilation", "hvac"]):
        return "Estate & Facilities (HVAC)", "facilities.hvac@campus.edu"
    elif any(k in text for k in ["water", "leak", "tap", "pipe", "drain", "sewage", "cooler", "purifier", "plumbing"]):
        return "Campus Water & Plumbing Services", "plumbing.services@campus.edu"
    elif any(k in text for k in ["wire", "spark", "shock", "switch", "socket", "power", "generator", "voltage", "fuse", "electricity"]):
        return "Electrical & Power Maintenance", "electrical.maintenance@campus.edu"
    elif any(k in text for k in ["projector", "mic", "audio", "speaker", "screen", "av", "display"]):
        return "Campus IT & Audio-Visual Services", "it.avservices@campus.edu"
    elif any(k in text for k in ["wifi", "wi-fi", "lan", "network", "router", "internet", "ethernet"]):
        return "Campus IT & Network Infrastructure", "it.networks@campus.edu"
    elif "hostel" in text:
        return "Hostel Management & Residential Services", "hostel.office@campus.edu"
    elif "library" in text:
        return "Central Library Facilities", "library.facilities@campus.edu"
    elif any(k in text for k in ["chair", "desk", "table", "bench", "door", "furniture", "lock", "cabinet"]):
        return "Estate & Facilities (Carpentry)", "estate.carpentry@campus.edu"
    elif any(k in text for k in ["dirty", "trash", "cleaning", "hygiene", "sanitation", "garbage"]):
        return "Campus Sanitation & Hygiene Services", "sanitation@campus.edu"
    elif any(k in text for k in ["computer science", "cs block", "lab"]):
        return "Computer Science Department Facilities", "cse.facilities@campus.edu"
    else:
        return "Campus Estate & Facilities Management", "facilities@campus.edu"
