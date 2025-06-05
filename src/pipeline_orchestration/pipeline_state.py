"""
Pipeline state management for tracking execution progress and enabling recovery.
"""

import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, date
from pathlib import Path
import pickle

from utils.database import get_db_manager

logger = logging.getLogger(__name__)


class PipelineState:
    """Manages pipeline execution state for recovery and monitoring."""
    
    def __init__(self, state_dir: Optional[Path] = None):
        """
        Initialize pipeline state manager.
        
        Args:
            state_dir: Directory to store state files (default: ./pipeline_state)
        """
        self.state_dir = state_dir or Path('./pipeline_state')
        self.state_dir.mkdir(exist_ok=True)
        self.db_manager = get_db_manager()
        
        # Current execution state
        self.execution_id = None
        self.start_time = None
        self.current_state = {}
    
    def start_execution(self, 
                       stages: List[str],
                       start_date: Optional[date] = None,
                       end_date: Optional[date] = None) -> str:
        """
        Start a new pipeline execution.
        
        Args:
            stages: List of stages to execute
            start_date: Pipeline start date
            end_date: Pipeline end date
            
        Returns:
            Execution ID
        """
        self.execution_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.start_time = datetime.now()
        
        self.current_state = {
            'execution_id': self.execution_id,
            'start_time': self.start_time.isoformat(),
            'stages': stages,
            'start_date': str(start_date) if start_date else None,
            'end_date': str(end_date) if end_date else None,
            'completed_stages': [],
            'failed_stages': [],
            'current_stage': None,
            'stage_states': {}
        }
        
        self._save_state()
        logger.info(f"Started pipeline execution: {self.execution_id}")
        
        return self.execution_id
    
    def start_stage(self, stage_name: str, stage_config: Dict[str, Any] = None):
        """
        Mark a stage as started.
        
        Args:
            stage_name: Name of the stage
            stage_config: Stage configuration
        """
        self.current_state['current_stage'] = stage_name
        self.current_state['stage_states'][stage_name] = {
            'status': 'running',
            'start_time': datetime.now().isoformat(),
            'config': stage_config or {},
            'checkpoints': {}
        }
        
        self._save_state()
        
        # Log to database
        self.db_manager.log_pipeline_execution(
            pipeline_stage=stage_name,
            execution_date=date.today(),
            status='running',
            execution_details={'execution_id': self.execution_id}
        )
    
    def update_stage_checkpoint(self, stage_name: str, checkpoint_name: str, 
                              checkpoint_data: Dict[str, Any]):
        """
        Update a checkpoint within a stage for fine-grained recovery.
        
        Args:
            stage_name: Name of the stage
            checkpoint_name: Name of the checkpoint
            checkpoint_data: Data to store at checkpoint
        """
        if stage_name in self.current_state['stage_states']:
            self.current_state['stage_states'][stage_name]['checkpoints'][checkpoint_name] = {
                'timestamp': datetime.now().isoformat(),
                'data': checkpoint_data
            }
            self._save_state()
    
    def complete_stage(self, stage_name: str, records_processed: Optional[int] = None,
                      execution_details: Optional[Dict[str, Any]] = None):
        """
        Mark a stage as completed.
        
        Args:
            stage_name: Name of the stage
            records_processed: Number of records processed
            execution_details: Additional execution details
        """
        if stage_name in self.current_state['stage_states']:
            self.current_state['stage_states'][stage_name]['status'] = 'completed'
            self.current_state['stage_states'][stage_name]['end_time'] = datetime.now().isoformat()
            
            if records_processed is not None:
                self.current_state['stage_states'][stage_name]['records_processed'] = records_processed
        
        self.current_state['completed_stages'].append(stage_name)
        self.current_state['current_stage'] = None
        
        self._save_state()
        
        # Log to database
        details = execution_details or {}
        details['execution_id'] = self.execution_id
        
        self.db_manager.log_pipeline_execution(
            pipeline_stage=stage_name,
            execution_date=date.today(),
            status='success',
            records_processed=records_processed,
            execution_details=details
        )
    
    def fail_stage(self, stage_name: str, error_message: str,
                  execution_details: Optional[Dict[str, Any]] = None):
        """
        Mark a stage as failed.
        
        Args:
            stage_name: Name of the stage
            error_message: Error message
            execution_details: Additional execution details
        """
        if stage_name in self.current_state['stage_states']:
            self.current_state['stage_states'][stage_name]['status'] = 'failed'
            self.current_state['stage_states'][stage_name]['end_time'] = datetime.now().isoformat()
            self.current_state['stage_states'][stage_name]['error'] = error_message
        
        self.current_state['failed_stages'].append(stage_name)
        self.current_state['current_stage'] = None
        
        self._save_state()
        
        # Log to database
        details = execution_details or {}
        details['execution_id'] = self.execution_id
        
        self.db_manager.log_pipeline_execution(
            pipeline_stage=stage_name,
            execution_date=date.today(),
            status='failed',
            error_message=error_message,
            execution_details=details
        )
    
    def complete_execution(self):
        """Mark the entire pipeline execution as completed."""
        self.current_state['end_time'] = datetime.now().isoformat()
        self.current_state['status'] = 'completed'
        self._save_state()
        
        logger.info(f"Completed pipeline execution: {self.execution_id}")
    
    def can_recover(self, execution_id: str) -> bool:
        """
        Check if a pipeline execution can be recovered.
        
        Args:
            execution_id: Execution ID to check
            
        Returns:
            True if recovery is possible
        """
        state_file = self.state_dir / f"{execution_id}.json"
        return state_file.exists()
    
    def recover_execution(self, execution_id: str) -> Dict[str, Any]:
        """
        Recover a previous pipeline execution state.
        
        Args:
            execution_id: Execution ID to recover
            
        Returns:
            Recovered state
        """
        state_file = self.state_dir / f"{execution_id}.json"
        
        if not state_file.exists():
            raise ValueError(f"No state found for execution ID: {execution_id}")
        
        with open(state_file, 'r') as f:
            self.current_state = json.load(f)
        
        self.execution_id = execution_id
        self.start_time = datetime.fromisoformat(self.current_state['start_time'])
        
        logger.info(f"Recovered pipeline execution: {execution_id}")
        logger.info(f"Completed stages: {self.current_state['completed_stages']}")
        logger.info(f"Failed stages: {self.current_state['failed_stages']}")
        
        return self.current_state
    
    def get_resumable_stages(self) -> List[str]:
        """
        Get list of stages that can be resumed.
        
        Returns:
            List of stage names that haven't been completed
        """
        if not self.current_state:
            return []
        
        all_stages = self.current_state['stages']
        completed_stages = self.current_state['completed_stages']
        
        return [stage for stage in all_stages if stage not in completed_stages]
    
    def get_stage_checkpoint(self, stage_name: str, checkpoint_name: str) -> Optional[Dict[str, Any]]:
        """
        Get checkpoint data for a stage.
        
        Args:
            stage_name: Name of the stage
            checkpoint_name: Name of the checkpoint
            
        Returns:
            Checkpoint data if exists
        """
        if stage_name in self.current_state['stage_states']:
            checkpoints = self.current_state['stage_states'][stage_name].get('checkpoints', {})
            checkpoint = checkpoints.get(checkpoint_name)
            return checkpoint['data'] if checkpoint else None
        return None
    
    def _save_state(self):
        """Save current state to file."""
        if self.execution_id:
            state_file = self.state_dir / f"{self.execution_id}.json"
            with open(state_file, 'w') as f:
                json.dump(self.current_state, f, indent=2)
    
    def cleanup_old_states(self, days_to_keep: int = 7):
        """
        Clean up old state files.
        
        Args:
            days_to_keep: Number of days to keep state files
        """
        cutoff_date = datetime.now().timestamp() - (days_to_keep * 24 * 60 * 60)
        
        for state_file in self.state_dir.glob("*.json"):
            if state_file.stat().st_mtime < cutoff_date:
                state_file.unlink()
                logger.info(f"Cleaned up old state file: {state_file.name}")
    
    def get_execution_summary(self) -> Dict[str, Any]:
        """Get summary of current execution."""
        if not self.current_state:
            return {}
        
        total_stages = len(self.current_state['stages'])
        completed_stages = len(self.current_state['completed_stages'])
        failed_stages = len(self.current_state['failed_stages'])
        
        duration = None
        if self.start_time:
            end_time = datetime.fromisoformat(self.current_state.get('end_time', datetime.now().isoformat()))
            duration = (end_time - self.start_time).total_seconds()
        
        return {
            'execution_id': self.execution_id,
            'start_time': self.current_state['start_time'],
            'end_time': self.current_state.get('end_time'),
            'duration_seconds': duration,
            'total_stages': total_stages,
            'completed_stages': completed_stages,
            'failed_stages': failed_stages,
            'progress_percentage': (completed_stages / total_stages * 100) if total_stages > 0 else 0,
            'current_stage': self.current_state.get('current_stage'),
            'status': self.current_state.get('status', 'running')
        }