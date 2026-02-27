#!/usr/bin/env python3
"""
AgentLink Matrix Notifier Daemon

Watches for new handoffs in the database and posts notifications
to Matrix rooms, mentioning the target agent.
"""

import os
import asyncio
import logging
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
from matrix_client.client import MatrixClient
from matrix_client.errors import MatrixRequestError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration from environment
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://agentlink:password@postgres:5432/agentlink')
MATRIX_HOMESERVER = os.getenv('MATRIX_HOMESERVER', 'https://talk.molkewolke.de')
MATRIX_USER_ID = os.getenv('MATRIX_USER_ID', '@agentlink:talk.molkewolke.de')
MATRIX_ACCESS_TOKEN = os.getenv('MATRIX_ACCESS_TOKEN')
MATRIX_ROOM_ID = os.getenv('MATRIX_ROOM_ID', '!your-room-id:talk.molkewolke.de')
POLL_INTERVAL = int(os.getenv('POLL_INTERVAL', '5'))  # seconds

# Agent Matrix ID mapping
AGENT_MATRIX_IDS = {
    'castiel': '@castiel:talk.molkewolke.de',
    'lilith': '@lilith:talk.molkewolke.de',
    'rowena': '@rowena:talk.molkewolke.de',
    'local-claude': '@local-claude:talk.molkewolke.de',  # falls später
}

class MatrixNotifier:
    def __init__(self):
        self.client = None
        self.room = None
        self.last_notified_id = None
        
    def connect_matrix(self):
        """Connect to Matrix homeserver"""
        try:
            logger.info(f"Connecting to Matrix homeserver: {MATRIX_HOMESERVER}")
            self.client = MatrixClient(MATRIX_HOMESERVER)
            self.client.login(token=MATRIX_ACCESS_TOKEN, user_id=MATRIX_USER_ID)
            self.room = self.client.join_room(MATRIX_ROOM_ID)
            logger.info(f"Connected to Matrix room: {MATRIX_ROOM_ID}")
            return True
        except MatrixRequestError as e:
            logger.error(f"Matrix connection failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected Matrix error: {e}")
            return False
    
    def get_db_connection(self):
        """Get PostgreSQL connection"""
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    
    def get_last_notified_id(self):
        """Get the last notified handoff ID from DB"""
        try:
            conn = self.get_db_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT MAX(id) as max_id 
                    FROM handoffs 
                    WHERE notified_at IS NOT NULL
                """)
                result = cur.fetchone()
                conn.close()
                return result['max_id'] if result and result['max_id'] else 0
        except Exception as e:
            logger.error(f"Failed to get last notified ID: {e}")
            return 0
    
    def get_new_handoffs(self):
        """Fetch new handoffs since last notification"""
        try:
            conn = self.get_db_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, source_agent, target_agent, task, context, 
                           created_at, status
                    FROM handoffs 
                    WHERE id > %s 
                      AND status = 'pending'
                      AND (notified_at IS NULL OR notified_at < created_at)
                    ORDER BY id ASC
                """, (self.last_notified_id,))
                results = cur.fetchall()
                conn.close()
                return results
        except Exception as e:
            logger.error(f"Failed to fetch new handoffs: {e}")
            return []
    
    def mark_as_notified(self, handoff_id):
        """Mark handoff as notified"""
        try:
            conn = self.get_db_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE handoffs 
                    SET notified_at = NOW() 
                    WHERE id = %s
                """, (handoff_id,))
                conn.commit()
                conn.close()
                return True
        except Exception as e:
            logger.error(f"Failed to mark handoff {handoff_id} as notified: {e}")
            return False
    
    def send_matrix_notification(self, handoff):
        """Send notification to Matrix room"""
        try:
            target_agent = handoff['target_agent']
            source_agent = handoff['source_agent']
            task = handoff['task']
            handoff_id = handoff['id']
            
            # Get Matrix ID for target agent
            matrix_id = AGENT_MATRIX_IDS.get(target_agent.lower(), f"@{target_agent}:talk.molkewolke.de")
            
            # Compose message
            message = f"""🔔 **Neuer AgentLink Handoff #{handoff_id}**

**Von:** {source_agent}
**An:** {matrix_id}
**Task:** {task}

Hol den Handoff ab mit: `/agentlink fetch {handoff_id}` oder check http://192.168.178.102:3000
"""
            
            # Send to Matrix
            self.room.send_text(message)
            logger.info(f"Sent Matrix notification for handoff #{handoff_id} to {target_agent}")
            
            # Mark as notified
            self.mark_as_notified(handoff_id)
            self.last_notified_id = handoff_id
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send Matrix notification for handoff #{handoff['id']}: {e}")
            return False
    
    async def run(self):
        """Main daemon loop"""
        logger.info("AgentLink Matrix Notifier starting...")
        
        # Connect to Matrix
        if not self.connect_matrix():
            logger.error("Failed to connect to Matrix. Exiting.")
            return
        
        # Get last notified ID
        self.last_notified_id = self.get_last_notified_id()
        logger.info(f"Starting from last notified ID: {self.last_notified_id}")
        
        # Main loop
        while True:
            try:
                # Check for new handoffs
                new_handoffs = self.get_new_handoffs()
                
                if new_handoffs:
                    logger.info(f"Found {len(new_handoffs)} new handoff(s)")
                    for handoff in new_handoffs:
                        self.send_matrix_notification(handoff)
                        await asyncio.sleep(1)  # Rate limiting
                
                # Wait before next poll
                await asyncio.sleep(POLL_INTERVAL)
                
            except KeyboardInterrupt:
                logger.info("Shutting down...")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(POLL_INTERVAL)

if __name__ == '__main__':
    notifier = MatrixNotifier()
    asyncio.run(notifier.run())
