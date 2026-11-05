import json, shutil, subprocess, sys

class GhError(SystemExit):
    pass

def gh(args, cwd, stdin=None):
    if not shutil.which("gh"): raise GhError("gh is not installed; install the GitHub CLI and sign in with gh auth login")
    r = subprocess.run(["gh"] + args, capture_output=True, text=True, cwd=cwd, input=stdin)
    if r.returncode != 0: raise GhError(f"gh {' '.join(args[:3])} failed: {r.stderr.strip()}")
    return r.stdout

def send_json(args, payload, cwd):
    out = gh(args + ["--input", "-"], cwd, json.dumps(payload)) if payload is not None else gh(args, cwd)
    return json.loads(out) if out.strip() else None

def graphql(query, variables, cwd):
    return send_json(["api", "graphql"], {"query": query, "variables": variables}, cwd)

def rest(method, path, fields, cwd):
    return send_json(["api", "-X", method, path], fields or None, cwd)

def rest_list(path, cwd):
    return [json.loads(line) for line in gh(["api", "--paginate", path, "--jq", ".[]"], cwd).splitlines() if line.strip()]

def repo_owner_name(cwd):
    return json.loads(gh(["repo", "view", "--json", "nameWithOwner"], cwd))["nameWithOwner"].split("/")

def pr_number(cwd):
    return json.loads(gh(["pr", "view", "--json", "number"], cwd))["number"]
