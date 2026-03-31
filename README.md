# Insurance Advisor Agent - 실행 가이드

## 설치
```bash
pip install -r requirements.txt
```

## DeepSeek API 키 설정
DeepSeek API는 무료로 사용 가능합니다:
1. https://platform.deepseek.com 에서 API 키 발급
2. 다음 방법 중 하나로 설정:

```bash
# 방법 1: 환경변수
export DEEPSEEK_API_KEY=your_api_key_here

# 방법 2: .env 파일 생성
echo "DEEPSEEK_API_KEY=your_api_key_here" > .env
```

## 실행
```bash
python insurance_agent.py
```

## 사용 예시
```
사용자 > 자녀 보험 추천해줘 (월 10만원 이하)
사용자 > 내 보험 포트폴리오 검증해줘
사용자 > ABC상품 해약환급금 계산해줘 (36개월 납입, 월 5만원)
사용자 > KB와 삼성 보험 비교해줘
사용자 > /help
사용자 > /exit
```

## 기능
- 자연어로 보험 상담
- 상품 검색 및 추천
- 해약환급금 계산
- 미래 보험료 예측
- 포트폴리오 검증
- 대화 내보내기 (JSON)
