"""
Phase 1: Environment & Dependency Verification Script
Checks Python version, virtual environment, and all core libraries.
"""
import sys

def verify_environment():
    print("=" * 60)
    print("PHASE 1: ENVIRONMENT & CORE DEPENDENCY VERIFICATION")
    print("=" * 60)
    
    # 1. Python version check
    py_ver = sys.version.split()[0]
    print(f"[*] Python Version: {py_ver}")
    if sys.version_info < (3, 9) or sys.version_info >= (3, 12):
        print("    [!] Warning: TenSEAL is best supported on Python 3.9 - 3.11.")
    else:
        print("    [+] Python version is compatible with TenSEAL.")

    # 2. Virtual environment check
    in_venv = sys.prefix != sys.base_prefix
    print(f"[*] Active Virtual Environment: {'Yes (' + sys.prefix + ')' if in_venv else 'No (Running in global Python)'}")

    # 3. Core Libraries Check
    libraries = [
        ("tenseal", "TenSEAL (CKKS Homomorphic Encryption)"),
        ("pandas", "Pandas (Streaming Dataset Handling)"),
        ("numpy", "NumPy (Numerical Processing)"),
        ("matplotlib", "Matplotlib (Real-time Visualization)"),
        ("kafka", "kafka-python (Apache Kafka Streaming Client)"),
    ]

    all_passed = True
    for mod_name, desc in libraries:
        try:
            mod = __import__(mod_name)
            ver = getattr(mod, "__version__", "installed")
            print(f"    [+] {desc}: version {ver}")
        except ImportError as e:
            print(f"    [-] FAILED to import {mod_name} ({desc}): {e}")
            all_passed = False

    print("=" * 60)
    if all_passed:
        print("[SUCCESS] All Phase 1 environment requirements are met!")
    else:
        print("[FAILURE] Some dependencies are missing.")
    print("=" * 60)

if __name__ == "__main__":
    verify_environment()
