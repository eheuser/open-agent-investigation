import sys
import os
from passlib.context import CryptContext

# Initialize password hasher (same as in api/app/auth.py)
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a password using Argon2."""
    return pwd_context.hash(password)


def generate_sql(password_hash: str) -> str:
    """Generate SQL to update admin password."""
    return f"""
-- Update admin password
UPDATE users 
SET password_hash = '{password_hash}'
WHERE username = 'admin';

-- Verify update
SELECT username, role, created_at 
FROM users 
WHERE username = 'admin';
"""


def main():
    if len(sys.argv) < 2:
        print("Usage: python change_admin_password.py <new_password>")
        print("")
        print("Example:")
        print("  python change_admin_password.py 'MySecureP@ssw0rd!'")
        print("")
        print("The script will:")
        print("  1. Hash the password using Argon2")
        print("  2. Generate SQL to update the database")
        print("  3. Print instructions for applying the change")
        sys.exit(1)

    new_password = sys.argv[1]

    # Validate password strength
    if len(new_password) < 12:
        print("ERROR: Password must be at least 12 characters long")
        sys.exit(1)

    if not any(c.isupper() for c in new_password):
        print("WARNING: Password should contain uppercase letters")

    if not any(c.islower() for c in new_password):
        print("WARNING: Password should contain lowercase letters")

    if not any(c.isdigit() for c in new_password):
        print("WARNING: Password should contain numbers")

    if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in new_password):
        print("WARNING: Password should contain special characters")

    print("Hashing password...")
    password_hash = hash_password(new_password)
    
    sql = generate_sql(password_hash)
    
    print("")
    print("=" * 70)
    print("SQL UPDATE STATEMENT")
    print("=" * 70)
    print(sql)
    print("=" * 70)
    print("")
    print("To apply this change, run ONE of the following:")
    print("")
    print("Option 1 - Direct execution:")
    print("  docker exec -i <db_container> psql -U postgres -d open_agent_inv <<EOF")
    print(f"  {sql.strip()}")
    print("  EOF")
    print("")
    print("Option 2 - Via file:")
    print("  Save the SQL above to 'update_admin.sql', then:")
    print("  docker exec -i <db_container> psql -U postgres -d open_agent_inv < update_admin.sql")
    print("")
    print("Option 3 - Interactive psql:")
    print("  docker exec -it <db_container> psql -U postgres -d open_agent_inv")
    print("  Then paste the SQL above")
    print("")
    print("WARNING: SECURITY NOTE: Keep this password hash secure!")
    print("")


if __name__ == "__main__":
    main()
