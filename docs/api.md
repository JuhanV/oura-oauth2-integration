# API Documentation

## Overview

This document describes the API endpoints available in the Oura Ring Data Comparison application. The API is built using Flask and integrates with the Oura Cloud API v2.

## Base URLs

- Local Development: `http://localhost:5000`
- Production: `https://your-domain.com`

## Authentication

Most endpoints require authentication via Flask session cookies. Users must first authenticate through the Oura OAuth2 flow.

## Endpoints

### Authentication

#### GET /login
Initiates the Oura OAuth2 flow.

**Response:**
- Redirects to Oura authorization page

#### GET /callback
Handles the OAuth2 callback from Oura.

**Query Parameters:**
- `code`: OAuth authorization code
- `state`: State parameter for security

**Response:**
- Success: Redirects to dashboard
- Error: Redirects to error page with message

### User Data

#### GET /dashboard
Displays the main dashboard with user's data.

**Response:**
```json
{
    "user_info": {
        "id": "uuid",
        "oura_user_id": "string",
        "email": "string"
    },
    "sleep_data": {
        "score": "number",
        "duration": "number",
        "efficiency": "number",
        "deep_sleep": "number",
        "rem_sleep": "number",
        "light_sleep": "number"
    },
    "readiness_data": {
        "score": "number",
        "temperature": "number",
        "hrv": "number"
    }
}
```

### Friend Management

#### GET /api/friends
Lists user's friends.

**Response:**
```json
{
    "friends": [
        {
            "id": "uuid",
            "oura_user_id": "string",
            "created_at": "timestamp"
        }
    ]
}
```

#### POST /api/friends/add
Sends a friend request.

**Request Body:**
```json
{
    "friend_id": "uuid"
}
```

**Response:**
```json
{
    "status": "success",
    "message": "Friend request sent"
}
```

### Data Comparison

#### GET /api/compare/{friend_id}
Compares data with a friend.

**Parameters:**
- `friend_id`: UUID of friend to compare with

**Query Parameters:**
- `metric`: Type of data to compare (sleep, readiness, activity)
- `timeframe`: Time period for comparison (day, week, month)

**Response:**
```json
{
    "user_data": {
        "sleep_scores": [
            {
                "date": "string",
                "score": "number"
            }
        ]
    },
    "friend_data": {
        "sleep_scores": [
            {
                "date": "string",
                "score": "number"
            }
        ]
    }
}
```

## Error Handling

### Error Responses

All error responses follow this format:
```json
{
    "error": {
        "code": "string",
        "message": "string",
        "details": {}
    }
}
```

### Common Error Codes

- `401`: Unauthorized
- `403`: Forbidden
- `404`: Not Found
- `429`: Too Many Requests
- `500`: Internal Server Error

## Rate Limiting

- 200 requests per day per user
- 50 requests per hour per user
- Applies to all API endpoints except authentication

## Example Usage

### Python

```python
import requests

# Login flow (browser-based)
# After authentication, use session cookie for requests

# Get dashboard data
response = requests.get(
    'http://localhost:5000/dashboard',
    cookies=session_cookie
)

# Add friend
response = requests.post(
    'http://localhost:5000/api/friends/add',
    json={'friend_id': 'uuid'},
    cookies=session_cookie
)

# Compare with friend
response = requests.get(
    'http://localhost:5000/api/compare/friend-uuid',
    params={
        'metric': 'sleep',
        'timeframe': 'week'
    },
    cookies=session_cookie
)
```

### JavaScript

```javascript
// Get dashboard data
fetch('/dashboard', {
    credentials: 'include'
})
.then(response => response.json())
.then(data => console.log(data));

// Add friend
fetch('/api/friends/add', {
    method: 'POST',
    credentials: 'include',
    headers: {
        'Content-Type': 'application/json'
    },
    body: JSON.stringify({
        friend_id: 'uuid'
    })
})
.then(response => response.json())
.then(data => console.log(data));
```

## Webhook Support (Future)

Planned webhook support for:
- Friend request notifications
- Data sync completion
- Achievement notifications

## API Versioning

Current version: v1

Version is specified in the URL path:
```
/api/v1/endpoint
```

## Development Guidelines

1. **Error Handling**
   - Always return appropriate HTTP status codes
   - Include detailed error messages
   - Log all errors server-side

2. **Security**
   - Validate all input
   - Sanitize all output
   - Use HTTPS in production
   - Implement rate limiting

3. **Performance**
   - Cache frequently accessed data
   - Use database indexes
   - Implement pagination
   - Optimize queries

## Testing

Example test cases using pytest:

```python
def test_dashboard_authenticated(client, auth):
    auth.login()
    response = client.get('/dashboard')
    assert response.status_code == 200
    assert b'sleep_data' in response.data

def test_friend_request(client, auth):
    auth.login()
    response = client.post('/api/friends/add', 
                          json={'friend_id': 'test-uuid'})
    assert response.status_code == 200
    assert response.json['status'] == 'success'
``` 