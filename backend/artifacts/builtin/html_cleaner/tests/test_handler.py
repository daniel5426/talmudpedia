"""
Tests for HTML Cleaner artifact.
"""
import pytest
from artifacts.builtin.html_cleaner.handler import execute

def test_html_cleaner_basic(artifact_context):
    html = "<html><body><h1>Title</h1><p>Hello World</p></body></html>"
    context = artifact_context(data=[{"text": html}], config={})
    
    result = execute(context)
    
    assert len(result) == 1
    assert result[0]["text"] == "Title Hello World"

def test_html_cleaner_remove_scripts(artifact_context):
    html = "<div><script>alert('bad')</script><span>Good</span></div>"
    # Default is remove_scripts=True
    context = artifact_context(data=[{"text": html}], config={"remove_scripts": True})
    
    result = execute(context)
    assert "alert" not in result[0]["text"]
    assert "Good" in result[0]["text"]

def test_html_cleaner_preserve_links(artifact_context):
    html = "<a href='https://google.com'>Google</a>"
    context = artifact_context(data=[{"text": html}], config={"preserve_links": True})
    
    result = execute(context)
    assert "Google (https://google.com)" in result[0]["text"]
