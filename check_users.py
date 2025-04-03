from supabase import create_client
import os
from dotenv import load_dotenv
import json
import requests
from datetime import datetime, timedelta
import time

load_dotenv()

supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

def clear_invalid_token(supabase, profile_id):
    print(f"\nAttempting to delete token for profile {profile_id}")
    try:
        # Try direct deletion first (should work with new policy)
        result = supabase.table('oura_tokens')\
            .delete()\
            .eq('profile_id', profile_id)\
            .execute()
        print(f"Direct delete result: {result}")
        
        # Verify deletion
        check = supabase.table('oura_tokens').select('*').eq('profile_id', profile_id).execute()
        print(f"Verification check result: {check}")
        
        if len(check.data) > 0:
            print(f"Warning: Token still exists for profile {profile_id}")
            # Try function call as fallback
            try:
                result = supabase.rpc('delete_token', {'target_profile_id': profile_id}).execute()
                print(f"Function delete result: {result}")
                
                # Final verification
                check = supabase.table('oura_tokens').select('*').eq('profile_id', profile_id).execute()
                if len(check.data) > 0:
                    print(f"Error: Unable to delete token for profile {profile_id}")
                else:
                    print(f"Success: Token deleted for profile {profile_id}")
            except Exception as e:
                print(f"Error calling delete function: {str(e)}")
        else:
            print(f"Success: Token deleted for profile {profile_id}")
    except Exception as e:
        print(f"Error deleting token: {str(e)}")

def decrypt_token(token_encrypted):
    # Get the token directly as it's already decrypted by Supabase RLS
    return token_encrypted

def refresh_oura_token(refresh_token, profile_id):
    try:
        # Make request to Oura API to refresh token
        response = requests.post(
            'https://api.ouraring.com/oauth/token',
            data={
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
                'client_id': os.getenv('OURA_CLIENT_ID'),
                'client_secret': os.getenv('OURA_CLIENT_SECRET')
            }
        )
        
        if response.status_code == 200:
            token_data = response.json()
            # Calculate new expiry time (current time + expires_in seconds)
            expires_at = (datetime.now() + timedelta(seconds=token_data['expires_in'])).isoformat()
            
            # Update token in database
            supabase.table('oura_tokens').update({
                'access_token_encrypted': token_data['access_token'],
                'refresh_token_encrypted': token_data['refresh_token'],
                'expires_at': expires_at
            }).eq('profile_id', profile_id).execute()
            
            print(f"Successfully refreshed token for profile {profile_id}")
            return token_data['access_token']
        else:
            print(f"Failed to refresh token: {response.text}")
            if 'invalid_grant' in response.text:
                # Token is invalid, clear it from database
                clear_invalid_token(supabase, profile_id)
            return None
    except Exception as e:
        print(f"Error refreshing token: {str(e)}")
        return None

def get_user_data():
    # Get fresh data with a direct query
    result = supabase.table('profiles').select('*, oura_tokens(*)').execute()
    
    # Process the data to handle the oura_tokens array
    for profile in result.data:
        if profile.get('oura_tokens'):
            if isinstance(profile['oura_tokens'], list):
                profile['oura_tokens'] = profile['oura_tokens'][0] if profile['oura_tokens'] else None
    
    return result

# Get all profiles with their tokens
profiles_with_tokens = get_user_data()

print("\nAll Users Data:")
print("-" * 80)

# Calculate date range for last 7 days
end_date = datetime.now().strftime('%Y-%m-%d')
start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

for profile in profiles_with_tokens.data:
    print(f"\nUser Details:")
    print(f"  Display Name: {profile['display_name']}")
    print(f"  User ID: {profile['id']}")
    print(f"  Oura User ID: {profile['oura_user_id']}")
    print(f"  Created At: {profile['created_at']}")
    print(f"  Email: {profile['email']}")
    
    token_data = profile.get('oura_tokens')
    if isinstance(token_data, list):
        token_data = token_data[0] if token_data else None
    
    if token_data:
        print("\nOura Token Details:")
        print(f"  Token ID: {token_data['id']}")
        print(f"  Expires At: {token_data['expires_at']}")
        print(f"  Scopes: {token_data['scopes'] or 'No scopes specified'}")
        print(f"  Access Token: {token_data['access_token_encrypted'][:50]}...")
        print(f"  Refresh Token: {token_data['refresh_token_encrypted'][:50]}...")
        
        token = decrypt_token(token_data['access_token_encrypted'])
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        try:
            # Get sleep data
            sleep_response = requests.get(
                f"https://api.ouraring.com/v2/usercollection/daily_sleep?start_date={start_date}&end_date={end_date}",
                headers=headers
            )
            
            print(f"\nSleep API Response Status: {sleep_response.status_code}")
            if sleep_response.status_code == 401:
                print("Token expired, attempting to refresh...")
                refresh_token = decrypt_token(token_data['refresh_token_encrypted'])
                new_token = refresh_oura_token(refresh_token, profile['id'])
                if new_token:
                    headers['Authorization'] = f'Bearer {new_token}'
                    # Retry the request with new token
                    sleep_response = requests.get(
                        f"https://api.ouraring.com/v2/usercollection/daily_sleep?start_date={start_date}&end_date={end_date}",
                        headers=headers
                    )
                else:
                    # Clear the token immediately if refresh failed
                    clear_invalid_token(supabase, profile['id'])
                    print("Token refresh failed - users will need to reconnect their Oura Ring")
                    continue  # Skip to next user since this token is invalid
            
            if sleep_response.status_code != 200:
                print(f"Sleep API Error: {sleep_response.text}")
            
            if sleep_response.status_code == 200:
                sleep_data = sleep_response.json()
                print("\nSleep Scores (last 7 days):")
                for day in sleep_data.get('data', []):
                    print(f"  {day['day']}: {day.get('score', 'No score')}")
                    print("  Contributors:")
                    for metric, value in day.get('contributors', {}).items():
                        print(f"    {metric}: {value}")
            
            # Get readiness data with the potentially refreshed token
            readiness_response = requests.get(
                f"https://api.ouraring.com/v2/usercollection/daily_readiness?start_date={start_date}&end_date={end_date}",
                headers=headers
            )
            
            print(f"\nReadiness API Response Status: {readiness_response.status_code}")
            if readiness_response.status_code != 200:
                print(f"Readiness API Error: {readiness_response.text}")
            
            if readiness_response.status_code == 200:
                readiness_data = readiness_response.json()
                print("\nReadiness Scores (last 7 days):")
                for day in readiness_data.get('data', []):
                    print(f"  {day['day']}: {day.get('score', 'No score')}")
                    print("  Contributors:")
                    for metric, value in day.get('contributors', {}).items():
                        print(f"    {metric}: {value}")
        except Exception as e:
            print(f"Error fetching data: {str(e)}")
    else:
        print("\nNo Oura Ring connected")
    
    print("-" * 80)

# Get updated user data after all operations
print("\nFinal User Status:")
print("-" * 80)

# Get fresh data
final_profiles = get_user_data()
for profile in final_profiles.data:
    print(f"\nUser: {profile['display_name']}")
    token_data = profile.get('oura_tokens')
    if isinstance(token_data, list):
        token_data = token_data[0] if token_data else None
    if token_data:
        print("  Status: Has Oura Ring token (needs reconnection)")
    else:
        print("  Status: No Oura Ring connected") 