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
from flask import request, abort
import sqlite3
from datetime import datetime

app = Flask(__name__)
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
@app.route('/super-secret-prof-portal-2024/delete/<int:response_id>')
def delete_response(response_id):
    conn = sqlite3.connect('classroom.db')
    c = conn.cursor()
    c.execute("DELETE FROM responses WHERE id = ?", (response_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))  # Refresh admin page

# Delete all responses for current class
@app.route('/super-secret-prof-portal-2024/clear-all')
def clear_all_responses():
    if 'class_id' not in session:
        return "No class selected", 400
        
    conn = sqlite3.connect('classroom.db')
    c = conn.cursor()
    c.execute("""
        DELETE FROM responses 
        WHERE question_id IN (
            SELECT id FROM questions 
            WHERE class_id = ?
        )
    """, (session['class_id'],))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))



# Admin interface
@app.route('/HKU_MSMKprof_portal_admin')
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