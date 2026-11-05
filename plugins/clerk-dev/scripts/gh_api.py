import json, subprocess, sys

def gh(args, cwd):
    r = subprocess.run(["gh"] + args, capture_output=True, text=True, cwd=cwd)
    if r.returncode != 0: sys.exit(f"gh {' '.join(args[:3])} failed: {r.stderr.strip()}")
    return r.stdout

def graphql(query, variables, cwd):
    fields = [x for k, v in variables.items() for x in ("-F", f"{k}={v}")]
    return json.loads(gh(["api", "graphql", "-f", f"query={query}"] + fields, cwd))

def repo_owner_name(cwd):
    return json.loads(gh(["repo", "view", "--json", "nameWithOwner"], cwd))["nameWithOwner"].split("/")

def pr_number(cwd):
    return json.loads(gh(["pr", "view", "--json", "number"], cwd))["number"]
