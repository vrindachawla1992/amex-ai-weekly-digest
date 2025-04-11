# test_scraper.py
import os
import json
import pytest
import asyncio
from unittest.mock import patch, MagicMock
from aioresponses import aioresponses
from datetime import datetime

# Import all components
from main import Config, WebScraper, NewsAnalyzer, ReportGenerator, EmailSender, FintechNewsScraper

# Sample test config
TEST_CONFIG = {
    "websites": [
        "https://www.test-site.com"
    ],
    "keywords": [
        "fintech",
        "crypto"
    ],
    "email": {
        "smtp_server": "smtp.test.com",
        "smtp_port": 587,
        "sender_email": "test@example.com",
        "recipients": ["recipient@example.com"],
        "password": "test-password"
    },
    "llm": {
        "provider": "anthropic",
        "api_key": "test-api-key",
        "model": "test-model"
    },
    "user_agents": [
        "Test User Agent"
    ],
    "request_delay": {
        "min": 0.1,
        "max": 0.2
    }
}

# Sample HTML content for testing
SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Test News Site</title></head>
<body>
    <article class="news-article">
        <h2><a href="/news/1">Fintech Revolution in Banking</a></h2>
        <p>This is a test article about fintech innovations.</p>
    </article>
    <article class="news-article">
        <h2><a href="/news/2">Sports News</a></h2>
        <p>This is an article about sports.</p>
    </article>
</body>
</html>
"""

@pytest.fixture
def test_config_file():
    """Create a temporary test config file"""
    with open("test_config.json", "w") as f:
        json.dump(TEST_CONFIG, f)
    yield "test_config.json"
    os.remove("test_config.json")

@pytest.fixture
def mock_llm_response():
    """Mock LLM response for testing"""
    return "RATING: 8\nSENTIMENT: BULLISH"

class TestConfig:
    def test_load_config(self, test_config_file):
        """Test that the config is loaded correctly"""
        config = Config(test_config_file)
        assert config.websites == TEST_CONFIG["websites"]
        assert config.keywords == TEST_CONFIG["keywords"]
        assert config.email_config == TEST_CONFIG["email"]
        assert config.llm_config == TEST_CONFIG["llm"]

    def test_validate_config_missing_section(self):
        """Test that validation fails when a required section is missing"""
        invalid_config = TEST_CONFIG.copy()
        del invalid_config["websites"]
        
        with open("invalid_config.json", "w") as f:
            json.dump(invalid_config, f)
        
        with pytest.raises(ValueError):
            Config("invalid_config.json")
        
        os.remove("invalid_config.json")

class TestWebScraper:
    @pytest.mark.asyncio
    async def test_scrape_site(self, test_config_file):
        """Test scraping a single site"""
        config = Config(test_config_file)
        scraper = WebScraper(config)
        
        with aioresponses() as m:
            m.get('https://www.test-site.com', status=200, body=SAMPLE_HTML)
            
            async with aiohttp.ClientSession() as session:
                articles = await scraper.scrape_site(session, 'https://www.test-site.com')
                
                assert len(articles) == 1
                assert articles[0]['title'] == 'Fintech Revolution in Banking'
                assert 'fintech' in articles[0]['keyword_matches']

    @pytest.mark.asyncio
    async def test_scrape_all_sites(self, test_config_file):
        """Test scraping all sites"""
        config = Config(test_config_file)
        scraper = WebScraper(config)
        
        with aioresponses() as m:
            m.get('https://www.test-site.com', status=200, body=SAMPLE_HTML)
            
            articles = await scraper.scrape_all_sites()
            
            assert len(articles) == 1
            assert articles[0]['title'] == 'Fintech Revolution in Banking'

class TestNewsAnalyzer:
    @pytest.mark.asyncio
    async def test_analyze_article(self, test_config_file, mock_llm_response):
        """Test analyzing an article"""
        config = Config(test_config_file)
        analyzer = NewsAnalyzer(config)
        
        article = {
            'title': 'Fintech Revolution in Banking',
            'summary': 'This is a test article about fintech innovations.',
            'link': 'https://www.test-site.com/news/1',
            'source': 'https://www.test-site.com',
            'keyword_matches': ['fintech']
        }
        
        with patch.object(analyzer, '_query_llm', return_value=mock_llm_response):
            result = await analyzer.analyze_article(article)
            
            assert result['importance'] == 8
            assert result['sentiment'] == 'BULLISH'

class TestReportGenerator:
    def test_generate_report(self, test_config_file):
        """Test generating a report"""
        config = Config(test_config_file)
        generator = ReportGenerator(config)
        
        articles = [
            {
                'title': 'Fintech Revolution in Banking',
                'summary': 'This is a test article about fintech innovations.',
                'link': 'https://www.test-site.com/news/1',
                'source': 'https://www.test-site.com',
                'keyword_matches': ['fintech'],
                'importance': 8,
                'sentiment': 'BULLISH'
            }
        ]
        
        html = generator.generate_report(articles)
        
        assert 'Fintech Revolution in Banking' in html
        assert 'Importance: 8/10' in html
        assert 'BULLISH' in html

    def test_generate_empty_report(self, test_config_file):
        """Test generating an empty report"""
        config = Config(test_config_file)
        generator = ReportGenerator(config)
        
        html = generator.generate_report([])
        
        assert 'No relevant news articles found today' in html

class TestEmailSender:
    def test_send_report(self, test_config_file):
        """Test sending an email report"""
        config = Config(test_config_file)
        sender = EmailSender(config)
        
        with patch('smtplib.SMTP') as mock_smtp:
            instance = mock_smtp.return_value
            
            result = sender.send_report("<html><body>Test Report</body></html>")
            
            assert result is True
            instance.sendmail.assert_called_once()

class TestFintechNewsScraper:
    @pytest.mark.asyncio
    async def test_run(self, test_config_file, mock_llm_response):
        """Test running the complete pipeline"""
        with patch('main.WebScraper.scrape_all_sites') as mock_scrape:
            mock_scrape.return_value = [
                {
                    'title': 'Fintech Revolution in Banking',
                    'summary': 'This is a test article about fintech innovations.',
                    'link': 'https://www.test-site.com/news/1',
                    'source': 'https://www.test-site.com',
                    'keyword_matches': ['fintech']
                }
            ]
            
            with patch('main.NewsAnalyzer.analyze_article') as mock_analyze:
                mock_analyze.return_value = {
                    'title': 'Fintech Revolution in Banking',
                    'summary': 'This is a test article about fintech innovations.',
                    'link': 'https://www.test-site.com/news/1',
                    'source': 'https://www.test-site.com',
                    'keyword_matches': ['fintech'],
                    'importance': 8,
                    'sentiment': 'BULLISH'
                }
                
                with patch('main.ReportGenerator.generate_report') as mock_generate:
                    mock_generate.return_value = "<html><body>Test Report</body></html>"
                    
                    with patch('main.EmailSender.send_report') as mock_send:
                        mock_send.return_value = True
                        
                        scraper = FintechNewsScraper(test_config_file)
                        await scraper.run()
                        
                        mock_scrape.assert_called_once()
                        mock_analyze.assert_called_once()
                        mock_generate.assert_called_once()
                        mock_send.assert_called_once()

if __name__ == "__main__":
    pytest.main()