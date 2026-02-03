"""
Tests for the FieldResolver - expression parsing and field mapping.
"""
import pytest
from app.agent.execution.field_resolver import (
    FieldResolver, 
    InputFieldSpec, 
    ResolutionError,
    resolve_artifact_inputs
)


class TestFieldResolver:
    """Unit tests for FieldResolver."""

    def test_resolve_literal_value(self):
        """Test that non-expression values are passed through as literals."""
        resolver = FieldResolver()
        state = {"messages": []}
        config = {"input_mappings": {"value": 42, "text": "hello"}}
        
        result = resolver.resolve_inputs(state, config)
        
        assert result["value"] == 42
        assert result["text"] == "hello"

    def test_resolve_state_field(self):
        """Test resolving {{ state.field }} expressions."""
        resolver = FieldResolver()
        state = {"messages": [{"role": "user", "content": "hello"}], "context": {"key": "value"}}
        config = {"input_mappings": {"msgs": "{{ state.messages }}", "ctx": "{{ state.context }}"}}
        
        result = resolver.resolve_inputs(state, config)
        
        assert result["msgs"] == [{"role": "user", "content": "hello"}]
        assert result["ctx"] == {"key": "value"}

    def test_resolve_shorthand_field(self):
        """Test resolving {{ messages }} shorthand (without state. prefix)."""
        resolver = FieldResolver()
        state = {"messages": [{"role": "user", "content": "test"}]}
        config = {"input_mappings": {"msgs": "{{ messages }}"}}
        
        result = resolver.resolve_inputs(state, config)
        
        assert result["msgs"] == [{"role": "user", "content": "test"}]

    def test_resolve_array_index(self):
        """Test resolving array indices like messages[-1]."""
        resolver = FieldResolver()
        state = {"messages": [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "second"},
            {"role": "user", "content": "third"}
        ]}
        config = {"input_mappings": {"last": "{{ messages[-1] }}", "first": "{{ messages[0] }}"}}
        
        result = resolver.resolve_inputs(state, config)
        
        assert result["last"]["content"] == "third"
        assert result["first"]["content"] == "first"

    def test_resolve_nested_field(self):
        """Test resolving nested paths like messages[-1].content."""
        resolver = FieldResolver()
        state = {"messages": [
            {"role": "user", "content": "hello world"}
        ]}
        config = {"input_mappings": {"query": "{{ messages[-1].content }}"}}
        
        result = resolver.resolve_inputs(state, config)
        
        assert result["query"] == "hello world"

    def test_resolve_upstream_node_output(self):
        """Test resolving {{ upstream.node_id.field }} expressions."""
        resolver = FieldResolver()
        state = {
            "messages": [],
            "_node_outputs": {
                "ingest_node": {"documents": [{"text": "doc1"}, {"text": "doc2"}]},
                "transform_node": {"result": "transformed"}
            }
        }
        config = {"input_mappings": {
            "docs": "{{ upstream.ingest_node.documents }}",
            "data": "{{ upstream.transform_node.result }}"
        }}
        
        result = resolver.resolve_inputs(state, config)
        
        assert result["docs"] == [{"text": "doc1"}, {"text": "doc2"}]
        assert result["data"] == "transformed"

    def test_resolve_with_defaults(self):
        """Test that default values are used when no mapping is provided."""
        resolver = FieldResolver()
        state = {"messages": []}
        config = {}  # No input_mappings
        
        input_specs = [
            InputFieldSpec(name="required_field", type="string", required=True),
            InputFieldSpec(name="optional_field", type="string", required=False, default="default_value"),
        ]
        
        result = resolver.resolve_inputs(state, config, input_specs)
        
        assert result["required_field"] is None  # Missing required field
        assert result["optional_field"] == "default_value"

    def test_validate_required_fields(self):
        """Test validation catches missing required fields."""
        resolver = FieldResolver()
        
        input_specs = [
            InputFieldSpec(name="required_field", type="string", required=True),
            InputFieldSpec(name="optional_field", type="string", required=False),
        ]
        resolved = {"required_field": None, "optional_field": "value"}
        
        errors = resolver.validate_inputs(resolved, input_specs)
        
        assert len(errors) == 1
        assert errors[0].field == "required_field"
        assert "missing" in errors[0].message.lower()

    def test_strict_mode_error_severity(self):
        """Test that strict mode uses 'error' severity."""
        resolver = FieldResolver(strict_mode=True)
        
        input_specs = [InputFieldSpec(name="field", type="string", required=True)]
        resolved = {"field": None}
        
        errors = resolver.validate_inputs(resolved, input_specs)
        
        assert errors[0].severity == "error"

    def test_lenient_mode_warning_severity(self):
        """Test that lenient mode uses 'warning' severity."""
        resolver = FieldResolver(strict_mode=False)
        
        input_specs = [InputFieldSpec(name="field", type="string", required=True)]
        resolved = {"field": None}
        
        errors = resolver.validate_inputs(resolved, input_specs)
        
        assert errors[0].severity == "warning"

    def test_string_interpolation(self):
        """Test embedding expressions within larger strings."""
        resolver = FieldResolver()
        state = {"name": "Alice", "count": 5}
        config = {"input_mappings": {
            "greeting": "Hello {{ name }}, you have {{ count }} items"
        }}
        
        result = resolver.resolve_inputs(state, config)
        
        assert result["greeting"] == "Hello Alice, you have 5 items"

    def test_missing_path_returns_none(self):
        """Test that missing paths return None gracefully."""
        resolver = FieldResolver()
        state = {"messages": []}
        config = {"input_mappings": {
            "missing": "{{ state.nonexistent.field }}",
            "out_of_range": "{{ messages[99] }}"
        }}
        
        result = resolver.resolve_inputs(state, config)
        
        assert result["missing"] is None
        assert result["out_of_range"] is None


class TestResolveArtifactInputs:
    """Tests for the convenience wrapper function."""
    
    def test_basic_resolution(self):
        """Test basic usage of resolve_artifact_inputs."""
        state = {"query": "test query", "context": {"key": "value"}}
        config = {"input_mappings": {"q": "{{ query }}"}}
        artifact_inputs = [
            {"name": "q", "type": "string", "required": True}
        ]
        
        result = resolve_artifact_inputs(state, config, artifact_inputs)
        
        assert result["q"] == "test query"

    def test_pass_through_mode(self):
        """Test that without artifact_inputs, it uses pass-through mode."""
        state = {"messages": [{"content": "hello"}]}
        config = {"input_mappings": {"msgs": "{{ messages }}"}}
        
        result = resolve_artifact_inputs(state, config, artifact_inputs=None)
        
        assert result["msgs"] == [{"content": "hello"}]
