#!/usr/bin/env python3
"""
Security audit script to check for exposed credentials and sensitive data.
Run this before committing code to ensure no secrets are exposed.
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple

# Patterns that might indicate secrets
SECRET_PATTERNS = [
    # API Keys and tokens
    (r'(?i)(api[_-]?key|apikey|api[_-]?token|access[_-]?token|auth[_-]?token)\s*[:=]\s*["\'][\w\-\.]+["\']', 'API Key'),
    (r'(?i)(secret[_-]?key|secret[_-]?token|private[_-]?key)\s*[:=]\s*["\'][\w\-\.]+["\']', 'Secret Key'),
    
    # Passwords
    (r'(?i)(password|passwd|pwd|pass)\s*[:=]\s*["\'][^"\']+["\']', 'Password'),
    
    # AWS
    (r'AKIA[0-9A-Z]{16}', 'AWS Access Key ID'),
    (r'(?i)aws[_-]?secret[_-]?access[_-]?key\s*[:=]\s*["\'][^"\']+["\']', 'AWS Secret Key'),
    
    # URLs with credentials
    (r'(https?|ftp|postgresql|mysql|mongodb)://[^:]+:[^@]+@[^\s]+', 'URL with credentials'),
    
    # JWT tokens
    (r'eyJ[A-Za-z0-9\-_]+\.eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+', 'JWT Token'),
    
    # Private keys
    (r'-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----', 'Private Key'),
    
    # Generic secrets
    (r'(?i)(client[_-]?secret|consumer[_-]?secret)\s*[:=]\s*["\'][^"\']+["\']', 'Client Secret'),
]

# File patterns to check
INCLUDE_PATTERNS = ['*.py', '*.yml', '*.yaml', '*.json', '*.conf', '*.config', '*.ini', '*.env*', '*.sh']

# Paths to exclude
EXCLUDE_PATHS = [
    '.git', '.venv', 'venv', 'env', '__pycache__', 'node_modules',
    '.pytest_cache', '.mypy_cache', 'build', 'dist', '*.egg-info',
    'logs', 'archive', '.env.example', '.env.*.example'
]


def should_check_file(file_path: Path) -> bool:
    """Check if file should be scanned."""
    # Skip excluded paths
    for exclude in EXCLUDE_PATHS:
        if exclude in str(file_path):
            return False
    
    # Check if file matches include patterns
    for pattern in INCLUDE_PATTERNS:
        if file_path.match(pattern):
            return True
    
    return False


def scan_file(file_path: Path) -> List[Tuple[int, str, str]]:
    """Scan a file for potential secrets."""
    issues = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                # Skip comments and empty lines
                stripped = line.strip()
                if not stripped or stripped.startswith('#') or stripped.startswith('//'):
                    continue
                
                # Skip lines that use environment variables
                if 'os.getenv' in line or 'os.environ' in line or 'getenv(' in line:
                    continue
                
                # Check against patterns
                for pattern, desc in SECRET_PATTERNS:
                    if re.search(pattern, line):
                        issues.append((line_num, desc, line.strip()))
                        break
    
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
    
    return issues


def check_git_tracked_env_files():
    """Check if any .env files are tracked in git."""
    import subprocess
    
    try:
        result = subprocess.run(
            ['git', 'ls-files'],
            capture_output=True,
            text=True,
            check=True
        )
        
        tracked_files = result.stdout.strip().split('\n')
        env_files = [f for f in tracked_files if '.env' in f and '.example' not in f]
        
        return env_files
    except:
        return []


def main():
    """Run security audit."""
    print("🔍 Running security audit...\n")
    
    # Check for tracked .env files
    print("Checking for tracked .env files...")
    tracked_env = check_git_tracked_env_files()
    if tracked_env:
        print("❌ Found tracked .env files:")
        for f in tracked_env:
            print(f"   - {f}")
        print("   Run: git rm --cached <filename> to untrack them\n")
    else:
        print("✅ No .env files tracked in git\n")
    
    # Scan for secrets
    print("Scanning for potential secrets...")
    
    total_issues = 0
    files_with_issues = []
    
    for file_path in Path('.').rglob('*'):
        if file_path.is_file() and should_check_file(file_path):
            issues = scan_file(file_path)
            if issues:
                files_with_issues.append((file_path, issues))
                total_issues += len(issues)
    
    # Report results
    if files_with_issues:
        print(f"\n❌ Found {total_issues} potential security issues in {len(files_with_issues)} files:\n")
        
        for file_path, issues in files_with_issues:
            print(f"{file_path}:")
            for line_num, issue_type, line_content in issues:
                print(f"  Line {line_num}: {issue_type}")
                print(f"    {line_content[:100]}{'...' if len(line_content) > 100 else ''}")
            print()
        
        print("\n⚠️  Please review these issues before committing!")
        return 1
    else:
        print("\n✅ No potential secrets found!")
        return 0


if __name__ == "__main__":
    sys.exit(main())