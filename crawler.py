#!/usr/bin/env python3
"""
UCR Dining Menus Crawler

Crawls https://foodpro.ucr.edu/foodpro/search.aspx to search for keywords
and stores results in data folder. Sends notifications via Slack, Telegram, or Lark.
"""

import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiohttp
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Import notification modules
from notifications import NotificationManager

# Configure logging
def setup_logging():
    """Setup logging with timestamped files in log directory."""
    # Create log directory
    log_dir = Path("log")
    log_dir.mkdir(exist_ok=True)
    
    # Create timestamped log filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = log_dir / f"crawler_{timestamp}.log"
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename),
            logging.StreamHandler(sys.stdout)
        ]
    )

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


class UCRCrawler:
    def __init__(self, config_path: str = "config.json"):
        """Initialize the crawler with configuration."""
        self.config = self._load_config(config_path)
        self.base_url = self.config['crawler']['base_url']
        self.search_delay = self.config['crawler']['search_delay']
        self.max_retries = self.config['crawler']['max_retries']
        self.timeout = self.config['crawler']['timeout']
        
        # Setup data directory
        self.data_dir = Path(self.config['storage']['data_dir'])
        self.data_dir.mkdir(exist_ok=True)
        
        # Clear data directory on startup
        self._clear_data_directory()
        
        # Initialize notification manager
        self.notification_manager = NotificationManager(self.config['notifications'])
        
        # Session headers to mimic browser
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        logger.info(f"Initialized crawler with base URL: {self.base_url}")

    def _get_current_timestamp(self) -> str:
        """Get current timestamp for filename."""
        from datetime import datetime
        return datetime.now().strftime("%Y%m%d_%H%M%S")

    def _clear_data_directory(self):
        """Clear all files in the data directory."""
        try:
            if self.data_dir.exists():
                for file_path in self.data_dir.iterdir():
                    if file_path.is_file():
                        file_path.unlink()
                        logger.info(f"Deleted file: {file_path}")
                logger.info(f"Cleared data directory: {self.data_dir}")
            else:
                logger.info(f"Data directory does not exist: {self.data_dir}")
        except Exception as e:
            logger.error(f"Error clearing data directory: {e}")

    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from JSON file."""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Configuration file {config_path} not found. Using template.")
            # Load from template if config.json doesn't exist
            template_path = "config_template.json"
            if os.path.exists(template_path):
                with open(template_path, 'r') as f:
                    return json.load(f)
            else:
                raise FileNotFoundError("Neither config.json nor config_template.json found")
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing configuration file: {e}")
            sys.exit(1)

    async def fetch_page(self, session: aiohttp.ClientSession, url: str, data: Optional[Dict] = None) -> str:
        """Fetch a page with retry logic."""
        # Ensure URL is absolute
        if url.startswith('/'):
            url = f"https://foodpro.ucr.edu{url}"
        elif not url.startswith('http'):
            url = f"{self.base_url.rstrip('/')}/{url.lstrip('/')}"
            
        for attempt in range(self.max_retries):
            try:
                if data:
                    async with session.post(url, data=data, timeout=self.timeout) as response:
                        return await response.text()
                else:
                    async with session.get(url, timeout=self.timeout) as response:
                        return await response.text()
            except asyncio.TimeoutError:
                logger.warning(f"Timeout on attempt {attempt + 1}/{self.max_retries} for {url}")
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
            except Exception as e:
                logger.error(f"Error fetching {url}: {e}")
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)

    def parse_search_form(self, html: str) -> Tuple[Dict, str]:
        """Parse the search form to extract necessary parameters."""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find the search form (not the aspnetForm)
        form = soup.find('form', {'action': 'search.aspx'})
        if not form:
            form = soup.find('form')
        
        if not form:
            raise ValueError("Could not find search form")
        
        # Extract form action
        action = form.get('action', '')
        if action.startswith('/'):
            action = f"https://foodpro.ucr.edu{action}"
        elif not action:
            action = self.base_url
        
        # Extract form data
        form_data = {}
        for input_tag in form.find_all('input'):
            name = input_tag.get('name')
            value = input_tag.get('value', '')
            if name:
                form_data[name] = value
        
        # Extract select values
        for select_tag in form.find_all('select'):
            name = select_tag.get('name')
            if name:
                # Get the first selected option or first option
                selected_option = select_tag.find('option', selected=True)
                if not selected_option:
                    selected_option = select_tag.find('option')
                if selected_option:
                    form_data[name] = selected_option.get('value', '')
        
        # Add search parameters
        form_data['__EVENTTARGET'] = ''
        form_data['__EVENTARGUMENT'] = ''
        
        return form_data, action

    def extract_menu_items(self, html: str, keyword: str) -> List[Dict]:
        """Extract menu items from search results by parsing table structure."""
        soup = BeautifulSoup(html, 'html.parser')
        results = []
        
        # Find all search result rows
        rows = soup.find_all('tr', class_='searchgridresultrow')
        
        for row in rows:
            try:
                # Extract description from the nested table structure
                # Look for the searchcoldesc div which contains the food name
                desc_div = row.find('div', class_='searchcoldesc')
                if not desc_div:
                    continue
                
                # Get the text content directly (no need to remove hyperlinks)
                description = desc_div.get_text(strip=True)
                
                # Extract location
                location_div = row.find('div', class_='searchcollocation')
                location = location_div.get_text(strip=True) if location_div else ""
                
                # Extract day
                day_div = row.find('div', class_='searchcoldate')
                day = day_div.get_text(strip=True) if day_div else ""
                
                # Extract meal
                meal_div = row.find('div', class_='searchcolmeal')
                meal = meal_div.get_text(strip=True) if meal_div else ""
                
                # Clean up the text
                clean_description = re.sub(r'\s+', ' ', description).strip()
                clean_location = re.sub(r'\s+', ' ', location).strip()
                clean_day = re.sub(r'\s+', ' ', day).strip()
                clean_meal = re.sub(r'\s+', ' ', meal).strip()
                
                # Check if the description contains the keyword (case insensitive)
                if keyword.lower() in clean_description.lower():
                    results.append({
                        'keyword': keyword,
                        'description': clean_description,
                        'location': clean_location,
                        'day': clean_day,
                        'meal': clean_meal,
                        'full_text': f"{clean_description} | Location: {clean_location} | Day: {clean_day} | Meal: {clean_meal}",
                        'source': str(row),
                        'timestamp': datetime.now().isoformat()
                    })
                        
            except Exception as e:
                logger.warning(f"Error parsing row: {e}")
                continue
        
        return results
    
    def _get_text_without_links(self, element) -> str:
        """Extract text from element, removing links but keeping their text content."""
        if not element:
            return ""
        
        # Create a copy to avoid modifying the original
        element_copy = element.copy()
        
        # Remove all anchor tags but keep their text
        for a_tag in element_copy.find_all('a'):
            a_tag.unwrap()  # Remove the tag but keep its contents
        
        return element_copy.get_text(strip=True)

    async def search_keyword(self, session: aiohttp.ClientSession, keyword: str) -> Dict:
        """Search for a specific keyword and return results."""
        logger.info(f"Searching for keyword: {keyword}")
        
        try:
            # First, get the search page to extract form parameters
            initial_html = await self.fetch_page(session, self.base_url)
            form_data, search_url = self.parse_search_form(initial_html)
            
            # Add search keyword - use the correct field name from the form
            form_data['strCurKeywords'] = keyword
            form_data['Action'] = 'SEARCH'  # Use the correct action parameter
            
            # Submit search
            search_results_html = await self.fetch_page(session, search_url, form_data)
            
            # Extract results
            results = self.extract_menu_items(search_results_html, keyword)
            
            # Save raw HTML if configured
            if self.config['storage']['save_raw_html']:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{self.data_dir}/raw_{keyword}_{timestamp}.html"
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(search_results_html)
                logger.info(f"Saved raw HTML to {filename}")
            
            return {
                'keyword': keyword,
                'results': results,
                'timestamp': datetime.now().isoformat(),
                'total_found': len(results)
            }
            
        except Exception as e:
            logger.error(f"Error searching for {keyword}: {e}")
            return {
                'keyword': keyword,
                'error': str(e),
                'results': [],
                'timestamp': datetime.now().isoformat(),
                'total_found': 0
            }

    async def run_search(self, keywords: List[str]) -> Dict:
        """Run search for all keywords."""
        async with aiohttp.ClientSession(headers=self.headers) as session:
            results = {}
            
            for i, keyword in enumerate(keywords):
                try:
                    # Add delay between searches to be respectful
                    if i > 0:
                        await asyncio.sleep(self.search_delay)
                    
                    result = await self.search_keyword(session, keyword)
                    results[keyword] = result
                    
                    # Send notification if results found
                    if result.get('total_found', 0) > 0:
                        await self.notification_manager.send_notification(keyword, result['results'])
                        
                except Exception as e:
                    logger.error(f"Failed to search for {keyword}: {e}")
                    results[keyword] = {
                        'keyword': keyword,
                        'error': str(e),
                        'results': [],
                        'timestamp': datetime.now().isoformat(),
                        'total_found': 0
                    }
            
            return results

    def save_results(self, results: Dict):
        """Save search results to JSON file."""
        if not self.config['storage']['save_json']:
            return
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.data_dir}/menus_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved results to {filename}")

    async def main(self, keywords_file: str = "keywords.txt"):
        """Main execution method."""
        logger.info("Starting UCR Dining Menus Crawler")
        
        # Load keywords
        try:
            with open(keywords_file, 'r') as f:
                keywords = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        except FileNotFoundError:
            logger.error(f"Keywords file {keywords_file} not found")
            return
        
        logger.info(f"Loaded {len(keywords)} keywords: {keywords}")
        
        # Run search
        results = await self.run_search(keywords)
        
        # Save results
        self.save_results(results)
        
        # Send summary notification
        total_found = sum(result.get('total_found', 0) for result in results.values())
        await self.notification_manager.send_summary(len(keywords), total_found)
        
        logger.info(f"Crawler completed. Found {total_found} items across {len(keywords)} keywords.")


async def main():
    """Entry point."""
    crawler = UCRCrawler()
    await crawler.main()


if __name__ == "__main__":
    asyncio.run(main())