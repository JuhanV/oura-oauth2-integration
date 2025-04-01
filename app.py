from flask import Flask, redirect, request, session, url_for
from oura import OuraOAuth2Client
from dotenv import load_dotenv
import os
import traceback
import requests
import json
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')

# OAuth2 Configuration
client_id = os.getenv('OURA_CLIENT_ID')
client_secret = os.getenv('OURA_CLIENT_SECRET')
redirect_uri = os.getenv('OURA_REDIRECT_URI')

@app.route('/')
def index():
    """Home page with login link."""
    return '''
        <h1>Oura Ring Data Viewer</h1>
        <a href="/login">Connect to Oura Ring</a>
    '''

@app.route('/login')
def login():
    """Initiate OAuth2 flow."""
    auth_client = OuraOAuth2Client(client_id=client_id, client_secret=client_secret)
    
    # Get the authorization URL - this returns a tuple, we need the first item
    auth_endpoint_result = auth_client.authorize_endpoint(
        redirect_uri=redirect_uri,
        scope=["personal", "daily", "heartrate", "workout", "session", "sleep"]
    )
    
    # The result might be a tuple or just a string, handle both cases
    if isinstance(auth_endpoint_result, tuple):
        auth_url = auth_endpoint_result[0]
    else:
        auth_url = auth_endpoint_result
        
    # Print for debugging
    print(f"Auth URL: {auth_url}")
    
    return redirect(auth_url)

@app.route('/callback')
def callback():
    """Handle OAuth2 callback and token exchange."""
    # Get the authorization code from the callback
    code = request.args.get('code')
    if not code:
        return 'Error: No authorization code received', 400

    try:
        # Use direct HTTP request to exchange the code for tokens
        token_url = "https://api.ouraring.com/oauth/token"
        
        payload = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri,
            'client_id': client_id,
            'client_secret': client_secret
        }
        
        response = requests.post(token_url, data=payload)
        
        # Check if the request was successful
        if response.status_code != 200:
            print(f"Error response: {response.status_code}, {response.text}")
            return f'Error during token exchange: {response.text}', 400
        
        # Parse the token response
        token_dict = response.json()
        
        # Store tokens in session
        session['access_token'] = token_dict['access_token']
        session['refresh_token'] = token_dict.get('refresh_token')  # Not all responses include refresh tokens
        
        return redirect(url_for('dashboard'))
    except Exception as e:
        # Print detailed error for debugging
        print(f"Error during token exchange: {str(e)}")
        print(traceback.format_exc())
        return f'Error during token exchange: {str(e)}', 400

@app.route('/dashboard')
def dashboard():
    """Display user's Oura Ring data."""
    if 'access_token' not in session:
        return redirect(url_for('login'))
    
    try:
        # Use direct API calls with the access token
        access_token = session['access_token']
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        # Get personal info
        personal_info_url = "https://api.ouraring.com/v2/usercollection/personal_info"
        personal_info_response = requests.get(personal_info_url, headers=headers)
        
        if personal_info_response.status_code != 200:
            raise Exception(f"Failed to fetch personal info: {personal_info_response.text}")
        
        personal_info = personal_info_response.json()
        
        # Get daily sleep data for the last 7 days
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        sleep_url = f"https://api.ouraring.com/v2/usercollection/daily_sleep?start_date={start_date}&end_date={end_date}"
        sleep_response = requests.get(sleep_url, headers=headers)
        
        if sleep_response.status_code != 200:
            raise Exception(f"Failed to fetch sleep data: {sleep_response.text}")
        
        sleep_data = sleep_response.json()
        
        return f'''
            <h1>Welcome to Your Oura Ring Dashboard</h1>
            <p>Successfully connected to Oura API!</p>
            
            <h2>Personal Info</h2>
            <pre>{json.dumps(personal_info, indent=2)}</pre>
            
            <h2>Sleep Data (Last 7 Days)</h2>
            <pre>{json.dumps(sleep_data, indent=2)}</pre>
            
            <a href="/logout">Logout</a>
        '''
    except Exception as e:
        print(f"Error fetching data: {str(e)}")
        print(traceback.format_exc())
        return f'Error fetching data: {str(e)}', 400

def save_tokens(token_dict):
    """Callback to save refreshed tokens."""
    session['access_token'] = token_dict['access_token']
    session['refresh_token'] = token_dict['refresh_token']

@app.route('/logout')
def logout():
    """Clear session and logout."""
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True) 