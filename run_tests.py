#!/usr/bin/env python3
"""
Test runner for the telegram-groupfactory application.
"""
import subprocess
import sys

def run_tests():
    """Run tests using pytest."""
    try:
        # Run pytest with verbose output
        result = subprocess.run([
            sys.executable, '-m', 'pytest', 
            '-v', 
            '--tb=short',
            'test_main.py'
        ], check=True, capture_output=True, text=True)
        
        print("Tests passed successfully!")
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print("Tests failed!")
        print("STDOUT:", e.stdout)
        print("STDERR:", e.stderr)
        return False

if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)