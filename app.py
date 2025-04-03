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
        # Get user's profile and tokens
        profile = supabase.table('profiles').select('*').eq('id', session['profile_id']).execute()
        if not profile.data:
            return redirect(url_for('login'))
        
        tokens = supabase.table('oura_tokens').select('*').eq('profile_id', session['profile_id']).execute()
        if not tokens.data:
            return redirect(url_for('login'))
        
        # Decrypt access token
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
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        sleep_response = requests.get(
            f"https://api.ouraring.com/v2/usercollection/daily_sleep?start_date={start_date}&end_date={end_date}",
            headers=headers
        )
        sleep_data = sleep_response.json()
        
        # Get all users for the leaderboard
        all_users = supabase.table('profiles').select('*').execute()
        
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
                        background-color: #f0f0f0;
                        border-radius: 10px;
                        height: 20px;
                        overflow: hidden;
                    }
                    .progress-bar-fill {
                        background-color: #4CAF50;
                        height: 100%;
                        transition: width 0.3s ease;
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

                    <div class="card">
                        <h2>Your Sleep Scores (Last 7 Days)</h2>
                        <div class="sleep-grid">
                            {% for day in sleep_data.get('data', []) %}
                            <div class="card">
                                <h3>{{ day['day'] }}</h3>
                                <div class="metric">
                                    <strong>Overall Sleep Score: {{ day['score'] }}</strong>
                                    <div class="progress-bar">
                                        <div class="progress-bar-fill" style="width: {{ day['score'] }}%"></div>
                                    </div>
                                </div>
                                {% for metric, value in day['contributors'].items() %}
                                <div class="metric">
                                    {{ metric.replace('_', ' ').title() }}: {{ value }}
                                    <div class="progress-bar">
                                        <div class="progress-bar-fill" style="width: {{ value }}%"></div>
                                    </div>
                                </div>
                                {% endfor %}
                            </div>
                            {% endfor %}
                        </div>
                    </div>

                    <div class="card leaderboard">
                        <h2>Global Leaderboard</h2>
                        <p>See how your sleep compares with others!</p>
                        <table class="leaderboard-table">
                            <thead>
                                <tr>
                                    <th>Rank</th>
                                    <th>User</th>
                                    <th>Latest Sleep Score</th>
                                    <th>Average Sleep Score (7 days)</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for user in all_users.data %}
                                <tr {% if user.id == profile.data[0].id %}class="current-user"{% endif %}>
                                    <td>{{ loop.index }}</td>
                                    <td>{{ user.display_name }}</td>
                                    <td>Coming soon</td>
                                    <td>Coming soon</td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
            </body>
            </html>
        ''', profile=profile, personal_info=personal_info, sleep_data=sleep_data, all_users=all_users)
        
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True) 