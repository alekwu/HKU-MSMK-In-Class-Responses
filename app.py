import os
import psycopg2
from psycopg2 import sql
from urllib.parse import urlparse
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone
import pytz


app = Flask(__name__)

# Configuration
ADMIN_PASSWORD = "strongpassword"  # Change this to a strong password!
ADMIN_PASSWORD_HASH = generate_password_hash(ADMIN_PASSWORD)
app.secret_key = 'your_secret_key_here'  # Change this for production!

# Database connection
def get_db_connection():
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    return conn

# Initialize database
def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Create tables
    c.execute('''
        CREATE TABLE IF NOT EXISTS classes (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            access_code TEXT NOT NULL UNIQUE
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS questions (
            id SERIAL PRIMARY KEY,
            class_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (class_id) REFERENCES classes (id)
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS responses (
            id SERIAL PRIMARY KEY,
            question_id INTEGER NOT NULL,
            uid TEXT NOT NULL,
            student_name TEXT NOT NULL,
            answer TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (question_id) REFERENCES questions (id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Initialize the database
init_db()

# add timezone conversion
@app.template_filter('convert_timezone')
def convert_timezone_filter(dt):
    # Convert UTC to Beijing time
    utc_time = dt.replace(tzinfo=timezone.utc)
    beijing_time = utc_time.astimezone(pytz.timezone('Asia/Shanghai'))
    return beijing_time.strftime('%Y-%m-%d %H:%M')

@app.route('/')
def home():
    return redirect(url_for('code_entry'))

@app.route('/code', methods=['GET', 'POST'])
def code_entry():
    if request.method == 'POST':
        access_code = request.form['access_code']
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT id, name FROM classes WHERE access_code = %s", (access_code,))
        class_data = c.fetchone()
        conn.close()
        
        if class_data:
            session['class_id'] = class_data[0]
            session['class_name'] = class_data[1]
            return redirect(url_for('student_submission'))
        else:
            return render_template('code_entry.html', error="Invalid access code")
    
    return render_template('code_entry.html')

@app.route('/student', methods=['GET', 'POST'])
def student_submission():
    if 'class_id' not in session:
        return redirect(url_for('code_entry'))
    
    if request.method == 'POST':
        question_text = request.form['question_text']
        uid = request.form['uid']
        student_name = request.form['student_name']
        answer = request.form['answer']
        
        conn = get_db_connection()
        c = conn.cursor()
        
        # Use the student-provided question text instead of auto-generated
        c.execute(
            "INSERT INTO questions (class_id, text) VALUES (%s, %s) RETURNING id",
            (session['class_id'], question_text)  # Changed from time-based to student input
        )
        question_id = c.fetchone()[0]
        
        # Save response (no changes needed here)
        c.execute(
            "INSERT INTO responses (question_id, uid, student_name, answer) VALUES (%s, %s, %s, %s)",
            (question_id, uid, student_name, answer)
        )
        
        conn.commit()
        conn.close()
        
        return render_template('student.html', 
                           class_name=session['class_name'],
                           submitted=True)
    
    return render_template('student.html', class_name=session['class_name'])

@app.route('/HKU_MSMKprof_portal_admin/delete/<int:response_id>')
def delete_response(response_id):
    if not session.get('admin_authenticated'):
        abort(403)
        
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM responses WHERE id = %s", (response_id,))
    conn.commit()
    conn.close()
    flash('Response deleted successfully', 'success')
    return redirect(url_for('admin'))

@app.route('/HKU_MSMKprof_portal_admin/clear-all/<int:class_id>')
def clear_all_responses(class_id):
    if not session.get('admin_authenticated'):
        abort(403)
        
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # Get class name for the message
        c.execute("SELECT name FROM classes WHERE id = %s", (class_id,))
        class_name = c.fetchone()[0]
        
        # Delete responses
        c.execute("""
            DELETE FROM responses 
            WHERE question_id IN (
                SELECT id FROM questions WHERE class_id = %s
            )
        """, (class_id,))
        
        # Delete questions
        c.execute("DELETE FROM questions WHERE class_id = %s", (class_id,))
        
        conn.commit()
        flash(f'Successfully cleared all responses for "{class_name}"', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Error clearing responses: {str(e)}', 'danger')
    finally:
        conn.close()
    
    return redirect(url_for('admin', focus_class=class_id))

@app.route('/HKU_MSMKprof_portal_admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password')
        if check_password_hash(ADMIN_PASSWORD_HASH, password):
            session['admin_authenticated'] = True
            return redirect(url_for('admin'))
        else:
            return render_template('admin_login.html', error="Invalid password")
    return render_template('admin_login.html')

@app.before_request
def require_admin_auth():
    if request.path.startswith('/HKU_MSMKprof_portal_admin') and not request.path.endswith('/login'):
        if not session.get('admin_authenticated'):
            return redirect(url_for('admin_login'))
        
@app.route('/HKU_MSMKprof_portal_admin/logout')
def admin_logout():
    session.pop('admin_authenticated', None)
    return redirect(url_for('home'))
        
@app.route('/HKU_MSMKprof_portal_admin')
def admin():
    if not session.get('admin_authenticated'):
        return redirect(url_for('admin_login'))
    
    try:
        focus_class = request.args.get('focus_class')
        
        conn = get_db_connection()
        c = conn.cursor()
        
        # Get all classes
        c.execute("SELECT id, name, access_code FROM classes")
        classes = c.fetchall()
        
        # Build response query
        query = '''
            SELECT r.id, c.name, q.text, r.uid, r.student_name, r.answer, r.timestamp
            FROM responses r
            JOIN questions q ON r.question_id = q.id
            JOIN classes c ON q.class_id = c.id
        '''
        params = ()
        
        if focus_class:
            query += ' WHERE c.id = %s'
            params = (focus_class,)
            
        query += ' ORDER BY r.timestamp DESC'
        
        c.execute(query, params)
        responses = c.fetchall()
        conn.close()
        
        return render_template('admin.html', 
                           classes=classes, 
                           responses=responses,
                           focus_class=focus_class)
    except Exception as e:
        print(f"Admin route error: {str(e)}")
        return f"Error loading admin page: {str(e)}", 500

@app.route('/HKU_MSMKprof_portal_admin/add_class', methods=['POST'])
def add_class():
    if not session.get('admin_authenticated'):
        abort(403)
        
    class_name = request.form['class_name']
    access_code = request.form['access_code']
    
    conn = get_db_connection()
    c = conn.cursor()
    
    try:
        c.execute(
            "INSERT INTO classes (name, access_code) VALUES (%s, %s)",
            (class_name, access_code)
        )
        conn.commit()
        flash('Class added successfully', 'success')
    except psycopg2.IntegrityError:
        flash("Access code must be unique", 'danger')
    finally:
        conn.close()
    
    return redirect(url_for('admin'))

@app.route('/HKU_MSMKprof_portal_admin/classes')
def view_classes():
    if not session.get('admin_authenticated'):
        abort(403)
        
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, name, access_code FROM classes")
    classes = c.fetchall()
    conn.close()
    return render_template('classes.html', classes=classes)

@app.route('/HKU_MSMKprof_portal_admin/update-access-code/<int:class_id>', methods=['POST'])
def update_access_code(class_id):
    if not session.get('admin_authenticated'):
        abort(403)
        
    new_code = request.form['new_access_code']
    
    conn = get_db_connection()
    c = conn.cursor()
    
    try:
        c.execute(
            "UPDATE classes SET access_code = %s WHERE id = %s",
            (new_code, class_id)
        )
        conn.commit()
        flash('Access code updated successfully!', 'success')
    except psycopg2.IntegrityError:
        flash('Access code must be unique!', 'danger')
    finally:
        conn.close()
    
    return redirect(url_for('view_classes'))

@app.route('/HKU_MSMKprof_portal_admin/delete-class/<int:class_id>')
def delete_class(class_id):
    if not session.get('admin_authenticated'):
        abort(403)
        
    conn = get_db_connection()
    c = conn.cursor()
    
    try:
        # Delete responses
        c.execute("""
            DELETE FROM responses 
            WHERE question_id IN (
                SELECT id FROM questions WHERE class_id = %s
            )
        """, (class_id,))
        
        # Delete questions
        c.execute("DELETE FROM questions WHERE class_id = %s", (class_id,))
        
        # Delete class
        c.execute("DELETE FROM classes WHERE id = %s", (class_id,))
        
        conn.commit()
        flash('Class deleted successfully', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Error deleting class: {str(e)}', 'danger')
    finally:
        conn.close()
    
    return redirect(url_for('view_classes'))

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)