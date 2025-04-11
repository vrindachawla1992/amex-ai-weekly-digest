import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# main.py
import os
import sys
import json
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
import asyncio
import aiohttp
from bs4 import BeautifulSoup
import random
import time
from typing import List, Dict, Any, Tuple, Optional
import requests
from pathlib import Path
import anthropic
import openai
import ssl
from urllib.parse import urlparse

# Brevo (Sendinblue) SDK
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("scraper.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("fintech-scraper")

# Add custom exception for scraping
class ScraperException(Exception):
    """Custom exception for scraping-related errors"""
    pass

class Config:
    """Configuration loader and validator"""
    
    def __init__(self, config_path="config.json"):
        self.config_path = config_path
        self.config = self._load_config()
        self._validate_config()
        
    def _load_config(self) -> Dict:
        """Load configuration from JSON file with environment variable substitution"""
        try:
            with open(self.config_path, 'r') as f:
                config_template = f.read()
                
                # Replace environment variable placeholders
                placeholders = {
                    '${SENDER_EMAIL}': os.environ.get('SENDER_EMAIL', ''),
                    '${RECIPIENT_EMAILS}': os.environ.get('RECIPIENT_EMAILS', ''),
                    '${BREVO_API_KEY}': os.environ.get('BREVO_API_KEY', ''),
                    '${ANTHROPIC_API_KEY}': os.environ.get('ANTHROPIC_API_KEY', ''),
                    '${LLM_PROVIDER}': os.environ.get('LLM_PROVIDER', 'anthropic'),
                    '${LLM_MODEL}': os.environ.get('LLM_MODEL', 'claude-3-opus-20240229')
                }
                
                for placeholder, value in placeholders.items():
                    config_template = config_template.replace(placeholder, value)
                
                return json.loads(config_template)
        except FileNotFoundError:
            logger.error(f"Config file not found: {self.config_path}")
            raise
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in config file: {self.config_path}")
            raise
            
    def _validate_config(self):
        """Validate configuration file"""
        logger.info(f"Config being validated: {self.config}")
        
        required_sections = ["websites", "keywords", "email", "llm"]
        for section in required_sections:
            if section not in self.config:
                raise ValueError(f"Missing required config section: {section}")
        
        # Validate email configuration
        email_cfg = self.config["email"]
        logger.info(f"Email configuration: {email_cfg}")
        
        # Relax email validation to allow empty values
        if not email_cfg.get("sender_email") or not email_cfg.get("recipients") or not email_cfg.get("api_key"):
            logger.warning("Incomplete email configuration. Email sending may be disabled.")
        
        # Validate LLM configuration
        llm_cfg = self.config["llm"]
        
        # Allow default provider if not specified
        provider = llm_cfg.get("provider", "anthropic")
        if provider not in ["anthropic", "openai"]:
            raise ValueError(f"Unsupported LLM provider: {provider}")
        
        # Relax API key validation to allow empty values
        if not llm_cfg.get("api_key"):
            logger.warning("No LLM API key provided. AI analysis may be disabled.")
        
        # Validate websites and keywords
        if not self.config['websites']:
            raise ValueError("At least one website must be specified")
        
        if not self.config['keywords']:
            raise ValueError("At least one keyword must be specified")
        
    @property
    def websites(self) -> List[str]:
        """Get list of websites to scrape"""
        return self.config["websites"]
        
    @property
    def keywords(self) -> List[str]:
        """Get list of keywords to search for, in priority order"""
        return self.config["keywords"]
        
    @property
    def email_config(self) -> Dict:
        """Get email configuration"""
        return self.config["email"]
        
    @property
    def llm_config(self) -> Dict:
        """Get LLM configuration"""
        return self.config["llm"]
    
    @property
    def user_agents(self) -> List[str]:
        """Get list of user agents to rotate through"""
        return self.config.get("user_agents", [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
        ])
    
    @property
    def proxy_config(self) -> Dict:
        """Get proxy configuration"""
        return self.config["proxy"]
    
    @property
    def request_delay_range(self) -> Tuple[float, float]:
        """Get range for random delay between requests in seconds"""
        delay_config = self.config.get("request_delay", {"min": 1, "max": 3})
        return (delay_config["min"], delay_config["max"])


class ProxyManager:
    """Manage and rotate proxies for web scraping"""
    def __init__(self, proxies: Optional[List[str]] = None):
        self.proxies = proxies or []
        self.current_proxy_index = 0
    
    def get_proxy(self) -> Optional[str]:
        """Rotate through available proxies"""
        if not self.proxies:
            return None
        
        proxy = self.proxies[self.current_proxy_index]
        self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxies)
        return proxy


class WebScraper:
    """Enhanced web scraper with advanced resilience mechanisms"""
    
    SITE_SPECIFIC_RULES = {
        "finextra.com": {
            "article_selectors": [
                "div.news-item",
                "article.news-article",
                "div.article-preview",
                "div.news-list-item"
            ],
            "title_selectors": [
                "h3 a.news-title",
                "h2 a.article-title",
                "h1.news-headline",
                "div.article-title a"
            ],
            "summary_selectors": [
                "div.news-summary",
                "p.article-excerpt",
                "div.article-preview-text"
            ]
        },
        "cnbc.com": {
            "article_selectors": [
                "div.Card-titleContainer",
                "div.Card-textContainer",
                "div.RiverHeadline",
                "div.RiverPlusCard-headline"
            ],
            "title_selectors": [
                "a.Card-title",
                "a.RiverHeadline-headline",
                "h3.RiverHeadline-headline",
                "h2.Card-title"
            ],
            "summary_selectors": [
                "div.Card-textContainer",
                "div.RiverHeadline-description",
                "p.RiverHeadline-description"
            ]
        },
        "pymnts.com": {
            "article_selectors": [
                "article.post",
                "div.post-item",
                "div.article-preview",
                "div.news-block"
            ],
            "title_selectors": [
                "h2.entry-title a",
                "h1.post-title a",
                "div.post-title a",
                "a.article-title"
            ],
            "summary_selectors": [
                "div.entry-summary",
                "p.post-excerpt",
                "div.article-excerpt"
            ]
        }
    }
    
    def __init__(self, config: 'Config'):
        self.config = config
        self.max_retries = 3
        self.timeout = aiohttp.ClientTimeout(total=30)
        
        # Only create ProxyManager if proxies are configured
        proxy_config = config.proxy_config
        self.proxy_manager = ProxyManager(proxy_config.get('proxies', [])) if proxy_config.get('rotate_proxy', False) else None
    
    def _get_site_specific_rules(self, url: str) -> Dict:
        """Get site-specific scraping rules"""
        domain = urlparse(url).netloc.replace('www.', '')
        return self.SITE_SPECIFIC_RULES.get(domain, {
            "article_selectors": ["article", "div.article"],
            "title_selectors": ["h1", "h2", ".title", "a.title"],
            "summary_selectors": ["p", ".summary", "div.excerpt"]
        })
    
    async def scrape_all_sites(self) -> List[Dict]:
        """Enhanced scraping with retry and fallback logic"""
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            tasks = [self.scrape_site_with_retry(session, site) for site in self.config.websites]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            all_articles = []
            for site, result in zip(self.config.websites, results):
                if isinstance(result, Exception):
                    logger.error(f"Failed to scrape {site}: {result}")
                elif result:
                    all_articles.extend(result)
            
            return all_articles
    
    async def scrape_site_with_retry(self, session: aiohttp.ClientSession, url: str) -> List[Dict]:
        """Retry scraping with exponential backoff and optional proxy rotation"""
        for attempt in range(self.max_retries):
            try:
                # Random delay to avoid rate limiting
                await asyncio.sleep(random.uniform(1, 3) * (attempt + 1))
                
                # Rotate proxies and user agents if proxy rotation is enabled
                proxy = self.proxy_manager.get_proxy() if self.proxy_manager else None
                headers = {
                    "User-Agent": random.choice(self.config.user_agents),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                    "Referer": "https://www.google.com/",
                }
                
                articles = await self._scrape_with_proxy(session, url, headers, proxy)
                
                if articles:
                    return articles
                
                logger.warning(f"No articles found for {url} on attempt {attempt + 1}")
            
            except Exception as e:
                logger.error(f"Scraping error for {url} (Attempt {attempt + 1}): {e}")
                
                # Fallback to requests if aiohttp fails
                if attempt == self.max_retries - 1:
                    try:
                        return self._fallback_requests_scrape(url)
                    except Exception as fallback_error:
                        logger.error(f"Fallback scraping failed for {url}: {fallback_error}")
        
        return []
    
    async def _scrape_with_proxy(self, session: aiohttp.ClientSession, url: str, headers: Dict, proxy: Optional[str] = None) -> List[Dict]:
        """Scrape a site using optional proxy"""
        try:
            async with session.get(url, headers=headers, proxy=proxy) as response:
                if response.status != 200:
                    logger.warning(f"HTTP {response.status} for {url}")
                    return []
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                return self._extract_articles(soup, url)
        
        except aiohttp.ClientError as e:
            logger.error(f"Proxy/Client error scraping {url}: {e}")
            raise
    
    def _fallback_requests_scrape(self, url: str) -> List[Dict]:
        """Fallback scraping method using requests library"""
        headers = {
            "User-Agent": random.choice(self.config.user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        return self._extract_articles(soup, url)
    
    def _extract_articles(self, soup: BeautifulSoup, base_url: str) -> List[Dict]:
        """Extract news articles from HTML content with site-specific rules"""
        rules = self._get_site_specific_rules(base_url)
        articles = []
        
        # Try multiple article and title selectors
        for article_selector in rules.get("article_selectors", ["article"]):
            for article_elem in soup.select(article_selector):
                try:
                    # Try multiple title selectors
                    title_elem = None
                    for title_selector in rules.get("title_selectors", ["h1", "h2"]):
                        title_elem = article_elem.select_one(title_selector)
                        if title_elem:
                            break
                    
                    if not title_elem:
                        continue
                    
                    title = title_elem.get_text(strip=True)
                    
                    # Try multiple summary selectors
                    summary_elem = None
                    for summary_selector in rules.get("summary_selectors", ["p"]):
                        summary_elem = article_elem.select_one(summary_selector)
                        if summary_elem:
                            break
                    
                    summary = summary_elem.get_text(strip=True) if summary_elem else ""
                    
                    # Create a short excerpt (2-3 lines)
                    excerpt_elems = article_elem.select('p')
                    excerpt_lines = [p.get_text(strip=True) for p in excerpt_elems[:3]]
                    excerpt = ' '.join(excerpt_lines)
                    
                    # Truncate excerpt if too long
                    if len(excerpt) > 300:
                        excerpt = excerpt[:300] + '...'
                    
                    # Keyword matching
                    keywords = [kw for kw in self.config.keywords if kw.lower() in title.lower() or kw.lower() in summary.lower()]
                    
                    if keywords:
                        articles.append({
                            "title": title,
                            "summary": summary,
                            "excerpt": excerpt,  # New field for short excerpt
                            "url": title_elem.get('href', base_url),
                            "source": base_url,
                            "keyword_matches": keywords
                        })
                
                except Exception as e:
                    logger.warning(f"Error extracting article from {base_url}: {e}")
        
        return articles


class NewsAnalyzer:
    """Enhanced news analyzer with fallback and error handling"""
    
    def __init__(self, config: Config):
        self.config = config
        self._setup_llm()
    
    def _setup_llm(self):
        """Robust LLM client setup"""
        try:
            llm_config = self.config.llm_config
            provider = llm_config["provider"]
            api_key = llm_config["api_key"]
            
            if provider == "anthropic":
                self.client = anthropic.Anthropic(api_key=api_key)
                self.model = llm_config.get("model", "claude-3-7-sonnet-20250219")
            elif provider == "openai":
                self.client = openai.Client(api_key=api_key)
                self.model = llm_config.get("model", "gpt-4o")
            else:
                raise ValueError(f"Unsupported LLM provider: {provider}")
        
        except Exception as e:
            logger.error(f"LLM client setup failed: {e}")
            self.client = None
            self.model = None
    
    async def analyze_article(self, article: Dict) -> Dict:
        """Analyze article with fallback to default values"""
        if not self.client:
            logger.warning("No LLM client available, using default analysis")
            article['importance'] = 5
            article['sentiment'] = 'NEUTRAL'
            return article
        
        try:
            # Truncate text to avoid hitting token limits
            title = article.get('title', '')[:200]
            summary = article.get('summary', '')[:500]
            keywords = article.get('keyword_matches', [])
            
            prompt = f"""
            Analyze this fintech news article:
            Title: {title}
            Summary: {summary}
            Keywords: {', '.join(keywords)}
            
            Rate importance (1-10) and market sentiment (BULLISH/BEARISH)
            Response format:
            RATING: [1-10]
            SENTIMENT: [BULLISH/BEARISH]
            """
            
            response = await self._query_llm(prompt)
            analysis = self._parse_llm_response(response)
            
            article['importance'] = analysis.get('importance', 5)
            article['sentiment'] = analysis.get('sentiment', 'NEUTRAL')
            
            return article
        
        except Exception as e:
            logger.error(f"Article analysis error: {e}")
            article['importance'] = 5
            article['sentiment'] = 'NEUTRAL'
            return article

    async def _query_llm(self, prompt: str) -> str:
        """Send query to LLM and get response"""
        provider = self.config.llm_config["provider"]
        
        try:
            if provider == "anthropic":
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=100,
                    messages=[{"role": "user", "content": prompt}]
                )
                return response.content[0].text
            
            elif provider == "openai":
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=100
                )
                return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error querying LLM ({provider}): {e}")
            raise
    
    def _parse_llm_response(self, response: str) -> Dict:
        """Parse the LLM response to extract rating and sentiment"""
        result = {
            'importance': 5,  # Default
            'sentiment': 'NEUTRAL'  # Default
        }
        
        try:
            for line in response.strip().split('\n'):
                if line.startswith('RATING:'):
                    rating_str = line.replace('RATING:', '').strip()
                    result['importance'] = int(rating_str)
                
                elif line.startswith('SENTIMENT:'):
                    sentiment = line.replace('SENTIMENT:', '').strip().upper()
                    if sentiment in ['BULLISH', 'BEARISH']:
                        result['sentiment'] = sentiment
        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}")
            
        return result


class ReportGenerator:
    """Generates HTML reports from analyzed news articles"""
    
    def __init__(self, config: Config):
        self.config = config
        self.output_dir = Path('reports')
        self.output_dir.mkdir(exist_ok=True)
        
        # Load HTML templates
        self.report_template_path = Path('templates/report_template.html')
        self.empty_report_template_path = Path('templates/empty_report_template.html')
    
    def generate_report(self, articles: List[Dict]) -> str:
        """Generate an HTML report for the analyzed articles"""
        if not articles:
            logger.warning("No articles to include in report")
            return self._generate_empty_report()
        
        # Sort articles by importance (descending)
        sorted_articles = sorted(articles, key=lambda x: x.get('importance', 0), reverse=True)
        
        # Generate articles HTML
        articles_html = ""
        for article in sorted_articles:
            title = article.get('title', 'No Title')
            summary = article.get('summary', 'No summary available')
            excerpt = article.get('excerpt', 'No excerpt available')
            link = article.get('url', '#')  
            source = article.get('source', 'Unknown source')
            importance = article.get('importance', 5)
            sentiment = article.get('sentiment', 'NEUTRAL')
            keywords = article.get('keyword_matches', [])
            
            sentiment_class = "bullish" if sentiment == "BULLISH" else "bearish"
            
            articles_html += f"""
            <div class="article">
                <div class="article-header">
                    <h2 class="title"><a href="{link}" target="_blank">{title}</a></h2>
                    <div class="metrics">
                        <span class="importance">Importance: {importance}/10</span>
                        <span class="{sentiment_class}">{sentiment}</span>
                    </div>
                </div>
                <div class="summary">{summary}</div>
                <div class="excerpt">{excerpt}</div>
                <div class="keywords">Keywords: {', '.join(keywords)}</div>
                <div class="source">Source: {source}</div>
            </div>
            """
        
        # Load and populate template
        report_date = datetime.now().strftime('%Y-%m-%d')
        report_datetime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        try:
            with open(self.report_template_path, 'r', encoding='utf-8') as f:
                template = f.read()
            
            # Use safer string formatting
            html = template.replace('{report_date}', report_date) \
                           .replace('{datetime}', report_datetime) \
                           .replace('{articles_html}', articles_html)
        except Exception as e:
            logger.error(f"Error reading report template: {e}")
            raise
        
        # Save report to file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_path = self.output_dir / f"fintech_news_report_{timestamp}.html"
        
        try:
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(html)
            
            logger.info(f"Report saved to {report_path}")
        except Exception as e:
            logger.error(f"Error saving report: {e}")
            raise
        
        return html
    
    def _generate_empty_report(self) -> str:
        """Generate an empty report when no articles are found"""
        report_date = datetime.now().strftime('%Y-%m-%d')
        report_datetime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        with open(self.empty_report_template_path, 'r') as f:
            template = f.read()
        
        html = template.format(
            report_date=report_date,
            datetime=report_datetime
        )
        
        # Save empty report to file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_path = self.output_dir / f"fintech_news_report_{timestamp}_empty.html"
        
        with open(report_path, 'w') as f:
            f.write(html)
            
        logger.info(f"Empty report saved to {report_path}")
        
        return html


class EmailSender:
    """Email sender using Brevo (Sendinblue) API"""
    
    def __init__(self, config: Config):
        self.config = config
        self.email_config = config.email_config
        self.output_dir = Path('reports')
        self.output_dir.mkdir(exist_ok=True)
        
        # Configure Brevo API
        # Use BREVO_API_KEY from environment or from the configuration
        self.brevo_api_key = os.environ.get('BREVO_API_KEY', self.email_config.get('api_key'))
        if not self.brevo_api_key:
            logger.error("No Brevo API key found. Email sending will be disabled.")
        
        # Create a configuration object for Brevo SDK
        configuration = sib_api_v3_sdk.Configuration()
        configuration.api_key['api-key'] = self.brevo_api_key
        
        # Instantiate an ApiClient with the configuration
        api_client = sib_api_v3_sdk.ApiClient(configuration)
        
        # Create the transactional email API instance with the ApiClient
        self.transactional_email_api = sib_api_v3_sdk.TransactionalEmailsApi(api_client)
    
    def send_report(self, html_content: str) -> bool:
        """Send report using Brevo Transactional Email API"""
        # Always save report locally
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_path = self.output_dir / f"fintech_news_report_{timestamp}.html"
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"Report saved locally to {report_path}")
        
        # Validate email configuration
        recipients = self.email_config.get("recipients", [])
        sender_email = self.email_config.get("sender_email", "noreply@fintechnewsscraper.com")
        
        # If no recipients or no API key, just return True (report is saved)
        if not recipients or not self.brevo_api_key:
            logger.warning("No recipients or API key. Report saved locally.")
            return True
        
        try:
            # Prepare the email
            send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
                to=[{"email": recipient} for recipient in recipients],
                sender={"name": "Fintech News Scraper", "email": sender_email},
                subject=f"Fintech News Report - {datetime.now().strftime('%Y-%m-%d')}",
                html_content=html_content
            )
            
            # Send the email
            api_response = self.transactional_email_api.send_transac_email(send_smtp_email)
            logger.info(f"Report email sent to {recipients}")
            return True
        
        except ApiException as e:
            logger.error(f"Failed to send report email: {e}")
            logger.info("Report was saved locally. Email sending failed.")
            return False


class FintechNewsScraper:
    """Main application class that orchestrates the scraping and reporting process"""
    
    def __init__(self, config_path="config.json"):
        self.config = Config(config_path)
        self.scraper = WebScraper(self.config)
        self.analyzer = NewsAnalyzer(self.config)
        self.report_generator = ReportGenerator(self.config)
        self.email_sender = EmailSender(self.config)
        
    async def run(self):
        """Run the complete scraping, analysis, and reporting pipeline"""
        try:
            logger.info("Starting Fintech News Scraper")
            
            # Step 1: Scrape all websites
            articles = await self.scraper.scrape_all_sites()
            logger.info(f"Found {len(articles)} relevant articles")
            
            if not articles:
                logger.warning("No articles found matching keywords")
                html_report = self.report_generator.generate_report([])
                self.email_sender.send_report(html_report)
                return
            
            # Step 2: Analyze each article for importance and sentiment
            analyzed_articles = []
            for article in articles:
                analyzed = await self.analyzer.analyze_article(article)
                analyzed_articles.append(analyzed)
            
            # Step 3: Generate HTML report
            html_report = self.report_generator.generate_report(analyzed_articles)
            
            # Step 4: Send email report
            self.email_sender.send_report(html_report)
            
            logger.info("Fintech News Scraper completed successfully")
            
        except Exception as e:
            logger.error(f"Error running Fintech News Scraper: {e}")
            raise   
    

async def main():
    """Application entry point"""
    scraper = FintechNewsScraper()
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())