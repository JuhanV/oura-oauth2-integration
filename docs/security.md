# Security Considerations

## Overview

This document outlines the security measures implemented in the Oura Ring Data Comparison application. Security is a critical aspect of our application as we handle sensitive user data and OAuth tokens.

## Key Security Measures

### 1. Token Security

#### Encryption at Rest
- All OAuth tokens are encrypted using Fernet (symmetric encryption)
- Encryption key is stored securely in environment variables
- Tokens are never logged or exposed in plaintext

Example token encryption:
```python
from cryptography.fernet import Fernet

def encrypt_token(token: str, key: bytes) -> str:
    f = Fernet(key)
    return f.encrypt(token.encode()).decode()

def decrypt_token(encrypted_token: str, key: bytes) -> str:
    f = Fernet(key)
    return f.decrypt(encrypted_token.encode()).decode()
```

### 2. Database Security

#### Row Level Security (RLS)
```sql
-- Example RLS policy for profiles table
alter table profiles enable row level security;

create policy "Users can only access their own profile"
    on profiles for all
    using (id = auth.uid());

-- Example RLS policy for oura_tokens table
alter table oura_tokens enable row level security;

create policy "Users can only access their own tokens"
    on oura_tokens for all
    using (profile_id = auth.uid());
```

#### Access Control
- Service role key used only in backend
- Public access restricted through RLS
- Prepared statements for all SQL queries
- Input validation and sanitization

### 3. Authentication & Authorization

#### Session Security
- Secure session configuration
- CSRF protection
- Session timeout
- Secure cookie settings

Example Flask configuration:
```python
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=24)
)
```

#### OAuth2 Security
- State parameter validation
- PKCE implementation (optional)
- Secure token storage
- Automatic token refresh

### 4. API Security

#### Request Validation
- Input sanitization
- Parameter validation
- Rate limiting
- Error handling

Example rate limiting:
```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)
```

#### HTTPS
- HTTPS required in production
- HSTS headers
- Secure redirect URIs
- Certificate management

### 5. Environment Security

#### Environment Variables
- Separate .env files for development/production
- Secure secret management
- No secrets in code or version control
- Regular key rotation

Example .env structure:
```env
# Production only - never commit
FLASK_ENV=production
FLASK_SECRET_KEY=<strong-random-key>
ENCRYPTION_KEY=<fernet-key>
SUPABASE_SERVICE_KEY=<service-key>

# Can be public
FLASK_APP=app.py
SUPABASE_URL=<url>
OURA_CLIENT_ID=<client-id>
```

### 6. Data Privacy

#### User Data Protection
- Minimal data collection
- Clear privacy policy
- Data encryption
- Secure data deletion

#### Friend System Privacy
- Explicit consent required
- Granular sharing controls
- Privacy-preserving comparisons
- Data anonymization options

## Security Best Practices

### 1. Development Practices

- Regular security updates
- Dependency scanning
- Code review process
- Security testing

### 2. Deployment Security

- Secure deployment process
- Environment separation
- Access control
- Monitoring and logging

### 3. Incident Response

#### Response Plan
1. Identify and isolate
2. Assess impact
3. Notify affected users
4. Fix vulnerability
5. Post-mortem analysis

#### Security Monitoring
- Error tracking
- Access logging
- Rate limit monitoring
- Security alerts

## Security Checklist

### Pre-deployment
- [ ] All secrets properly configured
- [ ] HTTPS enabled
- [ ] RLS policies tested
- [ ] Rate limits configured
- [ ] Error handling tested
- [ ] Session security configured
- [ ] Input validation implemented
- [ ] Token encryption tested
- [ ] Logging configured
- [ ] Monitoring setup

### Regular Maintenance
- [ ] Update dependencies
- [ ] Rotate secrets
- [ ] Review access logs
- [ ] Check rate limits
- [ ] Test backup/restore
- [ ] Review security policies
- [ ] Update documentation

## Reporting Security Issues

If you discover a security vulnerability:

1. DO NOT create a public issue
2. Email security@yourdomain.com
3. Include detailed information
4. Await confirmation before disclosure

## Additional Resources

- [Flask Security Guide](https://flask.palletsprojects.com/en/2.0.x/security/)
- [Supabase Security](https://supabase.io/docs/guides/auth/row-level-security)
- [OAuth 2.0 Security](https://oauth.net/2/security-considerations/)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/) 