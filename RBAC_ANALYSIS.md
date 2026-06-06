# ITSM RBAC and Security Audit Findings

## Current RBAC Implementation

### Roles Defined
- Admin: Full system access
- Manager: Service Manager / Resolver Lead
- User: Reporter / Self-service
- HR: HR ticket handling

### Role Helper Functions
- is_admin(): Checks if role == 'admin'
- is_manager(): Checks if role in ('admin', 'manager')
- is_hr_role(): Checks if role == 'hr'
- current_role(): Returns session role or defaults to 'user'

### Permission Functions
- can_manage_users(): Admin only
- can_view_assets(): Admin/Manager
- can_view_staff(): Admin/Manager/HR
- can_manage_staff(): Admin only
- can_manage_kb(): Admin/Manager
- can_access_ticket(): Role-based ticket access control
- can_manage_ticket(): Admin/Manager can manage any ticket; HR can manage HR tickets only

### Route Protection Analysis
**Open Routes (No Authentication):**
- /howto-public
- /interview
- /vision
- /login (GET/POST)
- /logout

**Login Required (Any Authenticated User):**
- All other routes except those listed below

**Admin-Only Routes:**
- /api/user (POST) - Create user
- /api/user/<int:uid>/role (POST) - Update user role
- /api/user/<int:uid>/delete (POST) - Delete user

**Missing Role Protections:**
- Manager-only routes: Leave approvals (/leave-approvals*), staff management
- HR-only routes: HR ticket viewing/management
- User-specific restrictions: None identified

## Security Findings

### Password Storage
- Issue: Passwords hashed with unsalted SHA-256 (line 18)
- Risk: Vulnerable to rainbow table attacks
- Recommendation: Use bcrypt, scrypt, or PBKDF2 with salt

### Secret Key Management
- Issue: Hardcoded secret key 'demo-2026-secret' (line 12)
- Risk: Compromised if source is exposed; same across all deployments
- Recommendation: Set via environment variable SECRET_KEY

### Configuration Management
- Issue: Database path configurable via DB_PATH env var (line 13), but other secrets not externalized
- Recommendation: Externalize all configuration (secret key, database credentials, etc.)

### Missing Security Headers
- No evidence of security headers (HSTS, CSP, etc.)
- No indication of HTTPS enforcement

## Demo vs Production Considerations

### Current Demo Setup
- Default admin password: demo2026 (line 20 in README)
- Demo data generation via generate_data.py
- SQLite database (tickets.db)

### Production Recommendations
1. Environment Variables:
   - SECRET_KEY: Strong random value
   - DB_PATH: Production database path
   - FLASK_ENV: Set to production
   - FLASK_DEBUG: 0

2. Password Security:
   - Update check_pw() and password storage to use bcrypt
   - Migrate existing hashes on next login

3. Session Security:
   - Use secure cookies in production
   - Implement session timeout

4. Input Validation:
   - Continue current parameterized query usage (good)
   - Add validation for file uploads if implemented

5. Logging & Monitoring:
   - Enable access logging
   - Log security events (failed logins, permission denials)

## Suggested RBAC Enhancements

### Route Protection Additions
1. Manager Routes:
   - /leave-approvals* -> @role_required('admin', 'manager')
   - Staff management routes -> Consider manager/HR access

2. HR Routes:
   - HR-specific ticket views -> @role_required('hr') or higher

3. Consistent Protection:
   - Review all routes for appropriate role requirements
   - Consider implementing resource-based permissions (e.g., branch-specific)

### Documentation Needs
1. User Guide: Explain role-based access in /howto-public or /interview
2. Admin Guide: Document role assignment and permission matrix
3. API Documentation: Specify required roles for each endpoint

## Next Steps (Safe Documentation Changes Only)

Since broad code changes are discouraged, recommended actions:

1. Add RBAC Explanation to Existing Docs:
   - Update /howto-public or /interview to include RBAC overview
   - Add section in README about roles and permissions

2. Create Security Best Practices Document:
   - Document current security measures
   - Outline recommended production hardening steps

3. Add Config Template:
   - Create config.example.py or .env.example showing recommended environment variables
   - Do not commit actual secrets

4. Update Comments:
   - Add inline comments to security-sensitive areas noting production considerations
   - Example: # TODO: In production, use environment variable for SECRET_KEY

## Conclusion

The ITSM system demonstrates a solid foundation for RBAC with well-defined roles and helper functions. However, route-level protection is inconsistent, with many routes accessible to any authenticated user regardless of role. Security practices around password storage and secret management need improvement for production use.

The recommended approach is to document the current state, clarify the intended RBAC model, and provide guidance for production deployment without making functional code changes.