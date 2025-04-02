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

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')

# OAuth2 Configuration
client_id = os.getenv('OURA_CLIENT_ID')
client_secret = os.getenv('OURA_CLIENT_SECRET')
redirect_uri = os.getenv('OURA_REDIRECT_URI')

# Supabase Configuration
supabase: Client = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    """Home page with login link."""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return '''
        <h1>Oura Ring Data Viewer</h1>
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
        
        # Store user and tokens in Supabase
        user_data = {
            'oura_user_id': user_info.get('id'),
            'email': user_info.get('email'),
            'access_token': token_dict['access_token'],
            'refresh_token': token_dict.get('refresh_token'),
            'created_at': datetime.now().isoformat()
        }
        
        # Check if user exists
        existing_user = supabase.table('users').select('*').eq('oura_user_id', user_info.get('id')).execute()
        
        if existing_user.data:
            # Update existing user
            supabase.table('users').update(user_data).eq('oura_user_id', user_info.get('id')).execute()
            user_id = existing_user.data[0]['id']
        else:
            # Create new user
            result = supabase.table('users').insert(user_data).execute()
            user_id = result.data[0]['id']
        
        # Store user_id in session
        session['user_id'] = user_id
        session['oura_user_id'] = user_info.get('id')
        
        return redirect(url_for('dashboard'))
    except Exception as e:
        print(f"Error during callback: {str(e)}")
        print(traceback.format_exc())
        return f'Error during callback: {str(e)}', 400

@app.route('/dashboard')
@login_required
def dashboard():
    """Display user's Oura Ring data and friend connections."""
    try:
        # Get user's tokens from Supabase
        user = supabase.table('users').select('*').eq('id', session['user_id']).execute()
        if not user.data:
            return redirect(url_for('login'))
        
        access_token = user.data[0]['access_token']
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
        
        # Get friend connections - Specify the foreign key relationship
        friends = supabase.table('friendships').select('*, friend:users!friendships_friend_id_fkey(*)').eq('user_id', session['user_id']).execute()
        
        return render_template_string('''
            <h1>Welcome to Your Oura Ring Dashboard</h1>
            <p>Successfully connected to Oura API!</p>
            
            <h2>Personal Info</h2>
            <pre>{{ personal_info | tojson(indent=2) }}</pre>
            
            <h2>Sleep Data (Last 7 Days)</h2>
            <pre>{{ sleep_data | tojson(indent=2) }}</pre>
            
            <h2>Friend Connections</h2>
            {% if friends.data %}
                <ul>
                {% for friendship in friends.data %}
                    <li>{{ friendship.friend.email }}</li>
                {% endfor %}
                </ul>
            {% else %}
                <p>No friends connected yet.</p>
            {% endif %}
            
            <form action="{{ url_for('add_friend') }}" method="post">
                <input type="email" name="friend_email" placeholder="Friend's email" required>
                <button type="submit">Add Friend</button>
            </form>
            
            <a href="{{ url_for('logout') }}">Logout</a>
        ''', personal_info=personal_info, sleep_data=sleep_data, friends=friends)
        
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
        friend = supabase.table('users').select('*').eq('email', friend_email).execute()
        if not friend.data:
            return 'Friend not found', 404
        
        friend_id = friend.data[0]['id']
        
        # Check if friendship already exists
        existing = supabase.table('friendships').select('*').eq('user_id', session['user_id']).eq('friend_id', friend_id).execute()
        if existing.data:
            return 'Already friends with this user', 400
        
        # Create friendship
        supabase.table('friendships').insert({
            'user_id': session['user_id'],
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True) 