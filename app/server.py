#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中枢 · 项目台 —— 本地单文件服务(零依赖,只用 Python 标准库)
启动:  python3 server.py        浏览器开 http://127.0.0.1:8766
真相源: 同目录 项目台.db (SQLite)  ← Claude 直接读这个库

设计原则(见 中枢/README.md):
- App 是"写"的界面;数据真相在 SQLite。后端很笨:只做 增/删/改/查 + 提交时间戳。
- "灵活可定制" = Claude 定期改 schema/视图,不是运行时元引擎。attrs 列是软扩展位。
"""
import json, os, sqlite3, socket, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from urllib import request as urlrequest
from urllib import error as urlerror

HERE = os.path.dirname(os.path.abspath(__file__))
DB   = os.path.join(HERE, "项目台.db")
PORT = int(os.environ.get("PORT", "8766"))
OPENMAIC_URL = os.environ.get("OPENMAIC_URL", "http://127.0.0.1:8770")

# projects 字段(前端/DB/API 共用)
PCOLS = ["emoji", "name", "status", "ball", "what",
         "just_done", "doing_next", "blocker", "path", "lastmove", "category"]

# tasks 字段(任务层 · 挂在项目下)
TCOLS = ["project_id", "title", "status", "goal", "owner",
         "start_date", "due_date", "progress", "note"]

# plans 字段(每日计划/预期层 · 睡前写"将要做",统计写→完成实际几天)
LCOLS = ["content", "project_id", "expect_days", "status", "note"]

# cards 字段(知识对战 · 可编辑部分;ease/interval/next_due 由复习逻辑管)
CCOLS = ["front", "back", "question", "options", "answer", "source", "tags", "image", "symbol", "quote", "logic"]

# reviews 字段(每日复盘 · Claude 写条目;用户打勾 checked + 留想法 note)
RCOLS = ["date", "section", "title", "detail", "checked", "note"]

NCOLS = ["concept", "status", "source", "initial_note", "learning_goal", "openmaic_prompt",
         "key_points", "examples", "misconceptions", "applications", "openmaic_url"]

SEED = [
    dict(emoji="🛰️", name="中枢升级", status="🟢进行", ball="🔴你",
         what="把“中央规划院”重建成老板驾驶舱(中枢)",
         just_done="重建骨架+记忆层+项目台App", doing_next="加提交/时间线/成果库 v2",
         blocker="无", path="/Users/tanghuiwen/工作/中枢", lastmove=""),
    dict(emoji="📝", name="Notion", status="⬜待补", ball="❔待定",
         what="Solo-Company AI-OS 项目中枢模板(自用+可卖)",
         just_done="", doing_next="", blocker="", path="/Users/tanghuiwen/工作/notion", lastmove=""),
    dict(emoji="🎬", name="营销工厂", status="⬜待补", ball="❔待定",
         what="营销视频/图文/科普/账号内容生产(原视频工厂升维)",
         just_done="", doing_next="先做 Step1 目标边界对齐", blocker="", path="/Users/tanghuiwen/工作/营销工厂", lastmove=""),
    dict(emoji="🏛️", name="SOP工厂", status="⬜待补", ball="❔待定",
         what="17步PDCA规范 + PDR模板库(≥16分项目骨架)",
         just_done="", doing_next="", blocker="", path="/Users/tanghuiwen/工作/SOP工厂", lastmove=""),
]


def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def cols_of(c, table):
    return [r[1] for r in c.execute(f"PRAGMA table_info({table})")]


def apply_card_review(c, rid, correct):
    row = c.execute("SELECT ease, interval FROM cards WHERE id=?", (rid,)).fetchone()
    ef = (row[0] if row and row[0] else 2.5)
    iv = (row[1] if row and row[1] else 0)
    if correct:
        ef = round(ef + 0.1, 2)
        iv = 1 if iv == 0 else (6 if iv == 1 else round(iv * ef))
        c.execute(f"""UPDATE cards
                      SET ease=?, interval=?, next_due=date('now','localtime','+{iv} days'),
                          last_seen=date('now','localtime'), correct_count=correct_count+1
                      WHERE id=?""", (ef, iv, rid))
    else:
        ef = round(max(1.3, ef - 0.2), 2)
        iv = 0
        c.execute("""UPDATE cards
                     SET ease=?, interval=0, next_due=date('now','localtime','+1 day'),
                         last_seen=date('now','localtime'), wrong_count=wrong_count+1
                     WHERE id=?""", (ef, rid))
    return {"ease": ef, "interval": iv}


def _option_text(card, idx):
    try:
        opts = json.loads(card.get("options") or "[]")
    except Exception:
        opts = []
    return opts[idx] if 0 <= idx < len(opts) else ""


def maic_feedback(card, selected_answer, correct, review_state):
    question = card.get("question") or card.get("front") or "这张卡"
    back = card.get("back") or "这张卡还没有解释，建议补充背面说明。"
    tags = card.get("tags") or "未标注"
    answer = int(card.get("answer") or 0)
    selected_text = _option_text(card, selected_answer)
    answer_text = _option_text(card, answer)
    base = 5 if correct else 2
    apply_score = 4 if correct else 2
    attack_score = 4 if correct else 2
    explanation_score = 4 if len(back) >= 24 else 3
    judge_reason = (
        "命中正确选项；下一步要验证能否迁移到真实项目。"
        if correct else
        "未命中正确选项；说明概念边界或反例识别还不稳，明天回炉。"
    )
    challenge = (
        f"你答对了，但还不能算完全掌握。请把「{question}」迁移到一个正在做的项目里，说明它会改变哪个节点或检查标准。"
        if correct else
        f"你选择了「{selected_text or '空'}」，正确答案是「{answer_text or '未设置'}」。请说出你为什么被错误选项吸引，避免下次被同类表述骗走。"
    )
    sediment = (
        f"调度结果：ease={review_state['ease']}，interval={review_state['interval']} 天。"
        + (" 这张卡进入更长复习间隔。" if correct else " 这张卡明天回炉，并建议补一张反例题。")
    )
    return {
        "agents": [
            {
                "role": "explainer",
                "name": "讲解者",
                "label": "Teacher",
                "content": f"核心解释：{back}",
            },
            {
                "role": "challenger",
                "name": "挑战者",
                "label": "Peer Challenger",
                "content": challenge,
            },
            {
                "role": "judge",
                "name": "裁判",
                "label": "Evaluator",
                "content": f"{judge_reason} 评分采用 Recall / Apply / Attack / Explain 四维，避免只看选择题对错。",
            },
            {
                "role": "sediment",
                "name": "沉淀者",
                "label": "Memory Coach",
                "content": sediment,
            },
        ],
        "scores": {
            "recall": base,
            "apply": apply_score,
            "attack": attack_score,
            "explain": explanation_score,
            "correct": 1 if correct else 0,
            "judge_reason": judge_reason,
        },
        "meta": {
            "question": question,
            "tags": tags,
            "selected_answer": selected_answer,
            "selected_text": selected_text,
            "correct_answer": answer,
            "correct_text": answer_text,
        },
    }


def build_openmaic_prompt(concept, initial_note="", learning_goal=""):
    goal = learning_goal or "先真正理解这个概念,再能迁移到我的中枢/项目台/SOP工厂/Agent节点体系。"
    note = initial_note or "我还没系统学会这个概念,请先从零建立理解。"
    return f"""请用 OpenMAIC 的多智能体互动课堂方式,带我学习「{concept}」。

我的学习目标:
{goal}

我的当前理解/上下文:
{note}

请按 5 个场景组织:
1. 8 岁版:用非常直观的比喻讲清楚它是什么,解决什么问题。
2. 专家版:给出专业定义、关键机制、边界条件和常见误区。
3. 白板/关系图:用流程图或结构图解释它和相邻概念的关系。
4. 圆桌辩论:让 teacher、assistant、challenger 三个角色讨论它在真实项目中如何使用,challenger 必须指出误用风险。
5. 小测验与迁移:给我 3 道题,其中至少 1 道要迁移到我的中枢/项目台/SOP工厂/Agent节点体系。

最后请输出一段可复制回中枢概念笔记的结构化总结:
- 关键点:
- 例子:
- 常见误区:
- 应用场景:
- 可以进入知识对战的题目方向:
"""


def split_lines(text):
    raw = (text or "").replace("；", "\n").replace(";", "\n").splitlines()
    return [x.strip(" -•\t") for x in raw if x.strip(" -•\t")]


def four_options(correct, *wrong):
    fillers = [
        "只背定义,不看使用场景",
        "直接进入复习题库,跳过理解",
        "把所有信息塞进长上下文",
        "只看工具名字,不验证效果",
        "用感觉判断,不做测试和评分",
    ]
    opts = [correct]
    for x in list(wrong) + fillers:
        if x and x not in opts:
            opts.append(x)
        if len(opts) == 4:
            break
    return opts[:4]


def concept_cards_from_note(note):
    concept = note.get("concept") or "这个概念"
    key_points = split_lines(note.get("key_points"))
    examples = split_lines(note.get("examples"))
    misconceptions = split_lines(note.get("misconceptions"))
    applications = split_lines(note.get("applications"))
    source = f"概念笔记#{note.get('id')} · OpenMAIC学习"
    tags = f"概念学习/{concept}"
    back_base = "\n".join([
        f"关键点:{note.get('key_points') or '待补'}",
        f"例子:{note.get('examples') or '待补'}",
        f"误区:{note.get('misconceptions') or '待补'}",
        f"应用:{note.get('applications') or '待补'}",
    ])
    cards = []
    if key_points:
        correct = key_points[0]
        cards.append({
            "front": f"{concept} 的核心抓手是什么?",
            "question": f"{concept} 的核心抓手是什么?",
            "options": four_options(correct),
            "answer": 0,
            "back": back_base,
            "source": source,
            "tags": tags,
            "symbol": "🧠",
        })
    if misconceptions:
        correct = misconceptions[0]
        cards.append({
            "front": f"学习 {concept} 时最容易踩的坑是什么?",
            "question": f"学习 {concept} 时最容易踩的坑是什么?",
            "options": four_options(correct, key_points[0] if key_points else ""),
            "answer": 0,
            "back": back_base,
            "source": source,
            "tags": tags + "/误区",
            "symbol": "⚠️",
        })
    if applications:
        correct = applications[0]
        cards.append({
            "front": f"把 {concept} 放进中枢/项目台时,最应该改变什么?",
            "question": f"把 {concept} 放进中枢/项目台时,最应该改变什么?",
            "options": four_options(correct, key_points[0] if key_points else ""),
            "answer": 0,
            "back": back_base,
            "source": source,
            "tags": tags + "/应用",
            "symbol": "🧭",
        })
    if examples:
        correct = examples[0]
        cards.append({
            "front": f"哪个例子最能说明 {concept}?",
            "question": f"哪个例子最能说明 {concept}?",
            "options": four_options(correct, applications[0] if applications else ""),
            "answer": 0,
            "back": back_base,
            "source": source,
            "tags": tags + "/例子",
            "symbol": "🧩",
        })
    return cards


def _json_loads(s, default):
    try:
        return json.loads(s or "")
    except Exception:
        return default


def close_stale_questions(c):
    cur = c.execute("""UPDATE card_questions
                       SET status='closed', closed_at=datetime('now','localtime')
                       WHERE status='open'
                         AND datetime(last_activity_at) <= datetime('now','localtime','-10 minutes')""")
    return cur.rowcount


def _card_prompt_context(card):
    opts = _json_loads(card.get("options"), [])
    answer_idx = int(card.get("answer") or 0)
    answer_text = opts[answer_idx] if 0 <= answer_idx < len(opts) else ""
    return {
        "question": card.get("question") or card.get("front") or "",
        "back": card.get("back") or "",
        "options": opts,
        "answer": answer_idx,
        "answer_text": answer_text,
        "source": card.get("source") or "",
        "tags": card.get("tags") or "",
        "logic": card.get("logic") or "",
        "quote": card.get("quote") or "",
    }


def local_card_question_answer(card, user_question, history):
    ctx = _card_prompt_context(card)
    prior = len([m for m in history if m.get("role") == "user"])
    return (
        "本地结构化回答：\n\n"
        f"1. 你问的是：{user_question}\n\n"
        f"2. 这张卡的核心问题是：{ctx['question']}\n\n"
        f"3. 正确抓手是：{ctx['answer_text'] or '这张卡暂未设置标准答案文本'}。\n"
        f"   背后解释：{ctx['back'] or '这张卡还没有背面解释，建议补充。'}\n\n"
        "4. 你现在最该区分的是：\n"
        "   - 这是在问概念定义，还是在问真实场景里的判断？\n"
        "   - 这个原则会改变哪个节点、检查门或行动标准？\n"
        "   - 如果换一个项目，这个原则还成立吗？边界在哪里？\n\n"
        "5. 你可以继续追问：\n"
        "   - 给我举一个我项目里的例子。\n"
        "   - 为什么其他选项错？\n"
        "   - 这个概念怎么变成一个 hook？\n"
        f"\n本轮已记录为第 {prior + 1} 次追问。若 10 分钟内没有继续对话，会话会自动关闭。"
    )


def call_card_question_llm(card, user_question, history):
    ctx = _card_prompt_context(card)
    base_url = os.environ.get("PROJECTTAI_LLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
    api_key = os.environ.get("PROJECTTAI_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("PROJECTTAI_LLM_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-4o-mini"
    if not base_url and api_key:
        base_url = "https://api.openai.com/v1"
    if not base_url:
        return local_card_question_answer(card, user_question, history), "local_fallback"

    messages = [
        {
            "role": "system",
            "content": (
                "你是中枢知识对战的脑科学学习教练。"
                "只能围绕当前卡片、用户疑问和已有对话回答。"
                "回答要结构化、具体、可迁移到项目节点；不要泛泛讲概念。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps({
                "card": ctx,
                "history": history[-8:],
                "user_question": user_question,
                "answer_style": [
                    "先回答疑问",
                    "再指出用户可能卡住的误区",
                    "给一个中枢/项目台里的应用例子",
                    "最后给一个可继续追问的问题"
                ],
            }, ensure_ascii=False),
        },
    ]
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0.3,
    }, ensure_ascii=False).encode("utf-8")
    req = urlrequest.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    try:
        with urlrequest.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = data["choices"][0]["message"]["content"].strip()
        return text, "llm"
    except (urlerror.URLError, urlerror.HTTPError, KeyError, IndexError, json.JSONDecodeError, TimeoutError) as e:
        fallback = local_card_question_answer(card, user_question, history)
        return fallback + f"\n\nLLM hook 未成功调用，已用本地结构化回答兜底。错误类型：{type(e).__name__}", "llm_fallback"


def init_db():
    c = conn()
    c.execute("""CREATE TABLE IF NOT EXISTS projects(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        emoji TEXT, name TEXT, status TEXT, ball TEXT, what TEXT,
        just_done TEXT, doing_next TEXT, blocker TEXT, path TEXT, lastmove TEXT,
        sort_order INTEGER DEFAULT 0,
        updated_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    # 迁移旧列名(focus→just_done, nextstep→doing_next),保留已有数据
    pc = cols_of(c, "projects")
    if "focus" in pc and "just_done" not in pc:
        c.execute("ALTER TABLE projects RENAME COLUMN focus TO just_done")
    if "nextstep" in pc and "doing_next" not in pc:
        c.execute("ALTER TABLE projects RENAME COLUMN nextstep TO doing_next")
    if "category" not in cols_of(c, "projects"):
        c.execute("ALTER TABLE projects ADD COLUMN category TEXT DEFAULT ''")

    c.execute("""CREATE TABLE IF NOT EXISTS commits(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER,
        ts TEXT DEFAULT (datetime('now','localtime')),
        just_done TEXT, doing_next TEXT, note TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS artifacts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER, commit_id INTEGER,
        type TEXT, title TEXT, maturity TEXT, path TEXT, note TEXT,
        attrs TEXT DEFAULT '{}',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS tasks(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER, title TEXT, status TEXT, goal TEXT, owner TEXT,
        start_date TEXT, due_date TEXT, progress INTEGER DEFAULT 0, note TEXT,
        sort_order INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        updated_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS plans(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content TEXT, project_id INTEGER, expect_days INTEGER,
        status TEXT DEFAULT '进行中', note TEXT,
        created_at TEXT DEFAULT (date('now','localtime')),
        done_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS cards(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        front TEXT, back TEXT, question TEXT, options TEXT, answer INTEGER,
        source TEXT, tags TEXT,
        ease REAL DEFAULT 2.5, interval INTEGER DEFAULT 0,
        next_due TEXT DEFAULT (date('now','localtime')),
        last_seen TEXT, correct_count INTEGER DEFAULT 0, wrong_count INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (date('now','localtime'))
    )""")
    for _col in ("image", "symbol", "quote", "logic"):
        if _col not in cols_of(c, "cards"):
            c.execute(f"ALTER TABLE cards ADD COLUMN {_col} TEXT DEFAULT ''")

    c.execute("""CREATE TABLE IF NOT EXISTS reviews(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT DEFAULT (date('now','localtime')),
        section TEXT, title TEXT, detail TEXT,
        checked INTEGER DEFAULT 0, note TEXT DEFAULT '',
        sort_order INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS battle_sessions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mode TEXT DEFAULT 'maic_review',
        source TEXT DEFAULT 'cards',
        status TEXT DEFAULT 'running',
        card_count INTEGER DEFAULT 0,
        correct_count INTEGER DEFAULT 0,
        wrong_count INTEGER DEFAULT 0,
        score_summary TEXT DEFAULT '{}',
        started_at TEXT DEFAULT (datetime('now','localtime')),
        ended_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS battle_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        card_id INTEGER,
        role TEXT,
        event_type TEXT,
        payload TEXT DEFAULT '{}',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS battle_scores(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        card_id INTEGER,
        selected_answer INTEGER,
        correct INTEGER,
        recall_score INTEGER,
        apply_score INTEGER,
        attack_score INTEGER,
        explanation_score INTEGER,
        judge_reason TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS card_questions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        card_id INTEGER,
        status TEXT DEFAULT 'open',
        question_text TEXT,
        answer_text TEXT DEFAULT '',
        history TEXT DEFAULT '[]',
        llm_status TEXT DEFAULT 'pending',
        turn_count INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        last_activity_at TEXT DEFAULT (datetime('now','localtime')),
        closed_at TEXT
    )""")
    qcols = cols_of(c, "card_questions")
    for _col, _ddl in {
        "session_id": "INTEGER",
        "card_id": "INTEGER",
        "status": "TEXT DEFAULT 'open'",
        "question_text": "TEXT",
        "answer_text": "TEXT DEFAULT ''",
        "history": "TEXT DEFAULT '[]'",
        "llm_status": "TEXT DEFAULT 'pending'",
        "turn_count": "INTEGER DEFAULT 0",
        "created_at": "TEXT DEFAULT (datetime('now','localtime'))",
        "last_activity_at": "TEXT DEFAULT (datetime('now','localtime'))",
        "closed_at": "TEXT",
    }.items():
        if _col not in qcols:
            c.execute(f"ALTER TABLE card_questions ADD COLUMN {_col} {_ddl}")
    c.execute("""CREATE TABLE IF NOT EXISTS concept_notes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        concept TEXT,
        status TEXT DEFAULT 'noted',
        source TEXT DEFAULT '',
        initial_note TEXT DEFAULT '',
        learning_goal TEXT DEFAULT '',
        openmaic_prompt TEXT DEFAULT '',
        key_points TEXT DEFAULT '',
        examples TEXT DEFAULT '',
        misconceptions TEXT DEFAULT '',
        applications TEXT DEFAULT '',
        openmaic_url TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now','localtime')),
        updated_at TEXT DEFAULT (datetime('now','localtime')),
        learned_at TEXT,
        graduated_at TEXT
    )""")
    ncols = cols_of(c, "concept_notes")
    for _col, _ddl in {
        "concept": "TEXT",
        "status": "TEXT DEFAULT 'noted'",
        "source": "TEXT DEFAULT ''",
        "initial_note": "TEXT DEFAULT ''",
        "learning_goal": "TEXT DEFAULT ''",
        "openmaic_prompt": "TEXT DEFAULT ''",
        "key_points": "TEXT DEFAULT ''",
        "examples": "TEXT DEFAULT ''",
        "misconceptions": "TEXT DEFAULT ''",
        "applications": "TEXT DEFAULT ''",
        "openmaic_url": "TEXT DEFAULT ''",
        "created_at": "TEXT DEFAULT (datetime('now','localtime'))",
        "updated_at": "TEXT DEFAULT (datetime('now','localtime'))",
        "learned_at": "TEXT",
        "graduated_at": "TEXT",
    }.items():
        if _col not in ncols:
            c.execute(f"ALTER TABLE concept_notes ADD COLUMN {_col} {_ddl}")
    c.execute("""CREATE TABLE IF NOT EXISTS concept_note_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        note_id INTEGER,
        event_type TEXT,
        payload TEXT DEFAULT '{}',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    # 每日开工时间(当天第一次打开 App = 你真正开始的时间)
    c.execute("""CREATE TABLE IF NOT EXISTS daystart(
        date TEXT PRIMARY KEY,
        started_at TEXT DEFAULT (datetime('now','localtime'))
    )""")

    if c.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0:
        ph = ",".join("?" * len(PCOLS))
        for i, p in enumerate(SEED):
            c.execute(f"INSERT INTO projects(sort_order,{','.join(PCOLS)}) VALUES(?,{ph})",
                      [i] + [p.get(k, "") for k in PCOLS])

    if c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0:
        def pid(nm):
            r = c.execute("SELECT id FROM projects WHERE name=?", (nm,)).fetchone()
            return r[0] if r else None
        tseed = [
            (pid("营销工厂"), "确定营销工厂边界", "进行", "G1赚钱", "你", "2026-06-03", "2026-06-03", 30, "从视频工厂升维为营销工厂"),
            (pid("营销工厂"), "做第一条营销内容 MVP", "进行", "G1赚钱", "你", "2026-05-21", "2026-06-10", 30, ""),
            (pid("SOP工厂"), "PDR 模板库补全", "进行", "G2成长", "你", "2026-05-20", "2026-05-27", 50, ""),
            (pid("中枢升级"), "项目台多视图(甘特等)", "进行", "G2成长", "你", "2026-05-22", "2026-05-28", 60, "示例任务,随便改/删"),
        ]
        php = ",".join("?" * len(TCOLS))
        for i, t in enumerate(tseed):
            if t[0] is None:
                continue
            c.execute(f"INSERT INTO tasks(sort_order,{','.join(TCOLS)}) VALUES(?,{php})", [i] + list(t))

    if c.execute("SELECT COUNT(*) FROM plans").fetchone()[0] == 0:
        r = c.execute("SELECT id FROM projects WHERE name=?", ("中枢升级",)).fetchone()
        cz = r[0] if r else None
        # 两条真实记录当示例:一条已完成(预估3天/实际1天),一条进行中
        c.execute("INSERT INTO plans(content,project_id,expect_days,status,created_at,done_at) VALUES(?,?,?,?,?,?)",
                  ("把中枢重建成驾驶舱 + 项目台 App v1", cz, 3, "已完成", "2026-05-22", "2026-05-23"))
        c.execute("INSERT INTO plans(content,project_id,expect_days,status,created_at) VALUES(?,?,?,?,?)",
                  ("OPC 比赛:P01 实测 + 报告 + 问作者", cz, 2, "进行中", "2026-05-23"))

    if c.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 0:
        cseed = [
            ("作为想破亿的超级个体,Vassallo 反对 all in 一个大注,他主张?",
             "小赌注组合(small bets):同时下多个小注,多数死、少数赢大,不押身家在一个上。🖼️ 撒一把种子,不赌一棵树。💥 你 all in OPC 也要设市场死亡线。",
             "Vassallo 的「小赌注」核心是?",
             ["把全部押在最有把握的一个项目", "同时下多个小注,接受多数失败少数赢大", "只做零风险的事", "等找到完美机会再重注"], 1,
             "记忆宫殿·一人公司变现", "组合下注/风险"),
            ("Sahil(Gumroad)关于「造产品顺序」的反直觉建议?",
             "先卖后造 · 利润优先:先验证有人买,再造。🖼️ 先收订金再开火做菜。💥 治你'建完才敢卖'的老毛病。",
             "「先卖后造」主张?",
             ["产品做到完美再上线", "先验证有人买(先卖)再投入造", "造得越多越好", "免费送让用户习惯"], 1,
             "记忆宫殿·一人公司变现", "先卖后造/验证"),
            ("Justin Welsh 的 Content OS 怎么用一个观点产出大量内容?",
             "一观点榨成 N 产物:一个核心观点 → 长文/图文/帖子/视频多形态分发。🖼️ 一头牛榨成牛排/牛奶/皮鞋。💥 你内容流水线的方法论母本。",
             "Content OS 的核心是?",
             ["每天想全新的选题", "一个观点榨成多种形态的 N 个产物", "只发长文", "蹭热点冲流量"], 1,
             "记忆宫殿·一人公司变现", "内容/Content OS"),
            ("一人公司(超级个体)真正的瓶颈通常是什么?",
             "不是缺时间/工具(AI 给了杠杆),是 ① 判断力 ② 触达真实客户 ③ 你自己的精力。🖼️ 引擎轰鸣但传动轴没接轮子。💥 你的真账:造得多但市场反馈少。",
             "一人公司真正的瓶颈通常是?",
             ["缺更多工具", "判断力 + 触达客户 + 你的精力", "代码写得不够多", "系统不够完善"], 1,
             "OPC必备", "瓶颈/触达"),
        ]
        for f, bk, q, opts, ans, src, tg in cseed:
            c.execute("INSERT INTO cards(front,back,question,options,answer,source,tags) VALUES(?,?,?,?,?,?,?)",
                      (f, bk, q, json.dumps(opts, ensure_ascii=False), ans, src, tg))
    c.commit(); c.close()


class Handler(BaseHTTPRequestHandler):
    # ---- helpers ----
    def _send(self, code, body=b"", ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def _tail_id(self, path):
        return int(path.rstrip("/").rsplit("/", 1)[1])

    # ---- GET ----
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            try:
                with open(os.path.join(HERE, "index.html"), "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            except FileNotFoundError:
                self._send(500, b"index.html missing", "text/plain")
            return
        if path == "/api/health":
            try:
                c = conn()
                tables = ["projects", "commits", "artifacts", "tasks", "plans", "cards", "reviews"]
                counts = {
                    table: c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in tables
                }
                c.close()
                self._json(200, {
                    "ok": True,
                    "app": "war-room-dashboard",
                    "version": "0.1.0",
                    "database": os.path.basename(DB),
                    "counts": counts,
                })
            except Exception as e:
                self._json(500, {"ok": False, "error": str(e)})
            return
        if path == "/api/openmaic/status":
            try:
                with urllib.request.urlopen(OPENMAIC_URL, timeout=2) as r:
                    ok = 200 <= r.status < 500
                    self._json(200, {"ok": ok, "url": OPENMAIC_URL, "status": r.status})
            except Exception as e:
                self._json(200, {"ok": False, "url": OPENMAIC_URL, "error": str(e)})
            return
        c = conn()
        if path == "/api/projects":
            rows = [dict(r) for r in c.execute("SELECT * FROM projects ORDER BY sort_order, id")]
        elif path == "/api/commits":
            rows = [dict(r) for r in c.execute("SELECT * FROM commits ORDER BY ts DESC, id DESC")]
        elif path == "/api/artifacts":
            rows = [dict(r) for r in c.execute("SELECT * FROM artifacts ORDER BY created_at DESC, id DESC")]
        elif path == "/api/tasks":
            rows = [dict(r) for r in c.execute("SELECT * FROM tasks ORDER BY sort_order, id")]
        elif path == "/api/plans":
            rows = [dict(r) for r in c.execute(
                "SELECT * FROM plans ORDER BY CASE status WHEN '进行中' THEN 0 ELSE 1 END, created_at DESC, id DESC")]
        elif path == "/api/cards":
            rows = [dict(r) for r in c.execute("SELECT * FROM cards ORDER BY next_due, id")]
        elif path == "/api/reviews":
            rows = [dict(r) for r in c.execute("SELECT * FROM reviews ORDER BY date DESC, sort_order, id")]
        elif path == "/api/daystart":
            rows = [dict(r) for r in c.execute("SELECT * FROM daystart ORDER BY date DESC")]
        elif path == "/api/battle/sessions":
            rows = [dict(r) for r in c.execute("SELECT * FROM battle_sessions ORDER BY id DESC LIMIT 30")]
        elif path == "/api/battle/events":
            qs = parse_qs(parsed.query)
            sid = int(qs.get("session_id", [0])[0] or 0)
            rows = [dict(r) for r in c.execute(
                "SELECT * FROM battle_events WHERE session_id=? ORDER BY id", (sid,))]
        elif path == "/api/card-questions":
            close_stale_questions(c)
            qs = parse_qs(parsed.query)
            card_id = int(qs.get("card_id", [0])[0] or 0)
            session_id = int(qs.get("session_id", [0])[0] or 0)
            status = qs.get("status", [""])[0]
            where, vals = [], []
            if card_id:
                where.append("q.card_id=?"); vals.append(card_id)
            if session_id:
                where.append("q.session_id=?"); vals.append(session_id)
            if status:
                where.append("q.status=?"); vals.append(status)
            sql = """SELECT q.*, cards.question AS card_question, cards.source AS card_source
                     FROM card_questions q
                     LEFT JOIN cards ON cards.id=q.card_id"""
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY q.last_activity_at DESC, q.id DESC LIMIT 80"
            rows = [dict(r) for r in c.execute(sql, vals)]
            c.commit()
        elif path == "/api/concept-notes":
            qs = parse_qs(parsed.query)
            status = qs.get("status", [""])[0]
            vals = []
            sql = "SELECT * FROM concept_notes"
            if status:
                sql += " WHERE status=?"; vals.append(status)
            sql += " ORDER BY updated_at DESC, id DESC"
            rows = [dict(r) for r in c.execute(sql, vals)]
        else:
            c.close(); self._send(404, b'{"error":"not found"}'); return
        c.close(); self._json(200, rows)

    # ---- POST ----
    def do_POST(self):
        path = urlparse(self.path).path
        b = self._body()
        c = conn()
        if path == "/api/projects":
            nxt = c.execute("SELECT COALESCE(MAX(sort_order),-1)+1 FROM projects").fetchone()[0]
            ph = ",".join("?" * len(PCOLS))
            cur = c.execute(f"INSERT INTO projects(sort_order,{','.join(PCOLS)}) VALUES(?,{ph})",
                            [nxt] + [b.get(k, "") for k in PCOLS])
            c.commit()
            row = dict(c.execute("SELECT * FROM projects WHERE id=?", (cur.lastrowid,)).fetchone())
            c.close(); self._json(200, row); return

        if path == "/api/commits":
            pid = b.get("project_id")
            cur = c.execute("INSERT INTO commits(project_id,just_done,doing_next,note) VALUES(?,?,?,?)",
                            (pid, b.get("just_done", ""), b.get("doing_next", ""), b.get("note", "")))
            cid = cur.lastrowid
            # 同步项目当前状态 + 最近提交时间
            c.execute("""UPDATE projects SET just_done=?, doing_next=?,
                         lastmove=strftime('%m-%d %H:%M','now','localtime'),
                         updated_at=datetime('now','localtime') WHERE id=?""",
                      (b.get("just_done", ""), b.get("doing_next", ""), pid))
            art = b.get("artifact")
            if art and (art.get("title") or art.get("path") or art.get("type")):
                c.execute("""INSERT INTO artifacts(project_id,commit_id,type,title,maturity,path,note,attrs)
                             VALUES(?,?,?,?,?,?,?,?)""",
                          (pid, cid, art.get("type", ""), art.get("title", ""),
                           art.get("maturity", ""), art.get("path", ""), art.get("note", ""),
                           json.dumps(art.get("attrs", {}), ensure_ascii=False)))
            c.commit()
            row = dict(c.execute("SELECT * FROM commits WHERE id=?", (cid,)).fetchone())
            c.close(); self._json(200, row); return

        if path == "/api/tasks":
            nxt = c.execute("SELECT COALESCE(MAX(sort_order),-1)+1 FROM tasks").fetchone()[0]
            ph = ",".join("?" * len(TCOLS))
            cur = c.execute(f"INSERT INTO tasks(sort_order,{','.join(TCOLS)}) VALUES(?,{ph})",
                            [nxt] + [b.get(k, 0 if k == "progress" else "") for k in TCOLS])
            c.commit()
            row = dict(c.execute("SELECT * FROM tasks WHERE id=?", (cur.lastrowid,)).fetchone())
            c.close(); self._json(200, row); return

        if path == "/api/plans":
            ph = ",".join("?" * len(LCOLS))
            cur = c.execute(f"INSERT INTO plans({','.join(LCOLS)}) VALUES({ph})",
                            [b.get(k) if k in ("project_id", "expect_days") else b.get(k, "") for k in LCOLS])
            c.commit()
            row = dict(c.execute("SELECT * FROM plans WHERE id=?", (cur.lastrowid,)).fetchone())
            c.close(); self._json(200, row); return

        if path == "/api/cards":
            vals = []
            for k in CCOLS:
                v = b.get(k)
                if k == "options":
                    v = json.dumps(v, ensure_ascii=False) if isinstance(v, list) else (v or "[]")
                elif v is None and k != "answer":
                    v = ""
                vals.append(v)
            ph = ",".join("?" * len(CCOLS))
            cur = c.execute(f"INSERT INTO cards({','.join(CCOLS)}) VALUES({ph})", vals)
            c.commit()
            row = dict(c.execute("SELECT * FROM cards WHERE id=?", (cur.lastrowid,)).fetchone())
            c.close(); self._json(200, row); return

        if path == "/api/reviews":
            nxt = c.execute("SELECT COALESCE(MAX(sort_order),-1)+1 FROM reviews").fetchone()[0]
            ph = ",".join("?" * len(RCOLS))
            cur = c.execute(f"INSERT INTO reviews(sort_order,{','.join(RCOLS)}) VALUES(?,{ph})",
                            [nxt] + [b.get(k, 0 if k == "checked" else "") for k in RCOLS])
            c.commit()
            row = dict(c.execute("SELECT * FROM reviews WHERE id=?", (cur.lastrowid,)).fetchone())
            c.close(); self._json(200, row); return

        if path == "/api/daystart":
            # 记录"今天第一次打开"的时刻;已有则不覆盖(只认当天第一次)
            c.execute("INSERT OR IGNORE INTO daystart(date, started_at) VALUES(date('now','localtime'), datetime('now','localtime'))")
            c.commit()
            row = dict(c.execute("SELECT * FROM daystart WHERE date=date('now','localtime')").fetchone())
            c.close(); self._json(200, row); return

        if path == "/api/battle/sessions":
            cur = c.execute("""INSERT INTO battle_sessions(mode,source,card_count)
                               VALUES(?,?,?)""",
                            (b.get("mode", "maic_review"), b.get("source", "cards"),
                             int(b.get("card_count") or 0)))
            c.commit()
            row = dict(c.execute("SELECT * FROM battle_sessions WHERE id=?", (cur.lastrowid,)).fetchone())
            c.close(); self._json(200, row); return

        if path == "/api/battle/answer":
            sid = int(b.get("session_id") or 0)
            rid = int(b.get("card_id") or 0)
            selected = int(b.get("selected_answer") if b.get("selected_answer") is not None else -1)
            if not sid:
                cur = c.execute("INSERT INTO battle_sessions(mode,source,card_count) VALUES(?,?,?)",
                                ("maic_review", "cards", 0))
                sid = cur.lastrowid
            card_row = c.execute("SELECT * FROM cards WHERE id=?", (rid,)).fetchone()
            if not card_row:
                c.close(); self._send(404, b'{"error":"card not found"}'); return
            card = dict(card_row)
            correct = selected == int(card.get("answer") or 0)
            review_state = apply_card_review(c, rid, correct)
            feedback = maic_feedback(card, selected, correct, review_state)
            c.execute("""INSERT INTO battle_events(session_id,card_id,role,event_type,payload)
                         VALUES(?,?,?,?,?)""",
                      (sid, rid, "player", "answer", json.dumps(feedback["meta"], ensure_ascii=False)))
            for agent in feedback["agents"]:
                c.execute("""INSERT INTO battle_events(session_id,card_id,role,event_type,payload)
                             VALUES(?,?,?,?,?)""",
                          (sid, rid, agent["role"], "agent_turn",
                           json.dumps(agent, ensure_ascii=False)))
            scores = feedback["scores"]
            c.execute("""INSERT INTO battle_scores(session_id,card_id,selected_answer,correct,
                         recall_score,apply_score,attack_score,explanation_score,judge_reason)
                         VALUES(?,?,?,?,?,?,?,?,?)""",
                      (sid, rid, selected, scores["correct"], scores["recall"], scores["apply"],
                       scores["attack"], scores["explain"], scores["judge_reason"]))
            if correct:
                c.execute("UPDATE battle_sessions SET correct_count=correct_count+1 WHERE id=?", (sid,))
            else:
                c.execute("UPDATE battle_sessions SET wrong_count=wrong_count+1 WHERE id=?", (sid,))
            c.commit(); c.close(); self._json(200, {"session_id": sid, "feedback": feedback}); return

        if path == "/api/battle/end":
            sid = int(b.get("session_id") or 0)
            if sid:
                row = c.execute("""SELECT COUNT(*) AS n, COALESCE(SUM(correct),0) AS c,
                                          AVG(recall_score) AS recall_avg,
                                          AVG(apply_score) AS apply_avg,
                                          AVG(attack_score) AS attack_avg,
                                          AVG(explanation_score) AS explain_avg
                                   FROM battle_scores WHERE session_id=?""", (sid,)).fetchone()
                summary = {
                    "answered": row["n"] if row else 0,
                    "correct": row["c"] if row else 0,
                    "recall_avg": round(row["recall_avg"] or 0, 2) if row else 0,
                    "apply_avg": round(row["apply_avg"] or 0, 2) if row else 0,
                    "attack_avg": round(row["attack_avg"] or 0, 2) if row else 0,
                    "explain_avg": round(row["explain_avg"] or 0, 2) if row else 0,
                }
                c.execute("""UPDATE battle_sessions
                             SET status='done', ended_at=datetime('now','localtime'),
                                 score_summary=?
                             WHERE id=?""", (json.dumps(summary, ensure_ascii=False), sid))
                c.commit()
                c.close(); self._json(200, {"ok": True, "summary": summary}); return
            c.close(); self._send(400, b'{"error":"missing session_id"}'); return

        if path == "/api/card-questions/close-stale":
            closed = close_stale_questions(c)
            c.commit(); c.close(); self._json(200, {"ok": True, "closed": closed}); return

        if path == "/api/card-questions":
            close_stale_questions(c)
            sid = int(b.get("session_id") or 0)
            card_id = int(b.get("card_id") or 0)
            qid = int(b.get("question_id") or 0)
            user_q = (b.get("question") or "").strip()
            if not card_id or not user_q:
                c.close(); self._send(400, b'{"error":"missing card_id or question"}'); return
            card_row = c.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
            if not card_row:
                c.close(); self._send(404, b'{"error":"card not found"}'); return
            qrow = None
            if qid:
                qrow = c.execute("SELECT * FROM card_questions WHERE id=? AND status='open'", (qid,)).fetchone()
            if not qrow:
                if sid:
                    qrow = c.execute("""SELECT * FROM card_questions
                                        WHERE status='open' AND card_id=? AND session_id=?
                                        ORDER BY id DESC LIMIT 1""", (card_id, sid)).fetchone()
                else:
                    qrow = c.execute("""SELECT * FROM card_questions
                                        WHERE status='open' AND card_id=? AND session_id IS NULL
                                        ORDER BY id DESC LIMIT 1""", (card_id,)).fetchone()
            if qrow:
                qid = qrow["id"]
                history = _json_loads(qrow["history"], [])
                first_question = qrow["question_text"] or user_q
                turn_count = int(qrow["turn_count"] or 0)
            else:
                cur = c.execute("""INSERT INTO card_questions(session_id,card_id,status,question_text,history,turn_count)
                                   VALUES(?,?,?,?,?,0)""",
                                (sid if sid else None, card_id, "open", user_q, "[]"))
                qid = cur.lastrowid
                history, first_question, turn_count = [], user_q, 0
            history.append({"role": "user", "content": user_q})
            answer, llm_status = call_card_question_llm(dict(card_row), user_q, history)
            history.append({"role": "assistant", "content": answer, "llm_status": llm_status})
            c.execute("""UPDATE card_questions
                         SET question_text=?, answer_text=?, history=?, llm_status=?,
                             turn_count=?, last_activity_at=datetime('now','localtime'),
                             status='open', closed_at=NULL
                         WHERE id=?""",
                      (first_question, answer, json.dumps(history, ensure_ascii=False),
                       llm_status, turn_count + 1, qid))
            if sid:
                c.execute("""INSERT INTO battle_events(session_id,card_id,role,event_type,payload)
                             VALUES(?,?,?,?,?)""",
                          (sid, card_id, "learner", "card_question",
                           json.dumps({"question_id": qid, "question": user_q}, ensure_ascii=False)))
                c.execute("""INSERT INTO battle_events(session_id,card_id,role,event_type,payload)
                             VALUES(?,?,?,?,?)""",
                          (sid, card_id, "question_coach", "card_question_answer",
                           json.dumps({"question_id": qid, "answer": answer, "llm_status": llm_status}, ensure_ascii=False)))
            c.commit()
            row = dict(c.execute("""SELECT q.*, cards.question AS card_question, cards.source AS card_source
                                    FROM card_questions q
                                    LEFT JOIN cards ON cards.id=q.card_id
                                    WHERE q.id=?""", (qid,)).fetchone())
            row["history"] = history
            c.close(); self._json(200, row); return

        if path == "/api/concept-notes":
            concept = (b.get("concept") or "").strip()
            if not concept:
                c.close(); self._send(400, b'{"error":"missing concept"}'); return
            initial_note = (b.get("initial_note") or "").strip()
            learning_goal = (b.get("learning_goal") or "").strip()
            prompt = (b.get("openmaic_prompt") or "").strip() or build_openmaic_prompt(concept, initial_note, learning_goal)
            vals = {
                "concept": concept,
                "status": b.get("status", "noted"),
                "source": b.get("source", "Codex概念笔记"),
                "initial_note": initial_note,
                "learning_goal": learning_goal,
                "openmaic_prompt": prompt,
                "key_points": b.get("key_points", ""),
                "examples": b.get("examples", ""),
                "misconceptions": b.get("misconceptions", ""),
                "applications": b.get("applications", ""),
                "openmaic_url": b.get("openmaic_url", OPENMAIC_URL),
            }
            ph = ",".join("?" * len(NCOLS))
            cur = c.execute(f"INSERT INTO concept_notes({','.join(NCOLS)}) VALUES({ph})",
                            [vals.get(k, "") for k in NCOLS])
            nid = cur.lastrowid
            c.execute("INSERT INTO concept_note_events(note_id,event_type,payload) VALUES(?,?,?)",
                      (nid, "note_created", json.dumps(vals, ensure_ascii=False)))
            c.commit()
            row = dict(c.execute("SELECT * FROM concept_notes WHERE id=?", (nid,)).fetchone())
            c.close(); self._json(200, row); return

        if path.startswith("/api/concept-notes/") and path.endswith("/graduate"):
            nid = int(path.rstrip("/").split("/")[-2])
            note = c.execute("SELECT * FROM concept_notes WHERE id=?", (nid,)).fetchone()
            if not note:
                c.close(); self._send(404, b'{"error":"concept note not found"}'); return
            note_d = dict(note)
            cards_to_create = concept_cards_from_note(note_d)
            if not cards_to_create:
                c.close(); self._send(400, b'{"error":"missing enrichment fields: key_points/examples/misconceptions/applications"}'); return
            created = []
            for card in cards_to_create:
                vals = []
                for k in CCOLS:
                    v = card.get(k)
                    if k == "options":
                        v = json.dumps(v, ensure_ascii=False) if isinstance(v, list) else (v or "[]")
                    elif v is None and k != "answer":
                        v = ""
                    vals.append(v)
                ph = ",".join("?" * len(CCOLS))
                cur = c.execute(f"INSERT INTO cards({','.join(CCOLS)}) VALUES({ph})", vals)
                created.append(cur.lastrowid)
            c.execute("""UPDATE concept_notes
                         SET status='graduated', graduated_at=datetime('now','localtime'),
                             updated_at=datetime('now','localtime')
                         WHERE id=?""", (nid,))
            c.execute("INSERT INTO concept_note_events(note_id,event_type,payload) VALUES(?,?,?)",
                      (nid, "graduated_to_battle",
                       json.dumps({"created_card_ids": created}, ensure_ascii=False)))
            c.commit()
            rows = [dict(r) for r in c.execute(
                "SELECT * FROM cards WHERE id IN (%s)" % ",".join("?" * len(created)), created)]
            c.close(); self._json(200, {"ok": True, "created_card_ids": created, "cards": rows}); return

        c.close(); self._send(404, b'{"error":"not found"}')

    # ---- PATCH ----
    def do_PATCH(self):
        path = urlparse(self.path).path; b = self._body()
        if path.startswith("/api/plans/"):
            rid = self._tail_id(path)
            fields = [k for k in LCOLS if k in b]
            sets = [f"{k}=?" for k in fields]; vals = [b[k] for k in fields]
            if b.get("status") == "已完成":
                sets.append("done_at=COALESCE(done_at, date('now','localtime'))")
            elif b.get("status") == "进行中":
                sets.append("done_at=NULL")
            if sets:
                c = conn(); c.execute(f"UPDATE plans SET {','.join(sets)} WHERE id=?", vals + [rid])
                c.commit(); c.close()
            self._json(200, {"ok": True}); return
        if path.startswith("/api/cards/"):
            rid = self._tail_id(path); c = conn()
            if "review" in b:  # 对战答题 → SM-2 调度
                apply_card_review(c, rid, b["review"] == "correct")
                c.commit(); c.close(); self._json(200, {"ok": True}); return
            flds = [k for k in CCOLS if k in b]
            if flds:
                vals = [json.dumps(b[k], ensure_ascii=False) if (k == "options" and isinstance(b[k], list)) else b[k] for k in flds]
                c.execute(f"UPDATE cards SET {','.join(f'{k}=?' for k in flds)} WHERE id=?", vals + [rid])
                c.commit()
            c.close(); self._json(200, {"ok": True}); return
        if path.startswith("/api/concept-notes/"):
            rid = self._tail_id(path); c = conn()
            fields = [k for k in NCOLS if k in b]
            if fields:
                sets = [f"{k}=?" for k in fields]
                vals = [b[k] for k in fields]
                if b.get("status") == "learned":
                    sets.append("learned_at=COALESCE(learned_at, datetime('now','localtime'))")
                sets.append("updated_at=datetime('now','localtime')")
                c.execute(f"UPDATE concept_notes SET {','.join(sets)} WHERE id=?", vals + [rid])
                c.execute("INSERT INTO concept_note_events(note_id,event_type,payload) VALUES(?,?,?)",
                          (rid, "note_updated", json.dumps({k: b[k] for k in fields}, ensure_ascii=False)))
                c.commit()
            row = c.execute("SELECT * FROM concept_notes WHERE id=?", (rid,)).fetchone()
            c.close(); self._json(200, dict(row) if row else {"ok": True}); return
        if path.startswith("/api/reviews/"):
            rid = self._tail_id(path); fields = [k for k in RCOLS if k in b]
            if fields:
                c = conn()
                c.execute(f"UPDATE reviews SET {','.join(f'{k}=?' for k in fields)} WHERE id=?",
                          [b[k] for k in fields] + [rid])
                c.commit(); c.close()
            self._json(200, {"ok": True}); return
        if path.startswith("/api/projects/"):
            rid = self._tail_id(path); fields = [k for k in PCOLS if k in b]
            if fields:
                c = conn()
                old = c.execute("SELECT just_done, doing_next FROM projects WHERE id=?", (rid,)).fetchone()
                old_jd = (old["just_done"] if old else "") or ""
                old_dn = (old["doing_next"] if old else "") or ""
                new_jd = b.get("just_done", old_jd) or ""
                # 改「刚刚完成的」且内容变了 → 自动落一条时间线提交(免去单独点「提交」)
                auto = ("just_done" in fields and new_jd.strip() and new_jd.strip() != old_jd.strip())
                sets = ",".join(f"{k}=?" for k in fields)
                extra = ", lastmove=strftime('%m-%d %H:%M','now','localtime')" if auto else ""
                c.execute(f"UPDATE projects SET {sets}{extra}, updated_at=datetime('now','localtime') WHERE id=?",
                          [b[k] for k in fields] + [rid])
                if auto:
                    new_dn = b.get("doing_next", old_dn) or ""
                    c.execute("INSERT INTO commits(project_id,just_done,doing_next,note) VALUES(?,?,?,?)",
                              (rid, new_jd, new_dn, "✍️ 改卡自动记录"))
                c.commit(); c.close()
            self._json(200, {"ok": True}); return
        if path.startswith("/api/tasks/"):
            rid = self._tail_id(path); fields = [k for k in TCOLS if k in b]
            if fields:
                c = conn()
                sets = ",".join(f"{k}=?" for k in fields)
                c.execute(f"UPDATE tasks SET {sets}, updated_at=datetime('now','localtime') WHERE id=?",
                          [b[k] for k in fields] + [rid])
                c.commit(); c.close()
            self._json(200, {"ok": True}); return
        self._send(404, b'{"error":"not found"}')

    # ---- DELETE ----
    def do_DELETE(self):
        path = urlparse(self.path).path
        c = conn()
        if path.startswith("/api/projects/"):
            rid = self._tail_id(path)
            c.execute("DELETE FROM artifacts WHERE project_id=?", (rid,))
            c.execute("DELETE FROM commits WHERE project_id=?", (rid,))
            c.execute("DELETE FROM tasks WHERE project_id=?", (rid,))
            c.execute("DELETE FROM projects WHERE id=?", (rid,))
        elif path.startswith("/api/tasks/"):
            c.execute("DELETE FROM tasks WHERE id=?", (self._tail_id(path),))
        elif path.startswith("/api/commits/"):
            c.execute("DELETE FROM commits WHERE id=?", (self._tail_id(path),))
        elif path.startswith("/api/artifacts/"):
            c.execute("DELETE FROM artifacts WHERE id=?", (self._tail_id(path),))
        elif path.startswith("/api/plans/"):
            c.execute("DELETE FROM plans WHERE id=?", (self._tail_id(path),))
        elif path.startswith("/api/cards/"):
            c.execute("DELETE FROM cards WHERE id=?", (self._tail_id(path),))
        elif path.startswith("/api/reviews/"):
            c.execute("DELETE FROM reviews WHERE id=?", (self._tail_id(path),))
        else:
            c.close(); self._send(404, b'{"error":"not found"}'); return
        c.commit(); c.close(); self._json(200, {"ok": True})

    def log_message(self, *a):
        pass


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]; s.close(); return ip
    except Exception:
        return "127.0.0.1"


if __name__ == "__main__":
    init_db()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)   # 0.0.0.0 = 局域网内手机/平板可访问
    print("✅ 项目台 running")
    print(f"   本机:        http://127.0.0.1:{PORT}")
    print(f"   手机同WiFi:  http://{lan_ip()}:{PORT}   (Ctrl+C 停)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n停。"); srv.shutdown()
