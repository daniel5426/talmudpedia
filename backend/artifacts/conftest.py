import pytest
import sys
import os

# Ensure backend root is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@pytest.fixture
def artifact_context():
    """Fixture to provide an ArtifactContext for testing operators."""
    from app.rag.pipeline.operator_executor import ArtifactContext
    
    def _create_context(data=None, config=None, metadata=None):
        return ArtifactContext(
            input_data=data or [],
            config=config or {},
            metadata=metadata or {}
        )
    
    return _create_context
