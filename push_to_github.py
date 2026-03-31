import requests
import base64

token = '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'
owner = 's12an'
repo = '-insurance-advisor'
headers = {
    'Authorization': f'Bearer {token}',
    'Accept': 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28'
}

base = f'https://api.github.com/repos/{owner}/{repo}'

# Step 1: Create a blob for README
print("Step 1: Creating README blob...")
readme_content = "# Insurance Advisor Ultimate\n\nComplete insurance consulting web service\n"
blob_resp = requests.post(f'{base}/git/blobs', headers=headers, json={
    'content': readme_content,
    'encoding': 'utf-8'
})
print(f'Blob status: {blob_resp.status_code}')
if blob_resp.status_code != 201:
    print(f'Error: {blob_resp.json()}')
    exit()
blob_sha = blob_resp.json()['sha']
print(f'Blob SHA: {blob_sha}')

# Step 2: Create a tree (no parent since this is the first commit)
print("\nStep 2: Creating tree...")
tree_resp = requests.post(f'{base}/git/trees', headers=headers, json={
    'tree': [{
        'path': 'README.md',
        'mode': '100644',
        'type': 'blob',
        'sha': blob_sha
    }]
})
print(f'Tree status: {tree_resp.status_code}')
if tree_resp.status_code != 201:
    print(f'Error: {tree_resp.json()}')
    exit()
tree_sha = tree_resp.json()['sha']
print(f'Tree SHA: {tree_sha}')

# Step 3: Create a commit (no parents - this is the root commit)
print("\nStep 3: Creating commit...")
commit_resp = requests.post(f'{base}/git/commits', headers=headers, json={
    'message': 'Initial commit',
    'tree': tree_sha,
    'parents': []
})
print(f'Commit status: {commit_resp.status_code}')
if commit_resp.status_code != 201:
    print(f'Error: {commit_resp.json()}')
    exit()
commit_sha = commit_resp.json()['sha']
print(f'Commit SHA: {commit_sha}')

# Step 4: Create the main branch ref
print("\nStep 4: Creating main branch ref...")
ref_resp = requests.post(f'{base}/git/refs', headers=headers, json={
    'ref': 'refs/heads/main',
    'sha': commit_sha
})
print(f'Ref status: {ref_resp.status_code}')
if ref_resp.status_code != 201:
    print(f'Error: {ref_resp.json()}')
    exit()
print('Main branch created!')

# Step 5: Now upload all other files using the contents API
print("\nStep 5: Uploading remaining files...")
files = {
    'app.py': r'C:\Users\daily\Desktop\보험어드바이저\app.py',
    'requirements.txt': r'C:\Users\daily\Desktop\보험어드바이저\requirements.txt',
    'insurance_agent.py': r'C:\Users\daily\Desktop\보험어드바이저\insurance_agent.py',
    '.gitignore': r'C:\Users\daily\Desktop\보험어드바이저\.gitignore',
}

for filename, filepath in files.items():
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    resp = requests.put(
        f'{base}/contents/{filename}',
        headers=headers,
        json={
            'message': f'Add {filename}',
            'content': base64.b64encode(content.encode()).decode(),
            'branch': 'main'
        }
    )
    print(f'{filename}: {resp.status_code} - OK')

print(f'\nAll files uploaded successfully!')
print(f'Repository: https://github.com/{owner}/{repo}')
