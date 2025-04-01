# Oura OAuth2 Integration

A Flask web application that demonstrates OAuth2 authentication with the Oura Ring API. This application allows users to connect their Oura Ring account and view their personal information and sleep data.

## Features

- OAuth2 authentication with Oura API
- Fetch and display personal information
- Fetch and display sleep data for the last 7 days
- Simple web interface
- Session management for tokens

## Prerequisites

- Python 3.7+
- An Oura Developer Account
- Oura API Client ID and Client Secret

## Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd oura-oauth2
```

2. Create and activate a virtual environment:
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# Linux/macOS
python -m venv venv
source venv/bin/activate
```

3. Install the dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file in the project root with your Oura API credentials:
```
OURA_CLIENT_ID=your_client_id
OURA_CLIENT_SECRET=your_client_secret
FLASK_SECRET_KEY=your_random_secret_key
OURA_REDIRECT_URI=http://localhost:5000/callback
```

5. Configure your Oura API Application:
   - Go to https://cloud.ouraring.com/
   - Create a new application
   - Set the redirect URI to `http://localhost:5000/callback`
   - Copy your Client ID and Client Secret to the `.env` file

## Running the Application

1. Ensure your virtual environment is activated
2. Run the Flask application:
```bash
python app.py
```
3. Open your browser and navigate to: http://localhost:5000

## Usage

1. Click "Connect to Oura Ring" on the home page
2. You will be redirected to the Oura authorization page
3. Log in to your Oura account and authorize the application
4. After successful authorization, you will be redirected to the dashboard
5. View your personal information and sleep data

## Security Notes

- Never commit your `.env` file to version control
- In production, use HTTPS and implement additional security measures
- Implement proper token storage and refresh mechanisms for production use

## License

MIT

## Author

Your Name 