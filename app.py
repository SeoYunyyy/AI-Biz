# ── Keepit 서버 진입점 ──

import sys
import io
import os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from flask import Flask, render_template, jsonify, session
from routes.auth import auth_bp, login_required

from routes.archive import archive_bp
from routes.search import search_bp
from routes.reminder import reminder_bp
from routes.report import report_bp
from hyoju_connection import hyoju_bp
from routes.group import group_bp
from routes.chat import chat_bp

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'keep-it-secret-key-2024')

# 개발용 로그인 스킵 — .env의 DEV_SKIP_LOGIN=true 일 때만 동작
@app.before_request
def dev_auto_login():
    if os.getenv('DEV_SKIP_LOGIN') != 'true':
        return
    dev_id = os.getenv('SUPABASE_USER_ID', '00000000-0000-0000-0000-000000000001')
    # 세션이 없거나 user_id가 UUID 형식이 아니면 강제 갱신
    current_id = (session.get('user') or {}).get('id', '')
    import re
    is_uuid = bool(re.match(r'^[0-9a-f-]{36}$', current_id, re.I))
    if not is_uuid:
        session['user'] = {
            'id':     dev_id,
            'email':  'dev@test.com',
            'name':   '개발자',
            'avatar': '',
        }

# Blueprint 등록 (기능별 라우트 연결)
app.register_blueprint(auth_bp)
app.register_blueprint(archive_bp)
app.register_blueprint(report_bp)
app.register_blueprint(search_bp)
app.register_blueprint(reminder_bp)
app.register_blueprint(hyoju_bp)
app.register_blueprint(group_bp)
app.register_blueprint(chat_bp)


@app.route('/')
@login_required
def index():
    return render_template(
        'index.html',
        user=session.get('user'),
        supabase_url=os.getenv('SUPABASE_URL', ''),
        supabase_anon_key=os.getenv('SUPABASE_ANON_KEY', ''),
        dev_skip_login=(os.getenv('DEV_SKIP_LOGIN') == 'true'),
    )


@app.route('/weekly-report')
def weekly_report_page():
    return render_template('report_weekly.html')


@app.errorhandler(Exception)
def handle_exception(e):
    return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)

# Flask 앱 초기화 및 기능별 Blueprint 등록, 서버 실행