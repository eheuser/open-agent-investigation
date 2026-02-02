import sys
import os

print("=" * 70)
print("Test Setup Verification")
print("=" * 70)

# Check Python version
print(f"\n1. Python Version: {sys.version}")
if sys.version_info < (3, 10):
    print("   ❌ ERROR: Python 3.11+ required")
    sys.exit(1)
else:
    print("   ✓ OK")

# Check if we're in the right directory
print(f"\n2. Current Directory: {os.getcwd()}")
if not os.path.exists("app"):
    print("   ❌ ERROR: Run this from the 'api' directory")
    sys.exit(1)
else:
    print("   ✓ OK")

# Check required packages
print("\n3. Checking Required Packages:")
required_packages = [
    ("pytest", "pytest"),
    ("pytest-asyncio", "pytest_asyncio"),
    ("factory-boy", "factory"),
    ("faker", "faker"),
    ("httpx", "httpx"),
]

missing = []
for display_name, import_name in required_packages:
    try:
        __import__(import_name)
        print(f"   ✓ {display_name}")
    except ImportError:
        print(f"   ❌ {display_name} - NOT FOUND")
        missing.append(display_name)

if missing:
    print(f"\n❌ Missing packages: {', '.join(missing)}")
    print("\nInstall with:")
    print("  pip install -r tests/requirements-test.txt")
    sys.exit(1)

# Check test files exist
print("\n4. Checking Test Files:")
test_files = [
    "tests/conftest.py",
    "tests/pytest.ini",
    "tests/factories.py",
    "tests/unit/core/test_security.py",
    "tests/unit/core/test_config.py",
    "tests/unit/models/test_user.py",
]

for test_file in test_files:
    if os.path.exists(test_file):
        print(f"   ✓ {test_file}")
    else:
        print(f"   ❌ {test_file} - NOT FOUND")

# Try to import app modules
print("\n5. Checking App Imports:")
try:
    from app.auth import hash_password, verify_password

    print("   ✓ app.auth")
except ImportError as e:
    print(f"   ❌ app.auth - {e}")

try:
    from app.models.user import User, UserRole

    print("   ✓ app.models.user")
except ImportError as e:
    print(f"   ❌ app.models.user - {e}")

try:
    from app.core.config import settings

    print("   ✓ app.core.config")
except ImportError as e:
    print(f"   ❌ app.core.config - {e}")

print("\n" + "=" * 70)
print("✓ Setup verification complete!")
print("=" * 70)
print("\nNext steps:")
print("  1. Run unit tests:  pytest tests/ -v -m unit")
print("  2. Run with coverage: pytest tests/ -v -m unit --cov=app")
print("  3. Run specific test: pytest tests/unit/core/test_security.py -v")
