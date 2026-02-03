"""
HTML Cleaner Artifact - Clean HTML content and extract plain text.

This is the first artifact-based operator, migrated from the hardcoded
HTMLCleanerExecutor in operator_executor.py.
"""
from typing import Any, Dict, List
import re

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


def execute(context) -> List[Dict[str, Any]]:
    """
    Execute the HTML cleaning operation.
    
    Args:
        context: ExecutionContext with:
            - input_data: List of documents (dicts with 'text' or 'content' key)
            - config: Dict with remove_scripts, remove_styles, preserve_links
            - metadata: Optional execution metadata
    
    Returns:
        List of documents with cleaned text.
    """
    input_data = context.input_data
    config = context.config
    
    remove_scripts = config.get("remove_scripts", True)
    remove_styles = config.get("remove_styles", True)
    preserve_links = config.get("preserve_links", False)
    
    documents = input_data if isinstance(input_data, list) else [input_data]
    result = []
    
    for doc in documents:
        if isinstance(doc, dict):
            text = doc.get("text", doc.get("content", ""))
        else:
            text = str(doc)
        
        cleaned_text = _clean_html(text, remove_scripts, remove_styles, preserve_links)
        
        if isinstance(doc, dict):
            doc["text"] = cleaned_text
            result.append(doc)
        else:
            result.append({"text": cleaned_text})
    
    return result


def _clean_html(html: str, remove_scripts: bool, remove_styles: bool, preserve_links: bool) -> str:
    """Clean HTML using BeautifulSoup if available, otherwise regex fallback."""
    if HAS_BS4:
        return _clean_with_bs4(html, remove_scripts, remove_styles, preserve_links)
    else:
        return _clean_with_regex(html)


def _clean_with_bs4(html: str, remove_scripts: bool, remove_styles: bool, preserve_links: bool) -> str:
    """Clean HTML using BeautifulSoup."""
    soup = BeautifulSoup(html, "html.parser")
    
    if remove_scripts:
        for script in soup.find_all("script"):
            script.decompose()
    
    if remove_styles:
        for style in soup.find_all("style"):
            style.decompose()
    
    if preserve_links:
        for a in soup.find_all("a", href=True):
            a.replace_with(f"{a.get_text()} ({a['href']})")
    
    return soup.get_text(separator=" ", strip=True)


def _clean_with_regex(html: str) -> str:
    """Fallback regex-based HTML cleaning."""
    # Remove script and style tags
    cleaned = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r'<style[^>]*>.*?</style>', ' ', cleaned, flags=re.DOTALL | re.IGNORECASE)
    # Remove tags and replace with space to avoid merging words
    cleaned = re.sub(r'<[^>]+>', ' ', cleaned)
    # Normalize whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned
