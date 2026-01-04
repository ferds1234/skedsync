from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import mysql.connector
from datetime import datetime, time


app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # Replace with a secure key

def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",         # <-- set your MariaDB username
        password="123", # <-- set your MariaDB password
        database="skedsync"
    )

def is_admin_or_faculty():
    """Check if current user is admin or faculty"""
    if session.get('user') == 'admin@skedsync.com':
        return True
    if not session.get('user'):
        return False
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT section, year_level FROM users WHERE email = %s", (session.get('user'),))
        user = cursor.fetchone()
        cursor.close()
        db.close()
        return user and user["section"] == "Faculty" and user["year_level"] == "Faculty"
    except:
        return False

@app.route("/")
def index():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        if not email or not password:
            flash("Please enter both email and password.", "danger")
            return render_template("login.html")
        try:
            db = get_db()
        except Exception as e:
            flash("Database connection failed: " + str(e), "danger")
            return render_template("login.html")
        try:
            cursor = db.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
            user = cursor.fetchone()
            cursor.close()
            db.close()
            print(f"DEBUG: Login attempt for {email}. User found: {bool(user)}")
            if user and user["password"] == password:
                session["user"] = user["email"]
                session["user_id"] = user["id"]  # Set user_id for flashcards
                print(f"DEBUG: Session user set to {session['user']}")
                if user["email"] == "admin@skedsync.com" or (user["section"] == "Faculty" and user["year_level"] == "Faculty"):
                    print("DEBUG: Redirecting to admindashboard")
                    return redirect(url_for("admindashboard"))
                else:
                    print("DEBUG: Redirecting to dashboard")
                    return redirect(url_for("dashboard"))
            else:
                print("DEBUG: Invalid credentials for", email)
                flash("Invalid email or password.", "danger")
        except Exception as e:
            print("DEBUG: Exception during login:", e)
            flash("An error occurred during login: " + str(e), "danger")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        student_id = request.form.get("student_id")
        name = request.form.get("name")
        email = request.form.get("email")
        section = request.form.get("section")
        department = request.form.get("department")
        year_level = request.form.get("year_level")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")
        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("register.html")
        db = get_db()
        cursor = db.cursor(dictionary=True)
        # Check for existing email or student_id
        cursor.execute("SELECT * FROM users WHERE email = %s OR student_id = %s", (email, student_id))
        existing = cursor.fetchone()
        if existing:
            cursor.close()
            db.close()
            if existing["email"] == email:
                flash("Email already registered.", "danger")
            else:
                flash("Student ID already registered.", "danger")
            return render_template("register.html")
        cursor.execute(
            "INSERT INTO users (student_id, name, email, section, department, year_level, password) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (student_id, name, email, section, department, year_level, password)
        )
        db.commit()
        cursor.close()
        db.close()
        
        # Log user registration activity
        log_admin_activity('user', f'New user registered: {name} ({email})')
        
        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/dashboard")
def dashboard():
    # Only redirect to admin dashboard if session user is exactly "admin"
    if session.get("user") == "admin":
        return redirect(url_for("admindashboard"))
    if not session.get("user"):
        return redirect(url_for("login"))
    
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    # Get user info for filtering
    cursor.execute(
        "SELECT department, year_level, section FROM users WHERE email = %s",
        (session['user'],)
    )
    user = cursor.fetchone()
    
    # Get user's notifications/announcements
    cursor.execute(
        "SELECT * FROM announcements WHERE status = 'published' AND department = %s AND year_level = %s AND section = %s ORDER BY date ASC LIMIT 10",
        (user['department'], user['year_level'], user['section'])
    )
    notifications = cursor.fetchall()
    
    # Convert timedelta to time objects for template rendering
    for notification in notifications:
        if notification.get('time') and hasattr(notification['time'], 'total_seconds'):
            # Convert timedelta to time
            total_seconds = int(notification['time'].total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            notification['time'] = time(hour=hours, minute=minutes)
    
    # Calculate widget statistics
    today = datetime.now().date()
    
    # Count upcoming classes (room type announcements)
    upcoming_classes = len([n for n in notifications if n['type'] == 'room' and n.get('date') and n['date'] >= today])
    
    # Count exams this week
    from datetime import timedelta
    week_end = today + timedelta(days=7)
    exams_this_week = len([n for n in notifications if n['type'] == 'exam' and n.get('date') and today <= n['date'] <= week_end])
    
    # Total notifications count
    total_notifications = len(notifications)
    
    # Count tasks/quizzes due soon
    tasks_due_soon = len([n for n in notifications if n['type'] == 'quiz' and n.get('date') and today <= n['date'] <= week_end])
    
    # Get next class info
    next_class = next((n for n in notifications if n['type'] == 'room' and n.get('date') and n['date'] >= today), None)
    
    # Get next exam info
    next_exam = next((n for n in notifications if n['type'] == 'exam' and n.get('date') and n['date'] >= today), None)
    
    # Get next task info
    next_task = next((n for n in notifications if n['type'] == 'quiz' and n.get('date') and n['date'] >= today), None)
    
    # Get past schedules (completed announcements)
    past_schedules = [n for n in notifications if n.get('date') and n['date'] < today][:4]
    
    cursor.close()
    db.close()
    
    return render_template("dashboard.html", 
                         notifications=notifications,
                         upcoming_classes=upcoming_classes,
                         exams_this_week=exams_this_week,
                         total_notifications=total_notifications,
                         tasks_due_soon=tasks_due_soon,
                         next_class=next_class,
                         next_exam=next_exam,
                         next_task=next_task,
                         past_schedules=past_schedules)

@app.route("/schedule")
def schedule():
    if not session.get("user"):
        return redirect(url_for("login"))
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(
        "SELECT student_id, name, email, section, department, year_level FROM users WHERE email = %s",
        (session["user"],)
    )
    user = cursor.fetchone()
    cursor.close()
    db.close()
    return render_template("schedule.html", user=user)

@app.route("/notifications")
def notifications():
    if not session.get("user"):
        return redirect(url_for("login"))
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    # Get user info for filtering
    cursor.execute(
        "SELECT department, year_level, section FROM users WHERE email = %s",
        (session["user"],)
    )
    user = cursor.fetchone()
    
    # Get announcements matching user's credentials
    cursor.execute(
        "SELECT * FROM announcements WHERE status = 'published' AND department = %s AND year_level = %s AND section = %s ORDER BY created_at DESC",
        (user['department'], user['year_level'], user['section'])
    )
    user_notifications = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template("notifications.html", notifications=user_notifications)

@app.route("/profile")
def profile():
    if not session.get("user"):
        return redirect(url_for("login"))
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(
        "SELECT student_id, name, email, section, department, year_level FROM users WHERE email = %s",
        (session["user"],)
    )
    user = cursor.fetchone()
    cursor.close()
    db.close()
    return render_template("profile.html", user=user)

def log_admin_activity(action_type, description):
    """Log admin activity to the database"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Create admin_activities table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admin_activities (
                id INT AUTO_INCREMENT PRIMARY KEY,
                action_type VARCHAR(50),
                description TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Insert the activity
        cursor.execute(
            "INSERT INTO admin_activities (action_type, description) VALUES (%s, %s)",
            (action_type, description)
        )
        db.commit()
        cursor.close()
        db.close()
    except Exception as e:
        print(f"Error logging admin activity: {e}")

@app.route("/admindashboard")
def admindashboard():
    if not is_admin_or_faculty():
        return redirect(url_for("login"))
    
    # Log admin dashboard access
    log_admin_activity('system', 'Admin dashboard accessed')
    
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    # Create admin_activities table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin_activities (
            id INT AUTO_INCREMENT PRIMARY KEY,
            action_type VARCHAR(50),
            description TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Add sample activities if table is empty
    cursor.execute("SELECT COUNT(*) as count FROM admin_activities")
    if cursor.fetchone()['count'] == 0:
        sample_activities = [
            ('system', 'Admin dashboard accessed'),
            ('user', 'User management system initialized'),
            ('announcement', 'Announcement system ready'),
            ('system', 'Database connection established')
        ]
        for activity_type, description in sample_activities:
            cursor.execute(
                "INSERT INTO admin_activities (action_type, description) VALUES (%s, %s)",
                (activity_type, description)
            )
        db.commit()
    
    cursor.execute("SELECT COUNT(*) as total_users FROM users")
    total_users = cursor.fetchone()['total_users']
    cursor.execute("SELECT COUNT(*) as active_schedules FROM schedules WHERE status = 'active'")
    active_schedules = cursor.fetchone()['active_schedules']
    cursor.execute("SELECT COUNT(*) as total_announcements FROM announcements WHERE status = 'published'")
    total_announcements = cursor.fetchone()['total_announcements']
    cursor.execute("SELECT * FROM announcements WHERE status = 'published' ORDER BY id DESC LIMIT 3")
    announcements = cursor.fetchall()
    
    # Get recent admin activities (last 4)
    cursor.execute("SELECT * FROM admin_activities ORDER BY timestamp DESC LIMIT 4")
    recent_activities = cursor.fetchall()
    
    cursor.close()
    db.close()
    return render_template("admindashboard.html", total_users=total_users, active_schedules=active_schedules, total_announcements=total_announcements, announcements=announcements, recent_activities=recent_activities)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route('/flashcards')
def flashcards():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM flashcards WHERE user_id = %s ORDER BY id DESC", (session.get('user_id'),))
    user_flashcards = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template('flashcards.html', flashcards=user_flashcards)

@app.route('/users')
def manage_users():
    if not is_admin_or_faculty():
        return redirect(url_for('login'))
    
    # Log user management access
    log_admin_activity('user', 'User management page accessed')
    
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users ORDER BY id DESC")
    users = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template('manage_users.html', users=users)

@app.route('/schedules')
def manage_schedules():
    if not is_admin_or_faculty():
        return redirect(url_for('login'))
    
    # Log schedule management access
    log_admin_activity('schedule', 'Schedule management page accessed')
    
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM announcements WHERE status = 'published' ORDER BY created_at DESC")
    announcements = cursor.fetchall()
    
    # Convert timedelta to time objects for template rendering
    for announcement in announcements:
        if announcement.get('time') and hasattr(announcement['time'], 'total_seconds'):
            # Convert timedelta to time
            total_seconds = int(announcement['time'].total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            announcement['time'] = datetime.min.time().replace(hour=hours, minute=minutes)
    
    cursor.close()
    db.close()
    return render_template('manage_schedules.html', announcements=announcements)

@app.route('/announcements/create', methods=['POST'])
def create_announcement():
    if session.get('user') != 'admin@skedsync.com':
        return redirect(url_for('login'))
    
    try:
        data = request.form
        date_obj = datetime.strptime(data.get('date'), '%Y-%m-%d').date() if data.get('date') else None
        time_obj = datetime.strptime(data.get('time'), '%H:%M').time() if data.get('time') else None
        
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "INSERT INTO announcements (type, title, description, subject, room, date, time, duration, instructions, department, year_level, section, status, created_by) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'published', %s)",
            (data.get('announcement_type'), data.get('title'), data.get('description'), data.get('subject'), data.get('room'), date_obj, time_obj, data.get('duration'), data.get('instructions'), data.get('department'), data.get('year_level'), data.get('section'), session.get('user_id'))
        )
        db.commit()
        cursor.close()
        db.close()
        
        # Log admin activity
        log_admin_activity('announcement', f'Created {data.get("announcement_type")} announcement: {data.get("title")}')
        
        flash('Announcement created successfully!', 'success')
    except Exception as e:
        flash(f'Error creating announcement: {str(e)}', 'error')
    
    return redirect(url_for('manage_schedules'))

@app.route('/announcements/edit/<int:id>', methods=['GET', 'POST'])
def edit_announcement(id):
    if session.get('user') != 'admin@skedsync.com':
        return redirect(url_for('login'))
    
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    if request.method == 'POST':
        data = request.form
        date_obj = datetime.strptime(data.get('date'), '%Y-%m-%d').date() if data.get('date') else None
        time_obj = datetime.strptime(data.get('time'), '%H:%M').time() if data.get('time') else None
        
        cursor.execute(
            "UPDATE announcements SET title = %s, description = %s, subject = %s, room = %s, date = %s, time = %s, duration = %s, instructions = %s, department = %s, year_level = %s, section = %s WHERE id = %s",
            (data.get('title'), data.get('description'), data.get('subject'), data.get('room'), date_obj, time_obj, data.get('duration'), data.get('instructions'), data.get('department'), data.get('year_level'), data.get('section'), id)
        )
        db.commit()
        cursor.close()
        db.close()
        
        # Log admin activity
        log_admin_activity('announcement', f'Updated announcement: {data.get("title")}')
        
        flash('Announcement updated successfully!', 'success')
        return redirect(url_for('manage_schedules'))
    
    cursor.execute("SELECT * FROM announcements WHERE id = %s", (id,))
    announcement = cursor.fetchone()
    cursor.close()
    db.close()
    return jsonify(announcement)

@app.route('/announcements/delete/<int:id>', methods=['POST'])
def delete_announcement(id):
    if session.get('user') != 'admin@skedsync.com':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        
        # Get announcement title before deleting
        cursor.execute("SELECT title FROM announcements WHERE id = %s", (id,))
        announcement = cursor.fetchone()
        title = announcement['title'] if announcement else 'Unknown'
        
        cursor.execute("DELETE FROM announcements WHERE id = %s", (id,))
        db.commit()
        cursor.close()
        db.close()
        
        # Log admin activity
        log_admin_activity('announcement', f'Deleted announcement: {title}')
        
        flash('Announcement deleted successfully!', 'success')
        return redirect(url_for('manage_schedules'))
    except Exception as e:
        flash(f'Error deleting announcement: {str(e)}', 'error')
        return redirect(url_for('manage_schedules'))

@app.route('/reports')
def reports():
    if not is_admin_or_faculty():
        return redirect(url_for('login'))
    
    # Log reports access
    log_admin_activity('system', 'Reports page accessed')
    
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    # Create activity_logs table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            activity_type VARCHAR(50),
            description TEXT,
            department VARCHAR(100),
            status VARCHAR(20),
            created_at DATETIME
        )
    """)
    
    # Insert sample activity logs if empty
    cursor.execute("SELECT COUNT(*) as count FROM activity_logs")
    if cursor.fetchone()['count'] == 0:
        sample_activities = [
            ('User', 'New user registration: John Doe', 'Computer Science', 'Success', '2024-01-15 10:30:00'),
            ('Schedule', 'Schedule updated for CS Department', 'Computer Science', 'Success', '2024-01-15 09:15:00'),
            ('Announcement', 'Quiz announcement sent: Math 101', 'Engineering', 'Success', '2024-01-14 15:00:00'),
            ('System', 'System backup completed', 'System', 'Success', '2024-01-14 11:45:00'),
            ('Announcement', 'Room update: Room 205 maintenance', 'All Departments', 'Success', '2024-01-13 14:20:00')
        ]
        for activity in sample_activities:
            cursor.execute(
                "INSERT INTO activity_logs (activity_type, description, department, status, created_at) VALUES (%s, %s, %s, %s, %s)",
                activity
            )
        db.commit()
    
    # Get statistics
    cursor.execute("SELECT COUNT(*) as total_users FROM users")
    total_users = cursor.fetchone()['total_users']
    
    cursor.execute("SELECT COUNT(*) as active_schedules FROM schedules WHERE status = 'active'")
    active_schedules = cursor.fetchone()['active_schedules']
    
    cursor.execute("SELECT COUNT(*) as total_announcements FROM announcements WHERE status = 'published'")
    total_announcements = cursor.fetchone()['total_announcements']
    
    # Get department distribution
    cursor.execute("SELECT department, COUNT(*) as count FROM users GROUP BY department")
    dept_distribution = cursor.fetchall()
    
    # Get user registration trends (simulate weekly data with user IDs)
    cursor.execute("""
        SELECT 
            CASE 
                WHEN id <= 5 THEN 'Week 1'
                WHEN id <= 10 THEN 'Week 2'
                WHEN id <= 15 THEN 'Week 3'
                WHEN id <= 20 THEN 'Week 4'
                WHEN id <= 25 THEN 'Week 5'
                WHEN id <= 30 THEN 'Week 6'
                WHEN id <= 35 THEN 'Week 7'
                ELSE 'Week 8'
            END as week,
            COUNT(*) as count
        FROM users 
        GROUP BY 
            CASE 
                WHEN id <= 5 THEN 'Week 1'
                WHEN id <= 10 THEN 'Week 2'
                WHEN id <= 15 THEN 'Week 3'
                WHEN id <= 20 THEN 'Week 4'
                WHEN id <= 25 THEN 'Week 5'
                WHEN id <= 30 THEN 'Week 6'
                WHEN id <= 35 THEN 'Week 7'
                ELSE 'Week 8'
            END
        ORDER BY week
    """)
    user_trends = cursor.fetchall()
    
    # Get system activity overview data from admin_activities table
    cursor.execute("""
        SELECT 
            action_type as activity_type,
            COUNT(*) as count
        FROM admin_activities 
        GROUP BY action_type
        ORDER BY count DESC
    """)
    system_activity = cursor.fetchall()
    
    # If no data, add some sample activities
    if not system_activity:
        sample_activities = [
            ('system', 'Database connection established'),
            ('user', 'User management initialized'),
            ('announcement', 'Announcement system ready'),
            ('system', 'Admin dashboard accessed')
        ]
        for activity_type, description in sample_activities:
            cursor.execute(
                "INSERT INTO admin_activities (action_type, description) VALUES (%s, %s)",
                (activity_type, description)
            )
        db.commit()
        
        # Re-fetch the data
        cursor.execute("""
            SELECT 
                action_type as activity_type,
                COUNT(*) as count
            FROM admin_activities 
            GROUP BY action_type
            ORDER BY count DESC
        """)
        system_activity = cursor.fetchall()
    
    # Get recent activity logs from admin_activities table
    cursor.execute("SELECT action_type as activity_type, description, 'System' as department, 'Success' as status, timestamp as created_at FROM admin_activities ORDER BY timestamp DESC LIMIT 20")
    activity_logs = cursor.fetchall()
    
    cursor.close()
    db.close()
    
    return render_template('reports.html', 
                         total_users=total_users,
                         active_schedules=active_schedules, 
                         total_announcements=total_announcements,
                         dept_distribution=dept_distribution,
                         user_trends=user_trends,
                         system_activity=system_activity,
                         activity_logs=activity_logs)

@app.route('/adminnotifications')
def adminnotifications():
    if session.get('user') != 'admin@skedsync.com':
        return redirect(url_for('login'))
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    # Create notifications table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INT AUTO_INCREMENT PRIMARY KEY,
            type VARCHAR(50),
            title VARCHAR(255),
            message TEXT,
            status VARCHAR(20) DEFAULT 'unread',
            created_at DATETIME,
            user_id INT
        )
    """)
    
    # Insert sample notifications if table is empty
    cursor.execute("SELECT COUNT(*) as count FROM notifications")
    if cursor.fetchone()['count'] == 0:
        sample_notifications = [
            ('sys', 'Server Maintenance Scheduled', 'System will be down for maintenance tomorrow at 2:00 AM'),
            ('sys', 'Backup Completed Successfully', 'Daily system backup completed without errors'),
            ('usr', 'New User Registration', 'Jane Smith has registered for Computer Science Department'),
            ('usr', 'Schedule Update Request', 'Engineering Department requested schedule modification'),
            ('snt', 'Quiz Announcement: Math 101', 'Sent to Engineering Department - Tomorrow 10:00 AM'),
            ('snt', 'Room Update: Room 205 Maintenance', 'Sent to All Departments - Maintenance until 3:00 PM')
        ]
        for notif in sample_notifications:
            cursor.execute(
                "INSERT INTO notifications (type, title, message) VALUES (%s, %s, %s)",
                notif
            )
        db.commit()
    
    cursor.execute("SELECT * FROM notifications ORDER BY id DESC LIMIT 50")
    notifications = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template('adminnotifications.html', notifications=notifications)

from flask import jsonify

@app.route('/api/announcements')
def get_announcements():
    if session.get('user') != 'admin@skedsync.com':
        return jsonify({'error': 'Unauthorized'}), 401
    
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM announcements WHERE status = 'published' ORDER BY id DESC")
    announcements = cursor.fetchall()
    cursor.close()
    db.close()
    return jsonify(announcements)

from datetime import datetime

@app.route('/api/announcements/filter')
def filter_announcements():
    if session.get('user') != 'admin@skedsync.com':
        return jsonify({'error': 'Unauthorized'}), 401
    
    announcement_type = request.args.get('type')
    search = request.args.get('search', '')
    
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    query = "SELECT * FROM announcements WHERE status = 'published'"
    params = []
    
    if announcement_type:
        query += " AND type = %s"
        params.append(announcement_type)
    
    if search:
        query += " AND (title LIKE %s OR description LIKE %s OR subject LIKE %s)"
        search_param = f"%{search}%"
        params.extend([search_param, search_param, search_param])
    
    query += " ORDER BY created_at DESC"
    
    cursor.execute(query, params)
    announcements = cursor.fetchall()
    cursor.close()
    db.close()
    
    # Convert date/time objects to strings for JSON serialization
    for announcement in announcements:
        if announcement.get('date'):
            announcement['date'] = announcement['date'].strftime('%Y-%m-%d')
        if announcement.get('time'):
            announcement['time'] = announcement['time'].strftime('%H:%M')
        if announcement.get('created_at'):
            announcement['created_at'] = announcement['created_at'].strftime('%Y-%m-%d %H:%M:%S')
    
    return jsonify(announcements)

@app.route('/users/delete/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if session.get('user') != 'admin@skedsync.com':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        
        # Check if user exists and is not admin
        cursor.execute("SELECT email, name FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            cursor.close()
            db.close()
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        if user['email'] == 'admin@skedsync.com':
            cursor.close()
            db.close()
            return jsonify({'success': False, 'message': 'Cannot delete admin user'}), 403
        
        # Delete user
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        db.commit()
        cursor.close()
        db.close()
        
        # Log admin activity
        log_admin_activity('user', f'Deleted user: {user["name"]} ({user["email"]})')
        
        return jsonify({'success': True, 'message': 'User deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error deleting user: {str(e)}'}), 500

@app.route('/api/notifications')
def get_notifications():
    if not session.get('user'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    # Get current user info for filtering
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(
        "SELECT department, year_level, section FROM users WHERE email = %s",
        (session['user'],)
    )
    user = cursor.fetchone()
    
    if not user:
        cursor.close()
        db.close()
        return jsonify({'error': 'User not found'}), 404
    
    # Get announcements that match user credentials
    cursor.execute(
        "SELECT * FROM announcements WHERE status = 'published' AND department = %s AND year_level = %s AND section = %s ORDER BY date ASC",
        (user['department'], user['year_level'], user['section'])
    )
    announcements = cursor.fetchall()
    cursor.close()
    db.close()
    
    # Convert date/time objects to strings for JSON serialization
    for announcement in announcements:
        if announcement.get('date'):
            announcement['date'] = announcement['date'].strftime('%Y-%m-%d')
        else:
            announcement['date'] = None
            
        if announcement.get('time'):
            if hasattr(announcement['time'], 'total_seconds'):
                # Convert timedelta to time string
                total_seconds = int(announcement['time'].total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                announcement['time'] = f"{hours:02d}:{minutes:02d}"
            else:
                announcement['time'] = announcement['time'].strftime('%H:%M')
        else:
            announcement['time'] = None
            
        if announcement.get('created_at'):
            announcement['created_at'] = announcement['created_at'].strftime('%Y-%m-%d %H:%M:%S')
    
    return jsonify(announcements)

@app.route('/api/system-activity')
def get_system_activity():
    if session.get('user') != 'admin@skedsync.com':
        return jsonify({'error': 'Unauthorized'}), 401
    
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    # Get system activity data
    cursor.execute("""
        SELECT 
            action_type as activity_type,
            COUNT(*) as count
        FROM admin_activities 
        GROUP BY action_type
        ORDER BY count DESC
    """)
    system_activity = cursor.fetchall()
    
    # Get recent activities
    cursor.execute("""
        SELECT 
            action_type as activity_type,
            description,
            timestamp as created_at
        FROM admin_activities 
        ORDER BY timestamp DESC 
        LIMIT 10
    """)
    recent_activities = cursor.fetchall()
    
    cursor.close()
    db.close()
    
    # Convert datetime objects to strings
    for activity in recent_activities:
        if activity.get('created_at'):
            activity['created_at'] = activity['created_at'].strftime('%Y-%m-%d %H:%M:%S')
    
    return jsonify({
        'system_activity': system_activity,
        'recent_activities': recent_activities
    })

@app.route('/api/notification/<int:notification_id>')
def get_notification_details(notification_id):
    if not session.get('user'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    # Get user info for filtering
    cursor.execute(
        "SELECT department, year_level, section FROM users WHERE email = %s",
        (session['user'],)
    )
    user = cursor.fetchone()
    
    if not user:
        cursor.close()
        db.close()
        return jsonify({'error': 'User not found'}), 404
    
    # Get notification details with user access check
    cursor.execute(
        "SELECT * FROM announcements WHERE id = %s AND status = 'published' AND department = %s AND year_level = %s AND section = %s",
        (notification_id, user['department'], user['year_level'], user['section'])
    )
    notification = cursor.fetchone()
    cursor.close()
    db.close()
    
    if not notification:
        return jsonify({'error': 'Notification not found'}), 404
    
    # Format the response
    response = {
        'title': notification['title'],
        'description': notification['description'] or 'No additional details available.',
        'subject': notification['subject'],
        'room': notification['room'],
        'date': notification['date'].strftime('%B %d, %Y') if notification['date'] else None,
        'time': notification['time'].strftime('%I:%M %p') if notification['time'] else None,
        'duration': notification['duration'],
        'instructions': notification['instructions'],
        'created_at': notification['created_at'].strftime('%B %d, %Y') if notification['created_at'] else 'Recently'
    }
    
    return jsonify(response)

@app.route('/create-faculty', methods=['POST'])
def create_faculty(): 
    if not is_admin_or_faculty():
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))
    
    faculty_id = request.form.get('faculty_id')
    name = request.form.get('name')
    email = request.form.get('email')
    department = request.form.get('department')
    password = request.form.get('password')
    confirm_password = request.form.get('confirm_password')
    
    if password != confirm_password:
        flash('Passwords do not match.', 'danger')
        return redirect(url_for('manage_users'))
    
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        
        # Check for existing email or faculty_id
        cursor.execute("SELECT * FROM users WHERE email = %s OR student_id = %s", (email, faculty_id))
        existing = cursor.fetchone()
        if existing:
            cursor.close()
            db.close()
            if existing["email"] == email:
                flash("Email already registered.", "danger")
            else:
                flash("Faculty ID already registered.", "danger")
            return redirect(url_for('manage_users'))
        
        # Insert faculty account with Admin role indicators
        cursor.execute(
            "INSERT INTO users (student_id, name, email, section, department, year_level, password) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (faculty_id, name, email, 'Faculty', department, 'Faculty', password)
        )
        db.commit()
        cursor.close()
        db.close()
        
        # Log admin activity
        log_admin_activity('user', f'Created faculty account: {name} ({email})')
        
        flash('Faculty account created successfully!', 'success')
    except Exception as e:
        flash(f'Error creating faculty account: {str(e)}', 'danger')
    
    return redirect(url_for('manage_users'))

if __name__ == "__main__":
    app.run(debug=True)


