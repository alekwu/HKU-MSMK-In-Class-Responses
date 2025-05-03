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
ADMIN_PASSWORD = "strongpassword"
ADMIN_PASSWORD_HASH = generate_password_hash(ADMIN_PASSWORD)
app.secret_key = 'your_secret_key_here'

# Database connection
def get_db_connection():
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    return conn

# Initialize database
def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
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
            is_starred BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (question_id) REFERENCES questions (id)
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

@app.template_filter('convert_timezone')
def convert_timezone_filter(dt):
    utc_time = dt.replace(tzinfo=timezone.utc)
    beijing_time = utc_time.astimezone(pytz.timezone('Asia/Shanghai'))
    return beijing_time.strftime('%Y-%m-%d %H:%M')

# [Previous routes remain the same until admin()]

@app.route('/HKU_MSMKprof_portal_admin')
def admin():
    if not session.get('admin_authenticated'):
        return redirect(url_for('admin_login'))
    
    try:
        focus_class = request.args.get('focus_class')
        filter_type = request.args.get('filter')
        
        conn = get_db_connection()
        c = conn.cursor()
        
        c.execute("SELECT id, name, access_code FROM classes")
        classes = c.fetchall()
        
        query = '''
            SELECT r.id, c.name, q.text, r.uid, r.student_name, r.answer, r.timestamp, r.is_starred
            FROM responses r
            JOIN questions q ON r.question_id = q.id
            JOIN classes c ON q.class_id = c.id
        '''
        params = ()
        
        if filter_type == 'starred':
            query += ' WHERE r.is_starred = TRUE'
        elif focus_class:
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

@app.route('/HKU_MSMKprof_portal_admin/star-response/<int:response_id>')
def star_response(response_id):
    if not session.get('admin_authenticated'):
        abort(403)
        
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE responses 
        SET is_starred = NOT is_starred 
        WHERE id = %s
        RETURNING is_starred
    """, (response_id,))
    new_state = c.fetchone()[0]
    conn.commit()
    conn.close()
    
    flash(f'Response {"starred ★" if new_state else "unstarred"} successfully', 'success')
    return redirect(request.referrer or url_for('admin'))

# [Keep all your other existing routes below]
