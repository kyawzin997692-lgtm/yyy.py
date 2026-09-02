# Telegram Bot on Render

Render ပေါ်တွင် ၂၄ နာရီပတ်လုံး အပြည့်အဝ အလုပ်လုပ်နိုင်ရန် ပြင်ဆင်ထားသော Python Telegram Bot ဖြစ်ပါသည်။

## လိုအပ်ချက်များ (Requirements)
- `requirements.txt` တွင် ပါဝင်သော Python Packages များ
- Telegram Bot Token (BotFather မှ ရယူထားသော Token)

## Render တွင် တင်နည်း (Deployment Steps)
1. Render တွင် **Web Service** အသစ်တစ်ခု တည်ဆောက်ပြီး သင့် GitHub Repository နှင့် ချိတ်ဆက်ပါ။
2. **Build Command** တွင် အောက်ပါအတိုင်း ထည့်ပါ:
   ```bash
   pip install -r requirements.txt
   
