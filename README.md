# Fintech News Scraper 🌐📰

## Overview
An advanced, AI-powered Fintech news scraping and analysis tool that:
- Scrapes news from multiple financial websites
- Analyzes articles using AI
- Generates comprehensive HTML reports
- Sends email notifications

## Features
- Multi-source web scraping
- AI-powered article analysis
- Sentiment and importance scoring
- Dynamic HTML report generation
- Email reporting via Brevo API
- Docker containerization
- Environment variable configuration

## Prerequisites
- Python 3.9+
- Docker (optional)
- Brevo API Key
- Anthropic/OpenAI API Key

## Installation

### Local Setup
1. Clone the repository
```bash
git clone https://github.com/mpm1811/fintech-news-scraper.git
cd fintech-news-scraper
```

2. Install dependencies
```bash
pip install -r requirements.txt
```

3. Configure environment variables
Create a `.env` file with:
```
BREVO_API_KEY=your_brevo_key
SENDER_EMAIL=your_email
RECIPIENT_EMAILS=recipient@example.com
ANTHROPIC_API_KEY=your_anthropic_key
LLM_PROVIDER=anthropic
LLM_MODEL=claude-3-opus-20240229
```

### Docker Deployment

#### Option 1: Using Environment Variables
```bash
# Build the image
docker build -t fintech-scraper .

# Run with environment variables
docker run \
    -e BREVO_API_KEY=your_brevo_key \
    -e SENDER_EMAIL=your_email \
    -e RECIPIENT_EMAILS=recipient@example.com \
    -e ANTHROPIC_API_KEY=your_anthropic_key \
    fintech-scraper
```

#### Option 2: Using .env File
1. Create a `.env` file
2. Build and run:
```bash
docker build -t fintech-scraper .
docker run --env-file .env fintech-scraper
```

## Configuration
- `config.json`: Website sources, keywords, and scraping settings
- `.env`: Sensitive configuration and API keys

## Security
- Sensitive data managed via environment variables
- Docker secrets support
- No hardcoded credentials

## Contributing
1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License
[Specify your license here]

## Contact
Pranav Mankar - pranav.mankar@gmail.com

## Acknowledgments
- Anthropic Claude AI
- Brevo (Sendinblue) API
- Beautiful Soup
- HTTPX
