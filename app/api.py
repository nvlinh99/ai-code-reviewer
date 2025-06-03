from fastapi import Request, APIRouter, Header, Query, Form, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from transformers import AutoModelForCausalLM, AutoTokenizer
import requests
import psycopg2
import json
import httpx
from openai import OpenAI
import re
import pandas as pd
from typing import Optional

from config.config import settings

router = APIRouter()

GITLAB_API = settings.GITLAB_API
GITLAB_TOKEN = settings.GITLAB_TOKEN
OPENAI_API_KEY = settings.OPENAI_API_KEY
PROJECT_ID = settings.PROJECT_ID
POSTGRES_DSN = settings.POSTGRES_DSN
MODEL = settings.MODEL
GITLAB_WEBHOOK_SECRET = settings.GITLAB_WEBHOOK_SECRET

conn = psycopg2.connect(POSTGRES_DSN)

http_client = httpx.Client()
client = OpenAI(
    api_key=OPENAI_API_KEY,
    http_client=http_client
)

templates = Jinja2Templates(directory="templates")

class ReviewRequest(BaseModel):
    mr_iid: int

@router.post("/review", summary="Review a GitLab MR")
async def review_mr(payload: ReviewRequest):
    mr_iid = payload.mr_iid
    diff, sha_info = get_mr_diff(mr_iid)
    if not diff:
        return JSONResponse(status_code=400, content={"error": "Empty diff"})

    ai_response = call_gpt_for_review(diff)
    post_comments_to_mr(mr_iid, ai_response.get("comments", []), sha_info)
    log_review(mr_iid, ai_response)
    update_badge_status(mr_iid, ai_response.get("pass", False))

    return JSONResponse(content=ai_response)

def get_mr_diff(mr_iid):
    url = f"{GITLAB_API}/projects/{PROJECT_ID}/merge_requests/{mr_iid}/changes"
    headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        print("GitLab error:", resp.text)
        return None, None

    data = resp.json()
    combined_diff = ""
    for change in data["changes"]:
        combined_diff += f"\nFile: {change['new_path']}\n{change['diff']}\n"

    sha_info = data.get("diff_refs", {})
    return combined_diff, sha_info

def call_gpt_for_review(diff_text):
    prompt = f"""
You are an expert code reviewer tasked with reviewing a pull request.

You are given the following:
- PR description
- Code changes (in unified diff format or full source)
Your job is to simulate a professional code review and generate actionable feedback.

## Review Goals:
1. Identify any bugs, logic errors, or potential issues
2. Suggest improvements in readability, performance, or maintainability
3. Comment on code structure and organization
4. Check for proper error handling and edge cases
5. Assess whether the implementation meets the described requirements

## Rules:
- Only comment on lines that have meaningful issues or opportunities for improvement.
- Skip any trivial or stylistic changes that don't affect functionality or clarity.
- Group related issues by file and line.
- Avoid duplicate or vague comments.
- Suggest fix/improvement if appropriate.

## Fix
If any issue can be fixed automatically, include a "fix" block using patch-style format:

--- path/to/file.py
+++ path/to/file.py
@@ -5,7 +5,7 @@
- bad_code()
+ good_code()

## Response Format:
Your response MUST be a valid JSON with the following structure:
```json
{{
  "summary": "Short title of the overall changes",
  "pass": true/false,
  "comments": [
    {{
      "file": "filename",
      "line": line_number,
      "message": "explanation"
      "fix": "optional patch block if applicable"
    }}
  ]
}}

## Diff:
{diff_text[:6000]}  # truncate if too long
"""
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        raw = response.choices[0].message.content.strip()
        print("==== GPT RESPONSE ====")
        print(raw)

        match = re.search(r"```json\n(.*?)```", raw, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        else:
            return json.loads(raw)
    except json.JSONDecodeError as e:
        print("JSON parse error:", e)
        return {"summary": "Parse failed", "pass": False, "comments": []}
    except Exception as e:
        print("GPT call failed:", e)
        return {"summary": "Call failed", "pass": False, "comments": []}

def format_comment_with_fix(c: dict) -> str:
    body = c["message"]
    if "fix" in c and c["fix"]:
        body += f"\n\n```diff\n{c['fix']}\n```"
    return body

# def post_comments_to_mr(mr_iid, comments, sha_info):
#     url = f"{GITLAB_API}/projects/{PROJECT_ID}/merge_requests/{mr_iid}/discussions"
#     headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}

#     base_sha = sha_info.get("base_sha")
#     start_sha = sha_info.get("start_sha")
#     head_sha = sha_info.get("head_sha")

#     for c in comments:
#         payload = {
#             "body": c["message"],
#             "position": {
#                 "position_type": "text",
#                 "base_sha": base_sha,
#                 "start_sha": start_sha,
#                 "head_sha": head_sha,
#                 "new_path": c["file"],
#                 "new_line": c["line"]
#             }
#         }
#         resp = requests.post(url, json=payload, headers=headers)
#         if resp.status_code != 201:
#             print("Failed to post comment:", resp.text)

def post_comments_to_mr(mr_iid, comments, sha_info):
    url = f"{GITLAB_API}/projects/{PROJECT_ID}/merge_requests/{mr_iid}/discussions"
    headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}

    base_sha = sha_info.get("base_sha")
    start_sha = sha_info.get("start_sha")
    head_sha = sha_info.get("head_sha")

    for c in comments:
        comment_body = format_comment_with_fix(c)

        payload = {
            "body": comment_body,
            "position": {
                "position_type": "text",
                "base_sha": base_sha,
                "start_sha": start_sha,
                "head_sha": head_sha,
                "new_path": c["file"],
                "new_line": c["line"]
            }
        }

        resp = requests.post(url, json=payload, headers=headers)
        if resp.status_code != 201:
            print("Failed to post comment:", resp.text)
        else:
            print("Posted comment:", c["file"], "line", c["line"])

            
def log_review(mr_iid, result):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO ai_reviews (mr_iid, project_id, passed, comment_count) VALUES (%s, %s, %s, %s)",
        (mr_iid, PROJECT_ID, result.get("pass"), len(result.get("comments", [])))
    )
    conn.commit()

def update_badge_status(mr_iid, passed):
    label = "ai-reviewed:pass" if passed else "ai-reviewed:fail"
    url = f"{GITLAB_API}/projects/{PROJECT_ID}/merge_requests/{mr_iid}/labels"
    headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}
    requests.put(url, headers=headers, json={"labels": label})

@router.post("/webhook", summary="GitLab MR Webhook")
async def gitlab_webhook(request: Request, x_gitlab_token: str = Header(None)):
    if x_gitlab_token != GITLAB_WEBHOOK_SECRET:
        return JSONResponse(status_code=403, content={"error": "Invalid token"})

    payload = await request.json()
    object_kind = payload.get("object_kind")
    if object_kind != "merge_request":
        return {"status": "ignored"}

    mr = payload.get("object_attributes", {})
    if mr.get("action") != "open":
        return {"status": "ignored"}

    mr_iid = mr.get("iid")
    if not mr_iid:
        return {"status": "ignored"}

    diff, sha_info = get_mr_diff(mr_iid)
    if not diff:
        return {"status": "no diff"}

    ai_response = call_gpt_for_review(diff)
    post_comments_to_mr(mr_iid, ai_response.get("comments", []), sha_info)
    log_review(mr_iid, ai_response)
    update_badge_status(mr_iid, ai_response.get("pass", False))

    return {"status": "reviewed"}

@router.get("/dashboard/{mr_iid}")
async def view_review_detail(request: Request, mr_iid: int):
    cur = conn.cursor()
    cur.execute("SELECT * FROM ai_reviews WHERE mr_iid = %s", (mr_iid,))
    row = cur.fetchone()
    if not row:
        return templates.TemplateResponse("not_found.html", {"request": request, "mr_iid": mr_iid})

    review = {
        "id": row[0], "project_id": row[1], "mr_iid": row[2],
        "passed": row[3], "comment_count": row[4], "feedback_rating": row[5], "created_at": row[6]
    }
    return templates.TemplateResponse("review_detail.html", {"request": request, "review": review})

@router.get("/dashboard/export/excel")
async def export_dashboard_excel():
    cur = conn.cursor()
    cur.execute("SELECT mr_iid, project_id, passed, comment_count FROM ai_reviews ORDER BY id DESC")
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["MR IID", "Project ID", "Passed", "Comments"])
    path = "export_reviews.xlsx"
    df.to_excel(path, index=False)
    return FileResponse(path, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', filename=path)

# Optional: export PDF
# Install: `pip install pdfkit` and `brew install wkhtmltopdf`
# import pdfkit
# @router.get("/dashboard/export/pdf")
# async def export_dashboard_pdf():
#     cur = conn.cursor()
#     cur.execute("SELECT mr_iid, project_id, passed, comment_count FROM ai_reviews ORDER BY id DESC")
#     rows = cur.fetchall()
#     html = "<h1>AI Review Report</h1><table border='1'><tr><th>MR IID</th><th>Project ID</th><th>Status</th><th>Comments</th></tr>"
#     for r in rows:
#         status = "PASS" if r[2] else "FAIL"
#         html += f"<tr><td>{r[0]}</td><td>{r[1]}</td><td>{status}</td><td>{r[3]}</td></tr>"
#     html += "</table>"

#     path_wkhtmltopdf = "/usr/local/bin/wkhtmltopdf"
#     config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)
#     pdfkit.from_string(html, "export_reviews.pdf", configuration=config)

#     return FileResponse("export_reviews.pdf", media_type="application/pdf", filename="reviews.pdf")

@router.get("/badge/{mr_iid}.svg")
async def badge_status(mr_iid: int):
    cur = conn.cursor()
    cur.execute("SELECT passed FROM ai_reviews WHERE mr_iid = %s ORDER BY id DESC LIMIT 1", (mr_iid,))
    row = cur.fetchone()
    status = "pass" if row and row[0] else "fail"
    color = "brightgreen" if status == "pass" else "red"
    return FileResponse(f"static/badges/{status}-{color}.svg", media_type="image/svg+xml")


@router.post("/dashboard/{mr_iid}/feedback")
async def update_feedback_rating(mr_iid: int, rating: int = Form(...)):
    if not (1 <= rating <= 5):
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")

    cur = conn.cursor()
    cur.execute("UPDATE ai_reviews SET feedback_rating = %s WHERE mr_iid = %s", (rating, mr_iid))
    conn.commit()
    return {"message": f"Rating {rating} updated for MR {mr_iid}"}


@router.get("/dashboard")
async def view_dashboard(request: Request, page: int = 1, passed: bool | None = Query(None)):
    limit = 10
    offset = (page - 1) * limit
    cur = conn.cursor()

    # Query review data with filtering + pagination
    query = "SELECT mr_iid, project_id, passed, comment_count FROM ai_reviews"
    where_clause = []
    if passed is not None:
        where_clause.append(f"passed = {passed}")
    if where_clause:
        query += " WHERE " + " AND ".join(where_clause)

    query += f" ORDER BY id DESC LIMIT {limit} OFFSET {offset}"
    cur.execute(query)
    rows = cur.fetchall()
    reviews = [
        {"mr_iid": r[0], "project_id": r[1], "passed": r[2], "comment_count": r[3]}
        for r in rows
    ]

    # Pie/Bar chart: stats from SAME filtered + paged data
    # Run separate query for that subset
    stats_query = "SELECT passed, COUNT(*) as num_reviews, SUM(comment_count) as total_comments FROM ai_reviews"
    if where_clause:
        stats_query += " WHERE " + " AND ".join(where_clause)
    stats_query += " GROUP BY passed"

    cur.execute(stats_query)
    chart_data = cur.fetchall()

    # Convert to pie+bar stats
    stats = {
        "pass_count": 0,
        "fail_count": 0,
        "pass_comments": 0,
        "fail_comments": 0
    }
    for passed_val, review_count, total_comments in chart_data:
        if passed_val:
            stats["pass_count"] = review_count
            stats["pass_comments"] = total_comments or 0
        else:
            stats["fail_count"] = review_count
            stats["fail_comments"] = total_comments or 0

    stats["total"] = stats["pass_count"] + stats["fail_count"]

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "reviews": reviews,
        "page": page,
        "passed": passed,
        "stats": stats
    })
