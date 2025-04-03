from flask import Flask, redirect, request, session, url_for, render_template_string
from oura import OuraOAuth2Client
from dotenv import load_dotenv
import os
import traceback
import requests
import json
from datetime import datetime, timedelta
from supabase import create_client, Client
from functools import wraps
from cryptography.fernet import Fernet

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')

# OAuth2 Configuration
client_id = os.getenv('OURA_CLIENT_ID')
client_secret = os.getenv('OURA_CLIENT_SECRET')
redirect_uri = os.getenv('OURA_REDIRECT_URI')

# Encryption Configuration
encryption_key = os.getenv('ENCRYPTION_KEY').encode()
fernet = Fernet(encryption_key)

# Supabase Configuration
supabase: Client = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)

def encrypt_token(token: str) -> str:
    """Encrypt a token using Fernet encryption."""
    return fernet.encrypt(token.encode()).decode()

def decrypt_token(encrypted_token: str) -> str:
    """Decrypt a token using Fernet encryption."""
    return fernet.decrypt(encrypted_token.encode()).decode()

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'profile_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    """Home page with login link."""
    if 'profile_id' in session:
        return redirect(url_for('dashboard'))
    return '''
        <h1>Oura Ring Data Comparison</h1>
        <p>Compare your Oura Ring data with friends!</p>
        <a href="/login">Connect to Oura Ring</a>
    '''

@app.route('/login')
def login():
    """Initiate OAuth2 flow."""
    auth_client = OuraOAuth2Client(client_id=client_id, client_secret=client_secret)
    
    # Get the authorization URL
    auth_endpoint_result = auth_client.authorize_endpoint(
        redirect_uri=redirect_uri,
        scope=["personal", "daily", "heartrate", "workout", "session", "sleep"]
    )
    
    # Handle both tuple and string responses
    if isinstance(auth_endpoint_result, tuple):
        auth_url = auth_endpoint_result[0]
    else:
        auth_url = auth_endpoint_result
        
    return redirect(auth_url)

@app.route('/callback')
def callback():
    """Handle OAuth2 callback and token exchange."""
    code = request.args.get('code')
    if not code:
        return 'Error: No authorization code received', 400

    try:
        # Exchange code for tokens
        token_url = "https://api.ouraring.com/oauth/token"
        payload = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri,
            'client_id': client_id,
            'client_secret': client_secret
        }
        
        response = requests.post(token_url, data=payload)
        if response.status_code != 200:
            return f'Error during token exchange: {response.text}', 400
        
        token_dict = response.json()
        
        # Get user info from Oura
        headers = {
            'Authorization': f'Bearer {token_dict["access_token"]}',
            'Content-Type': 'application/json'
        }
        user_info_response = requests.get(
            "https://api.ouraring.com/v2/usercollection/personal_info",
            headers=headers
        )
        
        if user_info_response.status_code != 200:
            return f'Error fetching user info: {user_info_response.text}', 400
        
        user_info = user_info_response.json()
        
        # Generate display name from email
        email = user_info.get('email')
        display_name = email.split('@')[0] if email else f"User_{datetime.now().strftime('%y%m%d%H%M%S')}"
        
        # Check if profile exists
        existing_profile = supabase.table('profiles').select('*').eq('oura_user_id', user_info.get('id')).execute()
        
        if existing_profile.data:
            # Update existing profile
            profile_id = existing_profile.data[0]['id']
            supabase.table('profiles').update({
                'email': email,
                'display_name': display_name
            }).eq('id', profile_id).execute()
        else:
            # Create new profile
            profile_result = supabase.table('profiles').insert({
                'oura_user_id': user_info.get('id'),
                'email': email,
                'display_name': display_name
            }).execute()
            profile_id = profile_result.data[0]['id']
        
        # Store/update tokens
        token_data = {
            'profile_id': profile_id,
            'access_token_encrypted': encrypt_token(token_dict['access_token']),
            'refresh_token_encrypted': encrypt_token(token_dict['refresh_token']) if token_dict.get('refresh_token') else None,
            'expires_at': (datetime.now() + timedelta(seconds=token_dict['expires_in'])).isoformat(),
            'scopes': ','.join(token_dict.get('scope', '').split(' '))
        }
        
        # Upsert tokens
        existing_tokens = supabase.table('oura_tokens').select('*').eq('profile_id', profile_id).execute()
        if existing_tokens.data:
            supabase.table('oura_tokens').update(token_data).eq('profile_id', profile_id).execute()
        else:
            supabase.table('oura_tokens').insert(token_data).execute()
        
        # Store profile_id in session
        session['profile_id'] = profile_id
        session['oura_user_id'] = user_info.get('id')
        
        return redirect(url_for('dashboard'))
    except Exception as e:
        print(f"Error during callback: {str(e)}")
        print(traceback.format_exc())
        return f'Error during callback: {str(e)}', 400

@app.route('/dashboard')
@login_required
def dashboard():
    """Display user's Oura Ring data and global leaderboard."""
    try:
        # Calculate date range for sleep data
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        # Get user's profile and tokens
        profile = supabase.table('profiles').select('*').eq('id', session['profile_id']).execute()
        if not profile.data:
            return redirect(url_for('login'))
        
        # Get all users and their tokens for the leaderboard
        all_users_with_tokens = supabase.table('profiles')\
            .select('*, oura_tokens(*)')\
            .execute()
            
        # Prepare leaderboard data
        leaderboard_data = []
        
        for user in all_users_with_tokens.data:
            try:
                if not user['oura_tokens']:
                    continue
                    
                # Decrypt token
                token = decrypt_token(user['oura_tokens'][0]['access_token_encrypted'])
                
                headers = {
                    'Authorization': f'Bearer {token}',
                    'Content-Type': 'application/json'
                }
                
                sleep_response = requests.get(
                    f"https://api.ouraring.com/v2/usercollection/daily_sleep?start_date={start_date}&end_date={end_date}",
                    headers=headers
                )
                
                if sleep_response.status_code == 200:
                    sleep_data = sleep_response.json()
                    # Print debug info to understand data structure
                    print(f"Sleep data for {user['display_name']}: {json.dumps(sleep_data, indent=2)}")
                    
                    # Get all valid scores from the data, sorted by date (most recent first)
                    daily_sleep = sleep_data.get('data', [])
                    daily_sleep.sort(key=lambda x: x['day'], reverse=True)  # Sort by date, newest first
                    scores = []
                    
                    for day in daily_sleep:
                        # Get the sleep score directly from the day data
                        score = day.get('score', None)
                        
                        if score is not None:
                            scores.append(score)
                            print(f"Found score {score} for day {day['day']}")
                    
                    # Print debug info
                    print(f"User {user['display_name']} - Valid scores found: {scores}")
                    
                    # Calculate scores
                    latest_score = scores[0] if scores else 0  # Most recent score
                    avg_score = round(sum(scores) / len(scores), 1) if scores else 0
                    
                    print(f"User {user['display_name']} - Latest: {latest_score}, Average: {avg_score}")
                    
                    leaderboard_data.append({
                        'user_id': user['id'],
                        'display_name': user['display_name'],
                        'latest_score': int(latest_score),  # Convert to integer for cleaner display
                        'avg_score': avg_score,
                        'is_current_user': user['id'] == session['profile_id'],
                        'num_days': len(scores)  # Track how many days of data we have
                    })
                else:
                    # Add user to leaderboard even if API call fails
                    leaderboard_data.append({
                        'user_id': user['id'],
                        'display_name': user['display_name'],
                        'latest_score': 0,
                        'avg_score': 0,
                        'is_current_user': user['id'] == session['profile_id'],
                        'num_days': 0  # Add num_days field
                    })
                        
            except Exception as e:
                print(f"Error fetching data for user {user['display_name']}: {str(e)}")
                # Add user to leaderboard even if there's an error
                leaderboard_data.append({
                    'user_id': user['id'],
                    'display_name': user['display_name'],
                    'latest_score': 0,
                    'avg_score': 0,
                    'is_current_user': user['id'] == session['profile_id'],
                    'num_days': 0  # Add num_days field
                })
        
        # Sort leaderboard by average score
        leaderboard_data.sort(key=lambda x: x['avg_score'], reverse=True)
        
        # Get current user's sleep data for detailed view
        tokens = supabase.table('oura_tokens').select('*').eq('profile_id', session['profile_id']).execute()
        if not tokens.data:
            return redirect(url_for('login'))
        
        access_token = decrypt_token(tokens.data[0]['access_token_encrypted'])
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        # Get personal info
        personal_info_response = requests.get(
            "https://api.ouraring.com/v2/usercollection/personal_info",
            headers=headers
        )
        personal_info = personal_info_response.json()
        
        # Get sleep data for the last 7 days
        sleep_response = requests.get(
            f"https://api.ouraring.com/v2/usercollection/daily_sleep?start_date={start_date}&end_date={end_date}",
            headers=headers
        )
        sleep_data = sleep_response.json()

        # Get readiness data
        readiness_response = requests.get(
            f"https://api.ouraring.com/v2/usercollection/daily_readiness?start_date={start_date}&end_date={end_date}",
            headers=headers
        )
        readiness_data = readiness_response.json()
        print(f"Readiness data: {json.dumps(readiness_data, indent=2)}")

        return render_template_string('''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Oura Ring Dashboard</title>
                <style>
                    body { font-family: Arial, sans-serif; margin: 20px; }
                    .container { max-width: 1200px; margin: 0 auto; }
                    .card { 
                        border: 1px solid #ddd; 
                        padding: 20px; 
                        margin: 10px 0; 
                        border-radius: 8px;
                        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    }
                    .sleep-grid {
                        display: grid;
                        grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                        gap: 20px;
                    }
                    .metric {
                        margin: 10px 0;
                    }
                    .progress-bar {
                        background-color: #e9ecef;
                        border-radius: 10px;
                        height: 15px;
                        overflow: hidden;
                        margin: 0 10px;
                    }
                    .progress-bar-fill {
                        background-color: #4CAF50;
                        height: 100%;
                        transition: width 0.3s ease;
                    }
                    .readiness-metric {
                        display: flex;
                        align-items: center;
                        margin: 8px 0;
                        padding: 5px;
                        border-radius: 4px;
                        background-color: white;
                    }
                    .readiness-label {
                        width: 160px;
                        font-weight: 500;
                        color: #333;
                    }
                    .readiness-value {
                        margin-left: 10px;
                        min-width: 40px;
                        text-align: right;
                        font-weight: bold;
                    }
                    .metric-group {
                        margin-bottom: 20px;
                        padding: 15px;
                        border-radius: 8px;
                        background-color: #f8f9fa;
                    }
                    h3 { 
                        color: #2c3e50;
                        margin-bottom: 15px;
                        font-size: 1.2em;
                    }
                    .date-header {
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        margin-bottom: 15px;
                        padding-bottom: 10px;
                        border-bottom: 1px solid #eee;
                    }
                    .score-badge {
                        background-color: #4CAF50;
                        color: white;
                        padding: 5px 15px;
                        border-radius: 20px;
                        font-weight: bold;
                        font-size: 0.9em;
                    }
                    .leaderboard {
                        margin-top: 30px;
                    }
                    .leaderboard-table {
                        width: 100%;
                        border-collapse: collapse;
                        margin-top: 10px;
                    }
                    .leaderboard-table th,
                    .leaderboard-table td {
                        padding: 12px;
                        text-align: left;
                        border-bottom: 1px solid #ddd;
                    }
                    .leaderboard-table th {
                        background-color: #f5f5f5;
                        font-weight: bold;
                    }
                    .leaderboard-table tr:hover {
                        background-color: #f9f9f9;
                    }
                    .current-user {
                        background-color: #e8f5e9;
                    }
                    .medal {
                        display: inline-block;
                        width: 20px;
                        height: 20px;
                        border-radius: 50%;
                        margin-right: 5px;
                        text-align: center;
                        color: white;
                        font-weight: bold;
                    }
                    .gold { background-color: #FFD700; }
                    .silver { background-color: #C0C0C0; }
                    .bronze { background-color: #CD7F32; }
                    button {
                        padding: 8px 16px;
                        background-color: #4CAF50;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        cursor: pointer;
                    }
                    button:hover {
                        background-color: #45a049;
                    }
                    .logout {
                        float: right;
                        background-color: #f44336;
                    }
                    .logout:hover {
                        background-color: #da190b;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="card">
                        <a href="{{ url_for('logout') }}" class="logout">Logout</a>
                        <h1>Your Oura Ring Dashboard</h1>
                        <p>Welcome, {{ profile.data[0].display_name }}!</p>
                    </div>

                    <div class="sleep-grid">
                    {% for day in sleep_data.get('data', []) %}
                        <div class="card">
                            <div class="date-header">
                                <h3>{{ day['day'] }}</h3>
                                <span class="score-badge">Score: {{ day.get('score', 0) }}</span>
                            </div>

                            <div class="metric-group">
                                <h3>Sleep Metrics</h3>
                                {% for metric, value in day['contributors'].items() %}
                                <div class="metric">
                                    {{ metric.replace('_', ' ').title() }}: {{ value }}
                                    <div class="progress-bar">
                                        <div class="progress-bar-fill" style="width: {{ value }}%"></div>
                                    </div>
                                </div>
                                {% endfor %}
                            </div>

                            {% for readiness_day in readiness_data.get('data', []) %}
                                {% if readiness_day['day'] == day['day'] %}
                                <div class="metric-group">
                                    <h3>Readiness Metrics</h3>
                                    
                                    <!-- Main Readiness Score -->
                                    <div class="readiness-metric">
                                        <span class="readiness-label">Readiness Score:</span>
                                        <div class="progress-bar" style="flex-grow: 1;">
                                            <div class="progress-bar-fill" style="width: {{ readiness_day.get('score', 0) }}%"></div>
                                        </div>
                                        <span class="readiness-value">{{ readiness_day.get('score', 0) }}</span>
                                    </div>

                                    <!-- Activity Balance -->
                                    <div class="readiness-metric">
                                        <span class="readiness-label">Activity Balance:</span>
                                        <div class="progress-bar" style="flex-grow: 1;">
                                            <div class="progress-bar-fill" style="width: {{ readiness_day.get('contributors', {}).get('activity_balance', 0) }}%"></div>
                                        </div>
                                        <span class="readiness-value">{{ readiness_day.get('contributors', {}).get('activity_balance', 0) }}</span>
                                    </div>

                                    <!-- Body Temperature -->
                                    <div class="readiness-metric">
                                        <span class="readiness-label">Body Temperature:</span>
                                        <div class="progress-bar" style="flex-grow: 1;">
                                            <div class="progress-bar-fill" style="width: {{ readiness_day.get('contributors', {}).get('body_temperature', 0) }}%"></div>
                                        </div>
                                        <span class="readiness-value">{{ readiness_day.get('contributors', {}).get('body_temperature', 0) }}</span>
                                    </div>

                                    <!-- HRV Balance -->
                                    <div class="readiness-metric">
                                        <span class="readiness-label">HRV Balance:</span>
                                        <div class="progress-bar" style="flex-grow: 1;">
                                            <div class="progress-bar-fill" style="width: {{ readiness_day.get('contributors', {}).get('hrv_balance', 0) }}%"></div>
                                        </div>
                                        <span class="readiness-value">{{ readiness_day.get('contributors', {}).get('hrv_balance', 0) }}</span>
                                    </div>

                                    <!-- Previous Day Activity -->
                                    <div class="readiness-metric">
                                        <span class="readiness-label">Previous Day Activity:</span>
                                        <div class="progress-bar" style="flex-grow: 1;">
                                            <div class="progress-bar-fill" style="width: {{ readiness_day.get('contributors', {}).get('previous_day_activity', 0) }}%"></div>
                                        </div>
                                        <span class="readiness-value">{{ readiness_day.get('contributors', {}).get('previous_day_activity', 0) }}</span>
                                    </div>

                                    <!-- Previous Night -->
                                    <div class="readiness-metric">
                                        <span class="readiness-label">Previous Night:</span>
                                        <div class="progress-bar" style="flex-grow: 1;">
                                            <div class="progress-bar-fill" style="width: {{ readiness_day.get('contributors', {}).get('previous_night', 0) }}%"></div>
                                        </div>
                                        <span class="readiness-value">{{ readiness_day.get('contributors', {}).get('previous_night', 0) }}</span>
                                    </div>

                                    <!-- Recovery Index -->
                                    <div class="readiness-metric">
                                        <span class="readiness-label">Recovery Index:</span>
                                        <div class="progress-bar" style="flex-grow: 1;">
                                            <div class="progress-bar-fill" style="width: {{ readiness_day.get('contributors', {}).get('recovery_index', 0) }}%"></div>
                                        </div>
                                        <span class="readiness-value">{{ readiness_day.get('contributors', {}).get('recovery_index', 0) }}</span>
                                    </div>

                                    <!-- Resting Heart Rate -->
                                    <div class="readiness-metric">
                                        <span class="readiness-label">Resting Heart Rate:</span>
                                        <div class="progress-bar" style="flex-grow: 1;">
                                            <div class="progress-bar-fill" style="width: {{ readiness_day.get('contributors', {}).get('resting_heart_rate', 0) }}%"></div>
                                        </div>
                                        <span class="readiness-value">{{ readiness_day.get('contributors', {}).get('resting_heart_rate', 0) }}</span>
                                    </div>

                                    <!-- Sleep Balance -->
                                    <div class="readiness-metric">
                                        <span class="readiness-label">Sleep Balance:</span>
                                        <div class="progress-bar" style="flex-grow: 1;">
                                            <div class="progress-bar-fill" style="width: {{ readiness_day.get('contributors', {}).get('sleep_balance', 0) }}%"></div>
                                        </div>
                                        <span class="readiness-value">{{ readiness_day.get('contributors', {}).get('sleep_balance', 0) }}</span>
                                    </div>
                                </div>
                                {% endif %}
                            {% endfor %}
                        </div>
                    {% endfor %}
                    </div>

                    <div class="card leaderboard">
                        <h2>Global Sleep Score Leaderboard</h2>
                        <p>See how your sleep compares with others!</p>
                        <table class="leaderboard-table">
                            <thead>
                                <tr>
                                    <th>Rank</th>
                                    <th>User</th>
                                    <th>Latest Sleep Score</th>
                                    <th>7-Day Average</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for user in leaderboard_data %}
                                <tr {% if user.is_current_user %}class="current-user"{% endif %}>
                                    <td>
                                        {% if loop.index == 1 %}
                                        <span class="medal gold">1</span>
                                        {% elif loop.index == 2 %}
                                        <span class="medal silver">2</span>
                                        {% elif loop.index == 3 %}
                                        <span class="medal bronze">3</span>
                                        {% else %}
                                        {{ loop.index }}
                                        {% endif %}
                                    </td>
                                    <td>
                                        <a href="/user/{{ user.user_id }}" style="text-decoration: underline; color: #2563eb;">
                                            {{ user.display_name }}
                                        </a>
                                    </td>
                                    <td>{{ user.latest_score }}</td>
                                    <td>
                                        {{ user.avg_score }}
                                        {% if user.num_days > 0 %}
                                        <small style="color: #666">({{ user.num_days }} days)</small>
                                        {% else %}
                                        <small style="color: #999">(no data)</small>
                                        {% endif %}
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
            </body>
            </html>
        ''', profile=profile, personal_info=personal_info, sleep_data=sleep_data, leaderboard_data=leaderboard_data, readiness_data=readiness_data)
        
    except Exception as e:
        print(f"Error in dashboard: {str(e)}")
        print(traceback.format_exc())
        return f'Error in dashboard: {str(e)}', 400

@app.route('/add_friend', methods=['POST'])
@login_required
def add_friend():
    """Add a friend connection."""
    friend_email = request.form.get('friend_email')
    if not friend_email:
        return 'Email is required', 400
    
    try:
        # Find friend by email
        friend = supabase.table('profiles').select('*').eq('email', friend_email).execute()
        if not friend.data:
            return 'Friend not found. They need to connect their Oura Ring first!', 404
        
        friend_id = friend.data[0]['id']
        
        # Check if friendship already exists
        existing = supabase.table('friendships').select('*')\
            .eq('user_id', session['profile_id'])\
            .eq('friend_id', friend_id)\
            .execute()
            
        if existing.data:
            return 'Already friends with this user', 400
        
        # Create friendship
        supabase.table('friendships').insert({
            'user_id': session['profile_id'],
            'friend_id': friend_id,
            'created_at': datetime.now().isoformat()
        }).execute()
        
        return redirect(url_for('dashboard'))
    except Exception as e:
        print(f"Error adding friend: {str(e)}")
        print(traceback.format_exc())
        return f'Error adding friend: {str(e)}', 400

@app.route('/logout')
def logout():
    """Clear session and logout."""
    session.clear()
    return redirect(url_for('index'))

@app.route('/check_tables')
def check_tables():
    """Check what tables exist in Supabase."""
    try:
        # List all tables
        tables = supabase.table('profiles').select('*').execute()
        return f'Tables exist and can be queried: {tables.data}'
    except Exception as e:
        return f'Error checking tables: {str(e)}'

@app.route('/user/<user_id>')
@login_required
def user_profile(user_id):
    """Get a user's profile data including sleep and readiness metrics."""
    try:
        # Get user's profile
        profile = supabase.table('profiles').select('*').eq('id', user_id).execute()
        if not profile.data:
            return 'User not found', 404

        # Get user's tokens
        tokens = supabase.table('oura_tokens').select('*').eq('profile_id', user_id).execute()
        if not tokens.data:
            return {
                'display_name': profile.data[0]['display_name'],
                'sleep_data': [],
                'readiness_data': []
            }

        # Calculate date range for last 7 days
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

        # Get access token
        access_token = decrypt_token(tokens.data[0]['access_token_encrypted'])
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        # Get sleep data
        sleep_response = requests.get(
            f"https://api.ouraring.com/v2/usercollection/daily_sleep?start_date={start_date}&end_date={end_date}",
            headers=headers
        )
        
        sleep_data = []
        if sleep_response.status_code == 200:
            sleep_data = sleep_response.json().get('data', [])
        
        # Get readiness data
        readiness_response = requests.get(
            f"https://api.ouraring.com/v2/usercollection/daily_readiness?start_date={start_date}&end_date={end_date}",
            headers=headers
        )
        
        readiness_data = []
        if readiness_response.status_code == 200:
            readiness_data = readiness_response.json().get('data', [])
        
        return {
            'display_name': profile.data[0]['display_name'],
            'sleep_data': sleep_data,
            'readiness_data': readiness_data
        }
        
    except Exception as e:
        print(f"Error in user profile: {str(e)}")
        print(traceback.format_exc())
        return f'Error fetching user profile: {str(e)}', 400

@app.route('/user/<path:path>')
def serve_react(path):
    """Serve React app for user profile routes."""
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            <title>Sleepy Panda Tracker</title>
        </head>
        <body>
            <div id="root"></div>
            <script type="module" src="/src/main.tsx"></script>
        </body>
        </html>
    ''')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True) 