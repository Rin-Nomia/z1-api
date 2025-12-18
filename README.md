---
title: Z1 Tone Firewall API
emoji: 🛡️
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
---

# Z1 Tone Firewall API

AI-powered tone detection and repair system with 95% accuracy.

## 🚀 API Endpoints

### Health Check
```bash
GET https://RinNomia-z1-tone-api.hf.space/health
Analyze Text
POST https://RinNomia-z1-tone-api.hf.space/api/v1/analyze

{
  "text": "Your text here"
}
📖 API Documentation
Visit: https://RinNomia-z1-tone-api.hf.space/docs
🧪 Quick Test
curl https://RinNomia-z1-tone-api.hf.space/health
🎯 Features
	∙	Tone Detection: Anxious, Cold, Sharp, Blur, Pushy
	∙	Accuracy: 95% (based on Rin alignment tests)
	∙	Repair Engine: Claude Haiku + Keyword Fallback
	∙	Scenario Detection: 4 scenarios (customer service, social, internal, business)
🔧 Technical Stack
	∙	FastAPI
	∙	Claude 4 Haiku
	∙	Z1 Pipeline (8-stage processing)
	∙	Auto-sync from z1_mvp
⚡ Performance
	∙	Single analysis: ~1-2 seconds
	∙	Confidence threshold: 0.2 for LLM repair
	∙	Rate limit: 50 req/min
    
    Built with ❤️ by Rin | Powered by Claude 4
    