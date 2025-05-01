# This would be in app.py
import sqlite3

def init_db():
    conn = sqlite3.connect('classroom.db')
    c = conn.cursor()
    
    # Create tables
    c.execute('''CREATE TABLE IF NOT EXISTS professors
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              email TEXT UNIQUE NOT NULL,
              password TEXT NOT NULL,
              name TEXT NOT NULL)''')
    
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
from flask import request, abort
import sqlite3
from datetime import datetime
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Change this for production!

# Flask-Login setup
login_manager = LoginManager(app)
login_manager.login_view = 'prof_login'

class Professor(UserMixin):
    pass

@login_manager.user_loader
def load_user(prof_id):
    conn = sqlite3.connect('classroom.db')
    c = conn.cursor()
    c.execute("SELECT id FROM professors WHERE id = ?", (prof_id,))
    prof = c.fetchone()
    conn.close()
    if not prof:
        return None
    user = Professor()
    user.id = prof[0]
    return user

# Professor Signup
@app.route('/prof/signup', methods=['GET', 'POST'])
def prof_signup():
    if request.method == 'POST':
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        name = request.form['name']
        
        try:
            conn = sqlite3.connect('classroom.db')
            c = conn.cursor()
            c.execute("INSERT INTO professors (email, password, name) VALUES (?, ?, ?)",
                     (email, password, name))
            conn.commit()
            return redirect(url_for('prof_login'))
        except sqlite3.IntegrityError:
            return "Email already exists", 400
    
    return render_template('prof_signup.html')

# Professor Login
@app.route('/prof/login', methods=['GET', 'POST'])
def prof_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        conn = sqlite3.connect('classroom.db')
        c = conn.cursor()
        c.execute("SELECT id, password FROM professors WHERE email = ?", (email,))
        prof = c.fetchone()
        conn.close()
        
        if prof and check_password_hash(prof[1], password):
            user = Professor()
            user.id = prof[0]
            login_user(user)
            return redirect(url_for('admin'))
        
        return "Invalid credentials", 401
    
    return render_template('prof_login.html')


# Flask-Login setup
login_manager = LoginManager(app)
login_manager.login_view = 'prof_login'

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

# Admin interface
@app.route('/admin')
@login_required  # ← This ensures only logged-in profs can access
def admin():
    conn = sqlite3.connect('classroom.db')
    c = conn.cursor()
    
    # Get all classes
    c.execute("SELECT id, name, access_code FROM classes")
    classes = c.fetchall()
    
    # Get all responses
    c.execute('''SELECT r.id, c.name, q.text, r.uid, r.student_name, r.answer, r.timestamp
                 FROM responses r
                 JOIN questions q ON r.question_id = q.id
                 JOIN classes c ON q.class_id = c.id
                 ORDER BY r.timestamp DESC''')
    responses = c.fetchall()
    
    conn.close()
    
    return render_template('admin.html', classes=classes, responses=responses)

# Add a new class (admin only)
@app.route('/admin/add_class', methods=['POST'])
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

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)