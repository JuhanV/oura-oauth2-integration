# Setup Guide

## Prerequisites

- Python 3.7+
- Pip (Python package installer)
- Git
- A Supabase Account (supabase.com)
- An Oura Ring Account and Developer Access

## Detailed Setup Steps

### 1. Python Environment Setup

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Supabase Setup

1. Create a new project at [Supabase](https://supabase.com)
2. Note down your Project URL and service_role key from Project Settings -> API
3. Create the required database tables:

#### profiles Table
```sql
create table profiles (
    id uuid primary key default uuid_generate_v4(),
    created_at timestamp with time zone default now(),
    oura_user_id text unique not null,
    email text unique
);

-- Add index for oura_user_id
create index idx_profiles_oura_user_id on profiles(oura_user_id);
```

#### oura_tokens Table
```sql
create table oura_tokens (
    id bigint primary key generated always as identity,
    profile_id uuid references profiles(id) unique not null,
    access_token_encrypted text not null,
    refresh_token_encrypted text,
    expires_at timestamp with time zone not null,
    scopes text
);

-- Add index for profile_id
create index idx_oura_tokens_profile_id on oura_tokens(profile_id);
```

#### friendships Table
```sql
create table friendships (
    user_id uuid references profiles(id),
    friend_id uuid references profiles(id),
    created_at timestamp with time zone default now(),
    primary key (user_id, friend_id)
);
```

### 3. Oura Developer Setup

1. Go to [Oura Cloud API](https://cloud.ouraring.com/)
2. Create a new application
3. Set your redirect URI (e.g., `http://localhost:5000/callback` for local development)
4. Note down your Client ID and Client Secret
5. Enable required scopes:
   - personal
   - daily
   - sleep
   - email (optional)

### 4. Environment Variables

Create a `.env` file in the project root:

```env
# Flask Configuration
FLASK_APP=app.py
FLASK_ENV=development
FLASK_SECRET_KEY=your_strong_random_secret_key_for_sessions

# Oura API Credentials
OURA_CLIENT_ID=your_oura_client_id
OURA_CLIENT_SECRET=your_oura_client_secret
OURA_REDIRECT_URI=http://localhost:5000/callback

# Supabase Credentials
SUPABASE_URL=your_supabase_project_url
SUPABASE_SERVICE_KEY=your_supabase_service_role_key

# Encryption Key
ENCRYPTION_KEY=your_secure_base64_encoded_encryption_key
```

To generate a secure encryption key:

```python
from cryptography.fernet import Fernet
key = Fernet.generate_key()
print(key.decode())
```

### 5. Running the Application

```bash
flask run
```

The application will be available at `http://localhost:5000`

## Production Deployment

For production deployment:

1. Set `FLASK_ENV=production`
2. Use a proper WSGI server (e.g., Gunicorn)
3. Enable HTTPS
4. Set appropriate Oura redirect URIs
5. Use secure session configuration
6. Implement proper logging
7. Set up monitoring

## Troubleshooting

### Common Issues

1. **Database Connection Errors**
   - Check Supabase credentials
   - Verify network connectivity
   - Check if tables are created correctly

2. **OAuth Errors**
   - Verify Oura credentials
   - Check redirect URI matches exactly
   - Ensure all required scopes are enabled

3. **Token Encryption Issues**
   - Verify ENCRYPTION_KEY is valid base64
   - Check if key is consistent across restarts
   - Ensure key is 32 bytes when decoded

For more issues, check the [Issues](https://github.com/your-repo/issues) page. 