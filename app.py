import os
import datetime
import MySQLdb.cursors
import MySQLdb
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, g, send_from_directory
from dotenv import load_dotenv
from functools import wraps
from werkzeug.utils import secure_filename

# Load environment variables from .env file
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
# IMPORTANT: Change this to a random, secure key for production
app.secret_key = os.getenv('SECRET_KEY', 'your_super_secret_key')

# Define a folder to store the uploaded documents
# The path is relative to the directory where app.py is run
UPLOAD_FOLDER = 'uploaded_documents'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Create the upload folder if it doesn't exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Database connection function
def get_db():
    """
    Establishes a connection to the MySQL database and stores it in g.db.
    It reuses the connection if one already exists for the current request.
    """
    if 'db' not in g:
        try:
            g.db = MySQLdb.connect(
                host=os.getenv('MYSQL_HOST', 'db'),
                user=os.getenv('MYSQL_USER', 'root'),
                password=os.getenv('MYSQL_PASSWORD', 'rootpassword'),
                database=os.getenv('MYSQL_DB', 'app_db')
            )
        except MySQLdb.Error as e:
            print(f"Error connecting to MySQL: {e}")
            g.db = None
    return g.db

@app.teardown_appcontext
def teardown_db(exception):
    """
    Closes the database connection at the end of the request.
    """
    db = g.pop('db', None)
    if db is not None:
        db.close()

# Context processor to make session data available to all templates
@app.context_processor
def inject_user_data():
    return dict(
        logged_in=session.get('logged_in'),
        username=session.get('username'),
        role=session.get('role')
    )

# Decorator to check for user login
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'logged_in' not in session or not session['logged_in']:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper

# Decorator to check for admin role
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get('role') != 'Admin':
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return wrapper

# Helper function to log events to the database
def log_event_action(username, action):
    """
    Logs a user's action with a current timestamp.
    """
    db = get_db()
    if db:
        cursor = db.cursor()
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('INSERT INTO events_logs (username, action, timestamp) VALUES (%s, %s, %s)', (username, action, timestamp))
        db.commit()

# Route for the login page
@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        db = get_db()
        if db is None:
            return "Database connection failed", 500
        
        cursor = db.cursor(MySQLdb.cursors.DictCursor)
        
        # NOTE: Passwords are not hashed. This is for demonstration only.
        # In a real application, hash and salt passwords!
        cursor.execute('SELECT * FROM users WHERE username = %s AND password = %s', (username, password,))
        user = cursor.fetchone()
        
        if user:
            session['logged_in'] = True
            session['id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            
            # Log the login action using the new function
            log_event_action(user['username'], 'User logged in')
            
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error='Invalid credentials')
    
    return render_template('login.html')

# Route for logging out
@app.route('/logout')
@login_required
def logout():
    # Log the logout action using the new function
    log_event_action(session.get('username'), 'User logged out')
    session.clear()
    return redirect(url_for('login'))

# Route for the main dashboard page
@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    cursor = db.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM platforms')
    platforms = cursor.fetchall()
    
    return render_template('index.html', platforms=platforms)

# Routes for menu items
@app.route('/user_management')
@login_required
@admin_required
def user_management():
    db = get_db()
    cursor = db.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT id, username, email, password, role FROM users')
    users = cursor.fetchall()
    return render_template('user_management.html', users=users)

@app.route('/events_logs')
@login_required
def events_logs():
    db = get_db()
    cursor = db.cursor(MySQLdb.cursors.DictCursor)
    
    # Initialize the base query and parameters.
    query = "SELECT username, action, timestamp FROM events_logs WHERE 1=1"
    params = []

    # Get filter values from the URL query parameters.
    filter_username = request.args.get('username')
    filter_timestamp = request.args.get('timestamp')

    # Add conditions to the query if filter values are provided.
    if filter_username:
        query += " AND username = %s"
        params.append(filter_username)
    
    if filter_timestamp:
        # We filter for logs on a specific day.
        query += " AND DATE(timestamp) = %s"
        params.append(filter_timestamp)

    # Order by timestamp to show the most recent logs first.
    query += " ORDER BY timestamp DESC"

    cursor.execute(query, tuple(params))
    logs = cursor.fetchall()

    return render_template('event_logs.html', logs=logs)

@app.route('/platform_tracker')
@login_required
def platform_tracker():
    db = get_db()
    cursor = db.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM documents')
    documents = cursor.fetchall()
    
    # Get unique platform names for the dropdown
    cursor.execute('SELECT DISTINCT name FROM platforms')
    platforms = cursor.fetchall()
    platform_names = [p['name'] for p in platforms]
    
    return render_template('platform_tracker.html', documents=documents, platform_names=platform_names)

# API endpoints for CRUD operations
@app.route('/api/users', methods=['POST'])
@login_required
@admin_required
def manage_users():
    db = get_db()
    cursor = db.cursor()
    data = request.json
    
    action = data.get('action')
    
    if action == 'add':
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        role = data.get('role')
        cursor.execute('INSERT INTO users (username, email, password, role) VALUES (%s, %s, %s, %s)', (username, email, password, role))
        db.commit()
        
        # Log the action
        log_event_action(session.get('username'), f'Added new user: {username}')
        return jsonify({'status': 'success', 'message': 'User added successfully'})
        
    elif action == 'update':
        id = data.get('id')
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        role = data.get('role')
        
        # Update user. Only update password if provided.
        if password:
            cursor.execute('UPDATE users SET username=%s, email=%s, password=%s, role=%s WHERE id=%s', (username, email, password, role, id))
        else:
            cursor.execute('UPDATE users SET username=%s, email=%s, role=%s WHERE id=%s', (username, email, role, id))
        db.commit()
        
        # Log the action
        log_event_action(session.get('username'), f'Updated user: {username}')
        return jsonify({'status': 'success', 'message': 'User updated successfully'})
        
    elif action == 'delete':
        id = data.get('id')
        cursor.execute('DELETE FROM users WHERE id=%s', (id,))
        db.commit()
        
        # Log the action
        log_event_action(session.get('username'), f'Deleted user with ID: {id}')
        return jsonify({'status': 'success', 'message': 'User deleted successfully'})
        
    return jsonify({'status': 'error', 'message': 'Invalid action'})

# Updated API endpoint to handle file uploads
@app.route('/api/documents', methods=['POST'])
@login_required
def manage_documents():
    db = get_db()
    cursor = db.cursor()

    # CRITICAL FIX: Try to get JSON data first, as the delete function sends a JSON payload.
    data = request.get_json(silent=True)
    if data:
        action = data.get('action')
        doc_id = data.get('id')
    else:
        # If no JSON, fall back to form data for add/update actions.
        action = request.form.get('action')
        doc_id = request.form.get('id')
    
    # Retrieve the other form fields, as they will be present for add/update actions
    platform_name = request.form.get('platform_name')
    doc_type = request.form.get('doc_type')
    doc_name = request.form.get('doc_name')
    version = request.form.get('version')
    doc_file = request.files.get('doc_file')
    comments = request.form.get('comments')  # New: Retrieve the comments field

    # Initialize path variable
    path = request.form.get('path')

    if action == 'add':
        if doc_file:
            # Secure the filename to prevent directory traversal attacks
            filename = secure_filename(doc_file.filename)
            # Create the full path to save the file
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            doc_file.save(file_path)
            # Set the path to be saved in the database
            path = file_path
        else:
            return jsonify({'status': 'error', 'message': 'No file uploaded for a new document.'})

        # New: Include comments in the SQL INSERT statement
        cursor.execute('INSERT INTO documents (platform_name, doc_type, doc_name, version, path, comments) VALUES (%s, %s, %s, %s, %s, %s)', (platform_name, doc_type, doc_name, version, path, comments))
        db.commit()
        
        # Log the action
        log_event_action(session.get('username'), f'Added new document for {platform_name}: {doc_name}')
        return jsonify({'status': 'success', 'message': 'Document added successfully'})
    
    elif action == 'update':
        if doc_file:
            # Secure the filename
            filename = secure_filename(doc_file.filename)
            # Save the new file, overwriting the old one if the name is the same
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            doc_file.save(file_path)
            # Update the path
            path = file_path
        
        # Use the existing path if no new file was uploaded
        if not path and not doc_file:
            # Fetch the old path from the database to avoid overwriting it with a blank value
            cursor.execute('SELECT path FROM documents WHERE id = %s', (doc_id,))
            old_path = cursor.fetchone()
            if old_path:
                path = old_path[0]
            else:
                return jsonify({'status': 'error', 'message': 'Document not found for update.'})
        
        # New: Include comments in the SQL UPDATE statement
        cursor.execute('UPDATE documents SET platform_name=%s, doc_type=%s, doc_name=%s, version=%s, path=%s, comments=%s WHERE id=%s', (platform_name, doc_type, doc_name, version, path, comments, doc_id))
        db.commit()
        
        # Log the action
        log_event_action(session.get('username'), f'Updated document with ID: {doc_id}')
        return jsonify({'status': 'success', 'message': 'Document updated successfully'})

    elif action == 'delete':
        # First, retrieve the path to the file to be deleted
        cursor.execute('SELECT path FROM documents WHERE id = %s', (doc_id,))
        doc_path = cursor.fetchone()

        if doc_path:
            file_to_delete = doc_path[0]
            # Check if the file exists on the filesystem and delete it
            if os.path.exists(file_to_delete):
                os.remove(file_to_delete)
            
        # Then, delete the record from the database
        cursor.execute('DELETE FROM documents WHERE id=%s', (doc_id,))
        db.commit()
        
        # Log the action
        log_event_action(session.get('username'), f'Deleted document with ID: {doc_id}')
        return jsonify({'status': 'success', 'message': 'Document deleted successfully'})
        
    return jsonify({'status': 'error', 'message': 'Invalid action'})

@app.route('/api/documents/<string:platform_name>')
@login_required
def get_documents_by_platform(platform_name):
    db = get_db()
    cursor = db.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM documents WHERE platform_name = %s', (platform_name,))
    documents = cursor.fetchall()
    return jsonify(documents)

# This is the new route you need to add to your app.py
@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    """
    Serves a specific file from the secure upload folder.
    The filename is a part of the URL.
    """
    # Use send_from_directory to securely serve the file
    # This prevents directory traversal attacks
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Main entry point for the Flask app
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
