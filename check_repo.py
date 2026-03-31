import requests
import base64

token = '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'
owner = 's12an'
repo = '-insurance-advisor'
headers = {
    'Authorization': f'token {token}',
    'Accept': 'application/vnd.github.v3+json'
}

# 브랜치 확인
resp = requests.get(f'https://api.github.com/repos/{owner}/{repo}/branches', headers=headers)
print('Branches:', resp.json())

# 기본 브랜치 확인
resp2 = requests.get(f'https://api.github.com/repos/{owner}/{repo}', headers=headers)
print('Default branch:', resp2.json().get('default_branch'))

# 내용 확인
resp3 = requests.get(f'https://api.github.com/repos/{owner}/{repo}/contents', headers=headers)
print('Contents:', resp3.json())
