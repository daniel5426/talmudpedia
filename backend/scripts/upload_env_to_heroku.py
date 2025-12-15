#!/usr/bin/env python3
import os
import subprocess
import sys
import json
import re
from pathlib import Path

def load_env_file(env_path):
    try:
        from dotenv import dotenv_values
        env_vars = dotenv_values(env_path)
        return {k: str(v) for k, v in env_vars.items() if v is not None}
    except ImportError:
        pass
    
    env_vars = {}
    with open(env_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].rstrip('\r\n')
        original_line = line
        
        if not line or line.strip().startswith('#'):
            i += 1
            continue
        
        if '=' not in line:
            i += 1
            continue
        
        key, value_part = line.split('=', 1)
        key = key.strip()
        
        if not key:
            i += 1
            continue
        
        value = value_part
        
        if value.startswith('"'):
            value = value[1:]
            quote_char = '"'
        elif value.startswith("'"):
            value = value[1:]
            quote_char = "'"
        else:
            quote_char = None
        
        if quote_char:
            if value.endswith(quote_char) and value.count(quote_char) == 1:
                value = value[:-1]
            else:
                i += 1
                collected_lines = [value]
                while i < len(lines):
                    next_line = lines[i].rstrip('\r\n')
                    collected_lines.append(next_line)
                    if next_line.endswith(quote_char):
                        value = '\n'.join(collected_lines)[:-1]
                        break
                    i += 1
                else:
                    value = '\n'.join(collected_lines)
        elif value.strip().startswith('{') or value.strip().startswith('['):
            json_lines = [value]
            i += 1
            brace_count = value.count('{') + value.count('[') - value.count('}') - value.count(']')
            
            while i < len(lines) and brace_count > 0:
                next_line = lines[i].rstrip('\r\n')
                json_lines.append(next_line)
                brace_count += next_line.count('{') + next_line.count('[')
                brace_count -= next_line.count('}') + next_line.count(']')
                i += 1
            
            value = '\n'.join(json_lines).strip()
            
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
        else:
            value = value.strip()
            i += 1
        
        if key:
            env_vars[key] = value
    
    return env_vars

def set_heroku_config(env_vars, app_name=None):
    heroku_cmd = ['heroku', 'config:set']
    if app_name:
        heroku_cmd.extend(['--app', app_name])
    
    for key, value in env_vars.items():
        if not key:
            continue
        
        import shlex
        escaped_value = shlex.quote(value)
        cmd = heroku_cmd + [f'{key}={escaped_value}']
        print(f"Setting {key}...")
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(f"✓ Set {key}")
        except subprocess.CalledProcessError as e:
            print(f"✗ Failed to set {key}: {e}")
            if e.stderr:
                print(f"  Error: {e.stderr}")
            return False
    return True

def main():
    backend_dir = Path(__file__).parent.parent
    env_path = backend_dir / '.env'
    
    if not env_path.exists():
        env_path = backend_dir.parent / '.env'
    
    if not env_path.exists():
        print(f"Error: .env file not found at {env_path}")
        print("Please make sure your .env file exists in the backend directory or project root")
        sys.exit(1)
    
    print(f"Loading environment variables from {env_path}")
    env_vars = load_env_file(env_path)
    
    if not env_vars:
        print("No environment variables found in .env file")
        sys.exit(1)
    
    print(f"\nFound {len(env_vars)} environment variables:")
    for key in env_vars.keys():
        print(f"  - {key}")
    
    app_name = sys.argv[1] if len(sys.argv) > 1 else None
    if app_name:
        print(f"\nUploading to Heroku app: {app_name}")
    else:
        print("\nUploading to default Heroku app")
        print("(To specify an app: python upload_env_to_heroku.py your-app-name)")
    
    confirm = input("\nProceed with uploading? (yes/no): ").strip().lower()
    if confirm not in ['yes', 'y']:
        print("Cancelled")
        sys.exit(0)
    
    print("\nUploading environment variables to Heroku...")
    success = set_heroku_config(env_vars, app_name)
    
    if success:
        print("\n✓ All environment variables uploaded successfully!")
        print("\nYou can verify with: heroku config")
    else:
        print("\n✗ Some environment variables failed to upload")
        sys.exit(1)

if __name__ == '__main__':
    main()

