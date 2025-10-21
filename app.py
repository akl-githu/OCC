import os
import datetime
import MySQLdb.cursors
import MySQLdb
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, g, send_from_directory
from dotenv import load_dotenv
from functools import wraps
from werkzeug.utils import secure_filename
import requests # Import for making HTTP requests

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

# MODIFIED: Helper function to check platform status, supporting both direct HTTP and PromQL
def check_platform_status(prometheus_url, health_check_endpoint):
    """
    Checks the platform status.
    If 'health_check_endpoint' looks like a PromQL query, it uses the Prometheus API.
    Otherwise, it performs a direct GET request.
    """
    if not prometheus_url or not health_check_endpoint:
        return 'Config Missing'
    
    # 1. Check if the endpoint looks like a PromQL query (contains metric name and label filters)
    is_promql = any(char in health_check_endpoint for char in ['{', '}', '=', '~'])

    if is_promql:
        # --- PromQL Query Logic ---
        
        # Ensure the Prom URL is correctly formed for the query API
        prom_query_url = f"{prometheus_url.rstrip('/')}/api/v1/query"
        
        try:
            # Send the PromQL query to the Prometheus server
            response = requests.get(
                prom_query_url, 
                params={'query': health_check_endpoint}, 
                timeout=10 # Use a longer timeout for PromQL queries if they are complex
            )
            response.raise_for_status() # Raise exception for bad status codes (4xx or 5xx)
            
            data = response.json()
            
            if data['status'] == 'success' and data['data']['result']:
                # PromQL result is an array of vectors. We check the value of the first one.
                # A value of '1' usually means the probe was successful/online.
                # The value is a string, e.g., ['1698200000', '1']
                metric_value = float(data['data']['result'][0]['value'][1])
                
                if metric_value >= 1.0:
                    return 'Online'
                else:
                    return 'Offline (Metric 0)'
            else:
                # Query succeeded but returned no data (e.g., target offline)
                return 'Offline (No Metric)'

        except requests.exceptions.HTTPError as e:
            # Prometheus server responded with an error (e.g., 400 Bad Request for invalid query)
            return f'Error (Prometheus HTTP {response.status_code})'
        except requests.exceptions.RequestException as e:
            # Connection errors, timeouts, etc.
            print(f"Error executing PromQL query against {prom_query_url}: {e}")
            return 'Offline (Prometheus Down)'
        except (ValueError, KeyError, IndexError) as e:
            # JSON parsing error or unexpected data structure
            print(f"Error processing PromQL response: {e}")
            return 'Error (Data Parse)'
            
    else:
        # --- Direct HTTP Endpoint Logic ---
        
        # Construct the full URL, ensuring only one separator
        full_url = f"{prometheus_url.rstrip('/')}/{health_check_endpoint.lstrip('/')}"
        
        try:
            # Perform direct GET request to the platform endpoint
            response = requests.get(full_url, timeout=5)
            
            if 200 <= response.status_code < 300:
                return 'Online'
            else:
                return f'Error ({response.status_code})'
                
        except requests.exceptions.RequestException as e:
            print(f"Error checking status for {full_url}: {e}")
            return 'Offline'

# NEW: API endpoint to check and return the status of a single platform (used by JS)
@app.route('/api/platform_status/<int:platform_id>')
@login_required
def get_platform_status(platform_id):
    db = get_db()
    cursor = db.cursor(MySQLdb.cursors.DictCursor)
    
    cursor.execute('SELECT prometheus_url, health_check_endpoint FROM platforms WHERE id = %s', (platform_id,))
    platform = cursor.fetchone()

    if platform:
        status = check_platform_status(platform.get('prometheus_url'), platform.get('health_check_endpoint'))
        return jsonify({'status': status})
    
    return jsonify({'status': 'Not Found'}), 404

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

# MODIFIED: Route for the main dashboard page - NO LONGER PERFORMS SYNCHRONOUS CHECKS
@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    cursor = db.cursor(MySQLdb.cursors.DictCursor)
    
    # Select all fields required for rendering the dashboard card.
    cursor.execute('SELECT id, name, status, image_url, grafana_url, manage_type, manage_url, prometheus_url, health_check_endpoint FROM platforms')
    platforms_raw = cursor.fetchall()
    
    # Send the raw platform data to the template. The status displayed will
    # initially be set by the template via JavaScript (e.g., "Loading...").
    # The original 'status' column in the database is no longer updated or relied upon for real-time check.
    
    return render_template('index.html', platforms=platforms_raw)

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

# MODIFIED: Route for the platform tracker page to pass the user's role
@app.route('/platform_tracker')
@login_required
def platform_tracker():
    db = get_db()
    cursor = db.cursor(MySQLdb.cursors.DictCursor)
    
    # Get unique platform names for the dropdowns
    cursor.execute('SELECT name FROM platforms')
    platforms = cursor.fetchall()
    
    # Get the user's role from the session
    user_role = session.get('role')
    
    return render_template('platform_tracker.html', platforms=platforms, user_role=user_role)

# NEW Route for the documents page
@app.route('/documents')
@login_required
def documents():
    db = get_db()
    cursor = db.cursor(MySQLdb.cursors.DictCursor)
    
    cursor.execute('SELECT * FROM documents')
    documents = cursor.fetchall()
    
    # Get unique platform names for the dropdowns
    cursor.execute('SELECT name FROM platforms')
    platforms = cursor.fetchall()
    
    return render_template('documents.html', documents=documents, platforms=platforms)

# MODIFIED: API endpoint to add a new platform, including Prometheus configuration
@app.route('/api/add_platform', methods=['POST'])
@login_required
@admin_required # Platform CRUD should be admin restricted
def add_platform():
    db = get_db()
    cursor = db.cursor()
    data = request.json
    
    platform_name = data.get('platform_name')
    grafana_url = data.get('grafana_url', '')
    # NEW FIELDS: Extract Prometheus configuration
    prometheus_url = data.get('prometheus_url', '')
    health_check_endpoint = data.get('health_check_endpoint', '')

    if not platform_name:
        return jsonify({'status': 'error', 'message': 'Platform name is required'}), 400
    
    # Initial status is set to 'Unknown'
    status = 'Unknown' 
    manage_url = "https://techpam.etisalat.corp.ae/SecretServer/Login.aspxReturnUrl=%2fSecretServer%2fdefault.aspx"
    image_url = 'https://placehold.co/100x100/A0E7E5/000000?text=' + platform_name
    manage_type = ''
    
    try:
        # Insert into platforms table with updated fields
        cursor.execute(
            'INSERT INTO platforms (name, status, image_url, grafana_url, manage_type, manage_url, prometheus_url, health_check_endpoint) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
            (platform_name, status, image_url, grafana_url, manage_type, manage_url, prometheus_url, health_check_endpoint)
        )
        
        # Insert into platform_progress table without 'progress_stage' and 'stage_date'
        cursor.execute(
            'INSERT INTO platform_progress (platform_name, comments) VALUES (%s, %s)',
            (platform_name, 'Platform added - Initial entry')
        )
        
        db.commit()
        log_event_action(session.get('username'), f'Added new platform: {platform_name}')
        return jsonify({'status': 'success', 'message': 'Platform added successfully'})
    except MySQLdb.Error as e:
        db.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

# MODIFIED: API endpoint to update a platform's details, including Prometheus configuration
@app.route('/api/update_platform', methods=['POST'])
@login_required
@admin_required # Platform CRUD should be admin restricted
def update_platform():
    db = get_db()
    cursor = db.cursor()
    data = request.json
    
    old_platform_name = data.get('old_platform_name')
    new_platform_name = data.get('new_platform_name')
    grafana_url = data.get('grafana_url', '')
    # NEW FIELDS: Extract Prometheus configuration
    prometheus_url = data.get('prometheus_url', '')
    health_check_endpoint = data.get('health_check_endpoint', '')

    if not old_platform_name or not new_platform_name:
        return jsonify({'status': 'error', 'message': 'Old and New Platform names are required for update'}), 400
    
    try:
        # Check if the platform exists
        cursor.execute('SELECT name FROM platforms WHERE name = %s', (old_platform_name,))
        if cursor.rowcount == 0:
            return jsonify({'status': 'error', 'message': f'Platform "{old_platform_name}" not found'}), 404

        # If the name is changing, we need to perform cascading updates
        if old_platform_name != new_platform_name:
            # 1. Check if the new name already exists (to prevent conflict)
            cursor.execute('SELECT name FROM platforms WHERE name = %s', (new_platform_name,))
            if cursor.rowcount > 0:
                return jsonify({'status': 'error', 'message': f'Platform name "{new_platform_name}" already exists. Please choose a unique name.'}), 400
                
            # 2. Update platform_progress records (cascading update)
            cursor.execute('UPDATE platform_progress SET platform_name = %s WHERE platform_name = %s', (new_platform_name, old_platform_name))

            # 3. Update documents records (cascading update)
            cursor.execute('UPDATE documents SET platform_name = %s WHERE platform_name = %s', (new_platform_name, old_platform_name))

        # 4. Update the platform itself (name, Grafana URL, and new Prometheus fields)
        cursor.execute(
            'UPDATE platforms SET name = %s, grafana_url = %s, prometheus_url = %s, health_check_endpoint = %s WHERE name = %s',
            (new_platform_name, grafana_url, prometheus_url, health_check_endpoint, old_platform_name)
        )
        
        db.commit()
        
        log_event_action(session.get('username'), f'Updated platform from "{old_platform_name}" to "{new_platform_name}" (URLs updated)')
        return jsonify({'status': 'success', 'message': f'Platform "{old_platform_name}" updated to "{new_platform_name}" successfully'})
    except MySQLdb.Error as e:
        db.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500


# NEW API endpoint to delete a platform and all its related data
@app.route('/api/delete_platform', methods=['POST'])
@login_required
@admin_required # Platform CRUD should be admin restricted
def delete_platform():
    db = get_db()
    cursor = db.cursor()
    data = request.json
    
    platform_name = data.get('platform_name')

    if not platform_name:
        return jsonify({'status': 'error', 'message': 'Platform name is required for deletion'}), 400
    
    try:
        # 1. Get list of files to delete from the filesystem
        cursor.execute('SELECT path FROM documents WHERE platform_name = %s', (platform_name,))
        files_to_delete = cursor.fetchall()
        
        # 2. Delete all related documents from the database
        cursor.execute('DELETE FROM documents WHERE platform_name = %s', (platform_name,))

        # 3. Delete all related progress entries
        cursor.execute('DELETE FROM platform_progress WHERE platform_name = %s', (platform_name,))
        
        # 4. Delete the platform itself
        cursor.execute('DELETE FROM platforms WHERE name = %s', (platform_name,))
        
        db.commit()
        
        # 5. Delete files from the filesystem
        for (file_path,) in files_to_delete:
            # Only attempt to delete files that exist and are within the UPLOAD_FOLDER
            if file_path.startswith(app.config['UPLOAD_FOLDER']) and os.path.exists(file_path):
                os.remove(file_path)
        
        log_event_action(session.get('username'), f'Deleted platform: {platform_name} and all related data')
        return jsonify({'status': 'success', 'message': f'Platform "{platform_name}" and all related data deleted successfully'})
    except MySQLdb.Error as e:
        db.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500


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

# MODIFIED: Updated API endpoint to handle file uploads and restrict deletion
@app.route('/api/documents', methods=['GET', 'POST'])
@login_required
def manage_documents():
    # FIX: Handle incorrect GET requests by redirecting to the correct page.
    if request.method == 'GET':
        return redirect(url_for('documents'))

    # If method is POST, proceed with the API logic.
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
    comments = request.form.get('comments')
    
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

        # Include comments in the SQL INSERT statement
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
        
        # Include comments in the SQL UPDATE statement
        cursor.execute('UPDATE documents SET platform_name=%s, doc_type=%s, doc_name=%s, version=%s, path=%s, comments=%s WHERE id=%s', (platform_name, doc_type, doc_name, version, path, comments, doc_id))
        db.commit()
        
        # Log the action
        log_event_action(session.get('username'), f'Updated document with ID: {doc_id}')
        return jsonify({'status': 'success', 'message': 'Document updated successfully'})

    elif action == 'delete':
        # NEW: Check for Admin role specifically for deletion
        if session.get('role') != 'Admin':
            return jsonify({'status': 'error', 'message': 'Permission denied. Only Admin users can delete documents.'}), 403

        # First, retrieve the path to the file to be deleted
        cursor.execute('SELECT path FROM documents WHERE id = %s', (doc_id,))
        doc_path = cursor.fetchone()

        if doc_path:
            file_to_delete = doc_path[0]
            # Check if the file exists on the filesystem and delete it
            if file_to_delete.startswith(app.config['UPLOAD_FOLDER']) and os.path.exists(file_to_delete):
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

# API endpoint to get progress data for a specific platform
@app.route('/api/platform_progress/<string:platform_name>')
@login_required
def get_platform_progress(platform_name):
    db = get_db()
    cursor = db.cursor(MySQLdb.cursors.DictCursor)
    # Get the latest entry for each stage for the selected platform
    cursor.execute("""
        SELECT 
            t1.progress_stage,
            t1.stage_date,
            t1.comments
        FROM platform_progress t1
        JOIN (
            SELECT
                progress_stage,
                MAX(stage_date) AS max_date
            FROM platform_progress
            WHERE platform_name = %s
            GROUP BY progress_stage
        ) t2
        ON t1.progress_stage = t2.progress_stage AND t1.stage_date = t2.max_date
        WHERE t1.platform_name = %s
        ORDER BY t1.stage_date ASC
    """, (platform_name, platform_name))
    progress = cursor.fetchall()
    if progress:
        return jsonify(progress)
    return jsonify({'status': 'error', 'message': 'No progress found for this platform'}), 404

# API endpoint to add/update platform progress
@app.route('/api/platform_progress', methods=['POST'])
@login_required
def manage_platform_progress():
    db = get_db()
    cursor = db.cursor()
    data = request.json
    
    platform_name = data.get('platform_name')
    stage = data.get('progress_stage')
    date = data.get('stage_date')
    comments = data.get('comments')

    if not all([platform_name, stage, date]):
        return jsonify({'status': 'error', 'message': 'Missing required fields'}), 400

    # Insert new progress entry
    cursor.execute(
        'INSERT INTO platform_progress (platform_name, progress_stage, stage_date, comments) VALUES (%s, %s, %s, %s)',
        (platform_name, stage, date, comments)
    )
    db.commit()
    
    log_event_action(session.get('username'), f'Updated progress for {platform_name} to stage: {stage}')
    
    return jsonify({'status': 'success', 'message': 'Platform progress updated successfully'})

# Route to serve uploaded files
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