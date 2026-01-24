# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

### How to Report

1. **Email**: Send details to the repository owner (see GitHub profile)
2. **Include**:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

### What to Expect

- **Acknowledgment**: Within 48 hours
- **Updates**: Regular progress updates
- **Timeline**: We aim to patch critical issues within 7 days
- **Credit**: You'll be credited in the security advisory (unless you prefer to remain anonymous)

## Security Best Practices

### For Users

- **Change default credentials** immediately after installation
- **Use strong passwords** (12+ characters, mixed case, numbers, symbols)
- **Enable SSL/TLS** in production
- **Keep dependencies updated** (use Dependabot alerts)
- **Limit network exposure** (use firewalls, VPNs)
- **Encrypt API keys** (use the built-in encryption)
- **Regular backups** of investigation data
- **Monitor logs** for suspicious activity

### For Developers

- **Never commit secrets** (use `.gitignore`)
- **Validate all inputs** (prevent injection attacks)
- **Use parameterized queries** (prevent SQL injection)
- **Sanitize outputs** (prevent XSS)
- **Follow least privilege** (minimize permissions)
- **Keep dependencies updated** (run `npm audit`, `pip-audit`)
- **Review security scan results** (Trivy, Bandit, CodeQL)

## Known Security Considerations

### Authentication

- JWT tokens expire after 24 hours
- Passwords hashed with Argon2id (industry standard)
- API keys encrypted at rest using pg_crypto

### Data Protection

- No plaintext password storage
- Prepared statements prevent SQL injection
- Input validation on all endpoints
- CORS configured for production

### Network Security

- SSL/TLS recommended for production
- Default ports can be changed
- Support for reverse proxy deployment

## Vulnerability Disclosure Policy

We follow **coordinated disclosure**:

1. Security researcher reports vulnerability privately
2. We confirm and develop a patch
3. We release the patch
4. Public disclosure after patch is available

## Security Updates

Security updates are released as:

- **Patch versions** (e.g., 0.1.1 → 0.1.2) for minor fixes
- **Minor versions** (e.g., 0.1.x → 0.2.0) for significant changes

Subscribe to GitHub releases to receive notifications.

## Third-Party Dependencies

We use automated tools to monitor dependencies:

- **Dependabot**: Automatic dependency updates
- **Trivy**: Container vulnerability scanning
- **Bandit**: Python security linting
- **CodeQL**: Code security analysis

## Contact

For security concerns, contact the maintainers through GitHub issues (for non-sensitive matters) or private channels (for vulnerabilities).

---

**Last Updated**: 2024
