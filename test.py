#!/usr/bin/env python3
"""
UCR Dining Menus Crawler - Complete Test Suite

This script combines the full workflow:
1. Clear data directory
2. Crawl UCR FoodPro for keywords
3. Extract menu items with filtering
4. Send notifications to configured platforms
5. Save results to data folder
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

import aiohttp

# Add the current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from crawler import UCRCrawler
from notifications import NotificationManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('test.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


async def test_notification_setup():
    """Test if notification configuration is working."""
    logger.info("Testing notification setup...")
    
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        logger.error("config.json not found")
        return False
    
    notification_manager = NotificationManager(config['notifications'])
    
    # Check which platforms are enabled
    enabled_platforms = []
    for platform, settings in config['notifications'].items():
        if settings.get('enabled', False):
            enabled_platforms.append(platform)
    
    if not enabled_platforms:
        logger.warning("No notification platforms are enabled")
        return False
    
    logger.info(f"Enabled platforms: {', '.join(enabled_platforms)}")
    return True


async def test_single_keyword_crawl():
    """Test crawling a single keyword to verify the workflow."""
    logger.info("Testing single keyword crawl...")
    
    crawler = UCRCrawler()
    
    # Test with a keyword that should have results
    test_keyword = "pizza"
    logger.info(f"Testing keyword: {test_keyword}")
    
    try:
        async with aiohttp.ClientSession() as session:
            result = await crawler.search_keyword(session, test_keyword)
            logger.info(f"Search completed for {test_keyword}")
            logger.info(f"Found {result.get('total_found', 0)} results")
            
            if result.get('results'):
                logger.info("Sample results:")
                for i, item in enumerate(result['results'][:3], 1):
                    print(f"  {i}. {item.get('description', '')}")
                    print(f"     Location: {item.get('location', '')}")
                    print(f"     Day: {item.get('day', '')}")
                    print(f"     Meal: {item.get('meal', '')}")
                    print()
            
            return result
            
    except Exception as e:
        logger.error(f"Error testing single keyword: {e}")
        return None


async def test_full_workflow():
    """Test the complete workflow with all keywords."""
    logger.info("Testing complete workflow...")
    
    # Initialize crawler (this will clear data directory)
    crawler = UCRCrawler()
    
    # Load keywords
    try:
        with open('keywords.txt', 'r') as f:
            keywords = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except FileNotFoundError:
        logger.error("keywords.txt not found")
        return None
    
    logger.info(f"Loaded {len(keywords)} keywords: {keywords}")
    
    # Run full search
    try:
        results = await crawler.run_search(keywords)
        logger.info("Full workflow completed")
        
        # Print summary
        total_found = 0
        for keyword, result in results.items():
            found = result.get('total_found', 0)
            total_found += found
            logger.info(f"  {keyword}: {found} results")
        
        logger.info(f"Total items found: {total_found}")
        
        # Save results
        crawler.save_results(results)
        
        # Send summary notification
        await crawler.notification_manager.send_summary(len(keywords), total_found)
        
        return results
        
    except Exception as e:
        logger.error(f"Error in full workflow: {e}")
        return None


async def send_test_notification():
    """Send a test notification to verify the notification system."""
    logger.info("Sending test notification...")
    
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        logger.error("config.json not found")
        return
    
    notification_manager = NotificationManager(config['notifications'])
    
    # Test message
    test_results = [
        {
            'keyword': 'test',
            'description': 'UCR Dining Menus Crawler Test Notification',
            'location': 'Glasgow',
            'day': 'Today',
            'meal': 'Dinner',
            'timestamp': '2024-01-01T12:00:00'
        }
    ]
    
    try:
        await notification_manager.send_notification('test', test_results)
        logger.info("Test notification sent successfully")
    except Exception as e:
        logger.error(f"Error sending test notification: {e}")


async def main():
    """Main test function - complete workflow."""
    print("UCR Dining Menus Crawler - Complete Test Suite")
    print("=" * 60)
    
    # Step 1: Test notification setup
    print("\n1. Testing notification setup...")
    notification_ok = await test_notification_setup()
    
    # Step 2: Send test notification
    if notification_ok:
        print("\n2. Sending test notification...")
        await send_test_notification()
    else:
        print("\n2. Skipping test notification (no platforms enabled)")
    
    # Step 3: Test single keyword crawl
    print("\n3. Testing single keyword crawl...")
    single_result = await test_single_keyword_crawl()
    
    # Step 4: Run complete workflow
    print("\n4. Running complete workflow...")
    full_results = await test_full_workflow()
    
    # Final summary
    print("\n" + "=" * 60)
    print("TEST SUITE COMPLETED")
    print("=" * 60)
    
    if full_results:
        total_found = sum(result.get('total_found', 0) for result in full_results.values())
        print(f"Total items found: {total_found}")
        print(f"Keywords searched: {len(full_results)}")
    
    print("\nCheck the data/ folder for saved results")
    print("Check test.log for detailed logs")
    print("Check your notification platforms for test messages")


if __name__ == "__main__":
    asyncio.run(main())