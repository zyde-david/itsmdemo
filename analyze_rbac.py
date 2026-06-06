import re

with open('app.py', 'r') as f:
    lines = f.readlines()

routes = []
i = 0
while i < len(lines):
    line = lines[i]
    if line.strip().startswith('@app.route'):
        decorators = []
        while i < len(lines) and lines[i].strip().startswith('@'):
            decorators.append(lines[i].rstrip())
            i += 1
        if i < len(lines) and lines[i].strip().startswith('def'):
            func_line = lines[i].rstrip()
            match = re.search(r'def\s+(\w+)', func_line)
            func_name = match.group(1) if match else 'unknown'
            route_match = re.search(r'@app\.route\((.*?)\)', decorators[0])
            route = route_match.group(1).strip('\'"') if route_match else 'unknown'
            routes.append({'route': route, 'function': func_name, 'decorators': decorators.copy()})
            i += 1
            while i < len(lines) and (lines[i].startswith(' ') or lines[i].startswith('\t') or lines[i].strip() == ''):
                i += 1
        else:
            i += 1
    else:
        i += 1

print("Route Analysis:")
print("=" * 80)
for r in routes:
    route = r['route']
    func = r['function']
    decs = r['decorators']
    has_login = any('@login_required' in d for d in decs)
    has_role_required = any('@role_required' in d for d in decs)
    if not has_login and not has_role_required:
        auth = 'OPEN (no auth)'
    elif has_login and not has_role_required:
        auth = 'LOGIN_REQUIRED (any authenticated user)'
    else:
        roles = []
        for d in decs:
            if '@role_required' in d:
                match = re.search(r'@role_required\((.*?)\)', d)
                if match:
                    roles_str = match.group(1)
                    for part in roles_str.split(','):
                        cleaned = part.strip().strip("'").strip('"')
                        if cleaned:
                            roles.append(cleaned)
        auth = 'ROLE_REQUIRED: ' + ', '.join(roles)
    print(f"Route: {route}")
    print(f"  Function: {func}")
    print(f"  Decorators: {', '.join(decs)}")
    print(f"  Auth: {auth}")
    print()

print("\n\nSummary:")
print("=" * 80)
open_routes = [r for r in routes if not any('@login_required' in d for d in r['decorators']) and not any('@role_required' in d for d in r['decorators'])]
if open_routes:
    print("OPEN ROUTES:")
    for r in open_routes:
        print(f"  {r['route']} -> {r['function']}")
else:
    print("No open routes found.")

login_only_routes = [r for r in routes if any('@login_required' in d for d in r['decorators']) and not any('@role_required' in d for d in r['decorators'])]
if login_only_routes:
    print("\nLogin-only routes (any authenticated user):")
    for r in login_only_routes:
        print(f"  {r['route']} -> {r['function']}")
else:
    print("\nNo login-only routes found.")

print("\n\nRole-specific routes:")
print("=" * 80)
for r in routes:
    role_decs = [d for d in r['decorators'] if '@role_required' in d]
    if role_decs:
        print(f"Route: {r['route']} ({r['function']})")
        for rd in role_decs:
            print(f"  {rd}")
        print()
