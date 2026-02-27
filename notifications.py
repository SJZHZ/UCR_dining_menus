#!/usr/bin/env python3
"""
Notification Manager for UCR Dining Menus Crawler

Handles sending notifications via Slack, Telegram, and Lark.
"""

import asyncio
import json
import logging
from typing import Dict, List

import aiohttp

logger = logging.getLogger(__name__)


class NotificationManager:
    def __init__(self, config: Dict):
        """Initialize notification manager with configuration."""
        self.config = config
        self.session = None

    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()

    async def send_slack_notification(self, keyword: str, results: List[Dict]):
        """Send notification to Slack."""
        if not self.config.get('slack', {}).get('enabled', False):
            return

        slack_config = self.config['slack']
        webhook_url = slack_config.get('webhook_url')
        if not webhook_url:
            logger.warning("Slack webhook URL not configured")
            return

        # Format message
        message = self._format_message(keyword, results, "Slack")
        
        payload = {
            "channel": slack_config.get('channel', '#general'),
            "username": slack_config.get('username', 'UCR Dining Bot'),
            "text": message,
            "icon_emoji": ":fork_and_knife:"
        }

        try:
            # Use aiohttp directly instead of self.session
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as response:
                    if response.status == 200:
                        logger.info(f"Slack notification sent for keyword: {keyword}")
                    else:
                        logger.error(f"Failed to send Slack notification: {response.status}")
        except Exception as e:
            logger.error(f"Error sending Slack notification: {e}")

    async def send_telegram_notification(self, keyword: str, results: List[Dict]):
        """Send notification to Telegram."""
        if not self.config.get('telegram', {}).get('enabled', False):
            return

        telegram_config = self.config['telegram']
        bot_token = telegram_config.get('bot_token')
        chat_id = telegram_config.get('chat_id')
        
        if not bot_token or not chat_id:
            logger.warning("Telegram bot token or chat ID not configured")
            return

        # Format message
        message = self._format_message(keyword, results, "Telegram")
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        logger.info(f"Telegram notification sent for keyword: {keyword}")
                    else:
                        logger.error(f"Failed to send Telegram notification: {response.status}")
        except Exception as e:
            logger.error(f"Error sending Telegram notification: {e}")

    async def send_lark_notification(self, keyword: str, results: List[Dict]):
        """Send notification to Lark (Feishu)."""
        if not self.config.get('lark', {}).get('enabled', False):
            return

        lark_config = self.config['lark']
        webhook_url = lark_config.get('webhook_url')
        if not webhook_url:
            logger.warning("Lark webhook URL not configured")
            return

        # Format message
        message = self._format_message(keyword, results, "Lark")
        
        payload = {
            "msg_type": "text",
            "content": {
                "text": message
            }
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as response:
                    if response.status == 200:
                        logger.info(f"Lark notification sent for keyword: {keyword}")
                    else:
                        logger.error(f"Failed to send Lark notification: {response.status}")
        except Exception as e:
            logger.error(f"Error sending Lark notification: {e}")

    def _format_message(self, keyword: str, results: List[Dict], platform: str) -> str:
        """Format notification message."""
        if not results:
            return f"🍽️ No items found for keyword: *{keyword}*"
        
        message = f"🍽️ Found {len(results)} item(s) for keyword: *{keyword}*\n\n"
        
        for i, result in enumerate(results[:5], 1):  # Limit to first 5 results
            # Use full_text field instead of text field
            text = result.get('full_text', '').strip()
            if len(text) > 100:
                text = text[:97] + "..."
            message += f"{i}. {text}\n"
        
        if len(results) > 5:
            message += f"\n... and {len(results) - 5} more items."
        
        # Remove the timestamp line
        # message += f"\n\nTime: {results[0].get('timestamp', '')}"
        
        return message

    async def send_notification(self, keyword: str, results: List[Dict]):
        """Send notification to all enabled platforms."""
        # Create a new session for each platform to avoid None session issues
        await self.send_slack_notification(keyword, results)
        await self.send_telegram_notification(keyword, results)
        await self.send_lark_notification(keyword, results)

    async def send_summary(self, total_keywords: int, total_found: int):
        """Send summary notification."""
        summary_message = (
            f"📊 Crawler Summary:\n"
            f"• Keywords searched: {total_keywords}\n"
            f"• Items found: {total_found}\n"
            f"• Time: {self._get_current_time()}"
        )
        
        # Send summary to all platforms
        for platform in ['slack', 'telegram', 'lark']:
            if self.config.get(platform, {}).get('enabled', False):
                try:
                    if platform == 'slack':
                        webhook_url = self.config['slack'].get('webhook_url')
                        if webhook_url:
                            payload = {
                                "channel": self.config['slack'].get('channel', '#general'),
                                "username": self.config['slack'].get('username', 'UCR Dining Bot'),
                                "text": summary_message,
                                "icon_emoji": ":bar_chart:"
                            }
                            async with aiohttp.ClientSession() as session:
                                async with session.post(webhook_url, json=payload):
                                    pass
                    elif platform == 'telegram':
                        bot_token = self.config['telegram'].get('bot_token')
                        chat_id = self.config['telegram'].get('chat_id')
                        if bot_token and chat_id:
                            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                            payload = {
                                'chat_id': chat_id,
                                'text': summary_message,
                                'parse_mode': 'HTML'
                            }
                            async with aiohttp.ClientSession() as session:
                                async with session.post(url, json=payload):
                                    pass
                    elif platform == 'lark':
                        webhook_url = self.config['lark'].get('webhook_url')
                        if webhook_url:
                            payload = {
                                "msg_type": "text",
                                "content": {"text": summary_message}
                            }
                            async with aiohttp.ClientSession() as session:
                                async with session.post(webhook_url, json=payload):
                                    pass
                except Exception as e:
                    logger.error(f"Error sending {platform} summary: {e}")

    def _get_current_time(self) -> str:
        """Get current time in readable format."""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")