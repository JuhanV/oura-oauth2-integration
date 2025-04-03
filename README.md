# Oura Ring Data Comparison App

A Flask-based web application that allows multiple users to connect their Oura Ring accounts and compare their health metrics with friends.

## Quick Start

1. Clone the repository:
```bash
git clone <your-repository-url>
cd <repository-directory>
```

2. Set up Python virtual environment:
```bash
python -m venv venv
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Linux/macOS:
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
- Copy `.env.example` to `.env`
- Fill in your credentials (see [Environment Setup](docs/setup.md#environment-variables))

5. Run the application:
```bash
flask run
```

Visit `http://localhost:5000` in your browser.

## Documentation

- [Setup Guide](docs/setup.md)
- [Architecture Overview](docs/architecture.md)
- [Security Considerations](docs/security.md)
- [API Documentation](docs/api.md)
- [Database Schema](docs/database.md)

## Features

- OAuth2 authentication with Oura Ring
- Secure token storage using Supabase
- User profile management
- Sleep data comparison between users
- Friend management system (coming soon)

## Security

This application implements several security measures:
- Encrypted token storage
- Secure session management
- Row Level Security in Supabase
- HTTPS enforcement in production

For more details, see our [Security Documentation](docs/security.md).

## Contributing

Please read our [Contributing Guidelines](docs/contributing.md) before submitting pull requests.

## License

[MIT License](LICENSE) 