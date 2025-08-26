"""Background tasks for connection management and maintenance."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from ..db.session import get_db
from ..db.models import Connection, ConnectionStatus, AuthMethod
from .services import ConnectionService

logger = logging.getLogger(__name__)

class BackgroundTaskManager:
    """Manager for background tasks related to connection maintenance."""
    
    def __init__(self):
        self._running = False
        self._tasks = []
    
    async def start(self):
        """Start all background tasks."""
        if self._running:
            return
        
        self._running = True
        logger.info("Starting background task manager")
        
        # Start connection refresh task
        refresh_task = asyncio.create_task(self._connection_refresh_loop())
        self._tasks.append(refresh_task)
        
        # Start OAuth state cleanup task
        cleanup_task = asyncio.create_task(self._oauth_cleanup_loop())
        self._tasks.append(cleanup_task)
        
        logger.info(f"Started {len(self._tasks)} background tasks")
    
    async def stop(self):
        """Stop all background tasks."""
        if not self._running:
            return
        
        self._running = False
        logger.info("Stopping background task manager")
        
        # Cancel all tasks
        for task in self._tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        
        self._tasks.clear()
        logger.info("Background task manager stopped")
    
    async def _connection_refresh_loop(self):
        """Background loop to refresh expiring connections."""
        logger.info("Starting connection refresh loop")
        
        while self._running:
            try:
                await self._refresh_expiring_connections()
                # Run every 5 minutes
                await asyncio.sleep(300)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in connection refresh loop: {e}")
                # Wait 1 minute before retrying on error
                await asyncio.sleep(60)
        
        logger.info("Connection refresh loop stopped")
    
    async def _oauth_cleanup_loop(self):
        """Background loop to clean up expired OAuth states."""
        logger.info("Starting OAuth cleanup loop")
        
        while self._running:
            try:
                await self._cleanup_expired_oauth_states()
                # Run every hour
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in OAuth cleanup loop: {e}")
                # Wait 10 minutes before retrying on error
                await asyncio.sleep(600)
        
        logger.info("OAuth cleanup loop stopped")
    
    async def _refresh_expiring_connections(self):
        """Refresh connections that are about to expire."""
        db = next(get_db())
        try:
            # Find connections expiring in the next 10 minutes
            expiry_threshold = datetime.utcnow() + timedelta(minutes=10)
            
            expiring_connections = db.query(Connection).filter(
                and_(
                    Connection.status == ConnectionStatus.valid,
                    Connection.expires_at.isnot(None),
                    Connection.expires_at <= expiry_threshold,
                    Connection.auth_method == AuthMethod.oauth2
                )
            ).all()
            
            if not expiring_connections:
                logger.debug("No expiring connections found")
                return
            
            logger.info(f"Found {len(expiring_connections)} expiring connections")
            
            refreshed_count = 0
            failed_count = 0
            
            for connection in expiring_connections:
                try:
                    logger.info(f"Refreshing connection {connection.id} for user {connection.user_id}")
                    success = ConnectionService.refresh_connection_tokens(db, connection)
                    
                    if success:
                        refreshed_count += 1
                        logger.info(f"Successfully refreshed connection {connection.id}")
                    else:
                        failed_count += 1
                        logger.warning(f"Failed to refresh connection {connection.id}")
                        
                        # Mark connection as invalid if refresh failed
                        ConnectionService.update_connection_status(
                            db, str(connection.id), ConnectionStatus.invalid,
                            "Token refresh failed"
                        )
                        
                except Exception as e:
                    failed_count += 1
                    logger.error(f"Error refreshing connection {connection.id}: {e}")
                    
                    # Mark connection as error
                    ConnectionService.update_connection_status(
                        db, str(connection.id), ConnectionStatus.error,
                        f"Token refresh error: {str(e)}"
                    )
            
            logger.info(f"Connection refresh completed: {refreshed_count} refreshed, {failed_count} failed")
            
        except Exception as e:
            logger.error(f"Error in refresh_expiring_connections: {e}")
        finally:
            db.close()
    
    async def _cleanup_expired_oauth_states(self):
        """Clean up expired OAuth states from the database."""
        db = next(get_db())
        try:
            cleaned_count = ConnectionService.cleanup_expired_oauth_states(db)
            if cleaned_count > 0:
                logger.info(f"Cleaned up {cleaned_count} expired OAuth states")
            else:
                logger.debug("No expired OAuth states to clean up")
        except Exception as e:
            logger.error(f"Error in cleanup_expired_oauth_states: {e}")
        finally:
            db.close()


# Global instance
background_task_manager = BackgroundTaskManager()


async def start_background_tasks():
    """Start background tasks."""
    await background_task_manager.start()


async def stop_background_tasks():
    """Stop background tasks."""
    await background_task_manager.stop()


def get_connection_for_execution(
    db: Session, 
    user_id: str, 
    app_key: str,
    prefer_connection_id: Optional[str] = None
) -> Optional[Connection]:
    """Get the best available connection for tool execution.
    
    This function implements intelligent connection selection logic:
    1. If a specific connection is preferred and valid, use it
    2. Otherwise, select the best available connection based on:
       - Connection status (valid > pending > error)
       - Priority (higher priority first)
       - Last used time (recently used first)
       - Expiry time (longer validity first)
    
    Args:
        db: Database session
        user_id: User ID
        app_key: Application key
        prefer_connection_id: Optional preferred connection ID
    
    Returns:
        Best available connection or None if no valid connection found
    """
    try:
        # If a specific connection is preferred, try to use it
        if prefer_connection_id:
            preferred_connection = db.query(Connection).filter(
                Connection.id == prefer_connection_id,
                Connection.user_id == user_id,
                Connection.enabled == True
            ).first()
            
            if preferred_connection and preferred_connection.status == ConnectionStatus.valid:
                # Check if token is about to expire and refresh if needed
                if (preferred_connection.expires_at and 
                    preferred_connection.expires_at < datetime.utcnow() + timedelta(minutes=5)):
                    
                    logger.info(f"Refreshing preferred connection {prefer_connection_id}")
                    success = ConnectionService.refresh_connection_tokens(db, preferred_connection)
                    
                    if not success:
                        logger.warning(f"Failed to refresh preferred connection {prefer_connection_id}")
                        # Fall through to general selection logic
                    else:
                        # Update last used time
                        preferred_connection.last_used_at = datetime.utcnow()
                        db.commit()
                        return preferred_connection
                else:
                    # Update last used time
                    preferred_connection.last_used_at = datetime.utcnow()
                    db.commit()
                    return preferred_connection
        
        # General connection selection logic
        return ConnectionService.select_connection(db, user_id, app_key)
        
    except Exception as e:
        logger.error(f"Error in get_connection_for_execution: {e}")
        return None