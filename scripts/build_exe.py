"""
build.py - PyInstaller Build Script

Run this to create the Supply Chain Planner.exe
Usage: python build.py
"""

import os
import subprocess
import sys

def build():
    """Build the application using PyInstaller."""
    print("=" * 50)
    print("Building Supply Chain Planner")
    print("=" * 50)
    
    # Base directory
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "Supply Chain Planner",
        "--onefile",
        "--windowed",
        "--clean",
        # Add icon if it exists
        # "--icon", "app/resources/icon.ico",
        # Include data files
        "--add-data", f"examples;examples",
        # Hidden imports
        "--hidden-import", "PyQt6.QtCore",
        "--hidden-import", "PyQt6.QtWidgets", 
        "--hidden-import", "PyQt6.QtGui",
        # Entry point
        os.path.join(base_dir, "app", "main.py")
    ]
    
    print(f"\nRunning: {' '.join(cmd)}\n")
    
    result = subprocess.run(cmd, cwd=base_dir)
    
    if result.returncode == 0:
        print("\n" + "=" * 50)
        print("✅ Build successful!")
        print(f"   Output: {os.path.join(base_dir, 'dist', 'Supply Chain Planner.exe')}")
        print("=" * 50)
    else:
        print("\n❌ Build failed!")
        sys.exit(1)


if __name__ == "__main__":
    build()
