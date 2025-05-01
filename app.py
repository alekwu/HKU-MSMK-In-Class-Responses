# This would be in app.py
import sqlite3

def init_db():
    conn = sqlite3.connect('classroom.db')
    c = conn.cursor()
    
    # Create tables
    c.execute('''CREATE TABLE IF NOT EXISTS classes
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  access_code TEXT NOT NULL UNIQUE)''')
                  
    c.execute('''CREATE TABLE IF NOT EXISTS questions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  class_id INTEGER NOT NULL,
                  text TEXT NOT NULL,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (class_id) REFERENCES classes (id))''')
                  
    c.execute('''CREATE TABLE IF NOT EXISTS responses
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  question_id INTEGER NOT NULL,
                  uid TEXT NOT NULL,
                  student_name TEXT NOT NULL,
                  answer TEXT NOT NULL,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (question_id) REFERENCES questions (id))''')
    
    conn.commit()
    conn.close()
    



from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from flask import request, abort
import sqlite3
from datetime import datetime
from flask import flash 
from flask import (
    Flask, 
    render_template, 
    request, 
    redirect, 
    url_for, 
    session,
    flash  # <-- THIS IS CRUCIAL
)

app = Flask(__name__)

# Add this at the top (after app creation)
ADMIN_PASSWORD = "strongpassword"  # Change this to a strong password!
ADMIN_PASSWORD_HASH = generate_password_hash(ADMIN_PASSWORD)  # Hashed version

app.secret_key = 'your_secret_key_here'  # Change this for production!

# Initialize database
init_db()

@app.route('/')
def home():
    return redirect(url_for('code_entry'))

# Access code entry
@app.route('/code', methods=['GET', 'POST'])
def code_entry():
    if request.method == 'POST':
        access_code = request.form['access_code']
        
        conn = sqlite3.connect('classroom.db')
        c = conn.cursor()
        c.execute("SELECT id, name FROM classes WHERE access_code = ?", (access_code,))
        class_data = c.fetchone()
        conn.close()
        
        if class_data:
            session['class_id'] = class_data[0]
            session['class_name'] = class_data[1]
            return redirect(url_for('student_submission'))
        else:
            return render_template('code_entry.html', error="Invalid access code")
    
    return render_template('code_entry.html')

# Student submission page
@app.route('/student', methods=['GET', 'POST'])
def student_submission():
    if 'class_id' not in session:
        return redirect(url_for('code_entry'))
    
    if request.method == 'POST':
        uid = request.form['uid']
        student_name = request.form['student_name']
        answer = request.form['answer']
        
        # In a real app, you'd want to validate these inputs
        
        conn = sqlite3.connect('classroom.db')
        c = conn.cursor()
        
        # Create a new question if needed
        c.execute("INSERT INTO questions (class_id, text) VALUES (?, ?)",
                 (session['class_id'], f"Question at {datetime.now().strftime('%H:%M')}"))
        question_id = c.lastrowid
        
        # Save the response
        c.execute("INSERT INTO responses (question_id, uid, student_name, answer) VALUES (?, ?, ?, ?)",
                 (question_id, uid, student_name, answer))
        
        conn.commit()
        conn.close()
        
        return render_template('student.html', 
                            class_name=session['class_name'],
                            submitted=True)
    
    return render_template('student.html', class_name=session['class_name'])


# Delete single response
@app.route('/HKU_MSMKprof_portal_admin/delete/<int:response_id>')
def delete_response(response_id):
    conn = sqlite3.connect('classroom.db')
    c = conn.cursor()
    c.execute("DELETE FROM responses WHERE id = ?", (response_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))  # Refresh admin page

# Delete all responses for current class
@app.route('/HKU_MSMKprof_portal_admin/clear-all/<int:class_id>')
def clear_all_responses(class_id):
    if not session.get('admin_authenticated'):
        abort(403)
        
    try:
        conn = sqlite3.connect('classroom.db')
        c = conn.cursor()
        
        # Get class name for the message
        c.execute("SELECT name FROM classes WHERE id = ?", (class_id,))
        class_name = c.fetchone()[0]
        
        # Delete responses
        c.execute("""
            DELETE FROM responses 
            WHERE question_id IN (
                SELECT id FROM questions WHERE class_id = ?
            )
        """, (class_id,))
        
        # Delete questions
        c.execute("DELETE FROM questions WHERE class_id = ?", (class_id,))
        
        conn.commit()
        flash(f'Successfully cleared all responses for "{class_name}"', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Error clearing responses: {str(e)}', 'danger')
    finally:
        conn.close()
    
    return redirect(url_for('admin', focus_class=class_id))

# New admin login route
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

# Protect all admin routes
@app.before_request
def require_admin_auth():
    if request.path.startswith('/HKU_MSMKprof_portal_admin') and not request.path.endswith('/login'):
        if not session.get('admin_authenticated'):
            return redirect(url_for('admin_login'))
        
@app.route('/HKU_MSMKprof_portal_admin/logout')
def admin_logout():
    session.pop('admin_authenticated', None)
    return redirect(url_for('home'))
        
# Admin interface
@app.route('/HKU_MSMKprof_portal_admin')
def admin():
    if not session.get('admin_authenticated'):
        return redirect(url_for('admin_login'))
    try:
        focus_class = request.args.get('focus_class')
        
        conn = sqlite3.connect('classroom.db', timeout=10)  # Add timeout
        c = conn.cursor()
        
        # Debug: Print tables to verify database structure
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        print("Tables in database:", c.fetchall())  # Check Render logs for this
        
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
            query += ' WHERE c.id = ?'
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
        print(f"Admin route error: {str(e)}")  # Check Render logs
        return f"Error loading admin page: {str(e)}", 500

# Add a new class (admin only)
@app.route('/HKU_MSMKprof_portal_admin/add_class', methods=['POST'])
def add_class():
    class_name = request.form['class_name']
    access_code = request.form['access_code']
    
    conn = sqlite3.connect('classroom.db')
    c = conn.cursor()
    
    try:
        c.execute("INSERT INTO classes (name, access_code) VALUES (?, ?)",
                 (class_name, access_code))
        conn.commit()
    except sqlite3.IntegrityError:
        return "Access code must be unique", 400
    
    conn.close()
    return redirect(url_for('admin'))

# View all classes
@app.route('/HKU_MSMKprof_portal_admin/classes')
def view_classes():
    conn = sqlite3.connect('classroom.db')
    c = conn.cursor()
    c.execute("SELECT id, name, access_code FROM classes")
    classes = c.fetchall()
    conn.close()
    return render_template('classes.html', classes=classes)

# Delete a class
@app.route('/HKU_MSMKprof_portal_admin/delete-class/<int:class_id>')
def delete_class(class_id):
    conn = sqlite3.connect('classroom.db')
    c = conn.cursor()
    
    # First delete responses linked to this class
    c.execute("""
        DELETE FROM responses 
        WHERE question_id IN (
            SELECT id FROM questions 
            WHERE class_id = ?
        )
    """, (class_id,))
    
    # Then delete questions
    c.execute("DELETE FROM questions WHERE class_id = ?", (class_id,))
    
    # Finally delete the class
    c.execute("DELETE FROM classes WHERE id = ?", (class_id,))
    
    conn.commit()
    conn.close()
    return redirect(url_for('view_classes'))

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
