#!/usr/bin/env python3

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import aiohttp

# Add the current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from crawler import UCRCrawler
from notifications import NotificationManager

# Configure logging
def setup_logging():
    """Setup logging with timestamped files in log directory."""
    # Create log directory
    log_dir = Path("log")
    log_dir.mkdir(exist_ok=True)
    
    # Create timestamped log filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = log_dir / f"run_{timestamp}.log"
    
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


async def main():
    """Main execution function."""
    print("UCR Dining Menus Crawler - Production Runner")
    print("=" * 60)
    
    try:
        # Initialize crawler (this will clear data directory)
        logger.info("Initializing crawler...")
        crawler = UCRCrawler()
        
        # Load keywords
        try:
            with open('keywords.txt', 'r') as f:
                keywords = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        except FileNotFoundError:
            logger.error("keywords.txt not found")
            return
        
        logger.info(f"Loaded {len(keywords)} keywords: {keywords}")
        print(f"Loaded {len(keywords)} keywords: {keywords}")
        
        # Run full search
        logger.info("Starting full search...")
        print("Starting full search...")
        results = await crawler.run_search(keywords)
        
        logger.info("Full search completed")
        print("Full search completed")
        
        # Process results to keep only full_text field
        processed_results = {}
        total_found = 0
        
        for keyword, result in results.items():
            if 'results' in result:
                # Keep only the full_text field for each result
                processed_results[keyword] = {
                    'keyword': keyword,
                    'results': [
                        {
                            'full_text': item.get('full_text', ''),
                            'timestamp': item.get('timestamp', '')
                        }
                        for item in result['results']
                    ],
                    'timestamp': result.get('timestamp', ''),
                    'total_found': len(result['results'])
                }
                total_found += len(result['results'])
            else:
                processed_results[keyword] = result
        
        # Save processed results
        if crawler.config['storage']['save_json']:
            timestamp = crawler._get_current_timestamp()
            filename = f"{crawler.data_dir}/menus_{timestamp}.json"
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(processed_results, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved processed results to {filename}")
            print(f"Saved processed results to {filename}")
        
        # Send summary notification
        # await crawler.notification_manager.send_summary(len(keywords), total_found)
        
        # Final summary
        print("\n" + "=" * 60)
        print("WORKFLOW COMPLETED SUCCESSFULLY")
        print("=" * 60)
        print(f"Total items found: {total_found}")
        print(f"Keywords searched: {len(keywords)}")
        print(f"Results saved to: {crawler.data_dir}/")
        print("\nCheck run.log for detailed logs")
        print("Check your notification platforms for alerts")
        
    except Exception as e:
        logger.error(f"Error in main execution: {e}")
        print(f"Error: {e}")
        print("Check run.log for detailed error information")


if __name__ == "__main__":
    asyncio.run(main())