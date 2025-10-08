"""
Integration tests for the FSM system.
Tests the complete FSM functionality including models, state management,
and API endpoints.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from django.test import TestCase
from fsm.models import AnnotationState, ProjectState, TaskState
from fsm.state_manager import get_state_manager
from projects.tests.factories import ProjectFactory
from tasks.tests.factories import AnnotationFactory, TaskFactory
from users.tests.factories import UserFactory


class TestFSMModels(TestCase):
    """Test FSM model functionality"""

    def setUp(self):
        self.user = UserFactory(email='test@example.com')
        self.project = ProjectFactory(created_by=self.user)
        self.task = TaskFactory(project=self.project, data={'text': 'test'})

        # Clear cache to ensure tests start with clean state
        from django.core.cache import cache

        cache.clear()

    def test_task_state_creation(self):
        """Test TaskState creation and basic functionality"""
        task_state = TaskState.objects.create(
            task=self.task,
            project_id=self.task.project_id,  # Denormalized from task.project_id
            state='CREATED',
            triggered_by=self.user,
            reason='Task created for testing',
        )

        # Check basic fields
        assert task_state.state == 'CREATED'
        assert task_state.task == self.task
        assert task_state.triggered_by == self.user

        # Check UUID7 functionality
        assert task_state.id.version == 7
        assert isinstance(task_state.timestamp_from_uuid, datetime)

        # Check string representation
        str_repr = str(task_state)
        assert 'Task' in str_repr
        assert 'CREATED' in str_repr

    def test_annotation_state_creation(self):
        """Test AnnotationState creation and basic functionality"""
        annotation = AnnotationFactory(task=self.task, completed_by=self.user, result=[])

        annotation_state = AnnotationState.objects.create(
            annotation=annotation,
            task_id=annotation.task.id,  # Denormalized from annotation.task_id
            project_id=annotation.task.project_id,  # Denormalized from annotation.task.project_id
            completed_by_id=annotation.completed_by.id if annotation.completed_by else None,  # Denormalized
            state='DRAFT',
            triggered_by=self.user,
            reason='Annotation draft created',
        )

        # Check basic fields
        assert annotation_state.state == 'DRAFT'
        assert annotation_state.annotation == annotation

        # Check terminal state property
        assert not annotation_state.is_terminal_state

        # Test completed state
        completed_state = AnnotationState.objects.create(
            annotation=annotation,
            task_id=annotation.task.id,
            project_id=annotation.task.project_id,
            completed_by_id=annotation.completed_by.id if annotation.completed_by else None,
            state='COMPLETED',
            triggered_by=self.user,
        )
        assert completed_state.is_terminal_state

    def test_project_state_creation(self):
        """Test ProjectState creation and basic functionality"""
        project_state = ProjectState.objects.create(
            project=self.project, state='CREATED', triggered_by=self.user, reason='Project created for testing'
        )

        # Check basic fields
        assert project_state.state == 'CREATED'
        assert project_state.project == self.project

        # Test terminal state
        assert not project_state.is_terminal_state

        completed_state = ProjectState.objects.create(project=self.project, state='COMPLETED', triggered_by=self.user)
        assert completed_state.is_terminal_state


class TestStateManager(TestCase):
    """Test StateManager functionality with mocked transaction support"""

    def setUp(self):
        self.user = UserFactory(email='test@example.com')
        self.project = ProjectFactory(created_by=self.user)
        self.task = TaskFactory(project=self.project, data={'text': 'test'})
        self.StateManager = get_state_manager()

        # Clear cache to ensure tests start with clean state
        from django.core.cache import cache

        cache.clear()

        # Ensure registry is properly initialized for TaskState
        from fsm.models import TaskState
        from fsm.registry import state_model_registry

        if not state_model_registry.get_model('task'):
            state_model_registry.register_model('task', TaskState)

    def test_get_current_state_empty(self):
        """Test getting current state when no states exist"""
        current_state = self.StateManager.get_current_state_value(self.task)
        assert current_state is None

    @patch('django.db.transaction.on_commit')
    def test_transition_state(self, mock_on_commit):
        """Test state transition functionality with mocked transaction.on_commit"""
        from django.core.cache import cache

        cache.clear()

        # Mock transaction.on_commit to immediately execute the callback
        def execute_callback(callback):
            callback()

        mock_on_commit.side_effect = execute_callback

        # Initial transition
        success = self.StateManager.transition_state(
            entity=self.task,
            new_state='CREATED',
            user=self.user,
            transition_name='create_task',
            reason='Initial task creation',
        )

        assert success
        # Verify transaction.on_commit was called once for cache update
        assert mock_on_commit.call_count == 1

        # Check current state - should work with mocked cache update
        current_state = self.StateManager.get_current_state_value(self.task)
        assert current_state == 'CREATED'

        # Another transition
        success = self.StateManager.transition_state(
            entity=self.task,
            new_state='IN_PROGRESS',
            user=self.user,
            transition_name='start_work',
            context={'started_by': 'user'},
        )

        assert success
        # Verify transaction.on_commit was called again (total 2 times)
        assert mock_on_commit.call_count == 2

        current_state = self.StateManager.get_current_state_value(self.task)
        assert current_state == 'IN_PROGRESS'

    @patch('django.db.transaction.on_commit')
    def test_get_current_state_object(self, mock_on_commit):
        """Test getting current state object with full details"""
        from django.core.cache import cache

        cache.clear()

        # Mock transaction.on_commit to immediately execute the callback
        def execute_callback(callback):
            callback()

        mock_on_commit.side_effect = execute_callback

        # Create some state transitions
        self.StateManager.transition_state(entity=self.task, new_state='CREATED', user=self.user)
        self.StateManager.transition_state(
            entity=self.task, new_state='IN_PROGRESS', user=self.user, context={'test': 'data'}
        )

        # Verify transaction.on_commit was called twice (once per transition)
        assert mock_on_commit.call_count == 2

        current_state_obj = self.StateManager.get_current_state_object(self.task)

        assert current_state_obj is not None
        assert current_state_obj.state == 'IN_PROGRESS'
        assert current_state_obj.previous_state == 'CREATED'
        assert current_state_obj.triggered_by == self.user
        assert current_state_obj.context_data == {'test': 'data'}

    @patch('django.db.transaction.on_commit')
    def test_get_state_history(self, mock_on_commit):
        """Test state history retrieval"""
        from django.core.cache import cache

        cache.clear()

        # Mock transaction.on_commit to immediately execute the callback
        def execute_callback(callback):
            callback()

        mock_on_commit.side_effect = execute_callback

        transitions = [('CREATED', 'create_task'), ('IN_PROGRESS', 'start_work'), ('COMPLETED', 'finish_work')]

        for state, transition in transitions:
            self.StateManager.transition_state(
                entity=self.task, new_state=state, user=self.user, transition_name=transition
            )

        # Verify transaction.on_commit was called 3 times (once per transition)
        assert mock_on_commit.call_count == 3

        history = self.StateManager.get_state_history(self.task, limit=10)

        # Should have 3 state records
        assert len(history) == 3

        # Should be ordered by most recent first (UUID7 ordering)
        states = [h.state for h in history]
        assert states == ['COMPLETED', 'IN_PROGRESS', 'CREATED']

        # Check previous states are set correctly
        assert history[2].previous_state is None  # First state has no previous
        assert history[1].previous_state == 'CREATED'
        assert history[0].previous_state == 'IN_PROGRESS'

    @patch('django.db.transaction.on_commit')
    def test_get_states_in_time_range(self, mock_on_commit):
        """Test time-based state queries using UUID7"""
        from django.core.cache import cache

        cache.clear()

        # Mock transaction.on_commit to immediately execute the callback
        def execute_callback(callback):
            callback()

        mock_on_commit.side_effect = execute_callback

        before_time = datetime.now(timezone.utc) - timedelta(seconds=1)

        # Create some states
        self.StateManager.transition_state(entity=self.task, new_state='CREATED', user=self.user)
        self.StateManager.transition_state(entity=self.task, new_state='IN_PROGRESS', user=self.user)

        # Verify transaction.on_commit was called twice (once per transition)
        assert mock_on_commit.call_count == 2

        # Record time after creating states
        after_time = datetime.now(timezone.utc) + timedelta(seconds=1)

        # Query states in time range
        states_in_range = self.StateManager.get_states_in_time_range(self.task, before_time, after_time)

        # Should find both states
        assert len(states_in_range) == 2

    @patch('django.db.transaction.on_commit')
    def test_transaction_on_commit_success_case(self, mock_on_commit):
        """Test that transaction.on_commit is called exactly once per successful transition"""
        from django.core.cache import cache

        cache.clear()

        # Track callback executions
        callbacks_executed = []

        def track_and_execute(callback):
            callbacks_executed.append(callback)
            callback()  # Execute the callback

        mock_on_commit.side_effect = track_and_execute

        # Perform a successful transition
        success = self.StateManager.transition_state(
            entity=self.task,
            new_state='CREATED',
            user=self.user,
            transition_name='create_task',
            reason='Initial task creation',
        )

        # Verify success and transaction.on_commit was called
        assert success
        assert mock_on_commit.call_count == 1
        assert len(callbacks_executed) == 1

        # Verify the cache was properly updated by executing the callback
        current_state = self.StateManager.get_current_state_value(self.task)
        assert current_state == 'CREATED'

        # Perform another successful transition
        success = self.StateManager.transition_state(
            entity=self.task,
            new_state='IN_PROGRESS',
            user=self.user,
            transition_name='start_work',
        )

        assert success
        assert mock_on_commit.call_count == 2
        assert len(callbacks_executed) == 2

        current_state = self.StateManager.get_current_state_value(self.task)
        assert current_state == 'IN_PROGRESS'

    @patch('django.db.transaction.on_commit')
    @patch('fsm.state_manager.get_state_model_for_entity')
    def test_transaction_on_commit_failure_case(self, mock_get_state_model, mock_on_commit):
        """Test that transaction.on_commit is NOT called when transition fails"""
        from django.core.cache import cache

        cache.clear()

        # Mock get_state_model_for_entity to return None (no state model found)
        mock_get_state_model.return_value = None

        # Attempt a transition that should fail due to missing state model
        with pytest.raises(Exception):  # Should raise StateManagerError
            self.StateManager.transition_state(
                entity=self.task,
                new_state='CREATED',
                user=self.user,
                transition_name='create_task',
                reason='This should fail',
            )

        # Verify transaction.on_commit was NOT called since transition failed
        assert mock_on_commit.call_count == 0

        # Verify cache was not updated (should raise exception)
        with pytest.raises(Exception):  # Should raise StateManagerError
            self.StateManager.get_current_state_value(self.task)

    @patch('django.db.transaction.on_commit')
    @patch('fsm.models.TaskState.objects.create')
    def test_transaction_on_commit_database_failure_case(self, mock_create, mock_on_commit):
        """Test that transaction.on_commit is NOT called when database operation fails"""
        from django.core.cache import cache

        cache.clear()

        # Mock database create operation to fail
        mock_create.side_effect = Exception('Database constraint violation')

        # Attempt a transition that should fail due to database error
        with pytest.raises(Exception):  # Should raise StateManagerError
            self.StateManager.transition_state(
                entity=self.task,
                new_state='CREATED',
                user=self.user,
                transition_name='create_task',
                reason='This should fail in DB',
            )

        # Verify transaction.on_commit was NOT called since transaction failed
        assert mock_on_commit.call_count == 0

        # Verify cache was deleted due to failure (cache.delete should be called)
        current_state = self.StateManager.get_current_state_value(self.task)
        assert current_state is None

    @patch('django.db.transaction.on_commit')
    def test_transaction_on_commit_callback_content(self, mock_on_commit):
        """Test that the transaction.on_commit callback properly updates the cache"""
        from django.core.cache import cache

        cache.clear()

        # Capture the callback without executing it
        captured_callbacks = []
        mock_on_commit.side_effect = lambda callback: captured_callbacks.append(callback)

        # Perform a transition
        success = self.StateManager.transition_state(
            entity=self.task,
            new_state='CREATED',
            user=self.user,
        )

        assert success
        assert len(captured_callbacks) == 1

        # Before executing callback, cache should be empty
        cache_key = self.StateManager.get_cache_key(self.task)
        cached_state = cache.get(cache_key)
        assert cached_state is None

        # Execute the callback manually
        captured_callbacks[0]()

        # After callback execution, cache should be updated
        cached_state = cache.get(cache_key)
        assert cached_state == 'CREATED'

        # Verify get_current_state_value uses the cached value
        current_state = self.StateManager.get_current_state_value(self.task)
        assert current_state == 'CREATED'
